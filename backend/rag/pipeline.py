"""
RAG pipeline — orchestrates ingest and retrieval.

Ingest:   chunks → dense embed + sparse encode → upsert into Qdrant
Retrieve: question → dense embed + sparse encode → hybrid search (RRF) → rerank → top-k chunks

Dense (BGE): asymmetric — embed_documents() for chunks, embed_query() for questions.
Sparse (BM25-style): same sparse_encode() for both — Qdrant applies IDF at search time.
RRF (Reciprocal Rank Fusion): merges dense + sparse ranked lists.
Reranker (BGE cross-encoder): rescores RRF candidates by true relevance — similarity ≠ relevance.
"""

import asyncio
import hashlib
import json
import logging
import re
import threading

from config import get_settings
from ingestion.chunker import SECTION_NAMES
from rag.embedder import embed_documents, embed_query, sparse_encode
from rag.retriever import ensure_collection, get_section_chunks, search, search_multi, upsert_chunks
from rag.reranker import rerank
from services.llm import CHEAP_MODEL, call_llm_raw

# Maps regex patterns (matched against the question) to 10-K Item numbers.
# Queries matching a pattern are restricted to those sections in Qdrant,
# eliminating irrelevant chunks from financial tables, boilerplate, etc.
_SECTION_ROUTING: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"risk|threat|challenge|vulnerabilit|expos|uncertaint|hazard", re.I), ["1A"]),
    (re.compile(r"cybersecurit|data breach|hack|attack|infosec", re.I),               ["1A", "1C"]),
    (re.compile(r"competi|market.?share|rival|industry.?position|strategic", re.I),   ["1", "1A"]),
    (re.compile(r"revenue|sales|income|profit|margin|earnings|cost|expense|financial.?result|growth|segment", re.I), ["7", "7A"]),
    (re.compile(r"outlook|guidance|forward.?look|strategy|management.?discuss|md&a", re.I), ["7"]),
    (re.compile(r"sentiment|tone|language|wording", re.I),                            ["7"]),
    (re.compile(r"governance|director|board|compensation|executive|officer", re.I),   ["10", "11"]),
    (re.compile(r"lawsuit|litigation|legal|court|regulatory.?action|enforcement", re.I), ["3", "1A"]),
    (re.compile(r"audit|internal.?control|accounting|disclosure.?control", re.I),     ["9A"]),
    (re.compile(r"business|operation|product|service|segment|employee|workforce|personnel", re.I), ["1"]),
]


def _detect_section(question: str) -> list[str] | None:
    """Return Item numbers to restrict search to, or None to search all sections."""
    for pattern, items in _SECTION_ROUTING:
        if pattern.search(question):
            return items
    return None

try:
    from langfuse import observe, get_client as _lf
except ImportError:
    def observe(*args, **kwargs):       # type: ignore
        def decorator(fn): return fn
        return decorator if args and callable(args[0]) else decorator
    class _LfStub:                      # type: ignore
        def update_current_span(self, **_): pass
    _stub = _LfStub()
    def _lf(): return _stub             # type: ignore

logger = logging.getLogger(__name__)

_RERANK_POOL = 4   # fetch top_k * 4 from Qdrant, rerank down to top_k
_SECTION_RETRIEVAL_LIMIT = 40


def _retrieval_mode() -> str:
    mode = get_settings().RETRIEVAL_MODE.lower().strip()
    return mode if mode in {"hybrid", "fusion"} else "hybrid"


def _section_cache_key(question: str, filing_scope: str) -> str:
    digest = hashlib.sha256(f"{filing_scope}:{question}".encode()).hexdigest()
    return f"llm_cache:sections:{digest}"


def _run_async_sync(coro):
    """Run an async LLM call from sync retrieval code, including inside FastAPI."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result = {}
    error = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - defensive bridge
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error["value"]
    return result.get("value")


async def _reason_sections_async(question: str, filing_scope: str) -> list[str] | None:
    """Use a cheap LLM to pick SEC Items for PageIndex-style section retrieval."""
    settings = get_settings()
    cache_key = _section_cache_key(question, filing_scope)

    try:
        from cache.redis_client import get_redis
        redis = get_redis()
        cached = redis.get(cache_key)
        if cached:
            items = json.loads(cached)
            if isinstance(items, list):
                return [str(i).upper() for i in items if str(i).upper() in SECTION_NAMES]
    except Exception:
        redis = None

    section_list = "\n".join(f"- Item {item}: {name}" for item, name in SECTION_NAMES.items())
    prompt = f"""You route SEC 10-K questions to relevant filing sections.

Return ONLY a JSON array of item numbers. Pick at most 3 items.
Use the available section tree:
{section_list}

Question: {question}

Examples:
"What are the biggest risks?" -> ["1A"]
"How did revenue and margins change?" -> ["7"]
"Any cybersecurity issues?" -> ["1C", "1A"]
"""

    text, _, _, model = await call_llm_raw(prompt, max_tokens=80, model=CHEAP_MODEL)
    try:
        raw_items = json.loads(text.strip())
    except json.JSONDecodeError:
        match = re.search(r"\[[^\]]*\]", text)
        raw_items = json.loads(match.group(0)) if match else []

    items = []
    for item in raw_items:
        normalized = str(item).upper().replace("ITEM", "").strip(" .:-")
        if normalized in SECTION_NAMES and normalized not in items:
            items.append(normalized)

    if not items:
        items = _detect_section(question) or []

    try:
        if redis:
            redis.setex(cache_key, settings.SECTION_REASONER_CACHE_TTL_SECONDS, json.dumps(items))
    except Exception:
        pass

    logger.info("Section reasoner: %s -> %s via %s", question[:80], items, model)
    return items or None


def reason_sections(question: str, filing_scope: str) -> list[str] | None:
    """Sync wrapper with deterministic regex fallback."""
    try:
        return _run_async_sync(_reason_sections_async(question, filing_scope))
    except Exception as exc:
        fallback = _detect_section(question)
        logger.warning("Section reasoner failed (%s) — falling back to regex sections %s", exc, fallback)
        return fallback


def _vector_retrieve(
    question: str,
    filing_id: str,
    top_k: int,
    item_filter: list[str] | None,
) -> tuple[list[dict], list[dict]]:
    query_vector = embed_query(question)
    query_sparse = sparse_encode(question)
    candidates = search(
        query_vector, query_sparse, filing_id,
        top_k=top_k * _RERANK_POOL,
        item_filter=item_filter,
    )
    chunks = rerank(question, candidates, top_k=top_k)
    return candidates, chunks


def _vector_retrieve_multi(
    question: str,
    filing_ids: list[str],
    top_k: int,
    item_filter: list[str] | None,
) -> tuple[list[dict], list[dict]]:
    query_vector = embed_query(question)
    query_sparse = sparse_encode(question)
    candidates = search_multi(
        query_vector, query_sparse, filing_ids,
        top_k=top_k * _RERANK_POOL,
        item_filter=item_filter,
    )
    chunks = rerank(question, candidates, top_k=top_k)
    return candidates, chunks


def _section_retrieve(question: str, filing_id: str, items: list[str] | None, top_k: int) -> list[dict]:
    if not items:
        return []
    candidates = []
    for item in items:
        for chunk in get_section_chunks(filing_id, item, limit=_SECTION_RETRIEVAL_LIMIT):
            chunk = dict(chunk)
            chunk.setdefault("filing_id", filing_id)
            chunk.setdefault("score", 0.0)
            chunk["retrieval_path"] = "section"
            candidates.append(chunk)
    return rerank(question, candidates, top_k=top_k)


def _section_retrieve_multi(question: str, filing_ids: list[str], items: list[str] | None, top_k: int) -> list[dict]:
    chunks = []
    for filing_id in filing_ids:
        chunks.extend(_section_retrieve(question, filing_id, items, top_k=top_k))
    return rerank(question, chunks, top_k=top_k)


def _dedupe_chunks(chunks: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for chunk in chunks:
        key = (chunk.get("filing_id", ""), chunk.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


@observe()
def ingest(filing_id: str, chunks: list[dict]) -> int:
    """Embed all chunks (dense + sparse) and store in Qdrant. Returns chunk count."""
    ensure_collection()
    texts = [c["text"] for c in chunks]
    embeddings = embed_documents(texts)
    sparse_vectors = [sparse_encode(t) for t in texts]
    upsert_chunks(filing_id, chunks, embeddings, sparse_vectors)

    _lf().update_current_span(
        name="rag-ingest",
        input={"filing_id": filing_id, "chunk_count": len(chunks)},
        output={"chunks_stored": len(chunks)},
        metadata={"filing_id": filing_id},
    )

    logger.info("RAG ingest complete: %d chunks for %s", len(chunks), filing_id)
    return len(chunks)


@observe()
def retrieve(question: str, filing_id: str, top_k: int = 5) -> list[dict]:
    """Retrieve chunks using hybrid or fusion RAG, then rerank to top_k."""
    section_items = _detect_section(question)
    mode = _retrieval_mode()

    if mode == "fusion":
        reasoned_items = reason_sections(question, filing_id)
        vector_candidates, vector_chunks = _vector_retrieve(question, filing_id, top_k, item_filter=None)
        section_chunks = _section_retrieve(question, filing_id, reasoned_items, top_k)
        candidates = _dedupe_chunks(vector_chunks + section_chunks)
        chunks = rerank(question, candidates, top_k=top_k)
        effective_top_k = top_k
    else:
        # Tighten to top-3 when section-filtered: fewer but more precise chunks
        effective_top_k = 3 if section_items else top_k
        vector_candidates, chunks = _vector_retrieve(question, filing_id, effective_top_k, item_filter=section_items)
        candidates = vector_candidates
        reasoned_items = None
        section_chunks = []


    _lf().update_current_span(
        name="rag-retrieve",
        input=question,
        output=str([c["text"][:100] for c in chunks]),
        metadata={
            "filing_id": filing_id,
            "retrieval_mode": mode,
            "section_filter": section_items,
            "reasoned_sections": reasoned_items,
            "vector_candidates": len(vector_candidates),
            "section_candidates": len(section_chunks),
            "candidates": len(candidates),
            "returned": len(chunks),
        },
    )

    logger.info(
        "RAG retrieve[%s]: %d candidates → %d reranked for filing %s | regex=%s reasoned=%s (top score: %s)",
        mode, len(candidates), len(chunks), filing_id, section_items, reasoned_items,
        chunks[0].get("rerank_score", chunks[0]["score"]) if chunks else "n/a",
    )
    return chunks


@observe()
def retrieve_multi(question: str, filing_ids: list[str], top_k: int = 5) -> list[dict]:
    """Retrieve chunks across multiple filings using hybrid or fusion RAG."""
    if not filing_ids:
        return []

    section_items = _detect_section(question)
    mode = _retrieval_mode()

    if mode == "fusion":
        filing_scope = ",".join(sorted(filing_ids))
        reasoned_items = reason_sections(question, filing_scope)
        vector_candidates, vector_chunks = _vector_retrieve_multi(question, filing_ids, top_k, item_filter=None)
        section_chunks = _section_retrieve_multi(question, filing_ids, reasoned_items, top_k)
        candidates = _dedupe_chunks(vector_chunks + section_chunks)
        chunks = rerank(question, candidates, top_k=top_k)
        effective_top_k = top_k
    else:
        effective_top_k = 3 if section_items else top_k
        vector_candidates, chunks = _vector_retrieve_multi(question, filing_ids, effective_top_k, item_filter=section_items)
        candidates = vector_candidates
        reasoned_items = None
        section_chunks = []


    _lf().update_current_span(
        name="rag-retrieve-multi",
        input=question,
        output=str([c["text"][:100] for c in chunks]),
        metadata={
            "filing_ids": filing_ids,
            "retrieval_mode": mode,
            "section_filter": section_items,
            "reasoned_sections": reasoned_items,
            "vector_candidates": len(vector_candidates),
            "section_candidates": len(section_chunks),
            "candidates": len(candidates),
            "returned": len(chunks),
        },
    )

    logger.info(
        "RAG retrieve_multi[%s]: %d candidates → %d reranked across %d filings | regex=%s reasoned=%s (top score: %s)",
        mode, len(candidates), len(chunks), len(filing_ids), section_items, reasoned_items,
        chunks[0].get("rerank_score", chunks[0]["score"]) if chunks else "n/a",
    )
    return chunks

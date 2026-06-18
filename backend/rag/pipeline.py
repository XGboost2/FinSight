"""
RAG pipeline — orchestrates ingest and retrieval.

Ingest:   chunks → dense embed + sparse encode → upsert into Qdrant
Retrieve: question → dense embed + sparse encode → hybrid search (RRF) → rerank → top-k chunks

Dense (BGE): asymmetric — embed_documents() for chunks, embed_query() for questions.
Sparse (BM25-style): same sparse_encode() for both — Qdrant applies IDF at search time.
RRF (Reciprocal Rank Fusion): merges dense + sparse ranked lists.
Reranker (BGE cross-encoder): rescores RRF candidates by true relevance — similarity ≠ relevance.
"""

import logging
import re

from rag.embedder import embed_documents, embed_query, sparse_encode
from rag.retriever import ensure_collection, search, search_multi, upsert_chunks
from rag.reranker import rerank

# Maps regex patterns (matched against the question) to 10-K Item numbers.
# Queries matching a pattern are restricted to those sections in Qdrant,
# eliminating irrelevant chunks from financial tables, boilerplate, etc.
_SECTION_ROUTING: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"risk|threat|challenge|vulnerabilit|expos|uncertaint|hazard", re.I), ["1A"]),
    (re.compile(r"cybersecurit|data breach|hack|attack|infosec", re.I),               ["1A", "1C"]),
    (re.compile(r"competi|market.?share|rival|industry.?position|strategic", re.I),   ["1", "1A"]),
    (re.compile(r"revenue|sales|income|profit|margin|earnings|cost|expense|financial.?result|growth|segment", re.I), ["7", "8"]),
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
    """Retrieve SEC filing chunks using Qdrant hybrid RAG, then rerank to top_k."""
    section_items = _detect_section(question)
    effective_top_k = 3 if section_items else top_k
    vector_candidates, chunks = _vector_retrieve(question, filing_id, effective_top_k, item_filter=section_items)


    _lf().update_current_span(
        name="rag-retrieve",
        input=question,
        output=str([c["text"][:100] for c in chunks]),
        metadata={
            "filing_id": filing_id,
            "retrieval_mode": "hybrid",
            "section_filter": section_items,
            "vector_candidates": len(vector_candidates),
            "candidates": len(vector_candidates),
            "returned": len(chunks),
        },
    )

    logger.info(
        "RAG retrieve[hybrid]: %d candidates → %d reranked for filing %s | regex=%s (top score: %s)",
        len(vector_candidates), len(chunks), filing_id, section_items,
        chunks[0].get("rerank_score", chunks[0]["score"]) if chunks else "n/a",
    )
    return chunks


@observe()
def retrieve_multi(question: str, filing_ids: list[str], top_k: int = 5) -> list[dict]:
    """Retrieve chunks across multiple SEC filings using Qdrant hybrid RAG."""
    if not filing_ids:
        return []

    section_items = _detect_section(question)
    effective_top_k = 3 if section_items else top_k
    vector_candidates, chunks = _vector_retrieve_multi(question, filing_ids, effective_top_k, item_filter=section_items)


    _lf().update_current_span(
        name="rag-retrieve-multi",
        input=question,
        output=str([c["text"][:100] for c in chunks]),
        metadata={
            "filing_ids": filing_ids,
            "retrieval_mode": "hybrid",
            "section_filter": section_items,
            "vector_candidates": len(vector_candidates),
            "candidates": len(vector_candidates),
            "returned": len(chunks),
        },
    )

    logger.info(
        "RAG retrieve_multi[hybrid]: %d candidates → %d reranked across %d filings | regex=%s (top score: %s)",
        len(vector_candidates), len(chunks), len(filing_ids), section_items,
        chunks[0].get("rerank_score", chunks[0]["score"]) if chunks else "n/a",
    )
    return chunks

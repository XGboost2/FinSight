"""Neo4j-backed vectorless graph store for uploaded documents.

Uploaded files are converted with MarkItDown, chunked, then stored in Neo4j:

    (:Document)-[:HAS_SECTION]->(:Section)-[:HAS_CHUNK]->(:Chunk)

Retrieval is vectorless: it reads the graph, boosts structurally relevant SEC
sections, and ranks chunks lexically. Official EDGAR filings can still use the
Qdrant vector/fusion path; uploaded documents use this graph path.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9$%.-]{1,}")
_SECTION_ROUTE: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"risk|threat|challenge|uncertain|hazard|red flag", re.I), ["1A"]),
    (re.compile(r"cyber|breach|hack|security", re.I), ["1C", "1A"]),
    (re.compile(r"revenue|sales|income|profit|margin|earnings|cost|expense|growth", re.I), ["7", "8"]),
    (re.compile(r"outlook|guidance|strategy|management|md&a|future", re.I), ["7"]),
    (re.compile(r"business|operation|product|service|segment|customer", re.I), ["1"]),
    (re.compile(r"legal|lawsuit|litigation|regulatory|court", re.I), ["3", "1A"]),
    (re.compile(r"governance|director|board|compensation|executive", re.I), ["10", "11"]),
]


@lru_cache(maxsize=1)
def _driver():
    from neo4j import GraphDatabase

    settings = get_settings()
    return GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )


def _database() -> str | None:
    database = get_settings().NEO4J_DATABASE.strip()
    return database or None


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _route_items(question: str) -> set[str]:
    items: set[str] = set()
    for pattern, route_items in _SECTION_ROUTE:
        if pattern.search(question):
            items.update(route_items)
    return items


def _ensure_schema(tx) -> None:
    tx.run("CREATE CONSTRAINT finsight_document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.filing_id IS UNIQUE")
    tx.run("CREATE INDEX finsight_section_id IF NOT EXISTS FOR (s:Section) ON (s.filing_id, s.section_id)")
    tx.run("CREATE INDEX finsight_chunk_id IF NOT EXISTS FOR (c:Chunk) ON (c.filing_id, c.chunk_index)")


def _clear_document(tx, filing_id: str) -> None:
    tx.run(
        """
        MATCH (d:Document {filing_id: $filing_id})
        OPTIONAL MATCH (d)-[:HAS_SECTION]->(s:Section)
        OPTIONAL MATCH (s)-[:HAS_CHUNK]->(c:Chunk)
        WITH collect(DISTINCT d) + collect(DISTINCT s) + collect(DISTINCT c) AS nodes
        UNWIND nodes AS n
        WITH n WHERE n IS NOT NULL
        DETACH DELETE n
        """,
        filing_id=filing_id,
    )


def _create_document_graph(tx, filing_id: str, metadata: dict, chunks: list[dict]) -> None:
    tx.run(
        """
        CREATE (d:Document)
        SET d = $properties
        """,
        properties={
            **metadata,
            "filing_id": filing_id,
            "graph_backend": "neo4j",
            "retrieval": "vectorless_graph",
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    sections: dict[str, dict] = {}
    for chunk in chunks:
        item = chunk.get("item") or "DOCUMENT"
        section_name = chunk.get("section") or "Document"
        section_id = f"section:{item}"
        sections.setdefault(section_id, {
            "section_id": section_id,
            "filing_id": filing_id,
            "item": item,
            "section": section_name,
        })

    for section in sections.values():
        tx.run(
            """
            MATCH (d:Document {filing_id: $filing_id})
            CREATE (s:Section)
            SET s = $section
            CREATE (d)-[:HAS_SECTION]->(s)
            """,
            filing_id=filing_id,
            section=section,
        )

    for chunk in chunks:
        item = chunk.get("item") or "DOCUMENT"
        section_id = f"section:{item}"
        tx.run(
            """
            MATCH (s:Section {filing_id: $filing_id, section_id: $section_id})
            CREATE (c:Chunk)
            SET c = $chunk
            CREATE (s)-[:HAS_CHUNK]->(c)
            """,
            filing_id=filing_id,
            section_id=section_id,
            chunk={
                "filing_id": filing_id,
                "chunk_index": int(chunk["chunk_index"]),
                "text": chunk.get("text", ""),
                "item": item,
                "section": chunk.get("section") or "Document",
                "char_start": int(chunk.get("char_start", 0)),
                "char_end": int(chunk.get("char_end", 0)),
            },
        )


def _read_chunks(tx, filing_id: str) -> list[dict]:
    result = tx.run(
        """
        MATCH (:Document {filing_id: $filing_id})-[:HAS_SECTION]->(:Section)-[:HAS_CHUNK]->(c:Chunk)
        RETURN c.filing_id AS filing_id,
               c.chunk_index AS chunk_index,
               c.text AS text,
               c.item AS item,
               c.section AS section,
               c.char_start AS char_start,
               c.char_end AS char_end
        ORDER BY c.chunk_index ASC
        """,
        filing_id=filing_id,
    )
    return [dict(record) for record in result]


def _document_exists(tx, filing_id: str) -> bool:
    record = tx.run(
        "MATCH (d:Document {filing_id: $filing_id}) RETURN count(d) > 0 AS exists",
        filing_id=filing_id,
    ).single()
    return bool(record and record["exists"])


def graph_exists(_redis_unused: Any, filing_id: str) -> bool:
    """Return True if a Neo4j document graph exists for this filing_id."""
    try:
        with _driver().session(database=_database()) as session:
            return session.execute_read(_document_exists, filing_id)
    except Exception as exc:
        logger.warning("Neo4j graph_exists failed for %s: %s", filing_id, exc)
        return False


def ingest_graph_document(_redis_unused: Any, filing_id: str, metadata: dict, chunks: list[dict]) -> None:
    """Store a document graph in Neo4j without embeddings."""
    with _driver().session(database=_database()) as session:
        session.execute_write(_ensure_schema)
        session.execute_write(_clear_document, filing_id)
        session.execute_write(_create_document_graph, filing_id, metadata, chunks)

    logger.info("Neo4j graph ingest complete: filing_id=%s chunks=%d", filing_id, len(chunks))


def _score_chunks(chunks: list[dict], question: str, top_k: int) -> list[dict]:
    query_terms = _tokens(question)
    if not query_terms:
        return chunks[:top_k]

    query_counts = Counter(query_terms)
    routed_items = _route_items(question)
    doc_count = len(chunks)
    doc_freq: defaultdict[str, int] = defaultdict(int)
    chunk_tokens: list[tuple[dict, Counter[str]]] = []

    for chunk in chunks:
        text = f"{chunk.get('item', '')} {chunk.get('section', '')} {chunk.get('text', '')}"
        counts = Counter(_tokens(text))
        chunk_tokens.append((chunk, counts))
        for term in set(counts):
            doc_freq[term] += 1

    scored: list[tuple[float, dict]] = []
    for chunk, counts in chunk_tokens:
        score = 0.0
        for term, qtf in query_counts.items():
            tf = counts.get(term, 0)
            if tf:
                idf = math.log((doc_count + 1) / (doc_freq[term] + 0.5)) + 1
                score += (1 + math.log(tf)) * idf * qtf

        if routed_items and chunk.get("item") in routed_items:
            score += 4.0
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: (pair[0], -int(pair[1].get("chunk_index", 0))), reverse=True)
    return [
        {
            **chunk,
            "score": round(score, 4),
            "retrieval_path": "neo4j_vectorless_graph",
        }
        for score, chunk in scored[:top_k]
    ]


def retrieve_graph(_redis_unused: Any, filing_id: str, question: str, top_k: int = 5) -> list[dict]:
    """Vectorless retrieval over the Neo4j document graph."""
    try:
        with _driver().session(database=_database()) as session:
            chunks = session.execute_read(_read_chunks, filing_id)
    except Exception as exc:
        logger.warning("Neo4j retrieve_graph failed for %s: %s", filing_id, exc)
        return []

    return _score_chunks(chunks, question, top_k)

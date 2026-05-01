"""
RAG pipeline — orchestrates ingest and retrieval.

Ingest flow:  chunks → embed (batch) → upsert into Qdrant
Query flow:   question → embed (single) → search Qdrant → return top-k chunks

Keeping ingest and query here means routes.py stays thin.
"""

import logging

from rag.embedder import embed
from rag.retriever import ensure_collection, search, upsert_chunks

logger = logging.getLogger(__name__)


def ingest(filing_id: str, chunks: list[dict]) -> int:
    """Embed all chunks and store in Qdrant. Returns chunk count."""
    ensure_collection()
    texts = [c["text"] for c in chunks]
    embeddings = embed(texts)
    upsert_chunks(filing_id, chunks, embeddings)
    logger.info("RAG ingest complete: %d chunks for %s", len(chunks), filing_id)
    return len(chunks)


def retrieve(question: str, filing_id: str, top_k: int = 5) -> list[dict]:
    """Embed question and return top-k relevant chunks from Qdrant."""
    query_vector = embed([question])[0]
    chunks = search(query_vector, filing_id, top_k=top_k)
    logger.info(
        "RAG retrieve: %d chunks for filing %s (top score: %s)",
        len(chunks),
        filing_id,
        chunks[0]["score"] if chunks else "n/a",
    )
    return chunks

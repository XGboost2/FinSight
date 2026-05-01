"""
RAG pipeline — orchestrates ingest and retrieval.

Ingest:   chunks → embed_documents (no prefix) → upsert into Qdrant
Retrieve: question → embed_query (with BGE prefix) → search Qdrant → top-k chunks

The asymmetry is intentional — BGE is trained to use different representations
for documents vs queries. Using embed_query on a question against document
vectors gives better semantic matching than using the same embedding for both.
"""

import logging

from rag.embedder import embed_documents, embed_query
from rag.retriever import ensure_collection, search, upsert_chunks

logger = logging.getLogger(__name__)


def ingest(filing_id: str, chunks: list[dict]) -> int:
    """Embed all chunks and store in Qdrant. Returns chunk count."""
    ensure_collection()
    texts = [c["text"] for c in chunks]
    embeddings = embed_documents(texts)
    upsert_chunks(filing_id, chunks, embeddings)
    logger.info("RAG ingest complete: %d chunks for %s", len(chunks), filing_id)
    return len(chunks)


def retrieve(question: str, filing_id: str, top_k: int = 5) -> list[dict]:
    """Embed question with query instruction and return top-k chunks from Qdrant."""
    query_vector = embed_query(question)
    chunks = search(query_vector, filing_id, top_k=top_k)
    logger.info(
        "RAG retrieve: %d chunks for filing %s (top score: %s)",
        len(chunks),
        filing_id,
        chunks[0]["score"] if chunks else "n/a",
    )
    return chunks

"""
RAG pipeline — orchestrates ingest and retrieval.

Ingest:   chunks → dense embed + sparse encode → upsert into Qdrant
Retrieve: question → dense embed + sparse encode → hybrid search (RRF) → top-k chunks

Dense (BGE): asymmetric — embed_documents() for chunks, embed_query() for questions.
Sparse (BM25-style): same sparse_encode() for both — Qdrant applies IDF at search time.
RRF (Reciprocal Rank Fusion): merges dense + sparse ranked lists into final top-k.
"""

import logging

from rag.embedder import embed_documents, embed_query, sparse_encode
from rag.retriever import ensure_collection, search, upsert_chunks

logger = logging.getLogger(__name__)


def ingest(filing_id: str, chunks: list[dict]) -> int:
    """Embed all chunks (dense + sparse) and store in Qdrant. Returns chunk count."""
    ensure_collection()
    texts = [c["text"] for c in chunks]
    embeddings = embed_documents(texts)
    sparse_vectors = [sparse_encode(t) for t in texts]
    upsert_chunks(filing_id, chunks, embeddings, sparse_vectors)
    logger.info("RAG ingest complete: %d chunks for %s", len(chunks), filing_id)
    return len(chunks)


def retrieve(question: str, filing_id: str, top_k: int = 5) -> list[dict]:
    """Hybrid search: dense + sparse query → RRF → top-k chunks."""
    query_vector = embed_query(question)
    query_sparse = sparse_encode(question)
    chunks = search(query_vector, query_sparse, filing_id, top_k=top_k)
    logger.info(
        "RAG retrieve: %d chunks for filing %s (top score: %s)",
        len(chunks),
        filing_id,
        chunks[0]["score"] if chunks else "n/a",
    )
    return chunks

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

from rag.embedder import embed_documents, embed_query, sparse_encode
from rag.retriever import ensure_collection, search, search_multi, upsert_chunks
from rag.reranker import rerank

logger = logging.getLogger(__name__)

_RERANK_POOL = 4   # fetch top_k * 4 from Qdrant, rerank down to top_k


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
    """Hybrid search → RRF → rerank → top-k chunks."""
    query_vector = embed_query(question)
    query_sparse = sparse_encode(question)

    # Fetch a wider pool so the reranker has candidates to choose from
    candidates = search(query_vector, query_sparse, filing_id, top_k=top_k * _RERANK_POOL)
    chunks = rerank(question, candidates, top_k=top_k)

    logger.info(
        "RAG retrieve: %d candidates → %d reranked for filing %s (top score: %s)",
        len(candidates), len(chunks), filing_id,
        chunks[0].get("rerank_score", chunks[0]["score"]) if chunks else "n/a",
    )
    return chunks


def retrieve_multi(question: str, filing_ids: list[str], top_k: int = 5) -> list[dict]:
    """Hybrid search across multiple filing IDs → RRF → rerank → top-k chunks."""
    if not filing_ids:
        return []
    query_vector = embed_query(question)
    query_sparse = sparse_encode(question)

    candidates = search_multi(query_vector, query_sparse, filing_ids, top_k=top_k * _RERANK_POOL)
    chunks = rerank(question, candidates, top_k=top_k)

    logger.info(
        "RAG retrieve_multi: %d candidates → %d reranked across %d filings (top score: %s)",
        len(candidates), len(chunks), len(filing_ids),
        chunks[0].get("rerank_score", chunks[0]["score"]) if chunks else "n/a",
    )
    return chunks

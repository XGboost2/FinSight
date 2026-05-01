"""
Retriever — Qdrant client for storing and searching filing chunks.

Two operations:
  upsert_chunks()  — called at ingest time, stores chunk vectors + text
  search()         — called at query time, finds top-k relevant chunks

Why filter by filing_id? We don't want Apple chunks showing up when the
user is asking about Tesla. The filter makes the vector search scoped.
"""

import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from config import get_settings
from rag.embedder import VECTOR_DIM

logger = logging.getLogger(__name__)

COLLECTION = "filings"


def _client() -> QdrantClient:
    return QdrantClient(url=get_settings().QDRANT_URL)


def ensure_collection() -> None:
    """Create the collection if it doesn't exist yet. Safe to call repeatedly."""
    client = _client()
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'", COLLECTION)


def _point_id(filing_id: str, chunk_index: int) -> str:
    """Stable UUID so re-ingesting the same filing overwrites, not duplicates."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{filing_id}:{chunk_index}"))


def upsert_chunks(filing_id: str, chunks: list[dict], embeddings: list[list[float]]) -> None:
    """Store chunk vectors in Qdrant. Upsert = insert or overwrite."""
    client = _client()
    points = [
        PointStruct(
            id=_point_id(filing_id, chunk["chunk_index"]),
            vector=embedding,
            payload={
                "filing_id": filing_id,
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
                "item": chunk.get("item", ""),
                "section": chunk.get("section", ""),
            },
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]
    client.upsert(collection_name=COLLECTION, points=points)
    logger.info("Upserted %d chunks for filing %s", len(points), filing_id)


def search(query_vector: list[float], filing_id: str, top_k: int = 5) -> list[dict]:
    """Find the top-k chunks most semantically similar to the query."""
    client = _client()
    result = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="filing_id", match=MatchValue(value=filing_id))]
        ),
        limit=top_k,
    )
    return [
        {
            "chunk_index": hit.payload["chunk_index"],
            "text": hit.payload["text"],
            "item": hit.payload.get("item", ""),
            "section": hit.payload.get("section", ""),
            "score": round(hit.score, 4),
        }
        for hit in result.points
    ]

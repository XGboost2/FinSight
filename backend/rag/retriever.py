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
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    Modifier,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from functools import lru_cache

from config import get_settings
from rag.embedder import VECTOR_DIM

logger = logging.getLogger(__name__)

COLLECTION = "filings"


@lru_cache(maxsize=1)
def _client() -> QdrantClient:
    return QdrantClient(url=get_settings().QDRANT_URL)


def ensure_collection() -> None:
    """Create hybrid collection (dense + sparse) if it doesn't exist."""
    client = _client()
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config={
                "text-dense": VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "text-sparse": SparseVectorParams(
                    index=SparseIndexParams(on_disk=False),
                    modifier=Modifier.IDF,
                )
            },
        )
        logger.info("Created hybrid Qdrant collection '%s' (dense 768-dim + sparse IDF)", COLLECTION)


def _point_id(filing_id: str, chunk_index: int) -> str:
    """Stable UUID so re-ingesting the same filing overwrites, not duplicates."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{filing_id}:{chunk_index}"))


def upsert_chunks(
    filing_id: str,
    chunks: list[dict],
    embeddings: list[list[float]],
    sparse_vectors: list[tuple[list[int], list[float]]],
) -> None:
    """Store dense + sparse vectors in Qdrant. Upsert = insert or overwrite."""
    client = _client()
    points = [
        PointStruct(
            id=_point_id(filing_id, chunk["chunk_index"]),
            vector={
                "text-dense": embedding,
                "text-sparse": SparseVector(
                    indices=sp_indices,
                    values=sp_values,
                ),
            },
            payload={
                "filing_id": filing_id,
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
                "item": chunk.get("item", ""),
                "section": chunk.get("section", ""),
            },
        )
        for chunk, embedding, (sp_indices, sp_values) in zip(chunks, embeddings, sparse_vectors)
    ]
    client.upsert(collection_name=COLLECTION, points=points)
    logger.info("Upserted %d chunks for filing %s", len(points), filing_id)


def search(
    query_vector: list[float],
    query_sparse: tuple[list[int], list[float]],
    filing_id: str,
    top_k: int = 5,
    item_filter: list[str] | None = None,
) -> list[dict]:
    """Hybrid search: dense + sparse via Reciprocal Rank Fusion (RRF).

    item_filter: if provided, restricts search to specific 10-K sections
    e.g. ["1A"] for Risk Factors, ["7"] for MD&A.
    """
    client = _client()
    must = [FieldCondition(key="filing_id", match=MatchValue(value=filing_id))]
    if item_filter:
        must.append(FieldCondition(key="item", match=MatchAny(any=item_filter)))
    filing_filter = Filter(must=must)
    sp_indices, sp_values = query_sparse
    result = client.query_points(
        collection_name=COLLECTION,
        prefetch=[
            Prefetch(
                query=SparseVector(indices=sp_indices, values=sp_values),
                using="text-sparse",
                filter=filing_filter,
                limit=top_k * 4,
            ),
            Prefetch(
                query=query_vector,
                using="text-dense",
                filter=filing_filter,
                limit=top_k * 4,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )
    return [
        {
            "chunk_index": hit.payload["chunk_index"],
            "text": hit.payload["text"],
            "item": hit.payload.get("item", ""),
            "section": hit.payload.get("section", ""),
            "filing_id": hit.payload.get("filing_id", ""),
            "score": round(hit.score, 4),
        }
        for hit in result.points
    ]


def search_multi(
    query_vector: list[float],
    query_sparse: tuple[list[int], list[float]],
    filing_ids: list[str],
    top_k: int = 5,
    item_filter: list[str] | None = None,
) -> list[dict]:
    """Hybrid search across multiple filing IDs (e.g. 10-K + 10-Q together)."""
    client = _client()
    must = [FieldCondition(key="filing_id", match=MatchAny(any=filing_ids))]
    if item_filter:
        must.append(FieldCondition(key="item", match=MatchAny(any=item_filter)))
    filing_filter = Filter(must=must)
    sp_indices, sp_values = query_sparse
    result = client.query_points(
        collection_name=COLLECTION,
        prefetch=[
            Prefetch(
                query=SparseVector(indices=sp_indices, values=sp_values),
                using="text-sparse",
                filter=filing_filter,
                limit=top_k * 4,
            ),
            Prefetch(
                query=query_vector,
                using="text-dense",
                filter=filing_filter,
                limit=top_k * 4,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )
    return [
        {
            "chunk_index": hit.payload["chunk_index"],
            "text": hit.payload["text"],
            "item": hit.payload.get("item", ""),
            "section": hit.payload.get("section", ""),
            "filing_id": hit.payload.get("filing_id", ""),
            "score": round(hit.score, 4),
        }
        for hit in result.points
    ]


def get_section_chunks(filing_id: str, item: str, limit: int = 40) -> list[dict]:
    """Fetch all stored chunks for a specific section of a filing (no vector search)."""
    client = _client()
    points, _ = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="filing_id", match=MatchValue(value=filing_id)),
                FieldCondition(key="item", match=MatchValue(value=item)),
            ]
        ),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return sorted(
        [
            {
                "chunk_index": p.payload["chunk_index"],
                "text": p.payload["text"],
                "item": p.payload.get("item", ""),
            }
            for p in points
        ],
        key=lambda c: c["chunk_index"],
    )

"""Cross-encoder reranker — rescores RAG candidates for relevance.

Flow:
  hybrid search → top-20 candidates (by RRF score)
      ↓
  reranker reads query + each chunk together → relevance score
      ↓
  return top-5 by reranker score

Why: cosine similarity measures vector proximity, not answer relevance.
A chunk about "geographic concentration" may be the answer to "supply chain risks"
but score poorly on similarity. The cross-encoder reads both and judges correctly.

Model: BAAI/bge-reranker-base — 280MB ONNX, CPU-viable, ~1-2s for 20 chunks.
"""

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    logger.info("Loading BAAI/bge-reranker-base (first call only)…")
    return TextCrossEncoder(model_name="BAAI/bge-reranker-base")


def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """Re-score chunks by relevance to query. Returns top_k sorted by reranker score."""
    if not chunks:
        return chunks
    if len(chunks) <= top_k:
        return chunks

    try:
        model = _get_reranker()
        texts = [c["text"] for c in chunks]
        scores = list(model.rerank(query, texts))

        ranked = sorted(
            zip(scores, chunks),
            key=lambda x: x[0],
            reverse=True,
        )
        result = []
        for score, chunk in ranked[:top_k]:
            chunk = dict(chunk)
            chunk["rerank_score"] = round(float(score), 4)
            result.append(chunk)

        logger.info(
            "Reranker: %d → %d chunks | top score %.4f → %.4f",
            len(chunks), len(result),
            ranked[0][0] if ranked else 0,
            ranked[top_k - 1][0] if len(ranked) >= top_k else 0,
        )
        return result

    except Exception as e:
        logger.warning("Reranker failed (%s) — falling back to RRF order", e)
        return chunks[:top_k]

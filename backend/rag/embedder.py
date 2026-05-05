"""
Embedder — dense + sparse vectors for hybrid search.

Dense model: BAAI/bge-base-en-v1.5
  - ~90MB ONNX, CPU only, 768-dim
  - Asymmetric: embed_documents() for chunks, embed_query() for questions

Sparse (BM25-style):
  - Simple tokenisation → raw token counts as sparse vector
  - Qdrant applies IDF at search time (modifier=IDF in collection config)
  - Together with dense: hybrid search via Reciprocal Rank Fusion (RRF)
"""

import logging
import re
from collections import Counter

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-base-en-v1.5"
VECTOR_DIM = 768

# Hash space for sparse vectors — 2^17 buckets balances collision rate and memory
_SPARSE_DIM = 2 ** 17

_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        logger.info("Loading embedding model %s (first load, ~5s)", MODEL_NAME)
        _model = TextEmbedding(MODEL_NAME)
    return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed filing chunks at ingest time."""
    if not texts:
        return []
    return [vec.tolist() for vec in get_model().embed(texts)]


def embed_query(question: str) -> list[float]:
    """Embed a search query — fastembed applies BGE instruction prefix internally."""
    return next(get_model().query_embed([question])).tolist()


def sparse_encode(text: str) -> tuple[list[int], list[float]]:
    """Convert text to a sparse TF vector using feature hashing.

    Tokenises into lowercase alphanumeric tokens, counts occurrences,
    maps each token to a bucket index via hash(). Qdrant applies IDF
    on top of these raw counts at search time (modifier=IDF).
    """
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    if not tokens:
        return [], []
    counts = Counter(tokens)
    merged: dict[int, float] = {}
    for token, count in counts.items():
        idx = abs(hash(token)) % _SPARSE_DIM
        merged[idx] = merged.get(idx, 0.0) + float(count)
    return list(merged.keys()), list(merged.values())
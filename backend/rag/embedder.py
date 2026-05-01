"""
Embedder — text to vectors using fastembed (local, ONNX, no torch).

Model: BAAI/bge-base-en-v1.5
  - ~90MB ONNX model (vs 440MB torch), runs on CPU
  - 768-dim vectors — richer semantic representation
  - Top of MTEB retrieval benchmarks for English financial/legal text

Asymmetric retrieval (BGE-specific):
  Documents use embed(), queries use query_embed() — fastembed applies
  the BGE instruction prefix internally for query_embed.
"""

import logging
from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-base-en-v1.5"
VECTOR_DIM = 768

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
"""
Embedder — text to vectors using sentence-transformers (local, free).

Model: BAAI/bge-base-en-v1.5
  - 440MB, runs on CPU, no API key needed
  - 768-dim vectors (vs 384 for MiniLM) — richer semantic representation
  - Top of MTEB retrieval benchmarks for English financial/legal text

Asymmetric retrieval (BGE-specific):
  Documents are embedded as-is at ingest time.
  Queries get a prefix instruction at search time — this is how BGE is designed
  to work and gives measurably better retrieval than embedding both the same way.
"""

import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-base-en-v1.5"
VECTOR_DIM = 768
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model %s (first load, ~5s)", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed filing chunks at ingest time. No prefix — documents embed as-is."""
    if not texts:
        return []
    return get_model().encode(texts, convert_to_numpy=True, show_progress_bar=False).tolist()


def embed_query(question: str) -> list[float]:
    """Embed a search query with BGE's instruction prefix for better retrieval."""
    prefixed = QUERY_INSTRUCTION + question
    return get_model().encode([prefixed], convert_to_numpy=True, show_progress_bar=False)[0].tolist()

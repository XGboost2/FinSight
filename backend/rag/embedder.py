"""
Embedder — converts text into vectors using sentence-transformers.

Why this exists: the LLM needs context, but a 10-K filing is 50k+ tokens.
We can't send the whole thing. Instead we embed every chunk once at ingest
time, then at query time we embed the question and find the closest chunks.
"Closest" = cosine similarity = chunks that mean the same thing, not just
share keywords.

Model choice: all-MiniLM-L6-v2
- 80MB, runs on CPU, no API key, 384-dim vectors
- Good enough for Day 14. Upgrade to bge-base-en-v1.5 at Day 56.
"""

import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_DIM = 384

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model %s (first load, ~2s)", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns list of 384-dim float vectors."""
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return vectors.tolist()

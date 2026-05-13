"""FinBERT sentiment scoring on MD&A (Item 7) chunks.

Flow:
  1. Redis cache check (30d TTL keyed by filing_id)
  2. Pull Item 7 chunks from Qdrant (no in-memory store dependency)
  3. Batch FinBERT inference on CPU — ~5s for 20 chunks
  4. Aggregate: weighted average pos/neg/neu across all chunks
  5. Scalar score = (avg_pos - avg_neg + 1) / 2  → range 0.0–1.0
  6. Return top 5 most-polarised sentences for the UI
"""

import asyncio
import json
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

SENTIMENT_TTL = 60 * 60 * 24 * 30  # 30 days
_CACHE_KEY = "finsight:sentiment:{filing_id}"


@lru_cache(maxsize=1)
def _get_pipeline():
    from transformers import pipeline as hf_pipeline
    logger.info("Loading ProsusAI/finbert model (first call only)…")
    return hf_pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        device=-1,          # CPU
        truncation=True,
        max_length=512,
    )


def _is_boilerplate(text: str) -> bool:
    """Skip section headers and short boilerplate that carries no sentiment signal."""
    t = text.strip()
    if len(t) < 120:
        return True
    lower = t.lower()
    return (
        lower.startswith("item ") or
        "should be read in conjunction" in lower or
        "incorporated herein by reference" in lower or
        "table of contents" in lower
    )


def _score_chunks(chunks: list[dict]) -> dict:
    meaningful = [c for c in chunks if not _is_boilerplate(c["text"])]
    if not meaningful:
        return _empty_result()

    pipe = _get_pipeline()
    texts = [c["text"][:1500] for c in meaningful]   # trim before tokeniser

    all_scores = pipe(texts, batch_size=8, top_k=None)

    pos_sum = neg_sum = neu_sum = 0.0
    polarised: list[tuple[float, dict]] = []

    for chunk, scores in zip(meaningful, all_scores):
        score_map = {s["label"]: s["score"] for s in scores}
        pos = score_map.get("positive", 0.0)
        neg = score_map.get("negative", 0.0)
        neu = score_map.get("neutral",  0.0)

        pos_sum += pos
        neg_sum += neg
        neu_sum += neu

        polarity = abs(pos - neg)
        label = "positive" if pos >= neg and pos >= neu else \
                "negative" if neg >= pos and neg >= neu else "neutral"
        polarised.append((polarity, {
            "text":  chunk["text"][:500],
            "label": label,
            "score": round(max(pos, neg, neu), 3),
        }))

    n = len(meaningful)
    avg_pos = pos_sum / n
    avg_neg = neg_sum / n
    avg_neu = neu_sum / n

    scalar = (avg_pos - avg_neg + 1) / 2
    label = "Positive" if scalar >= 0.6 else "Negative" if scalar <= 0.4 else "Neutral"

    top_sentences = [s for _, s in sorted(polarised, key=lambda x: x[0], reverse=True)[:5]]

    return {
        "score":        round(scalar, 3),
        "label":        label,
        "avg_positive": round(avg_pos, 3),
        "avg_negative": round(avg_neg, 3),
        "avg_neutral":  round(avg_neu, 3),
        "chunk_count":  n,
        "top_sentences": top_sentences,
        "model":        "ProsusAI/finbert",
        "source":       "Item 7 — MD&A",
    }


def _empty_result() -> dict:
    return {
        "score": 0.5, "label": "Neutral",
        "avg_positive": 0.0, "avg_negative": 0.0, "avg_neutral": 1.0,
        "chunk_count": 0, "top_sentences": [],
        "model": "ProsusAI/finbert", "source": "Item 7 — MD&A",
    }


async def get_or_score_sentiment(
    redis_client,
    ticker: str,
    filing_id: str,
    refresh: bool = False,
) -> dict:
    key = _CACHE_KEY.format(filing_id=filing_id)

    if not refresh:
        cached = redis_client.get(key)
        if cached:
            logger.info("Sentiment cache hit: %s (%s)", ticker, filing_id)
            return json.loads(cached)

    from rag.retriever import get_section_chunks
    chunks = get_section_chunks(filing_id, "7")
    logger.info("Sentiment: %d item_7 chunks for %s (%s)", len(chunks), ticker, filing_id)

    result = await asyncio.to_thread(_score_chunks, chunks)
    result["ticker"]     = ticker.upper()
    result["filing_id"]  = filing_id

    redis_client.setex(key, SENTIMENT_TTL, json.dumps(result))
    logger.info(
        "Sentiment scored: %s score=%.3f label=%s chunks=%d",
        ticker, result["score"], result["label"], result["chunk_count"],
    )
    return result

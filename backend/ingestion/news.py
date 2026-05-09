"""Finnhub news ingestion — fetches recent company headlines by ticker.

Flow:
  1. Redis cache check (1hr TTL keyed by ticker)
  2. Call Finnhub /company-news for last 7 days
  3. Score each headline with FinBERT (reuses loaded pipeline — no extra cost)
  4. Store in Redis + embed summaries into Qdrant 'news' collection
  5. Return structured NewsItem list
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

NEWS_TTL   = 60 * 60           # 1hr — news goes stale fast
NEWS_KEY   = "finsight:news:{ticker}"
_BASE_URL  = "https://finnhub.io/api/v1"
_MAX_ITEMS = 20                 # cap per ticker per fetch


async def fetch_company_news(ticker: str, days: int = 7) -> list[dict]:
    """Fetch recent headlines from Finnhub for a ticker. Returns raw API items."""
    settings = get_settings()
    token = settings.FINNHUB_API_KEY
    if not token:
        logger.warning("FINNHUB_API_KEY not set — skipping news fetch")
        return []

    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=days)).isoformat()
    to_date   = today.isoformat()

    url = f"{_BASE_URL}/company-news"
    params = {"symbol": ticker.upper(), "from": from_date, "to": to_date, "token": token}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            items = resp.json()
            logger.info("Finnhub: %d articles for %s (%s → %s)", len(items), ticker, from_date, to_date)
            return items[:_MAX_ITEMS]
    except httpx.HTTPStatusError as e:
        logger.error("Finnhub HTTP error for %s: %s", ticker, e)
        return []
    except Exception as e:
        logger.error("Finnhub fetch failed for %s: %s", ticker, e)
        return []


def _score_sentiment(texts: list[str]) -> list[str]:
    """Run FinBERT on a list of texts, return label per text."""
    if not texts:
        return []
    try:
        from services.sentiment import _get_pipeline
        pipe = _get_pipeline()
        results = pipe(texts, batch_size=8, top_k=None, truncation=True, max_length=128)
        labels = []
        for scores in results:
            score_map = {s["label"]: s["score"] for s in scores}
            pos = score_map.get("positive", 0)
            neg = score_map.get("negative", 0)
            neu = score_map.get("neutral",  0)
            labels.append("positive" if pos >= neg and pos >= neu else
                          "negative" if neg >= pos and neg >= neu else "neutral")
        return labels
    except Exception as e:
        logger.warning("FinBERT news scoring failed: %s — defaulting to neutral", e)
        return ["neutral"] * len(texts)


def _format_item(raw: dict, sentiment: str) -> dict:
    return {
        "headline":     raw.get("headline", ""),
        "summary":      raw.get("summary", "")[:300],
        "url":          raw.get("url", ""),
        "source":       raw.get("source", ""),
        "published_at": datetime.fromtimestamp(
            raw.get("datetime", 0), tz=timezone.utc
        ).isoformat() if raw.get("datetime") else "",
        "sentiment":    sentiment,
        "image":        raw.get("image", ""),
    }


def _sentiment_counts(items: list[dict]) -> dict:
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for item in items:
        counts[item["sentiment"]] = counts.get(item["sentiment"], 0) + 1
    return counts


async def _generate_summary(ticker: str, items: list[dict], counts: dict) -> str:
    """One cheap LLM call — summarise news sentiment in 2-3 sentences."""
    if not items:
        return ""
    try:
        from services.llm import call_llm_raw, CHEAP_MODEL
        headlines = "\n".join(f"- [{i['sentiment'].upper()}] {i['headline']}" for i in items[:15])
        total = sum(counts.values())
        prompt = (
            f"You are summarising recent news coverage for {ticker} ({total} articles, last 7 days).\n\n"
            f"Sentiment breakdown: {counts['positive']} positive, {counts['neutral']} neutral, {counts['negative']} negative.\n\n"
            f"Headlines:\n{headlines}\n\n"
            f"Write a 2-3 sentence summary of the news sentiment. Be specific — name actual themes, "
            f"events, or concerns appearing in the headlines. Do not use filler phrases like 'overall' or 'it appears'."
        )
        text, _, _, _ = await call_llm_raw(prompt, max_tokens=150, model=CHEAP_MODEL)
        return text.strip()
    except Exception as e:
        logger.warning("News summary generation failed for %s: %s", ticker, e)
        return ""


async def get_or_fetch_news(redis_client, ticker: str, refresh: bool = False) -> dict:
    """Return cached news or fetch fresh from Finnhub with FinBERT scoring."""
    ticker = ticker.upper()
    key = NEWS_KEY.format(ticker=ticker)

    if not refresh:
        cached = redis_client.get(key)
        if cached:
            logger.info("News cache hit: %s", ticker)
            return json.loads(cached)

    raw_items = await fetch_company_news(ticker)

    if not raw_items:
        result = {"ticker": ticker, "items": [], "sentiment_counts": {"positive": 0, "negative": 0, "neutral": 0}, "source": "finnhub"}
        return result

    # Score all headlines in one batch
    headlines = [item.get("headline", "") for item in raw_items]
    sentiments = _score_sentiment(headlines)

    items = [_format_item(raw, sent) for raw, sent in zip(raw_items, sentiments)]
    counts  = _sentiment_counts(items)
    summary = await _generate_summary(ticker, items, counts)

    result = {
        "ticker":            ticker,
        "items":             items,
        "sentiment_counts":  counts,
        "summary":           summary,
        "source":            "finnhub",
    }

    redis_client.setex(key, NEWS_TTL, json.dumps(result))
    logger.info("News cached: %s — %d items, sentiment: %s", ticker, len(items), result["sentiment_counts"])
    return result

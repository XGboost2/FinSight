import json
import logging
import time

from config import get_settings

logger = logging.getLogger(__name__)

DASHBOARD_PREFIX = "finsight:dashboard:"
DASHBOARD_TTL = 60 * 60 * 24 * 7  # 7 days
CHEAP_MODEL = "claude-3-5-haiku-20241022"

_PRICING = {
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
}


def _cost(model: str, tok_in: int, tok_out: int) -> float:
    p = _PRICING.get(model, {"input": 0.0, "output": 0.0})
    return round((tok_in * p["input"] + tok_out * p["output"]) / 1_000_000, 6)


async def get_or_extract_dashboard(
    redis_client,
    ticker: str,
    filing_id: str,
    fallback_chunks: list[dict] | None = None,
) -> dict:
    """Return dashboard metrics. Redis cache first; Haiku extraction on miss."""
    key = DASHBOARD_PREFIX + ticker.upper()
    cached = redis_client.get(key)
    if cached:
        logger.info("Dashboard cache hit: %s", ticker)
        return json.loads(cached)

    metrics = await _extract_metrics(ticker, filing_id, fallback_chunks or [])
    redis_client.setex(key, DASHBOARD_TTL, json.dumps(metrics))
    logger.info("Dashboard metrics cached for %s (TTL 7d)", ticker)
    return metrics


async def _extract_metrics(ticker: str, filing_id: str, fallback_chunks: list[dict]) -> dict:
    from rag.pipeline import retrieve

    context_chunks = retrieve(
        "revenue net income gross margin risk factors management outlook revenue segments",
        filing_id,
        top_k=8,
    )
    if not context_chunks:
        context_chunks = fallback_chunks[:8]

    context = "\n\n---\n\n".join(
        f"[Chunk {c.get('chunk_index', i)}]\n{c['text']}"
        for i, c in enumerate(context_chunks)
    )[:12000]

    prompt = f"""Extract structured financial metrics from this SEC 10-K filing for {ticker}.
Return ONLY valid JSON with exactly these keys. Use null for any metric not found in the text.

{{
  "executive_summary": "2-3 paragraph holistic overview of company FY performance and key themes",
  "revenue_latest_year": "formatted value e.g. $383B",
  "revenue_yoy_change": "formatted percentage e.g. +2.9%",
  "net_income_latest_year": "formatted value e.g. $96.9B",
  "gross_margin_pct": "formatted percentage e.g. 45.2%",
  "top_3_risk_factors": ["concise risk 1", "concise risk 2", "concise risk 3"],
  "primary_revenue_segments": ["Segment A 52%", "Segment B 22%", "Segment C 8%"],
  "management_outlook_summary": "1-2 sentences on forward guidance from management"
}}

--- FILING TEXT ---
{context}
--- END ---

Return only the JSON object. No markdown, no explanation."""

    settings = get_settings()
    start = time.perf_counter()

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=CHEAP_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        tok_in = response.usage.input_tokens
        tok_out = response.usage.output_tokens

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        metrics = json.loads(raw.strip())

        logger.info(
            "Dashboard extraction: model=%s tok_in=%d tok_out=%d cost=$%.4f latency=%.0fms",
            CHEAP_MODEL, tok_in, tok_out,
            _cost(CHEAP_MODEL, tok_in, tok_out),
            (time.perf_counter() - start) * 1000,
        )
    except Exception as e:
        logger.error("Dashboard extraction failed for %s: %s", ticker, e)
        metrics = {
            "executive_summary": None,
            "revenue_latest_year": None,
            "revenue_yoy_change": None,
            "net_income_latest_year": None,
            "gross_margin_pct": None,
            "top_3_risk_factors": [],
            "primary_revenue_segments": [],
            "management_outlook_summary": None,
        }

    metrics["ticker"] = ticker.upper()
    return metrics

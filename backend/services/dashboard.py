import json
import logging
import time

from cache.ticker_cache import get_ticker_info
from ingestion.xbrl import get_xbrl_metrics
from services.llm import call_llm_raw, _calc_cost

logger = logging.getLogger(__name__)

DASHBOARD_PREFIX = "finsight:dashboard:"
DASHBOARD_TTL = 60 * 60 * 24 * 7  # 7 days


def _cache_key(ticker: str, filing_type: str = "10-K") -> str:
    return f"{DASHBOARD_PREFIX}{ticker.upper()}:{filing_type.upper()}"


async def get_or_extract_dashboard(
    redis_client,
    ticker: str,
    filing_id: str,
    fallback_chunks: list[dict] | None = None,
    filing_type: str = "10-K",
) -> dict:
    """Return dashboard metrics. Redis cache first; XBRL + Haiku extraction on miss."""
    key = _cache_key(ticker, filing_type)
    cached = redis_client.get(key)
    if cached:
        logger.info("Dashboard cache hit: %s (%s)", ticker, filing_type)
        return json.loads(cached)

    metrics = await _extract_metrics(redis_client, ticker, filing_id, fallback_chunks or [])

    has_data = any(
        metrics.get(f) for f in ("revenue_latest_year", "executive_summary", "top_3_risk_factors")
    )
    if has_data:
        redis_client.setex(key, DASHBOARD_TTL, json.dumps(metrics))
        logger.info("Dashboard cached: %s (%s, TTL 7d)", ticker, filing_type)
    else:
        logger.warning("Dashboard extraction empty for %s (%s) — not caching", ticker, filing_type)
    return metrics


async def _extract_metrics(
    redis_client,
    ticker: str,
    filing_id: str,
    fallback_chunks: list[dict],
) -> dict:
    # ── 1. XBRL: deterministic quantitative metrics ───────────────────
    xbrl_metrics = {}
    company_info = get_ticker_info(redis_client, ticker)
    if company_info and company_info.get("cik"):
        xbrl_metrics = await get_xbrl_metrics(company_info["cik"])
        if xbrl_metrics:
            logger.info("XBRL metrics fetched for %s", ticker)
        else:
            logger.warning("XBRL returned no data for %s (CIK %s)", ticker, company_info["cik"])

    # ── 2. LLM: narrative-only fields ────────────────────────────────
    from rag.pipeline import retrieve

    queries = [
        "risk factors material risks business challenges regulatory",
        "management discussion analysis outlook future guidance strategy",
        "business segments revenue breakdown product line geography",
        "executive summary company overview annual performance",
    ]
    seen_indices: set = set()
    context_chunks = []
    for query in queries:
        for c in retrieve(query, filing_id, top_k=5):
            if c.get("chunk_index") not in seen_indices:
                seen_indices.add(c.get("chunk_index"))
                context_chunks.append(c)

    if not context_chunks:
        context_chunks = fallback_chunks[:15]

    context = "\n\n---\n\n".join(
        f"[Chunk {c.get('chunk_index', i)}]\n{c['text']}"
        for i, c in enumerate(context_chunks)
    )[:14000]

    prompt = f"""Extract narrative insights from this SEC 10-K filing for {ticker}.
Return ONLY valid JSON with exactly these keys. Use null if not found.

{{
  "executive_summary": "2-3 sentence overview of FY performance and key themes",
  "top_3_risk_factors": ["concise risk 1", "concise risk 2", "concise risk 3"],
  "primary_revenue_segments": ["Segment A", "Segment B", "Segment C"],
  "management_outlook_summary": "1-2 sentences on forward guidance from management"
}}

--- FILING TEXT ---
{context}
--- END ---

Return only the JSON object. No markdown, no explanation."""

    start = time.perf_counter()
    llm_metrics: dict = {}

    try:
        raw, tok_in, tok_out, model_used = await call_llm_raw(prompt, max_tokens=512)
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        llm_metrics = json.loads(raw.strip())
        logger.info(
            "LLM narrative extraction: model=%s tok_in=%d tok_out=%d cost=$%.4f latency=%.0fms",
            model_used, tok_in, tok_out,
            _calc_cost(model_used, tok_in, tok_out),
            (time.perf_counter() - start) * 1000,
        )
    except Exception as e:
        logger.error("LLM narrative extraction failed for %s: %s", ticker, e)

    # ── 3. Merge: XBRL wins for numbers, LLM wins for narrative ──────
    return {
        "ticker": ticker.upper(),
        "executive_summary": llm_metrics.get("executive_summary"),
        "revenue_latest_year": xbrl_metrics.get("revenue_latest_year"),
        "revenue_yoy_change": xbrl_metrics.get("revenue_yoy_change"),
        "net_income_latest_year": xbrl_metrics.get("net_income_latest_year"),
        "gross_margin_pct": xbrl_metrics.get("gross_margin_pct"),
        "top_3_risk_factors": llm_metrics.get("top_3_risk_factors") or [],
        "primary_revenue_segments": llm_metrics.get("primary_revenue_segments") or [],
        "management_outlook_summary": llm_metrics.get("management_outlook_summary"),
    }

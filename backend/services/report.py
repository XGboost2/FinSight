"""
Report service — generates comprehensive 10-K fundamental analysis report.
Combines XBRL deterministic data + RAG context + LLM synthesis.
Output: structured AnalysisReport with findings table, bull/bear cases, verdict.
"""

import json
import logging
import time
from datetime import datetime, timezone

from cache.ticker_cache import get_ticker_info
from ingestion.xbrl import get_xbrl_metrics
from services.llm import call_llm_raw, _calc_cost

logger = logging.getLogger(__name__)

REPORT_PREFIX = "finsight:report:"
REPORT_TTL = 60 * 60 * 24  # 24h — refresh daily


def _cache_key(ticker: str, filing_type: str = "10-K") -> str:
    return f"{REPORT_PREFIX}{filing_type.upper()}:{ticker.upper()}"


async def get_or_generate_report(
    redis_client,
    ticker: str,
    filing_id: str,
    fallback_chunks: list | None = None,
    refresh: bool = False,
    filing_type: str = "10-K",
) -> dict:
    key = _cache_key(ticker, filing_type)
    if not refresh:
        cached = redis_client.get(key)
        if cached:
            logger.info("Report cache hit: %s (%s)", ticker, filing_type)
            return json.loads(cached)

    report = await _generate_report(redis_client, ticker, filing_id, fallback_chunks or [])

    if report.get("verdict"):
        redis_client.setex(key, REPORT_TTL, json.dumps(report))
        logger.info("Report cached: %s (%s, TTL 24h)", ticker, filing_type)
    else:
        logger.warning("Report incomplete for %s (%s) — not caching", ticker, filing_type)

    return report


async def _generate_report(
    redis_client,
    ticker: str,
    filing_id: str,
    fallback_chunks: list,
) -> dict:
    from rag.pipeline import retrieve

    # XBRL — deterministic financial data
    company_info = get_ticker_info(redis_client, ticker)
    xbrl = {}
    if company_info and company_info.get("cik"):
        xbrl = await get_xbrl_metrics(company_info["cik"])

    # RAG — targeted multi-query context gathering
    queries = [
        "company overview business description products services markets",
        "revenue growth financial performance results of operations",
        "risk factors material risks regulatory competition supply chain",
        "management discussion analysis outlook strategy future guidance",
        "executive highlights key achievements annual performance summary",
    ]
    seen: set = set()
    chunks = []
    for q in queries:
        for c in retrieve(q, filing_id, top_k=5):
            if c.get("chunk_index") not in seen:
                seen.add(c.get("chunk_index"))
                chunks.append(c)

    if not chunks:
        chunks = fallback_chunks[:20]

    context = "\n\n---\n\n".join(
        f"[{c.get('item','Section')} — Chunk {c.get('chunk_index', i)}]\n{c['text']}"
        for i, c in enumerate(chunks)
    )[:20000]

    financial_block = ""
    if xbrl:
        financial_block = f"""
CONFIRMED XBRL FINANCIAL DATA — use these exact numbers in your report:
  Revenue:        {xbrl.get('revenue_latest_year', 'N/A')}
  YoY Change:     {xbrl.get('revenue_yoy_change', 'N/A')}
  Net Income:     {xbrl.get('net_income_latest_year', 'N/A')}
  Gross Margin:   {xbrl.get('gross_margin_pct', 'N/A')}
"""

    prompt = f"""You are a senior equity research analyst. Generate a comprehensive fundamental analysis report for {ticker} based on their SEC 10-K filing.
{financial_block}
--- FILING TEXT ---
{context}
--- END ---

Return ONLY valid JSON with exactly this structure. Ground every claim in the filing. Be specific with numbers and evidence.

{{
  "company_overview": "2-3 sentences: what the company does, key products/services, primary markets and geographic presence",
  "trend_narrative": "2-3 sentences: financial trajectory, revenue trend direction, margin movement, business momentum",
  "findings_table": [
    {{
      "category": "Revenue",
      "metric": "Total Revenue",
      "value": "use exact XBRL value if available",
      "yoy": "e.g. -2.8% or null",
      "signal": "positive",
      "interpretation": "one sentence grounded in filing data"
    }},
    {{
      "category": "Profitability",
      "metric": "Net Income",
      "value": "exact value",
      "yoy": "change or null",
      "signal": "positive",
      "interpretation": "one sentence"
    }},
    {{
      "category": "Profitability",
      "metric": "Gross Margin",
      "value": "exact value",
      "yoy": "change or null",
      "signal": "positive",
      "interpretation": "one sentence"
    }},
    {{
      "category": "Profitability",
      "metric": "YoY Revenue Growth",
      "value": "exact value",
      "yoy": null,
      "signal": "caution",
      "interpretation": "one sentence"
    }},
    {{
      "category": "Risk",
      "metric": "Primary Risk",
      "value": "risk category",
      "yoy": null,
      "signal": "negative",
      "interpretation": "one sentence on top risk"
    }},
    {{
      "category": "Sentiment",
      "metric": "Management Tone",
      "value": "Positive / Neutral / Negative",
      "yoy": null,
      "signal": "neutral",
      "interpretation": "one sentence on management language"
    }}
  ],
  "risk_score": 0.35,
  "risk_factors": [
    "Concise risk 1 with specific evidence from filing",
    "Concise risk 2",
    "Concise risk 3"
  ],
  "sentiment_score": 0.65,
  "sentiment_label": "Positive",
  "management_themes": "2 sentences on management's key focus areas, strategic priorities, and language tone",
  "bull_case": [
    "Specific bull point 1 with evidence from filing",
    "Specific bull point 2",
    "Specific bull point 3"
  ],
  "bear_case": [
    "Specific bear point 1 with evidence",
    "Specific bear point 2",
    "Specific bear point 3"
  ],
  "verdict": "2-3 sentence balanced conclusion. State risk level and investment thesis in plain language."
}}

Signal values must be exactly one of: positive, caution, negative, neutral.
risk_score: 0.0=very low, 0.3=low-moderate, 0.5=moderate, 0.7=high, 1.0=very high.
sentiment_score: 0.0=very negative, 0.5=neutral, 1.0=very positive.
Return only the JSON object. No markdown fences, no explanation."""

    start = time.perf_counter()

    try:
        raw, tok_in, tok_out, model_used = await call_llm_raw(prompt, max_tokens=2500)
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        report = json.loads(raw.strip())
        report["ticker"] = ticker.upper()
        report["company_name"] = company_info.get("name", ticker) if company_info else ticker
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        report["financial_data"] = xbrl
        logger.info(
            "Report generated: %s model=%s tok_in=%d tok_out=%d cost=$%.4f latency=%.0fms",
            ticker, model_used, tok_in, tok_out,
            _calc_cost(model_used, tok_in, tok_out),
            (time.perf_counter() - start) * 1000,
        )
        return report
    except Exception as e:
        logger.error("Report generation failed for %s: %s", ticker, e, exc_info=True)
        return {
            "ticker": ticker.upper(),
            "company_name": company_info.get("name", ticker) if company_info else ticker,
            "error": str(e),
        }



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

try:
    from langfuse.decorators import observe, langfuse_context
except ImportError:
    def observe(*args, **kwargs):       # type: ignore
        def decorator(fn): return fn
        return decorator if args and callable(args[0]) else decorator
    class langfuse_context:             # type: ignore
        @staticmethod
        def update_current_observation(**_): pass
        @staticmethod
        def update_current_trace(**_): pass

logger = logging.getLogger(__name__)

REPORT_PREFIX = "finsight:report:"
REPORT_TTL = 60 * 60 * 24  # 24h — refresh daily


def _clean_json(raw: str) -> str:
    """Strip markdown fences and leading/trailing whitespace from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _filing_belongs_to_ticker(record: dict, ticker: str, redis_client) -> bool:
    """Check if a registry record belongs to a ticker via its stored metadata."""
    from services.store import get_filing
    filing = get_filing(record.get("filing_id", ""))
    return filing is not None and filing.get("ticker", "").upper() == ticker.upper()


def _cache_key(ticker: str, filing_type: str = "10-K") -> str:
    return f"{REPORT_PREFIX}{filing_type.upper()}:{ticker.upper()}"


@observe()
async def get_or_generate_report(
    redis_client,
    ticker: str,
    filing_id: str,
    fallback_chunks: list | None = None,
    refresh: bool = False,
    filing_type: str = "10-K",
) -> dict:
    langfuse_context.update_current_observation(
        name=f"report-lookup/{ticker}",
        input={"ticker": ticker, "filing_id": filing_id, "refresh": refresh, "filing_type": filing_type},
    )

    cache_key = _cache_key(ticker, filing_type)
    if not refresh:
        cached = redis_client.get(cache_key)
        if cached:
            logger.info("Report cache hit: %s (%s)", ticker, filing_type)
            langfuse_context.update_current_observation(metadata={"cache": "hit"})
            return json.loads(cached)

    report = await _generate_report(redis_client, ticker, filing_id, fallback_chunks or [])

    if report.get("verdict"):
        redis_client.setex(cache_key, REPORT_TTL, json.dumps(report))
        logger.info("Report cached: %s (%s, TTL 24h)", ticker, filing_type)
    else:
        logger.warning("Report incomplete for %s (%s) — not caching", ticker, filing_type)

    return report


@observe()
async def _generate_report(
    redis_client,
    ticker: str,
    filing_id: str,
    fallback_chunks: list,
) -> dict:
    langfuse_context.update_current_trace(
        name=f"report/{ticker}",
        user_id=ticker,
        tags=["report", "10-K"],
        metadata={"filing_id": filing_id},
    )
    langfuse_context.update_current_observation(
        name=f"report-generate/{ticker}",
        input={"ticker": ticker, "filing_id": filing_id},
    )
    from rag.pipeline import retrieve, retrieve_multi
    from cache.filing_registry import get_filing_record, list_ingested

    # XBRL — deterministic financial data
    company_info = get_ticker_info(redis_client, ticker)
    xbrl = {}
    if company_info and company_info.get("cik"):
        xbrl = await get_xbrl_metrics(company_info["cik"])

    # Collect all filing IDs: 10-K (primary) + any ingested 10-Q for this ticker
    ten_q_records = [r for r in list_ingested(redis_client, "10-Q")
                     if r.get("filing_id", "").startswith(ticker.lower()) or
                     _filing_belongs_to_ticker(r, ticker, redis_client)]
    all_filing_ids = [filing_id] + [r["filing_id"] for r in ten_q_records
                                    if r["filing_id"] != filing_id][:4]

    # RAG — multi-query across 10-K + 10-Q
    queries = [
        "company overview business description products services markets",
        "revenue growth financial performance results of operations quarterly",
        "risk factors material risks regulatory competition supply chain",
        "management discussion analysis outlook strategy future guidance",
        "recent quarterly performance earnings revenue trend",
    ]
    seen: set = set()
    chunks = []
    retrieve_fn = retrieve_multi if len(all_filing_ids) > 1 else retrieve
    for q in queries:
        results = (retrieve_multi(q, all_filing_ids, top_k=5)
                   if len(all_filing_ids) > 1
                   else retrieve(q, filing_id, top_k=5))
        for c in results:
            key = (c.get("filing_id", ""), c.get("chunk_index"))
            if key not in seen:
                seen.add(key)
                chunks.append(c)

    if not chunks:
        chunks = fallback_chunks[:20]

    context = "\n\n---\n\n".join(
        f"[{c.get('item','Section')} — {c.get('filing_id','')[:6]} Chunk {c.get('chunk_index', i)}]\n{c['text']}"
        for i, c in enumerate(chunks)
    )[:20000]

    # 8-K events enrichment — material events since last 10-K
    import json as _json
    raw_events = redis_client.get(f"finsight:events:8-K:{ticker.upper()}")
    events_block = ""
    if raw_events:
        events = _json.loads(raw_events)[-10:]  # last 10 events
        if events:
            events_block = "\n\nRECENT MATERIAL EVENTS (8-K filings):\n" + "\n".join(
                f"- {e['date']} [{e['event_type'].upper()}]: {e['summary'][:200]}"
                for e in reversed(events)
            )

    financial_block = ""
    if xbrl:
        financial_block = f"""
CONFIRMED XBRL FINANCIAL DATA — use these exact numbers in your report:
  Revenue:        {xbrl.get('revenue_latest_year', 'N/A')}
  YoY Change:     {xbrl.get('revenue_yoy_change', 'N/A')}
  Net Income:     {xbrl.get('net_income_latest_year', 'N/A')}
  Gross Margin:   {xbrl.get('gross_margin_pct', 'N/A')}
"""

    prompt = f"""You are a senior equity research analyst. Generate a comprehensive fundamental analysis report for {ticker} based on their SEC filings (10-K annual + 10-Q quarterly where available).
{financial_block}{events_block}
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

    last_error: Exception | None = None
    for attempt in range(1, 4):  # up to 3 attempts
        try:
            raw, tok_in, tok_out, model_used = await call_llm_raw(prompt, max_tokens=2500)
            raw = _clean_json(raw)
            try:
                report = json.loads(raw)
            except json.JSONDecodeError:
                from json_repair import repair_json
                logger.warning("Report JSON malformed for %s (attempt %d) — running json-repair", ticker, attempt)
                report = json.loads(repair_json(raw))

            report["ticker"] = ticker.upper()
            report["company_name"] = company_info.get("name", ticker) if company_info else ticker
            report["generated_at"] = datetime.now(timezone.utc).isoformat()
            report["financial_data"] = xbrl
            logger.info(
                "Report generated: %s attempt=%d model=%s tok_in=%d tok_out=%d cost=$%.4f latency=%.0fms",
                ticker, attempt, model_used, tok_in, tok_out,
                _calc_cost(model_used, tok_in, tok_out),
                (time.perf_counter() - start) * 1000,
            )

            report["debate_transcript"] = await _generate_debate(
                ticker, report.get("bull_case", []), report.get("bear_case", [])
            )
            return report

        except Exception as e:
            last_error = e
            logger.warning("Report attempt %d failed for %s: %s", attempt, ticker, e)

    logger.error("Report generation failed after 3 attempts for %s: %s", ticker, last_error)
    return {
        "ticker": ticker.upper(),
        "company_name": company_info.get("name", ticker) if company_info else ticker,
        "error": str(last_error),
    }


@observe()
async def _generate_debate(ticker: str, bull_case: list[str], bear_case: list[str]) -> list[dict]:
    """Single LLM call simulating a 2-round bull/bear debate.

    NOTE (Feature 3c): Replace with real CrewAI Bull + Bear researcher agents
    doing multi-turn reasoning with tool access to filing chunks.
    """
    langfuse_context.update_current_observation(
        name=f"debate/{ticker}",
        input={"ticker": ticker, "bull_case": bull_case, "bear_case": bear_case},
    )

    if not bull_case or not bear_case:
        return []

    bull_block = "\n".join(f"- {p}" for p in bull_case)
    bear_block = "\n".join(f"- {p}" for p in bear_case)

    prompt = f"""You are simulating a structured investment debate for {ticker} between a Bull analyst and a Bear analyst.

Bull case points:
{bull_block}

Bear case points:
{bear_block}

Generate a 4-turn debate transcript. Each turn challenges the previous argument with specific evidence.
Return ONLY a JSON array:
[
  {{"role": "Bull", "argument": "Opening argument building on the strongest bull point. 2-3 sentences."}},
  {{"role": "Bear", "argument": "Direct counter to Bull's argument, citing specific risk. 2-3 sentences."}},
  {{"role": "Bull", "argument": "Bull rebuts Bear's concern with mitigating evidence. 2-3 sentences."}},
  {{"role": "Bear", "argument": "Bear's closing — identifies the risk that remains unresolved. 2-3 sentences."}}
]
Return only the JSON array. No markdown."""

    try:
        raw, tok_in, tok_out, model = await call_llm_raw(prompt, max_tokens=600)
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        transcript = json.loads(raw.strip())
        logger.info("Debate transcript: %s model=%s cost=$%.4f", ticker, model, _calc_cost(model, tok_in, tok_out))
        langfuse_context.update_current_observation(
            output=transcript,
            metadata={"model": model, "cost_usd": _calc_cost(model, tok_in, tok_out)},
        )
        return transcript if isinstance(transcript, list) else []
    except Exception as e:
        logger.warning("Debate generation failed for %s: %s", ticker, e)
        langfuse_context.update_current_observation(metadata={"error": str(e)})
        return []

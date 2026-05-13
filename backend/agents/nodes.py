"""
LangGraph node functions — each validates its output against a Pydantic contract.

Parallel nodes (run simultaneously):
  node_fundamentals  — XBRL financial data + company overview/revenue RAG
  node_risk          — Item 1A risk factor RAG
  node_sentiment     — FinBERT MD&A sentiment scoring
  node_news          — Finnhub headlines + 8-K events

Sequential (runs after all parallel nodes complete):
  node_synthesize    — combines all typed outputs, calls LLM, produces ReportOutput
"""

import json
import logging
import time
from datetime import datetime, timezone

from agents.contracts import (
    DebateTurn,
    Event8K,
    FindingRow,
    FundamentalsOutput,
    NewsHeadline,
    NewsOutput,
    RagChunk,
    ReportOutput,
    RiskOutput,
    SentimentOutput,
    XBRLFinancials,
)
from agents.state import AnalysisState

try:
    from langfuse.decorators import observe, langfuse_context
except ImportError:
    def observe(*args, **kwargs):
        def decorator(fn): return fn
        return decorator if args and callable(args[0]) else decorator
    class langfuse_context:
        @staticmethod
        def update_current_observation(**_): pass

logger = logging.getLogger(__name__)


# ── node_fundamentals ──────────────────────────────────────────────────────────

@observe()
async def node_fundamentals(state: AnalysisState) -> dict:
    ticker = state["ticker"]
    filing_id = state["filing_id"]
    company_info = state.get("company_info") or {}

    langfuse_context.update_current_observation(
        name=f"node_fundamentals/{ticker}",
        input={"ticker": ticker, "filing_id": filing_id},
    )

    errors: list[str] = []
    xbrl = XBRLFinancials()
    chunks: list[RagChunk] = []

    try:
        from ingestion.xbrl import get_xbrl_metrics
        if company_info.get("cik"):
            raw_xbrl = await get_xbrl_metrics(company_info["cik"])
            xbrl = XBRLFinancials.model_validate(raw_xbrl)
            logger.info("[fundamentals] XBRL fetched for %s", ticker)
    except Exception as e:
        errors.append(f"fundamentals/xbrl: {e}")
        logger.warning("[fundamentals] XBRL failed for %s: %s", ticker, e)

    try:
        from rag.pipeline import retrieve
        queries = [
            "company overview business description products services markets segments",
            "revenue growth financial performance results of operations earnings",
        ]
        seen: set = set()
        for q in queries:
            for c in retrieve(q, filing_id, top_k=3):
                if c["chunk_index"] not in seen:
                    seen.add(c["chunk_index"])
                    chunks.append(RagChunk.model_validate(c))
        logger.info("[fundamentals] %d chunks for %s", len(chunks), ticker)
    except Exception as e:
        errors.append(f"fundamentals/rag: {e}")
        logger.warning("[fundamentals] RAG failed for %s: %s", ticker, e)

    output = FundamentalsOutput(xbrl=xbrl, chunks=chunks)
    langfuse_context.update_current_observation(
        output={"chunks": len(chunks), "xbrl_revenue": xbrl.revenue_latest_year},
    )
    return {"fundamentals": output, "errors": errors}


# ── node_risk ──────────────────────────────────────────────────────────────────

@observe()
async def node_risk(state: AnalysisState) -> dict:
    ticker = state["ticker"]
    filing_id = state["filing_id"]

    langfuse_context.update_current_observation(
        name=f"node_risk/{ticker}",
        input={"ticker": ticker, "filing_id": filing_id},
    )

    errors: list[str] = []
    chunks: list[RagChunk] = []

    try:
        from rag.pipeline import retrieve
        queries = [
            "material risk factors regulatory competition supply chain",
            "cybersecurity risk legal proceedings litigation government regulation",
        ]
        seen: set = set()
        for q in queries:
            for c in retrieve(q, filing_id, top_k=3):
                if c["chunk_index"] not in seen:
                    seen.add(c["chunk_index"])
                    chunks.append(RagChunk.model_validate(c))
        logger.info("[risk] %d chunks for %s", len(chunks), ticker)
    except Exception as e:
        errors.append(f"risk/rag: {e}")
        logger.warning("[risk] RAG failed for %s: %s", ticker, e)

    output = RiskOutput(chunks=chunks)
    langfuse_context.update_current_observation(output={"chunks": len(chunks)})
    return {"risk": output, "errors": errors}


# ── node_sentiment ─────────────────────────────────────────────────────────────

@observe()
async def node_sentiment(state: AnalysisState) -> dict:
    ticker = state["ticker"]
    filing_id = state["filing_id"]

    langfuse_context.update_current_observation(
        name=f"node_sentiment/{ticker}",
        input={"ticker": ticker},
    )

    errors: list[str] = []
    output = SentimentOutput()

    try:
        from cache.redis_client import get_redis
        from services.sentiment import get_or_score_sentiment
        redis = get_redis()
        raw = await get_or_score_sentiment(redis, ticker, filing_id)
        output = SentimentOutput.model_validate(raw)
        logger.info("[sentiment] score=%.3f label=%s for %s", output.score, output.label, ticker)
    except Exception as e:
        errors.append(f"sentiment: {e}")
        logger.warning("[sentiment] failed for %s: %s", ticker, e)

    langfuse_context.update_current_observation(
        output={"score": output.score, "label": output.label},
    )
    return {"sentiment": output, "errors": errors}


# ── node_news ──────────────────────────────────────────────────────────────────

@observe()
async def node_news(state: AnalysisState) -> dict:
    ticker = state["ticker"]

    langfuse_context.update_current_observation(
        name=f"node_news/{ticker}",
        input={"ticker": ticker},
    )

    errors: list[str] = []
    items: list[NewsHeadline] = []
    events: list[Event8K] = []
    sentiment_counts: dict = {}
    summary = ""

    try:
        from cache.redis_client import get_redis
        from ingestion.news import get_or_fetch_news
        redis = get_redis()
        raw = await get_or_fetch_news(redis, ticker)
        items = [NewsHeadline.model_validate(h) for h in raw.get("items", [])]
        sentiment_counts = raw.get("sentiment_counts", {})
        summary = raw.get("summary", "")
        logger.info("[news] %d items for %s", len(items), ticker)
    except Exception as e:
        errors.append(f"news: {e}")
        logger.warning("[news] fetch failed for %s: %s", ticker, e)

    try:
        from cache.redis_client import get_redis
        redis = get_redis()
        raw = redis.get(f"finsight:events:8-K:{ticker.upper()}")
        if raw:
            for e in json.loads(raw)[-10:]:
                try:
                    events.append(Event8K.model_validate(e))
                except Exception:
                    pass
        logger.info("[news] %d 8-K events for %s", len(events), ticker)
    except Exception as e:
        errors.append(f"events: {e}")
        logger.warning("[news] events failed for %s: %s", ticker, e)

    output = NewsOutput(
        items=items,
        sentiment_counts=sentiment_counts,
        summary=summary,
        events=events,
    )
    langfuse_context.update_current_observation(
        output={"news_items": len(items), "events": len(events)},
    )
    return {"news": output, "errors": errors}


# ── node_synthesize ────────────────────────────────────────────────────────────

@observe()
async def node_synthesize(state: AnalysisState) -> dict:
    """
    Combine all typed parallel node outputs and call LLM to produce ReportOutput.
    Accesses data via Pydantic model attributes — no raw dict key guessing.
    """
    ticker = state["ticker"]
    company_info = state.get("company_info") or {}

    fundamentals: FundamentalsOutput = state.get("fundamentals") or FundamentalsOutput()
    risk: RiskOutput = state.get("risk") or RiskOutput()
    sentiment: SentimentOutput = state.get("sentiment") or SentimentOutput()
    news: NewsOutput = state.get("news") or NewsOutput()

    langfuse_context.update_current_observation(
        name=f"node_synthesize/{ticker}",
        input={
            "ticker": ticker,
            "fundamentals_chunks": len(fundamentals.chunks),
            "risk_chunks": len(risk.chunks),
            "sentiment_score": sentiment.score,
            "news_items": len(news.items),
            "events": len(news.events),
        },
    )

    from services.llm import call_llm_raw, _calc_cost

    xbrl = fundamentals.xbrl

    # Build structured context blocks — typed access, not dict.get()
    fundamentals_text = "\n\n---\n\n".join(
        f"[{c.item or 'Section'} Chunk {c.chunk_index}]\n{c.text}"
        for c in fundamentals.chunks
    )[:8000]

    risk_text = "\n\n---\n\n".join(
        f"[{c.item or 'Section'} Chunk {c.chunk_index}]\n{c.text}"
        for c in risk.chunks
    )[:6000]

    xbrl_block = ""
    if xbrl.revenue_latest_year:
        xbrl_block = f"""CONFIRMED XBRL FINANCIAL DATA (use these exact numbers):
  Revenue (latest year): {xbrl.revenue_latest_year}
  YoY Change:            {xbrl.revenue_yoy_change}
  Net Income:            {xbrl.net_income_latest_year}
  Gross Margin:          {xbrl.gross_margin_pct}"""

    sentiment_block = (
        f"FINBERT SENTIMENT (MD&A): score={sentiment.score:.2f} ({sentiment.label}) | "
        f"pos={sentiment.pos_pct:.0%} neg={sentiment.neg_pct:.0%} neu={sentiment.neu_pct:.0%}"
    )

    news_block = ""
    if news.items:
        news_block = "RECENT NEWS:\n" + "\n".join(
            f"  [{h.sentiment.upper()}] {h.headline[:120]}"
            for h in news.items[:5]
        )

    events_block = ""
    if news.events:
        events_block = "RECENT 8-K EVENTS:\n" + "\n".join(
            f"  {e.date} [{e.event_type.upper()}]: {e.summary[:150]}"
            for e in reversed(news.events)
        )

    prompt = f"""You are a senior equity research analyst. Generate a comprehensive fundamental analysis report for {ticker} ({company_info.get('name', ticker)}).

{xbrl_block}

{sentiment_block}

{news_block}

{events_block}

BUSINESS OVERVIEW & FINANCIAL PERFORMANCE:
{fundamentals_text}

RISK FACTORS (Item 1A):
{risk_text}

Return ONLY valid JSON with exactly this structure:

{{
  "company_overview": "2-3 sentences: what the company does, key products/services, markets",
  "trend_narrative": "2-3 sentences: financial trajectory, revenue trend, margin movement",
  "findings_table": [
    {{"category": "Revenue",       "metric": "Total Revenue",   "value": "use exact XBRL", "yoy": "+6.7%",  "signal": "positive", "interpretation": "one grounded sentence"}},
    {{"category": "Profitability", "metric": "Net Income",      "value": "exact value",    "yoy": "or null","signal": "positive", "interpretation": "one sentence"}},
    {{"category": "Profitability", "metric": "Gross Margin",    "value": "exact value",    "yoy": "or null","signal": "positive", "interpretation": "one sentence"}},
    {{"category": "Risk",          "metric": "Primary Risk",    "value": "risk category",  "yoy": null,     "signal": "negative", "interpretation": "one sentence"}},
    {{"category": "Sentiment",     "metric": "Management Tone", "value": "{sentiment.label}","yoy": null,   "signal": "neutral",  "interpretation": "one sentence"}}
  ],
  "risk_score": 0.35,
  "risk_factors": ["specific risk 1 with evidence", "specific risk 2", "specific risk 3"],
  "sentiment_score": {sentiment.score},
  "sentiment_label": "{sentiment.label}",
  "management_themes": "2 sentences on management focus and strategic priorities",
  "bull_case": ["bull point 1 with filing evidence", "bull point 2", "bull point 3"],
  "bear_case": ["bear point 1 with evidence", "bear point 2", "bear point 3"],
  "verdict": "2-3 sentence balanced conclusion with risk level and investment thesis"
}}

Signal values: exactly one of positive, caution, negative, neutral.
risk_score: 0.0=very low, 0.5=moderate, 1.0=very high.
Return only the JSON. No markdown fences."""

    start = time.perf_counter()
    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            raw, tok_in, tok_out, model_used = await call_llm_raw(prompt, max_tokens=2500)
            raw = raw.strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                from json_repair import repair_json
                logger.warning("[synthesize] JSON repair for %s attempt=%d", ticker, attempt)
                data = json.loads(repair_json(raw))

            # Validate findings_table rows
            findings = [FindingRow.model_validate(r) for r in data.get("findings_table", [])]
            # Validate debate
            debate = await _generate_debate(ticker, data.get("bull_case", []), data.get("bear_case", []))

            output = ReportOutput(
                ticker=ticker.upper(),
                company_name=company_info.get("name", ticker),
                company_overview=data.get("company_overview", ""),
                trend_narrative=data.get("trend_narrative", ""),
                findings_table=findings,
                risk_score=float(data.get("risk_score", 0.5)),
                risk_factors=data.get("risk_factors", []),
                sentiment_score=float(data.get("sentiment_score", sentiment.score)),
                sentiment_label=data.get("sentiment_label", sentiment.label),
                management_themes=data.get("management_themes", ""),
                bull_case=data.get("bull_case", []),
                bear_case=data.get("bear_case", []),
                verdict=data.get("verdict", ""),
                debate_transcript=debate,
                financial_data=xbrl.model_dump(),
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

            cost = _calc_cost(model_used, tok_in, tok_out)
            logger.info(
                "[synthesize] done: %s attempt=%d model=%s cost=$%.4f latency=%.0fms",
                ticker, attempt, model_used, cost, (time.perf_counter() - start) * 1000,
            )
            langfuse_context.update_current_observation(
                output={"verdict": bool(output.verdict), "model": model_used},
                metadata={"cost_usd": cost, "tokens_in": tok_in, "tokens_out": tok_out},
            )
            return {"report": output, "errors": []}

        except Exception as e:
            last_error = e
            logger.warning("[synthesize] attempt %d failed for %s: %s", attempt, ticker, e)

    error_msg = f"synthesize: {last_error}"
    logger.error("[synthesize] all attempts failed for %s: %s", ticker, last_error)
    return {
        "report": ReportOutput(
            ticker=ticker.upper(),
            company_name=company_info.get("name", ticker),
            error=str(last_error),
        ),
        "errors": [error_msg],
    }


@observe()
async def _generate_debate(ticker: str, bull_case: list, bear_case: list) -> list[DebateTurn]:
    """4-turn bull/bear debate. Returns validated DebateTurn list."""
    if not bull_case or not bear_case:
        return []

    from services.llm import call_llm_raw

    bull_block = "\n".join(f"- {p}" for p in bull_case)
    bear_block = "\n".join(f"- {p}" for p in bear_case)

    prompt = f"""Simulate a 4-turn investment debate for {ticker}.
Bull case: {bull_block}
Bear case: {bear_block}

Return ONLY a JSON array:
[
  {{"role": "Bull", "argument": "Opening on strongest bull point. 2-3 sentences."}},
  {{"role": "Bear", "argument": "Direct counter with specific risk. 2-3 sentences."}},
  {{"role": "Bull", "argument": "Rebuttal with mitigating evidence. 2-3 sentences."}},
  {{"role": "Bear", "argument": "Closing — unresolved risk. 2-3 sentences."}}
]"""

    try:
        raw, _, _, _ = await call_llm_raw(prompt, max_tokens=600)
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        turns = json.loads(raw.strip())
        return [DebateTurn.model_validate(t) for t in turns if isinstance(t, dict)]
    except Exception as e:
        logger.warning("[debate] failed for %s: %s", ticker, e)
        return []

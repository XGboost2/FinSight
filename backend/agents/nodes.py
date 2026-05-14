"""
LangGraph node functions — each validated against a Pydantic contract.

Parallel nodes (run simultaneously):
  node_fundamentals  — XBRL + adaptive RAG via FundamentalsAnalyst agent
  node_risk          — Item 1A adaptive RAG via RiskAnalyst agent
  node_sentiment     — FinBERT MD&A sentiment (deterministic service)
  node_news          — Finnhub headlines + 8-K events (deterministic service)
  node_technical     — RSI, MACD, SMA50/200, Bollinger Bands, volume (deterministic service)

Sequential debate nodes (run after parallel nodes complete):
  node_bull          — BullResearcher agent → typed BullCase
  node_bear          — BearResearcher agent (with search tool) → typed BearCase
  node_report        — ReportWriter agent → full ReportOutput
"""

import json
import logging
import time
from datetime import datetime, timezone

from agents.contracts import (
    BullCase,
    BearCase,
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
    TechnicalOutput,
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
    ticker    = state["ticker"]
    filing_id = state["filing_id"]
    cik       = (state.get("company_info") or {}).get("cik")

    langfuse_context.update_current_observation(
        name=f"node_fundamentals/{ticker}",
        input={"ticker": ticker, "filing_id": filing_id},
    )

    errors: list[str] = []

    try:
        from agents.analyst_agents import run_fundamentals_agent
        analysis, chunks, xbrl = await run_fundamentals_agent(ticker, filing_id, cik)
        output = FundamentalsOutput(xbrl=xbrl, chunks=chunks, analysis=analysis)
        logger.info(
            "[fundamentals] agent done: %d chunks, revenue=%s",
            len(chunks), xbrl.revenue_latest_year,
        )
    except Exception as e:
        errors.append(f"fundamentals/agent: {e}")
        logger.warning("[fundamentals] agent failed for %s: %s — falling back", ticker, e)
        # Fallback: plain service calls (existing behaviour)
        output = await _fallback_fundamentals(ticker, filing_id, cik, errors)

    langfuse_context.update_current_observation(
        output={"chunks": len(output.chunks), "xbrl_revenue": output.xbrl.revenue_latest_year},
    )
    return {"fundamentals": output, "errors": errors}


async def _fallback_fundamentals(
    ticker: str, filing_id: str, cik: str | None, errors: list[str],
) -> FundamentalsOutput:
    xbrl = XBRLFinancials()
    chunks: list[RagChunk] = []
    try:
        from ingestion.xbrl import get_xbrl_metrics
        if cik:
            xbrl = XBRLFinancials.model_validate(await get_xbrl_metrics(cik))
    except Exception as e:
        errors.append(f"fundamentals/xbrl_fallback: {e}")
    try:
        from rag.pipeline import retrieve
        seen: set = set()
        for q in [
            "company overview business description products services",
            "revenue growth financial performance results of operations",
        ]:
            for c in retrieve(q, filing_id, top_k=3):
                if c["chunk_index"] not in seen:
                    seen.add(c["chunk_index"])
                    chunks.append(RagChunk.model_validate(c))
    except Exception as e:
        errors.append(f"fundamentals/rag_fallback: {e}")
    return FundamentalsOutput(xbrl=xbrl, chunks=chunks)


# ── node_risk ──────────────────────────────────────────────────────────────────

@observe()
async def node_risk(state: AnalysisState) -> dict:
    ticker    = state["ticker"]
    filing_id = state["filing_id"]

    langfuse_context.update_current_observation(
        name=f"node_risk/{ticker}",
        input={"ticker": ticker, "filing_id": filing_id},
    )

    errors: list[str] = []

    try:
        from agents.analyst_agents import run_risk_agent
        assessment, chunks = await run_risk_agent(ticker, filing_id)
        output = RiskOutput(chunks=chunks, assessment=assessment)
        logger.info(
            "[risk] agent done: %d chunks, score=%.2f",
            len(chunks), assessment.risk_score,
        )
    except Exception as e:
        errors.append(f"risk/agent: {e}")
        logger.warning("[risk] agent failed for %s: %s — falling back", ticker, e)
        output = await _fallback_risk(ticker, filing_id, errors)

    langfuse_context.update_current_observation(output={"chunks": len(output.chunks)})
    return {"risk": output, "errors": errors}


async def _fallback_risk(ticker: str, filing_id: str, errors: list[str]) -> RiskOutput:
    chunks: list[RagChunk] = []
    try:
        from rag.pipeline import retrieve
        seen: set = set()
        for q in [
            "material risk factors regulatory competition supply chain",
            "cybersecurity risk legal proceedings litigation regulation",
        ]:
            for c in retrieve(q, filing_id, top_k=3):
                if c["chunk_index"] not in seen:
                    seen.add(c["chunk_index"])
                    chunks.append(RagChunk.model_validate(c))
    except Exception as e:
        errors.append(f"risk/rag_fallback: {e}")
    return RiskOutput(chunks=chunks)


# ── node_sentiment ─────────────────────────────────────────────────────────────

@observe()
async def node_sentiment(state: AnalysisState) -> dict:
    ticker    = state["ticker"]
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
        redis  = get_redis()
        raw    = await get_or_score_sentiment(redis, ticker, filing_id)
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
    items:  list[NewsHeadline] = []
    events: list[Event8K]      = []
    sentiment_counts: dict     = {}
    summary = ""

    try:
        from cache.redis_client import get_redis
        from ingestion.news import get_or_fetch_news
        redis = get_redis()
        raw   = await get_or_fetch_news(redis, ticker)
        items = [NewsHeadline.model_validate(h) for h in raw.get("items", [])]
        sentiment_counts = raw.get("sentiment_counts", {})
        summary          = raw.get("summary", "")
        logger.info("[news] %d items for %s", len(items), ticker)
    except Exception as e:
        errors.append(f"news: {e}")
        logger.warning("[news] fetch failed for %s: %s", ticker, e)

    try:
        from cache.redis_client import get_redis
        redis = get_redis()
        raw   = redis.get(f"finsight:events:8-K:{ticker.upper()}")
        if raw:
            for ev in json.loads(raw)[-10:]:
                try:
                    events.append(Event8K.model_validate(ev))
                except Exception:
                    pass
        logger.info("[news] %d 8-K events for %s", len(events), ticker)
    except Exception as e:
        errors.append(f"events: {e}")
        logger.warning("[news] events failed for %s: %s", ticker, e)

    output = NewsOutput(
        items=items, sentiment_counts=sentiment_counts,
        summary=summary, events=events,
    )
    langfuse_context.update_current_observation(
        output={"news_items": len(items), "events": len(events)},
    )
    return {"news": output, "errors": errors}


# ── node_technical ────────────────────────────────────────────────────────────

@observe()
async def node_technical(state: AnalysisState) -> dict:
    ticker = state["ticker"]

    langfuse_context.update_current_observation(
        name=f"node_technical/{ticker}",
        input={"ticker": ticker},
    )

    errors: list[str] = []
    output = TechnicalOutput()

    try:
        from cache.redis_client import get_redis
        from services.technical import get_or_fetch_technicals
        redis = get_redis()
        raw   = await get_or_fetch_technicals(redis, ticker)
        if raw.get("error"):
            errors.append(f"technical: {raw['error']}")
            logger.warning("[technical] service error for %s: %s", ticker, raw["error"])
        else:
            output = TechnicalOutput.model_validate(raw)
            logger.info(
                "[technical] %s overall=%s rsi=%.1f",
                ticker, output.overall_signal, output.rsi or 0,
            )
    except Exception as e:
        errors.append(f"technical: {e}")
        logger.warning("[technical] failed for %s: %s", ticker, e)

    langfuse_context.update_current_observation(
        output={"overall_signal": output.overall_signal, "rsi": output.rsi},
    )
    return {"technical": output, "errors": errors}


# ── node_bull ──────────────────────────────────────────────────────────────────

@observe()
async def node_bull(state: AnalysisState) -> dict:
    ticker       = state["ticker"]
    company_info = state.get("company_info") or {}

    langfuse_context.update_current_observation(
        name=f"node_bull/{ticker}",
        input={"ticker": ticker},
    )

    fundamentals = state.get("fundamentals") or FundamentalsOutput()
    risk         = state.get("risk")         or RiskOutput()
    sentiment    = state.get("sentiment")    or SentimentOutput()
    news         = state.get("news")         or NewsOutput()
    technical    = state.get("technical")    or TechnicalOutput()

    from agents.debate_agents import DebateDeps, run_bull_agent
    deps = DebateDeps(
        ticker=ticker,
        filing_id=state["filing_id"],
        company_name=company_info.get("name", ticker),
        fundamentals=fundamentals,
        risk=risk,
        sentiment=sentiment,
        news=news,
        technical=technical,
    )

    bull_case = await run_bull_agent(deps)
    langfuse_context.update_current_observation(
        output={"points": len(bull_case.points), "catalyst": bool(bull_case.key_catalyst)},
    )
    return {"bull_case": bull_case, "errors": []}


# ── node_bear ──────────────────────────────────────────────────────────────────

@observe()
async def node_bear(state: AnalysisState) -> dict:
    ticker       = state["ticker"]
    company_info = state.get("company_info") or {}

    langfuse_context.update_current_observation(
        name=f"node_bear/{ticker}",
        input={"ticker": ticker},
    )

    fundamentals = state.get("fundamentals") or FundamentalsOutput()
    risk         = state.get("risk")         or RiskOutput()
    sentiment    = state.get("sentiment")    or SentimentOutput()
    news         = state.get("news")         or NewsOutput()
    technical    = state.get("technical")    or TechnicalOutput()
    bull_case    = state.get("bull_case")    or BullCase()

    from agents.debate_agents import DebateDeps, run_bear_agent
    deps = DebateDeps(
        ticker=ticker,
        filing_id=state["filing_id"],
        company_name=company_info.get("name", ticker),
        fundamentals=fundamentals,
        risk=risk,
        sentiment=sentiment,
        news=news,
        technical=technical,
        bull_case=bull_case,
    )

    bear_case = await run_bear_agent(deps)
    langfuse_context.update_current_observation(
        output={"points": len(bear_case.points), "key_risk": bool(bear_case.key_risk)},
    )
    return {"bear_case": bear_case, "errors": []}


# ── node_report ────────────────────────────────────────────────────────────────

@observe()
async def node_report(state: AnalysisState) -> dict:
    """
    ReportWriter agent synthesises all typed outputs → ReportOutput.
    Falls back to the original single-LLM approach if the agent fails.
    """
    ticker       = state["ticker"]
    company_info = state.get("company_info") or {}

    langfuse_context.update_current_observation(
        name=f"node_report/{ticker}",
        input={"ticker": ticker},
    )

    start        = time.perf_counter()
    fundamentals = state.get("fundamentals") or FundamentalsOutput()
    risk         = state.get("risk")         or RiskOutput()
    sentiment    = state.get("sentiment")    or SentimentOutput()
    news         = state.get("news")         or NewsOutput()
    technical    = state.get("technical")    or TechnicalOutput()
    bull_case    = state.get("bull_case")    or BullCase()
    bear_case    = state.get("bear_case")    or BearCase()

    from agents.debate_agents import DebateDeps, build_debate_transcript, run_report_agent
    deps = DebateDeps(
        ticker=ticker,
        filing_id=state["filing_id"],
        company_name=company_info.get("name", ticker),
        fundamentals=fundamentals,
        risk=risk,
        sentiment=sentiment,
        news=news,
        technical=technical,
        bull_case=bull_case,
        bear_case=bear_case,
    )

    try:
        report = await run_report_agent(deps)

        # Post-process: fill system-set fields and merge debate transcript
        debate_turns = build_debate_transcript(bull_case, bear_case)
        report = report.model_copy(update={
            "ticker":             ticker.upper(),
            "company_name":       company_info.get("name", ticker),
            "bull_case":          bull_case.points,
            "bear_case":          bear_case.points,
            "debate_transcript":  debate_turns,
            "financial_data":     fundamentals.xbrl.model_dump(),
            "generated_at":       datetime.now(timezone.utc).isoformat(),
            "pipeline":           "pydantic-ai",
        })

        logger.info(
            "[report] agent done: %s latency=%.0fms",
            ticker, (time.perf_counter() - start) * 1000,
        )
        langfuse_context.update_current_observation(
            output={"verdict": bool(report.verdict), "pipeline": "pydantic-ai"},
        )
        return {"report": report, "errors": []}

    except Exception as e:
        logger.warning("[report] agent failed for %s: %s — falling back to LLM", ticker, e)
        return await _fallback_report(state, deps, start)


@observe()
async def _fallback_report(state: AnalysisState, deps: "DebateDeps", start: float) -> dict:
    """Single-LLM fallback if ReportWriter agent fails."""
    from services.llm import call_llm_raw, _calc_cost
    from agents.debate_agents import build_debate_transcript

    ticker       = deps.ticker
    company_info = state.get("company_info") or {}
    fundamentals = deps.fundamentals
    risk         = deps.risk
    sentiment    = deps.sentiment
    news         = deps.news
    bull_case    = deps.bull_case or BullCase()
    bear_case    = deps.bear_case or BearCase()

    xbrl = fundamentals.xbrl
    xbrl_block = ""
    if xbrl.revenue_latest_year:
        xbrl_block = (
            f"XBRL: Revenue={xbrl.revenue_latest_year} (YoY: {xbrl.revenue_yoy_change}) "
            f"NetIncome={xbrl.net_income_latest_year} GrossMargin={xbrl.gross_margin_pct}"
        )

    fund_text  = "\n\n---\n\n".join(f"[{c.item}] {c.text}" for c in fundamentals.chunks)[:6000]
    risk_text  = "\n\n---\n\n".join(f"[{c.item}] {c.text}" for c in risk.chunks)[:4000]
    bull_block = "\n".join(f"- {p}" for p in bull_case.points)
    bear_block = "\n".join(f"- {p}" for p in bear_case.points)

    prompt = f"""You are a senior equity analyst. Write a comprehensive report for {ticker} ({company_info.get('name', ticker)}).

{xbrl_block}
SENTIMENT: {sentiment.score:.2f} ({sentiment.label})
BULL CASE: {bull_block}
BEAR CASE: {bear_block}

FILING CONTEXT:
{fund_text}

RISK FACTORS:
{risk_text}

Return only valid JSON matching this schema:
{{
  "company_overview": "2-3 sentences",
  "trend_narrative": "2-3 sentences on financial trajectory",
  "findings_table": [
    {{"category":"Revenue","metric":"Total Revenue","value":"use XBRL","yoy":"+6.7%","signal":"positive","interpretation":"one sentence"}},
    {{"category":"Profitability","metric":"Net Income","value":"exact","yoy":null,"signal":"positive","interpretation":"one sentence"}},
    {{"category":"Profitability","metric":"Gross Margin","value":"exact","yoy":null,"signal":"positive","interpretation":"one sentence"}},
    {{"category":"Risk","metric":"Primary Risk","value":"category","yoy":null,"signal":"negative","interpretation":"one sentence"}},
    {{"category":"Sentiment","metric":"Management Tone","value":"{sentiment.label}","yoy":null,"signal":"neutral","interpretation":"one sentence"}}
  ],
  "risk_score": 0.35,
  "risk_factors": ["risk 1", "risk 2", "risk 3"],
  "sentiment_score": {sentiment.score},
  "sentiment_label": "{sentiment.label}",
  "management_themes": "2 sentences",
  "verdict": "2-3 sentence balanced conclusion"
}}"""

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            raw, tok_in, tok_out, model_used = await call_llm_raw(prompt, max_tokens=2500)
            raw = raw.strip().lstrip("```json").rstrip("```").strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                from json_repair import repair_json
                data = json.loads(repair_json(raw))

            findings = [FindingRow.model_validate(r) for r in data.get("findings_table", [])]
            report   = ReportOutput(
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
                bull_case=bull_case.points,
                bear_case=bear_case.points,
                verdict=data.get("verdict", ""),
                debate_transcript=build_debate_transcript(bull_case, bear_case),
                financial_data=xbrl.model_dump(),
                generated_at=datetime.now(timezone.utc).isoformat(),
                pipeline="langgraph-fallback",
            )
            cost = _calc_cost(model_used, tok_in, tok_out)
            logger.info("[report] fallback done: %s attempt=%d model=%s cost=$%.4f latency=%.0fms",
                        ticker, attempt, model_used, cost,
                        (time.perf_counter() - start) * 1000)
            return {"report": report, "errors": []}
        except Exception as e:
            last_error = e
            logger.warning("[report] fallback attempt %d failed: %s", attempt, e)

    error_report = ReportOutput(
        ticker=ticker.upper(),
        company_name=company_info.get("name", ticker),
        error=str(last_error),
    )
    return {"report": error_report, "errors": [f"report_fallback: {last_error}"]}

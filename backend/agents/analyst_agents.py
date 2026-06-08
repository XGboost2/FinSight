"""
Pydantic AI analyst agents — context-stuffed synthesis.

Pattern: pre-retrieve data outside the agent (XBRL + RAG), inject as context
into the prompt, call a tool-free agent that only synthesises and validates output.

No tool loops, no ReAct cycles — single LLM call per agent, typed output guaranteed.

Agents:
  fundamentals_agent  — synthesises business overview + financial summary
  risk_agent          — synthesises risk assessment from Item 1A + YoY diff
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic_ai import Agent

from agents.contracts import (
    FundamentalsAnalysis,
    RagChunk,
    RiskAssessment,
    XBRLFinancials,
)

logger = logging.getLogger(__name__)

_DEEPSEEK_CHAT = "deepseek-chat"
_KIMI_MODEL    = "kimi-k2.6"


def _make_model(primary: bool = True):
    from config import get_settings
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    settings = get_settings()

    if primary and settings.DEEPSEEK_API_KEY:
        base = settings.DEEPSEEK_BASE_URL or "https://api.deepseek.com"
        if not base.endswith("/v1"):
            base = base.rstrip("/") + "/v1"
        provider = OpenAIProvider(base_url=base, api_key=settings.DEEPSEEK_API_KEY)
        return OpenAIChatModel(_DEEPSEEK_CHAT, provider=provider)

    provider = OpenAIProvider(
        base_url=settings.KIMI_BASE_URL or "https://api.moonshot.ai/v1",
        api_key=settings.KIMI_API_KEY or "no-key",
    )
    return OpenAIChatModel(_KIMI_MODEL, provider=provider)


# Kept for type compatibility with nodes.py DebateDeps construction
@dataclass
class AnalystDeps:
    ticker: str
    filing_id: str
    cik: str | None = None
    retrieved_chunks: list[RagChunk] = field(default_factory=list)
    seen_chunk_indices: set[int] = field(default_factory=set)
    xbrl_data: XBRLFinancials | None = None


# ── FundamentalsAnalyst (no tools — single synthesis call) ─────────────────────

_fundamentals_agent: Agent | None = None


def get_fundamentals_agent() -> Agent:
    global _fundamentals_agent
    if _fundamentals_agent is not None:
        return _fundamentals_agent

    _fundamentals_agent = Agent(
        model=_make_model(),
        output_type=FundamentalsAnalysis,
        retries=3,
        system_prompt=(
            "You are a fundamentals analyst specialising in SEC 10-K filings. "
            "You will be given pre-retrieved financial data and filing excerpts. "
            "Write concrete, specific summaries — use exact numbers, segment names, "
            "and product lines from the provided data. No generic statements."
        ),
    )
    return _fundamentals_agent


# ── RiskAnalyst (no tools — single synthesis call) ─────────────────────────────

_risk_agent: Agent | None = None


def get_risk_agent() -> Agent:
    global _risk_agent
    if _risk_agent is not None:
        return _risk_agent

    _risk_agent = Agent(
        model=_make_model(),
        output_type=RiskAssessment,
        retries=3,
        system_prompt=(
            "You are a risk analyst specialising in SEC 10-K Item 1A Risk Factors. "
            "You will be given pre-retrieved risk factor text and YoY change data. "
            "Identify 3-5 most material risks with specific filing evidence. "
            "Score overall risk 0.0 (minimal) to 1.0 (severe). "
            "Every risk point must name a specific threat — no generic statements."
        ),
    )
    return _risk_agent


# ── Runner functions ───────────────────────────────────────────────────────────

async def run_fundamentals_agent(
    ticker: str,
    filing_id: str,
    cik: str | None,
) -> tuple[FundamentalsAnalysis, list[RagChunk], XBRLFinancials]:
    """
    Pre-retrieves XBRL + RAG chunks, then calls the synthesis agent once.
    Single LLM call — no tool loops.
    """
    from rag.pipeline import retrieve

    # Pre-fetch XBRL
    xbrl = XBRLFinancials()
    if cik:
        try:
            from ingestion.xbrl import get_xbrl_metrics
            xbrl = XBRLFinancials.model_validate(await get_xbrl_metrics(cik))
        except Exception as e:
            logger.warning("[fundamentals_agent] XBRL pre-fetch failed: %s", e)

    # Pre-retrieve RAG chunks
    seen: set[int] = set()
    chunks: list[RagChunk] = []
    for q in [
        "business overview products services segments revenue",
        "financial performance revenue growth results of operations",
    ]:
        for c in retrieve(q, filing_id, top_k=4):
            if c["chunk_index"] not in seen:
                seen.add(c["chunk_index"])
                chunks.append(RagChunk.model_validate(c))

    xbrl_block = ""
    if xbrl.revenue_latest_year:
        xbrl_block = (
            f"XBRL FINANCIALS:\n"
            f"  Revenue: {xbrl.revenue_latest_year} (YoY: {xbrl.revenue_yoy_change})\n"
            f"  Net Income: {xbrl.net_income_latest_year}\n"
            f"  Gross Margin: {xbrl.gross_margin_pct}"
        )

    filing_text = "\n---\n".join(f"[{c.item}] {c.text[:400]}" for c in chunks[:6])

    prompt = (
        f"Synthesise the following data for {ticker} and return "
        "business_summary and financial_summary.\n\n"
        f"{xbrl_block}\n\n"
        f"FILING EXCERPTS:\n{filing_text}\n\n"
        "business_summary: what the company does, key segments, competitive moat (2-3 sentences).\n"
        "financial_summary: exact revenue/income/margin numbers, YoY trend, key growth driver (2-3 sentences)."
    )

    agent = get_fundamentals_agent()
    result = await agent.run(prompt)
    logger.info("[fundamentals_agent] done for %s: %d chunks", ticker, len(chunks))
    return result.output, chunks, xbrl


async def run_risk_agent(
    ticker: str,
    filing_id: str,
) -> tuple[RiskAssessment, list[RagChunk]]:
    """
    Pre-retrieves Item 1A chunks + YoY diff, then calls the synthesis agent once.
    Single LLM call — no tool loops.
    """
    from rag.pipeline import retrieve

    # Pre-retrieve risk chunks
    seen: set[int] = set()
    chunks: list[RagChunk] = []
    for q in [
        "material risk factors regulatory competition supply chain",
        "cybersecurity risk legal proceedings geopolitical",
    ]:
        for c in retrieve(q, filing_id, top_k=4):
            if c["chunk_index"] not in seen:
                seen.add(c["chunk_index"])
                chunks.append(RagChunk.model_validate(c))

    # Pre-fetch YoY diff summary
    diff_block = ""
    try:
        from services.diff import get_or_compute_diff
        from cache.redis_client import get_redis
        redis = get_redis()
        diff = await get_or_compute_diff(redis, ticker, filing_id)
        new_count     = len(diff.get("new", []))
        changed_count = len(diff.get("changed", []))
        removed_count = len(diff.get("removed", []))
        examples      = [r[:80] for r in diff.get("new", [])[:2]]
        diff_block = (
            f"YoY RISK CHANGES: {new_count} new, {changed_count} changed, {removed_count} removed.\n"
            + ("New risks: " + "; ".join(examples) if examples else "")
        )
    except Exception as e:
        logger.warning("[risk_agent] YoY diff pre-fetch failed: %s", e)

    risk_text = "\n---\n".join(f"[{c.item}] {c.text[:400]}" for c in chunks[:6])

    prompt = (
        f"Synthesise Item 1A risk data for {ticker} and return "
        "top_risks, risk_score, and risk_rationale.\n\n"
        f"{diff_block}\n\n"
        f"RISK FACTOR TEXT:\n{risk_text}\n\n"
        "top_risks: list 3-5 specific material risks with filing evidence.\n"
        "risk_score: float 0.0 (minimal) to 1.0 (severe).\n"
        "risk_rationale: 1-2 sentences explaining the overall risk profile."
    )

    agent = get_risk_agent()
    result = await agent.run(prompt)
    logger.info("[risk_agent] done for %s: score=%.2f %d chunks",
                ticker, result.output.risk_score, len(chunks))
    return result.output, chunks

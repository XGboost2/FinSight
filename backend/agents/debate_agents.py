"""
Pydantic AI debate agents — the real Bull/Bear upgrade.

Three sequential agents replace the old single-LLM _generate_debate call:

  BullResearcher  — reads fundamentals + sentiment → typed BullCase
  BearResearcher  — reads risk + news + BullCase, searches for counter-evidence → typed BearCase
  ReportWriter    — reads all typed outputs → full ReportOutput

Each agent uses deepseek-v4-pro (reasoning model) for multi-step analysis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from pydantic_ai import Agent

from agents.contracts import (
    BullCase,
    BearCase,
    DebateTurn,
    FindingRow,
    FundamentalsOutput,
    NewsOutput,
    PortfolioSignal,
    RagChunk,
    ReportOutput,
    RiskOutput,
    SentimentOutput,
    TechnicalOutput,
)

logger = logging.getLogger(__name__)

_DEEPSEEK_CHAT = "deepseek-chat"  # DeepSeek V3 — primary, function calling supported
_KIMI_MODEL    = "kimi-k2.6"      # Kimi K2.6 — secondary fallback, 256k context


def _make_model():
    """
    Primary: deepseek-chat.
    Fallback to Kimi K2.6 if DeepSeek key unavailable.
    """
    from config import get_settings
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    settings = get_settings()

    if settings.DEEPSEEK_API_KEY:
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


# ── Deps ───────────────────────────────────────────────────────────────────────

@dataclass
class DebateDeps:
    ticker: str
    filing_id: str
    company_name: str
    fundamentals: FundamentalsOutput
    risk: RiskOutput
    sentiment: SentimentOutput
    news: NewsOutput
    technical: TechnicalOutput = None  # type: ignore[assignment]
    bull_case: BullCase | None = None
    bear_case: BearCase | None = None

    def __post_init__(self):
        if self.technical is None:
            self.technical = TechnicalOutput()


# ── BullResearcher ─────────────────────────────────────────────────────────────

_bull_agent: Agent | None = None


def get_bull_agent() -> Agent:
    global _bull_agent
    if _bull_agent is not None:
        return _bull_agent

    _bull_agent = Agent(
        model=_make_model(),
        output_type=BullCase,
        retries=3,
        system_prompt=(
            "You are a bullish equity researcher building an investment thesis. "
            "Given financial data and MD&A sentiment, identify 3-5 specific reasons to be bullish. "
            "Each point must reference concrete evidence: revenue growth %, margin levels, "
            "specific product lines, or competitive moats from the filing. "
            "No generic statements. If revenue grew 6.7%, say 6.7%. "
            "key_catalyst is the single strongest reason to buy."
        ),
        deps_type=DebateDeps,
    )
    return _bull_agent


def _build_bull_prompt(deps: DebateDeps) -> str:
    xbrl = deps.fundamentals.xbrl
    analysis = deps.fundamentals.analysis
    sentiment = deps.sentiment

    xbrl_block = ""
    if xbrl.revenue_latest_year:
        xbrl_block = f"""XBRL FINANCIALS (exact):
  Revenue: {xbrl.revenue_latest_year} (YoY: {xbrl.revenue_yoy_change})
  Net Income: {xbrl.net_income_latest_year}
  Gross Margin: {xbrl.gross_margin_pct}"""

    chunks_text = "\n---\n".join(
        f"[{c.item}] {c.text[:300]}" for c in deps.fundamentals.chunks[:6]
    )

    tech = deps.technical
    tech_block = ""
    if tech.overall_signal and tech.overall_signal != "Neutral":
        ind_lines = "\n".join(
            f"  {i.name}: {i.value} ({i.signal.upper()})" for i in tech.indicators
        )
        tech_block = f"""
TECHNICAL SIGNALS (price action):
  Overall: {tech.overall_signal} | Price: ${tech.price} | RSI: {tech.rsi}
  SMA50: ${tech.sma50} | SMA200: ${tech.sma200}
{ind_lines}
  Verdict: {tech.verdict}"""

    return f"""Build the bull case for {deps.ticker} ({deps.company_name}).

{xbrl_block}

AGENT ANALYSIS:
Business: {analysis.business_summary}
Financials: {analysis.financial_summary}

MD&A SENTIMENT: {sentiment.score:.2f} ({sentiment.label})
Positive themes: {', '.join(sentiment.top_positive[:3])}
{tech_block}

FILING EXCERPTS:
{chunks_text[:3000]}

Identify 3-5 specific, evidence-backed bull points and the single strongest catalyst.
Where technicals confirm fundamentals (e.g. price above SMA200 with strong earnings), use that convergence as evidence."""


# ── BearResearcher ─────────────────────────────────────────────────────────────

_bear_agent: Agent | None = None


def get_bear_agent() -> Agent:
    global _bear_agent
    if _bear_agent is not None:
        return _bear_agent

    _bear_agent = Agent(
        model=_make_model(),
        output_type=BearCase,
        retries=3,
        system_prompt=(
            "You are a short-seller analyst challenging the bull thesis. "
            "You will be given pre-retrieved risk factor text, news, and the bull case to challenge. "
            "Each bear point must directly challenge a specific bull argument with evidence from the provided text. "
            "key_risk is the single biggest unresolved threat to the thesis. "
            "No generic statements — every point must cite specific evidence from the data provided."
        ),
    )
    return _bear_agent


def _build_bear_prompt(deps: DebateDeps) -> str:
    bull = deps.bull_case
    risk_chunks = "\n---\n".join(
        f"[{c.item}] {c.text[:300]}" for c in deps.risk.chunks[:5]
    )
    news_block = "\n".join(
        f"[{h.sentiment.upper()}] {h.headline}" for h in deps.news.items[:5]
    )
    events_block = "\n".join(
        f"{e.date} {e.event_type}: {e.summary}" for e in deps.news.events[-3:]
    ) if deps.news.events else "No recent 8-K events."

    bull_points = "\n".join(f"- {p}" for p in (bull.points if bull else []))

    tech = deps.technical
    tech_block = ""
    if tech.rsi is not None:
        sell_signals = [i for i in tech.indicators if i.signal == "sell"]
        if sell_signals:
            sell_lines = "\n".join(f"  {i.name}: {i.value} — {i.note}" for i in sell_signals)
            tech_block = f"""
TECHNICAL WARNINGS (bearish signals):
  Overall: {tech.overall_signal} | RSI: {tech.rsi} | Price: ${tech.price}
{sell_lines}
  Verdict: {tech.verdict}"""

    return f"""Challenge the bull thesis for {deps.ticker} ({deps.company_name}).

BULL CASE TO CHALLENGE:
{bull_points}
Key catalyst: {bull.key_catalyst if bull else 'N/A'}

RISK FACTORS (Item 1A):
{risk_chunks[:2500]}

RECENT NEWS:
{news_block}

RECENT 8-K EVENTS:
{events_block}
{tech_block}

Using only the risk factor text, news, and technical signals above, build 3-5 bear points that directly challenge the bull case.
Where technicals contradict fundamentals (e.g. RSI overbought despite strong earnings growth), flag that divergence.
Identify the single biggest unresolved risk as key_risk."""


# ── ReportWriter ───────────────────────────────────────────────────────────────

_report_agent: Agent | None = None


def get_report_agent() -> Agent:
    global _report_agent
    if _report_agent is not None:
        return _report_agent

    _report_agent = Agent(
        model=_make_model(),
        output_type=ReportOutput,
        retries=3,
        system_prompt=(
            "You are a senior equity research analyst writing the final report. "
            "Synthesise the bull case, bear case, and all analyst data into a balanced report. "
            "CRITICAL: Use exact XBRL numbers for revenue/income/margin fields. "
            "findings_table rows must have specific values and grounded one-sentence interpretations. "
            "The verdict must acknowledge both sides before reaching a conclusion. "
            "risk_score: 0.0=minimal, 0.5=moderate, 1.0=severe. "
            "signal values: positive | caution | negative | neutral (exactly one of these)."
        ),
        deps_type=DebateDeps,
    )
    return _report_agent


def _build_report_prompt(deps: DebateDeps) -> str:
    xbrl = deps.fundamentals.xbrl
    analysis = deps.fundamentals.analysis
    risk_assessment = deps.risk.assessment
    sentiment = deps.sentiment
    bull = deps.bull_case
    bear = deps.bear_case

    xbrl_block = ""
    if xbrl.revenue_latest_year:
        xbrl_block = (
            f"XBRL FINANCIALS:\n"
            f"  Revenue: {xbrl.revenue_latest_year} (YoY: {xbrl.revenue_yoy_change})\n"
            f"  Net Income: {xbrl.net_income_latest_year}\n"
            f"  Gross Margin: {xbrl.gross_margin_pct}"
        )

    bull_points = "\n".join(f"- {p}" for p in (bull.points if bull else []))
    bear_points = "\n".join(f"- {p}" for p in (bear.points if bear else []))

    risk_chunks = "\n---\n".join(
        f"[{c.item}] {c.text[:250]}" for c in deps.risk.chunks[:4]
    )

    news_block = "\n".join(
        f"[{h.sentiment.upper()}] {h.headline}" for h in deps.news.items[:4]
    )

    tech = deps.technical
    tech_block = ""
    if tech.overall_signal:
        tech_block = (
            f"\nTECHNICAL PICTURE: {tech.overall_signal} | "
            f"RSI={tech.rsi} | Price=${tech.price} | "
            f"SMA50=${tech.sma50} | SMA200=${tech.sma200}\n"
            f"  {tech.verdict}"
        )

    return f"""Write the full investment report for {deps.ticker} ({deps.company_name}).

{xbrl_block}
{tech_block}

ANALYST SUMMARIES:
Business: {analysis.business_summary}
Financials: {analysis.financial_summary}

MD&A SENTIMENT: {sentiment.score:.2f} ({sentiment.label})
Risk assessment: score={risk_assessment.risk_score} — {risk_assessment.risk_rationale}
Top risks: {'; '.join(risk_assessment.top_risks[:3])}

BULL CASE:
{bull_points}
Catalyst: {bull.key_catalyst if bull else 'N/A'}

BEAR CASE:
{bear_points}
Key risk: {bear.key_risk if bear else 'N/A'}

RISK FACTOR TEXT:
{risk_chunks[:2000]}

RECENT NEWS:
{news_block}

Produce the complete ReportOutput JSON. Use exact XBRL numbers.
ticker="{deps.ticker}", company_name="{deps.company_name}".
Leave generated_at, pipeline, error, financial_data, debate_transcript as empty/null — the system fills these."""


# ── Convenience runners ────────────────────────────────────────────────────────

async def run_bull_agent(deps: DebateDeps, max_corrections: int = 2) -> BullCase:
    from agents.validators import validate_bull_case

    agent = get_bull_agent()
    prompt = _build_bull_prompt(deps)

    try:
        for attempt in range(1 + max_corrections):
            result = await agent.run(prompt, deps=deps)
            output = result.output
            issues = validate_bull_case(output, deps.ticker)

            if not issues:
                logger.info("[bull_agent] %d points for %s (attempt %d)",
                            len(output.points), deps.ticker, attempt + 1)
                return output

            if attempt < max_corrections:
                correction = (
                    "\n\nYour previous output had these issues — fix them:\n"
                    + "\n".join(f"- {i}" for i in issues)
                )
                prompt = _build_bull_prompt(deps) + correction
                logger.info("[bull_agent] self-correcting for %s: attempt %d, %d issues",
                            deps.ticker, attempt + 1, len(issues))

        logger.warning("[bull_agent] returning output with %d unresolved issues for %s",
                       len(issues), deps.ticker)
        return output
    except Exception as e:
        logger.error("[bull_agent] failed for %s: %s", deps.ticker, e)
        return BullCase(points=[], key_catalyst="", confidence=0.5)


async def run_bear_agent(deps: DebateDeps, max_corrections: int = 2) -> BearCase:
    from agents.validators import validate_bear_case

    agent = get_bear_agent()
    bull_points = deps.bull_case.points if deps.bull_case else []
    prompt = _build_bear_prompt(deps)

    try:
        for attempt in range(1 + max_corrections):
            result = await agent.run(prompt)
            output = result.output
            issues = validate_bear_case(output, deps.ticker, bull_points)

            if not issues:
                logger.info("[bear_agent] %d points for %s (attempt %d)",
                            len(output.points), deps.ticker, attempt + 1)
                return output

            if attempt < max_corrections:
                correction = (
                    "\n\nYour previous output had these issues — fix them:\n"
                    + "\n".join(f"- {i}" for i in issues)
                )
                prompt = _build_bear_prompt(deps) + correction
                logger.info("[bear_agent] self-correcting for %s: attempt %d, %d issues",
                            deps.ticker, attempt + 1, len(issues))

        logger.warning("[bear_agent] returning output with %d unresolved issues for %s",
                       len(issues), deps.ticker)
        return output
    except Exception as e:
        logger.error("[bear_agent] failed for %s: %s", deps.ticker, e)
        return BearCase(points=[], key_risk="", confidence=0.5)


async def run_report_agent(deps: DebateDeps, max_corrections: int = 2) -> ReportOutput:
    from agents.validators import validate_report

    agent = get_report_agent()
    prompt = _build_report_prompt(deps)

    try:
        for attempt in range(1 + max_corrections):
            result = await agent.run(prompt, deps=deps)
            output = result.output
            issues = validate_report(output, deps.ticker)

            if not issues:
                logger.info("[report_agent] verdict=%s for %s (attempt %d)",
                            bool(output.verdict), deps.ticker, attempt + 1)
                return output

            if attempt < max_corrections:
                correction = (
                    "\n\nYour previous output had these issues — fix them:\n"
                    + "\n".join(f"- {i}" for i in issues)
                )
                prompt = _build_report_prompt(deps) + correction
                logger.info("[report_agent] self-correcting for %s: attempt %d, %d issues",
                            deps.ticker, attempt + 1, len(issues))

        logger.warning("[report_agent] returning output with %d unresolved issues for %s",
                       len(issues), deps.ticker)
        return output
    except Exception as e:
        logger.error("[report_agent] failed for %s: %s", deps.ticker, e)
        raise


# ── PortfolioSignal Agent ──────────────────────────────────────────────────────

_portfolio_agent: Agent | None = None


def get_portfolio_agent() -> Agent:
    global _portfolio_agent
    if _portfolio_agent is not None:
        return _portfolio_agent

    _portfolio_agent = Agent(
        model=_make_model(),
        output_type=PortfolioSignal,
        retries=3,
        system_prompt=(
            "You are a portfolio strategist issuing a BUY, HOLD, or SELL recommendation. "
            "You receive a complete equity analysis: bull/bear debate, technicals, sentiment, risk score, and the report verdict. "
            "Weigh all signals — fundamentals, technicals, sentiment, risk — to issue a single actionable signal. "
            "signal must be exactly one of: BUY, HOLD, SELL. "
            "confidence: 0.0=no conviction, 1.0=maximum conviction. "
            "risk_reward: Favorable | Balanced | Unfavorable. "
            "key_factors: 3-4 most important factors driving the recommendation. "
            "rationale: 2-3 sentences explaining the recommendation."
        ),
        deps_type=DebateDeps,
    )
    return _portfolio_agent


def _build_portfolio_prompt(deps: DebateDeps) -> str:
    bull = deps.bull_case or BullCase()
    bear = deps.bear_case or BearCase()
    tech = deps.technical
    sentiment = deps.sentiment
    risk = deps.risk.assessment

    bull_points = "\n".join(f"- {p}" for p in bull.points)
    bear_points = "\n".join(f"- {p}" for p in bear.points)

    return f"""Issue a portfolio signal for {deps.ticker} ({deps.company_name}).

BULL CASE (confidence: {bull.confidence:.0%}):
{bull_points}
Catalyst: {bull.key_catalyst}

BEAR CASE (confidence: {bear.confidence:.0%}):
{bear_points}
Key risk: {bear.key_risk}

DEBATE WINNER: {'Bull' if bull.confidence > bear.confidence else 'Bear' if bear.confidence > bull.confidence else 'Draw'}

TECHNICALS: {tech.overall_signal} | RSI={tech.rsi} | Price=${tech.price}
  {tech.verdict}

SENTIMENT: {sentiment.score:.2f} ({sentiment.label})
RISK SCORE: {risk.risk_score:.2f} — {risk.risk_rationale}

Based on all signals, issue your BUY/HOLD/SELL recommendation with confidence and rationale."""


async def run_portfolio_agent(deps: DebateDeps, max_corrections: int = 2) -> PortfolioSignal:
    from agents.validators import validate_portfolio_signal

    agent = get_portfolio_agent()
    prompt = _build_portfolio_prompt(deps)

    try:
        for attempt in range(1 + max_corrections):
            result = await agent.run(prompt, deps=deps)
            output = result.output
            if output.signal not in ("BUY", "HOLD", "SELL"):
                output = output.model_copy(update={"signal": output.signal.upper()})
            issues = validate_portfolio_signal(output, deps.ticker)

            if not issues:
                logger.info("[portfolio_agent] %s signal=%s confidence=%.0f%% for %s (attempt %d)",
                            deps.ticker, output.signal, output.confidence * 100,
                            deps.ticker, attempt + 1)
                return output

            if attempt < max_corrections:
                correction = (
                    "\n\nYour previous output had these issues — fix them:\n"
                    + "\n".join(f"- {i}" for i in issues)
                )
                prompt = _build_portfolio_prompt(deps) + correction
                logger.info("[portfolio_agent] self-correcting for %s: attempt %d, %d issues",
                            deps.ticker, attempt + 1, len(issues))

        logger.warning("[portfolio_agent] returning output with %d unresolved issues for %s",
                       len(issues), deps.ticker)
        return output
    except Exception as e:
        logger.error("[portfolio_agent] failed for %s: %s", deps.ticker, e)
        return PortfolioSignal()


def build_debate_transcript(bull: BullCase, bear: BearCase) -> list[DebateTurn]:
    """Convert BullCase/BearCase into the 4-turn DebateTurn list."""
    if not bull.points or not bear.points:
        return []
    return [
        DebateTurn(role="Bull", argument=bull.points[0] if bull.points else bull.key_catalyst),
        DebateTurn(role="Bear", argument=bear.points[0] if bear.points else bear.key_risk),
        DebateTurn(role="Bull", argument=bull.key_catalyst),
        DebateTurn(role="Bear", argument=bear.key_risk),
    ]

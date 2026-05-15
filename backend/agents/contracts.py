"""
Agent output contracts — Pydantic models for typed data flow between LangGraph nodes.

Each node validates its output against one of these models before writing to state.
Analyst agents (Fundamentals, Risk) populate chunks + analysis structs.
Debate agents (Bull, Bear, ReportWriter) consume typed data and produce typed outputs.
"""

from pydantic import BaseModel, Field


# ── Shared primitives ──────────────────────────────────────────────────────────

class RagChunk(BaseModel):
    chunk_index: int = 0
    text: str
    item: str = ""
    section: str = ""
    score: float = 0.0
    filing_id: str = ""


# ── node_fundamentals output ───────────────────────────────────────────────────

class XBRLFinancials(BaseModel):
    revenue_latest_year: str | None = None
    revenue_yoy_change: str | None = None
    net_income_latest_year: str | None = None
    gross_margin_pct: str | None = None
    primary_revenue_segments: list[str] = Field(default_factory=list)
    revenue_trend: list[dict] = Field(default_factory=list)


class FundamentalsAnalysis(BaseModel):
    """Agent-synthesised summaries from FundamentalsAnalyst (result_type)."""
    business_summary: str = ""
    financial_summary: str = ""


class FundamentalsOutput(BaseModel):
    xbrl: XBRLFinancials = Field(default_factory=XBRLFinancials)
    chunks: list[RagChunk] = Field(default_factory=list)
    analysis: FundamentalsAnalysis = Field(default_factory=FundamentalsAnalysis)


# ── node_risk output ───────────────────────────────────────────────────────────

class RiskAssessment(BaseModel):
    """Agent-generated risk analysis from RiskAnalyst (result_type)."""
    top_risks: list[str] = Field(default_factory=list)
    risk_score: float = 0.5
    risk_rationale: str = ""


class RiskOutput(BaseModel):
    chunks: list[RagChunk] = Field(default_factory=list)
    assessment: RiskAssessment = Field(default_factory=RiskAssessment)


# ── Debate agent outputs ───────────────────────────────────────────────────────

class BullCase(BaseModel):
    """BullResearcher agent output — grounded bull thesis."""
    points: list[str] = Field(default_factory=list)
    key_catalyst: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class BearCase(BaseModel):
    """BearResearcher agent output — grounded bear thesis with counter-evidence."""
    points: list[str] = Field(default_factory=list)
    key_risk: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class PortfolioSignal(BaseModel):
    """Portfolio signal agent output — actionable BUY/HOLD/SELL recommendation."""
    signal: str = "HOLD"             # BUY | HOLD | SELL
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = ""
    key_factors: list[str] = Field(default_factory=list)
    risk_reward: str = ""            # e.g. "Favorable" / "Balanced" / "Unfavorable"


# ── node_sentiment output ──────────────────────────────────────────────────────

class SentimentOutput(BaseModel):
    score: float = 0.5           # 0.0 very negative → 1.0 very positive
    label: str = "Neutral"       # Positive | Negative | Neutral
    pos_pct: float = 0.0
    neg_pct: float = 0.0
    neu_pct: float = 0.0
    top_positive: list[str] = Field(default_factory=list)
    top_negative: list[str] = Field(default_factory=list)


# ── node_news output ───────────────────────────────────────────────────────────

class NewsHeadline(BaseModel):
    headline: str
    source: str = ""
    sentiment: str = "neutral"   # positive | negative | neutral
    published_at: str | None = None
    url: str | None = None


class Event8K(BaseModel):
    date: str
    event_type: str
    summary: str


class NewsOutput(BaseModel):
    items: list[NewsHeadline] = Field(default_factory=list)
    sentiment_counts: dict[str, int] = Field(default_factory=dict)
    summary: str = ""
    events: list[Event8K] = Field(default_factory=list)


# ── node_technical output ─────────────────────────────────────────────────────

class TechnicalIndicator(BaseModel):
    name: str
    value: str
    signal: str = "neutral"  # buy | neutral | sell
    note: str = ""


class TechnicalOutput(BaseModel):
    price: float | None = None
    rsi: float | None = None
    macd_hist: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None
    volume_ratio: float | None = None
    overall_signal: str = "Neutral"
    signal_counts: dict[str, int] = Field(default_factory=dict)
    indicators: list[TechnicalIndicator] = Field(default_factory=list)
    verdict: str = ""
    error: str | None = None


# ── node_synthesize output ─────────────────────────────────────────────────────

class FindingRow(BaseModel):
    category: str
    metric: str
    value: str
    yoy: str | None = None
    signal: str = "neutral"      # positive | caution | negative | neutral
    interpretation: str


class DebateTurn(BaseModel):
    role: str                    # Bull | Bear
    argument: str


class ReportOutput(BaseModel):
    ticker: str
    company_name: str
    company_overview: str = ""
    trend_narrative: str = ""
    findings_table: list[FindingRow] = Field(default_factory=list)
    risk_score: float = 0.5
    risk_factors: list[str] = Field(default_factory=list)
    sentiment_score: float = 0.5
    sentiment_label: str = "Neutral"
    management_themes: str = ""
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    bull_confidence: float = 0.5
    bear_confidence: float = 0.5
    debate_winner: str = ""          # Bull | Bear | Draw
    verdict: str = ""
    debate_transcript: list[DebateTurn] = Field(default_factory=list)
    citations: list[RagChunk] = Field(default_factory=list)
    financial_data: dict = Field(default_factory=dict)
    generated_at: str = ""
    pipeline: str = "langgraph"
    error: str | None = None

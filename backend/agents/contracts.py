"""
Agent output contracts — Pydantic models for typed data flow between LangGraph nodes.

Each parallel node validates its output against one of these models before writing
to state. The synthesize node receives typed objects, not raw dicts.

When CrewAI agents are added, each agent's output must conform to these contracts.
This makes the interface explicit and catches shape errors at the boundary.
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


class FundamentalsOutput(BaseModel):
    xbrl: XBRLFinancials = Field(default_factory=XBRLFinancials)
    chunks: list[RagChunk] = Field(default_factory=list)


# ── node_risk output ───────────────────────────────────────────────────────────

class RiskOutput(BaseModel):
    chunks: list[RagChunk] = Field(default_factory=list)


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
    verdict: str = ""
    debate_transcript: list[DebateTurn] = Field(default_factory=list)
    financial_data: dict = Field(default_factory=dict)
    generated_at: str = ""
    pipeline: str = "langgraph"
    error: str | None = None

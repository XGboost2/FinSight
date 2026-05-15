"""FinSight AI — Pydantic data models for API requests/responses.

All structured data flows through these models. Never use raw dicts.
"""

import re
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator


# === Filing Models (legacy — keep for /api/filings/* endpoints) ===

class FetchFilingRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    filing_type: str = Field(default="10-K")


class ChunkInfo(BaseModel):
    id: str
    text: str
    chunk_index: int
    char_start: int
    char_end: int


class FilingInfo(BaseModel):
    id: str
    ticker: str
    company_name: str = ""
    filing_type: str
    filed_date: str = ""
    chunk_count: int
    status: str = "ready"
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FilingResponse(BaseModel):
    success: bool
    filing: FilingInfo | None = None
    message: str = ""


class FilingListResponse(BaseModel):
    filings: list[FilingInfo]
    total: int


# === Chat Models ===

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    ticker: str = Field(..., min_length=1, max_length=10)
    model: str | None = None     # None = auto-route
    include_context: bool = False  # set True to get full chunk text (eval only)
    session_id: str | None = None  # omit for sessionless (eval / direct API)


class SourceChunk(BaseModel):
    chunk_index: int
    text_preview: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    model_used: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float
    trace_id: str | None = None
    contexts: list[str] | None = None  # full chunk text, only when include_context=True
    from_cache: bool = False           # True when answer was served from session cache
    history_len: int = 0               # number of prior turns in this session


class FeedbackRequest(BaseModel):
    trace_id: str = Field(..., min_length=1)
    helpful: bool
    comment: str | None = Field(default=None, max_length=500)


# === Company Search / Ingest (Day 15) ===

class CompanyInfo(BaseModel):
    name: str
    ticker: str
    cik: str


class SearchResponse(BaseModel):
    results: list[CompanyInfo]
    total: int


class IngestResponse(BaseModel):
    ticker: str
    filing_id: str
    chunk_count: int
    already_existed: bool
    company_name: str = ""
    filed_date: str = ""


# === Dashboard (Day 15) ===

class DashboardResponse(BaseModel):
    ticker: str
    executive_summary: str | None = None
    revenue_latest_year: str | None = None
    revenue_yoy_change: str | None = None
    net_income_latest_year: str | None = None
    gross_margin_pct: str | None = None
    top_3_risk_factors: list[str] = []
    primary_revenue_segments: list[str] = []
    management_outlook_summary: str | None = None

    @field_validator("top_3_risk_factors", "primary_revenue_segments", mode="before")
    @classmethod
    def none_to_empty_list(cls, v):
        return v if v is not None else []


# === Comparison (Day 15) ===

class CompareRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=2)


class RevenueYear(BaseModel):
    year: str
    value: str
    raw: float


class CompareResponse(BaseModel):
    ticker1: str
    ticker2: str
    metrics1: dict
    metrics2: dict
    analysis: dict
    trends1: list[RevenueYear] = []
    trends2: list[RevenueYear] = []


# === Analysis Report ===

class FindingRow(BaseModel):
    category: str
    metric: str
    value: str
    yoy: str | None = None
    signal: str = "neutral"   # positive | caution | negative | neutral
    interpretation: str = ""


class AnalysisReport(BaseModel):
    ticker: str
    company_name: str = ""
    generated_at: str = ""
    company_overview: str = ""
    trend_narrative: str = ""
    findings_table: list[FindingRow] = []
    risk_score: float = 0.0
    risk_factors: list[str] = []
    sentiment_score: float = 0.5
    sentiment_label: str = "Neutral"
    management_themes: str = ""
    bull_case: list[str] = []
    bear_case: list[str] = []
    bull_confidence: float = 0.5
    bear_confidence: float = 0.5
    debate_winner: str = ""          # Bull | Bear | Draw
    debate_transcript: list[dict] = []   # [{role, argument}]
    verdict: str = ""
    portfolio_signal: dict | None = None  # {signal, confidence, rationale, key_factors, risk_reward}
    financial_data: dict = {}
    error: str | None = None

    @field_validator("risk_factors", "bull_case", "bear_case", "findings_table", "debate_transcript", mode="before")
    @classmethod
    def none_to_empty(cls, v):
        return v if v is not None else []


# === YoY Diff ===

class ChangedParagraph(BaseModel):
    current: str
    prior: str
    similarity: float = 0.0


class SectionDiff(BaseModel):
    section: str = ""
    current_year: str = ""
    prior_year: str = ""
    summary: str = ""
    new: list[str] = []
    removed: list[str] = []
    changed: list[ChangedParagraph] = []
    unchanged_count: int = 0

    @field_validator("new", "removed", mode="before")
    @classmethod
    def coerce_list(cls, v):
        return v if v is not None else []

    @field_validator("changed", mode="before")
    @classmethod
    def coerce_changed(cls, v):
        if not v:
            return []
        return [ChangedParagraph(**i) if isinstance(i, dict) else i for i in v]


class YoYDiffResponse(BaseModel):
    ticker: str
    current_year: str = ""
    prior_year: str = ""
    item_1:  SectionDiff = SectionDiff()
    item_1a: SectionDiff = SectionDiff()
    item_7:  SectionDiff = SectionDiff()


# === News (Feature 3a) ===

class NewsItem(BaseModel):
    headline:     str
    summary:      str = ""
    url:          str = ""
    source:       str = ""
    published_at: str = ""
    sentiment:    str = "neutral"   # positive | negative | neutral (FinBERT)
    image:        str = ""


class NewsResponse(BaseModel):
    ticker:           str
    items:            list[NewsItem] = []
    sentiment_counts: dict = {}
    summary:          str = ""
    source:           str = "finnhub"

    @field_validator("items", mode="before")
    @classmethod
    def coerce_items(cls, v):
        if not v:
            return []
        return [NewsItem(**i) if isinstance(i, dict) else i for i in v]


# === FinBERT Sentiment (Feature 2) ===

class SentimentSentence(BaseModel):
    text: str
    label: str   # positive | negative | neutral
    score: float


class SentimentResult(BaseModel):
    ticker: str
    filing_id: str
    score: float = 0.5          # 0.0 → 1.0 (rescaled from pos - neg)
    label: str = "Neutral"      # Positive | Neutral | Negative
    avg_positive: float = 0.0
    avg_negative: float = 0.0
    avg_neutral: float = 0.0
    chunk_count: int = 0
    top_sentences: list[SentimentSentence] = []
    model: str = "ProsusAI/finbert"
    source: str = "Item 7 — MD&A"

    @field_validator("top_sentences", mode="before")
    @classmethod
    def coerce_sentences(cls, v):
        if not v:
            return []
        return [SentimentSentence(**s) if isinstance(s, dict) else s for s in v]


# === Health ===

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.2.0"
    filings_loaded: int = 0
    redis_ok: bool = False
    qdrant_ok: bool = False

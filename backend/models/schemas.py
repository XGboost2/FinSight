"""FinSight AI — Pydantic data models for API requests/responses.

All structured data flows through these models. Never use raw dicts.
"""

from datetime import datetime
from pydantic import BaseModel, Field


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
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


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


# === Comparison (Day 15) ===

class CompareRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=2)


class CompareResponse(BaseModel):
    ticker1: str
    ticker2: str
    metrics1: dict
    metrics2: dict
    analysis: dict


# === Health ===

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.2.0"
    filings_loaded: int = 0
    redis_ok: bool = False

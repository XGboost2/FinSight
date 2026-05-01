"""FinSight AI — Pydantic data models for API requests/responses.

All structured data flows through these models. Never use raw dicts.
"""

from datetime import datetime
from pydantic import BaseModel, Field


# === Filing Models ===

class FetchFilingRequest(BaseModel):
    """Request to fetch and ingest a 10-K filing."""
    ticker: str = Field(..., min_length=1, max_length=10, description="Stock ticker symbol (e.g. AAPL)")
    filing_type: str = Field(default="10-K", description="SEC filing type")


class ChunkInfo(BaseModel):
    """A single text chunk from a filing."""
    id: str
    text: str
    chunk_index: int
    char_start: int
    char_end: int


class FilingInfo(BaseModel):
    """Metadata for an ingested filing."""
    id: str
    ticker: str
    company_name: str = ""
    filing_type: str
    filed_date: str = ""
    chunk_count: int
    status: str = "ready"  # fetching | chunking | ready | error
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


class FilingResponse(BaseModel):
    """API response for filing operations."""
    success: bool
    filing: FilingInfo | None = None
    message: str = ""


class FilingListResponse(BaseModel):
    """API response for listing all filings."""
    filings: list[FilingInfo]
    total: int


# === Chat Models ===

class ChatRequest(BaseModel):
    """Request to ask a question about a filing."""
    question: str = Field(..., min_length=1, max_length=2000, description="Your question about the filing")
    filing_id: str = Field(..., description="ID of the ingested filing to query")


class SourceChunk(BaseModel):
    """A source chunk cited in the answer."""
    chunk_index: int
    text_preview: str = Field(..., description="First 200 chars of the chunk")


class ChatResponse(BaseModel):
    """API response for chat/Q&A."""
    answer: str
    sources: list[SourceChunk]
    model_used: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float


# === Health ===

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "0.1.0"
    filings_loaded: int = 0

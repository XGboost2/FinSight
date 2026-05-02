import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# ── Shared mock data ──────────────────────────────────────────────────────────

TICKER = "AAPL"
TICKER2 = "MSFT"
FILING_ID = "aapl-10k-2023"
FILING_ID2 = "msft-10k-2023"

CHUNKS = [
    {"chunk_index": 0, "text": "Apple Inc. is a technology company.", "item": "Item 1", "section": ""},
    {"chunk_index": 1, "text": "Risk factors include supply chain disruption.", "item": "Item 1A", "section": ""},
]

EDGAR_RESULT = {
    "id": FILING_ID,
    "ticker": TICKER,
    "company_name": "Apple Inc.",
    "filing_type": "10-K",
    "filed_date": "2023-11-03",
    "text": "Full 10-K filing text content.",
}

FILING_RECORD = {
    "filing_id": FILING_ID,
    "filed_date": "2023-11-03",
    "chunk_count": len(CHUNKS),
    "ingested_at": "2024-01-01T00:00:00+00:00",
}

STORED_FILING = {**EDGAR_RESULT, "chunks": CHUNKS}

DASHBOARD = {
    "ticker": TICKER,
    "executive_summary": "Apple reported strong revenue.",
    "revenue_latest_year": "$394.3B",
    "revenue_yoy_change": "-2.8%",
    "net_income_latest_year": "$96.9B",
    "gross_margin_pct": "44.1%",
    "top_3_risk_factors": ["Competition", "Supply chain", "Regulatory"],
    "primary_revenue_segments": ["iPhone", "Services", "Mac"],
    "management_outlook_summary": "Management is optimistic.",
}

DASHBOARD2 = {**DASHBOARD, "ticker": TICKER2, "revenue_latest_year": "$211.9B"}

LLM_RESULT = {
    "answer": "The main risk factors are competition and supply chain disruption.",
    "model_used": "claude-haiku-4-5",
    "tokens_in": 500,
    "tokens_out": 100,
    "cost_usd": 0.0005,
    "latency_ms": 350.0,
}

COMPANY_INFO = {"name": "Apple Inc.", "ticker": TICKER, "cik": "0000320193"}

COMPARISON_RESULT = {
    "ticker1": TICKER,
    "ticker2": TICKER2,
    "metrics1": DASHBOARD,
    "metrics2": DASHBOARD2,
    "analysis": {
        "financial_head_to_head": "Apple has higher revenue than Microsoft.",
        "pros_cons": {
            TICKER: {"pros": ["Strong brand"], "cons": ["Premium pricing"]},
            TICKER2: {"pros": ["Diversified revenue"], "cons": ["Cloud competition"]},
        },
        "strategic_positioning": "Different market strategies.",
        "verdict": "Both are strong companies.",
    },
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.ping.return_value = True
    redis.exists.return_value = True  # ticker cache already loaded
    return redis


@pytest.fixture
def client(mock_redis):
    """TestClient with startup dependencies mocked (Redis, ticker loader)."""
    with patch("cache.redis_client.get_redis", return_value=mock_redis), \
         patch("cache.ticker_cache.load_tickers_into_redis", new_callable=AsyncMock, return_value=0):
        from main import app
        with TestClient(app) as c:
            yield c

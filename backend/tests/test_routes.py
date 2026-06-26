"""API route tests — all external dependencies mocked."""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


REPORT_DATA = {
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "generated_at": "2026-01-01T00:00:00+00:00",
    "company_overview": "Apple designs consumer electronics.",
    "trend_narrative": "Revenue softened, margins expanded.",
    "findings_table": [],
    "risk_score": 0.34,
    "risk_factors": ["Competition", "Regulatory"],
    "sentiment_score": 0.68,
    "sentiment_label": "Positive",
    "management_themes": "Management is focused on AI.",
    "bull_case": ["Services growth"],
    "bear_case": ["Hardware decline"],
    "debate_transcript": [],
    "verdict": "Solid fundamentals, moderate risk.",
    "financial_data": {},
}

SENTIMENT_DATA = {
    "ticker": "AAPL",
    "filing_id": "abc123def456",
    "score": 0.72,
    "label": "Positive",
    "avg_positive": 0.65,
    "avg_negative": 0.08,
    "avg_neutral": 0.27,
    "chunk_count": 12,
    "top_sentences": [],
    "model": "ProsusAI/finbert",
    "source": "Item 7 — MD&A",
}

DIFF_DATA = {
    "ticker": "AAPL",
    "current_year": "2025",
    "prior_year": "2024",
    "item_1":  {"section": "Business Overview (Item 1)", "current_year": "2025", "prior_year": "2024", "summary": "", "new": [], "removed": [], "changed": [], "unchanged_count": 0},
    "item_1a": {"section": "Risk Factors (Item 1A)",     "current_year": "2025", "prior_year": "2024", "summary": "AI regulation added.", "new": ["AI risk"], "removed": [], "changed": [], "unchanged_count": 15},
    "item_7":  {"section": "MD&A (Item 7)",              "current_year": "2025", "prior_year": "2024", "summary": "", "new": [], "removed": [], "changed": [], "unchanged_count": 0},
}


# ── Health ────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.get_filing_count", return_value=3), \
             patch("qdrant_client.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value.get_collections.return_value = MagicMock(collections=[])
            resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── Report ────────────────────────────────────────────────────────────

class TestReport:
    def test_404_when_not_ingested(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False):
            resp = client.get("/api/companies/AAPL/report")
        assert resp.status_code == 404

    def test_returns_report_when_ingested(self, client, mock_redis, filing_record):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=filing_record), \
             patch("api.routes.get_filing_by_ticker", return_value={"chunks": []}), \
             patch("api.routes.get_or_generate_report", new=AsyncMock(return_value=REPORT_DATA)):
            resp = client.get("/api/companies/AAPL/report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "AAPL"
        assert body["verdict"] == REPORT_DATA["verdict"]
        assert body["risk_score"] == 0.34

    def test_refresh_param_passed_through(self, client, mock_redis, filing_record):
        mock_generate = AsyncMock(return_value=REPORT_DATA)
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=filing_record), \
             patch("api.routes.get_filing_by_ticker", return_value={"chunks": []}), \
             patch("api.routes.get_or_generate_report", mock_generate):
            client.get("/api/companies/AAPL/report?refresh=true")
        mock_generate.assert_called_once()
        _, kwargs = mock_generate.call_args
        assert kwargs.get("refresh") is True

    def test_502_on_service_error(self, client, mock_redis, filing_record):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=filing_record), \
             patch("api.routes.get_filing_by_ticker", return_value={"chunks": []}), \
             patch("api.routes.get_or_generate_report", new=AsyncMock(side_effect=RuntimeError("LLM down"))):
            resp = client.get("/api/companies/AAPL/report")
        assert resp.status_code == 502


# ── Chat ─────────────────────────────────────────────────────────────

class TestChat:
    def test_local_mode_passes_through_to_llm(self, client, mock_redis):
        mock_llm = AsyncMock(return_value={
            "answer": "Local answer",
            "model_used": "qwen3.5:0.8b",
            "llm_mode": "local",
            "tokens_in": 12,
            "tokens_out": 34,
            "cost_usd": 0.0,
            "latency_ms": 42.0,
        })
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.graph_exists", return_value=False), \
             patch("api.routes.list_events", return_value=[]), \
             patch("api.routes.rag_retrieve", return_value=[{"chunk_index": 0, "text": "ctx"}]), \
             patch("api.routes.ask_llm", mock_llm):
            resp = client.post("/api/chat", json={
                "question": "What are the risks?",
                "ticker": "AAPL",
                "filing_id": "abc123def456",
                "llm_mode": "local",
                "model": "qwen3.5:0.8b",
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_mode"] == "local"
        assert body["model_used"] == "qwen3.5:0.8b"
        _, kwargs = mock_llm.call_args
        assert kwargs["llm_mode"] == "local"
        assert kwargs["model"] == "qwen3.5:0.8b"


# ── Sentiment ─────────────────────────────────────────────────────────

class TestSentiment:
    def test_404_when_not_ingested(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False):
            resp = client.get("/api/companies/AAPL/sentiment")
        assert resp.status_code == 404

    def test_returns_sentiment_result(self, client, mock_redis, filing_record):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=filing_record), \
             patch("api.routes.get_or_score_sentiment", new=AsyncMock(return_value=SENTIMENT_DATA)):
            resp = client.get("/api/companies/AAPL/sentiment")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "AAPL"
        assert body["score"] == 0.72
        assert body["label"] == "Positive"
        assert body["model"] == "ProsusAI/finbert"

    def test_chunk_count_in_response(self, client, mock_redis, filing_record):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=filing_record), \
             patch("api.routes.get_or_score_sentiment", new=AsyncMock(return_value=SENTIMENT_DATA)):
            resp = client.get("/api/companies/AAPL/sentiment")
        assert resp.json()["chunk_count"] == 12

    def test_502_on_service_error(self, client, mock_redis, filing_record):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=filing_record), \
             patch("api.routes.get_or_score_sentiment", new=AsyncMock(side_effect=RuntimeError("model unavailable"))):
            resp = client.get("/api/companies/AAPL/sentiment")
        assert resp.status_code == 502

    def test_ticker_uppercased(self, client, mock_redis, filing_record):
        mock_score = AsyncMock(return_value=SENTIMENT_DATA)
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=filing_record), \
             patch("api.routes.get_or_score_sentiment", mock_score):
            client.get("/api/companies/aapl/sentiment")
        args, _ = mock_score.call_args
        assert args[1] == "AAPL"


# ── YoY Diff ──────────────────────────────────────────────────────────

class TestDiff:
    def test_404_when_not_ingested(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False):
            resp = client.get("/api/companies/AAPL/diff")
        assert resp.status_code == 404

    def test_returns_diff_structure(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_or_compute_diff", new=AsyncMock(return_value=DIFF_DATA)):
            resp = client.get("/api/companies/AAPL/diff")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "AAPL"
        assert body["current_year"] == "2025"
        assert body["prior_year"] == "2024"
        assert body["item_1a"]["summary"] == "AI regulation added."
        assert body["item_1a"]["new"] == ["AI risk"]

    def test_404_when_no_prior_year(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_or_compute_diff", new=AsyncMock(side_effect=ValueError("No prior year 10-K available"))):
            resp = client.get("/api/companies/AAPL/diff")
        assert resp.status_code == 404

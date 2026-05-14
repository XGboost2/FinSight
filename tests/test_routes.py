"""Backend endpoint tests — all external dependencies mocked."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import (
    CHUNKS, COMPANY_INFO, COMPARISON_RESULT, DASHBOARD, DASHBOARD2,
    EDGAR_RESULT, FILING_ID, FILING_ID2, FILING_RECORD, LLM_RESULT,
    STORED_FILING, TICKER, TICKER2,
)


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_redis_up_qdrant_down(self, client, mock_redis):
        """Qdrant connection refused → qdrant_ok=False, redis_ok=True."""
        mock_qc = MagicMock()
        mock_qc.get_collections.side_effect = ConnectionRefusedError
        with patch("api.routes.get_filing_count", return_value=3), \
             patch("rag.retriever._client", return_value=mock_qc):
            r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["redis_ok"] is True
        assert body["qdrant_ok"] is False
        assert body["filings_loaded"] == 3

    def test_both_up(self, client, mock_redis):
        mock_qc = MagicMock()
        mock_qc.get_collections.return_value = MagicMock()
        with patch("api.routes.get_filing_count", return_value=1), \
             patch("rag.retriever._client", return_value=mock_qc):
            r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["qdrant_ok"] is True

    def test_redis_down(self, client, mock_redis):
        mock_redis.ping.side_effect = Exception("Redis unreachable")
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.get_filing_count", return_value=0), \
             patch("qdrant_client.QdrantClient") as mock_qc:
            mock_qc.return_value.get_collections.side_effect = Exception
            r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["redis_ok"] is False


# ── Company Search ────────────────────────────────────────────────────────────

class TestCompanySearch:
    def test_returns_results(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.search_tickers", return_value=[COMPANY_INFO]):
            r = client.get("/api/companies/search?q=apple")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["results"][0]["ticker"] == TICKER

    def test_empty_results(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.search_tickers", return_value=[]):
            r = client.get("/api/companies/search?q=zzz")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_missing_query_param(self, client):
        r = client.get("/api/companies/search")
        assert r.status_code == 422


# ── Company Info ──────────────────────────────────────────────────────────────

class TestCompanyInfo:
    def test_found(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.get_ticker_info", return_value=COMPANY_INFO):
            r = client.get(f"/api/companies/{TICKER}/info")
        assert r.status_code == 200
        assert r.json()["ticker"] == TICKER

    def test_not_found(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.get_ticker_info", return_value=None):
            r = client.get("/api/companies/FAKE/info")
        assert r.status_code == 404


# ── Ingest ────────────────────────────────────────────────────────────────────

class TestIngest:
    def test_already_ingested_returns_cached(self, client, mock_redis):
        """All filing types present → returns already_existed=True immediately."""
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.get_filing_record", return_value=FILING_RECORD):
            r = client.post(f"/api/companies/{TICKER}/ingest")
        assert r.status_code == 200
        body = r.json()
        assert body["already_existed"] is True
        assert body["task_id"] is None
        assert body["filing_id"] == FILING_RECORD["filing_id"]

    def test_new_filing_queues_celery_task(self, client, mock_redis):
        """10-K missing → queues Celery task → returns task_id, already_existed=False."""
        mock_task = MagicMock()
        mock_task.id = "test-task-id"
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False), \
             patch("api.routes.get_filing_record", return_value=None), \
             patch("api.routes.get_filing_by_ticker", return_value=None), \
             patch("tasks.edgar_tasks.ingest_company_filings.delay", return_value=mock_task):
            r = client.post(f"/api/companies/{TICKER}/ingest")
        assert r.status_code == 200
        body = r.json()
        assert body["already_existed"] is False
        assert body["task_id"] is not None

    def test_ticker_uppercased(self, client, mock_redis):
        """Lowercase ticker → uppercased in response."""
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.get_filing_record", return_value=FILING_RECORD):
            r = client.post("/api/companies/aapl/ingest")
        assert r.status_code == 200
        assert r.json()["ticker"] == "AAPL"


# ── Ingest Status ─────────────────────────────────────────────────────────────

VALID_TASK_ID = "abcdef12-3456-7890-abcd-ef1234567890"  # valid hex UUID format


class TestIngestStatus:
    def test_pending_status(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("celery_app.celery_app.AsyncResult") as mock_ar:
            mock_ar.return_value.state = "PENDING"
            mock_ar.return_value.info  = None
            r = client.get(f"/api/companies/{TICKER}/ingest/status?task_id={VALID_TASK_ID}")
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

    def test_success_status(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("celery_app.celery_app.AsyncResult") as mock_ar:
            mock_ar.return_value.state  = "SUCCESS"
            mock_ar.return_value.result = {"chunks": 100}
            r = client.get(f"/api/companies/{TICKER}/ingest/status?task_id={VALID_TASK_ID}")
        assert r.status_code == 200
        assert r.json()["status"] == "done"

    def test_invalid_task_id_rejected(self, client):
        r = client.get(f"/api/companies/{TICKER}/ingest/status?task_id=../../etc/passwd")
        assert r.status_code == 400


# ── Dashboard ─────────────────────────────────────────────────────────────────

class TestDashboard:
    def test_returns_metrics(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=FILING_RECORD), \
             patch("api.routes.get_filing_by_ticker", return_value=STORED_FILING), \
             patch("api.routes.get_or_extract_dashboard", new_callable=AsyncMock, return_value=DASHBOARD):
            r = client.get(f"/api/companies/{TICKER}/dashboard")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == TICKER
        assert body["revenue_latest_year"] == "$394.3B"
        assert len(body["top_3_risk_factors"]) == 3

    def test_not_ingested_returns_404(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False):
            r = client.get(f"/api/companies/{TICKER}/dashboard")
        assert r.status_code == 404


# ── Compare ───────────────────────────────────────────────────────────────────

class TestCompare:
    def _base_patches(self, mock_redis):
        return [
            patch("api.routes.get_redis", return_value=mock_redis),
            patch("api.routes.is_ingested", return_value=True),
            patch("api.routes.get_ticker_info", return_value=COMPANY_INFO),
            patch("api.routes.get_filing_record", side_effect=[
                {**FILING_RECORD, "filing_id": FILING_ID},
                {**FILING_RECORD, "filing_id": FILING_ID2},
            ]),
            patch("api.routes.get_filing_by_ticker", return_value=STORED_FILING),
            patch("api.routes.get_or_extract_dashboard", new_callable=AsyncMock,
                  side_effect=[DASHBOARD, DASHBOARD2]),
            patch("api.routes.get_or_generate_comparison", new_callable=AsyncMock,
                  return_value=COMPARISON_RESULT),
        ]

    def test_successful_comparison(self, client, mock_redis):
        patches = self._base_patches(mock_redis)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            r = client.post("/api/companies/compare", json={"tickers": [TICKER, TICKER2]})
        assert r.status_code == 200
        body = r.json()
        assert body["ticker1"] == TICKER
        assert body["ticker2"] == TICKER2
        assert "analysis" in body

    def test_wrong_ticker_count(self, client):
        r = client.post("/api/companies/compare", json={"tickers": ["AAPL"]})
        assert r.status_code in (400, 422)

    def test_requires_exactly_two_tickers(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis):
            r = client.post("/api/companies/compare", json={"tickers": ["AAPL", "MSFT", "GOOG"]})
        assert r.status_code == 422


# ── Chat ──────────────────────────────────────────────────────────────────────

class TestChat:
    def test_returns_answer(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=FILING_RECORD), \
             patch("api.routes.rag_retrieve", return_value=CHUNKS), \
             patch("api.routes.ask_llm", new_callable=AsyncMock, return_value=LLM_RESULT):
            r = client.post("/api/chat", json={"ticker": TICKER, "question": "What are the risks?"})
        assert r.status_code == 200
        body = r.json()
        assert body["answer"] == LLM_RESULT["answer"]
        assert body["model_used"] == "claude-haiku-4-5"
        assert body["cost_usd"] == LLM_RESULT["cost_usd"]

    def test_filing_not_found_returns_404(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False):
            r = client.post("/api/chat", json={"ticker": "FAKE", "question": "test"})
        assert r.status_code == 404

    def test_llm_failure_returns_502(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=FILING_RECORD), \
             patch("api.routes.rag_retrieve", return_value=CHUNKS), \
             patch("api.routes.ask_llm", new_callable=AsyncMock, side_effect=RuntimeError("LLM down")):
            r = client.post("/api/chat", json={"ticker": TICKER, "question": "test"})
        assert r.status_code == 502

    def test_falls_back_gracefully_when_rag_empty(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=FILING_RECORD), \
             patch("api.routes.rag_retrieve", return_value=[]), \
             patch("api.routes.ask_llm", new_callable=AsyncMock, return_value=LLM_RESULT):
            r = client.post("/api/chat", json={"ticker": TICKER, "question": "test"})
        assert r.status_code == 200


# ── Admin ─────────────────────────────────────────────────────────────────────

class TestAdmin:
    def test_refresh_tickers(self, client, mock_redis):
        admin_key = "test-admin-key"
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.load_tickers_into_redis", new_callable=AsyncMock, return_value=13000), \
             patch.dict("os.environ", {"FINSIGHT_ADMIN_KEY": admin_key}):
            r = client.post("/api/admin/refresh-tickers", headers={"X-Admin-Key": admin_key})
        assert r.status_code == 200
        body = r.json()
        assert body["loaded"] == 13000

    def test_admin_requires_key(self, client):
        r = client.post("/api/admin/refresh-tickers")
        assert r.status_code == 403

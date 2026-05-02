"""Backend endpoint tests — all external dependencies mocked."""

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
        with patch("api.routes.get_filing_count", return_value=3), \
             patch("qdrant_client.QdrantClient") as mock_qc:
            mock_qc.return_value.get_collections.side_effect = ConnectionRefusedError
            r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["redis_ok"] is True
        assert body["qdrant_ok"] is False
        assert body["filings_loaded"] == 3

    def test_both_up(self, client, mock_redis):
        with patch("api.routes.get_filing_count", return_value=1), \
             patch("qdrant_client.QdrantClient") as mock_qc:
            mock_qc.return_value.get_collections.return_value = MagicMock()
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
    def test_new_filing(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False), \
             patch("api.routes.fetch_and_extract", new_callable=AsyncMock, return_value=EDGAR_RESULT), \
             patch("api.routes.chunk_text", return_value=CHUNKS), \
             patch("api.routes.store_filing"), \
             patch("api.routes.rag_ingest"), \
             patch("api.routes.register_filing"), \
             patch("api.routes.get_or_extract_dashboard", new_callable=AsyncMock, return_value=DASHBOARD):
            r = client.post(f"/api/companies/{TICKER}/ingest")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == TICKER
        assert body["filing_id"] == FILING_ID
        assert body["chunk_count"] == len(CHUNKS)
        assert body["already_existed"] is False

    def test_idempotent_already_exists(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=True), \
             patch("api.routes.get_filing_record", return_value=FILING_RECORD), \
             patch("api.routes.get_filing_by_ticker", return_value=STORED_FILING):
            r = client.post(f"/api/companies/{TICKER}/ingest")
        assert r.status_code == 200
        assert r.json()["already_existed"] is True

    def test_edgar_not_found(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False), \
             patch("api.routes.fetch_and_extract", new_callable=AsyncMock, return_value=None):
            r = client.post("/api/companies/FAKE/ingest")
        assert r.status_code == 404

    def test_chunking_fails(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False), \
             patch("api.routes.fetch_and_extract", new_callable=AsyncMock, return_value=EDGAR_RESULT), \
             patch("api.routes.chunk_text", return_value=[]):
            r = client.post(f"/api/companies/{TICKER}/ingest")
        assert r.status_code == 422

    def test_unexpected_error_returns_502(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.is_ingested", return_value=False), \
             patch("api.routes.fetch_and_extract", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            r = client.post(f"/api/companies/{TICKER}/ingest")
        assert r.status_code == 502


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
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
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
        with patch("api.routes.get_filing_by_ticker", return_value=STORED_FILING), \
             patch("api.routes.rag_retrieve", return_value=CHUNKS), \
             patch("api.routes.ask_llm", new_callable=AsyncMock, return_value=LLM_RESULT):
            r = client.post("/api/chat", json={"ticker": TICKER, "question": "What are the risks?"})
        assert r.status_code == 200
        body = r.json()
        assert body["answer"] == LLM_RESULT["answer"]
        assert body["model_used"] == "claude-haiku-4-5"
        assert len(body["sources"]) == len(CHUNKS)
        assert body["cost_usd"] == LLM_RESULT["cost_usd"]

    def test_filing_not_found_returns_404(self, client):
        with patch("api.routes.get_filing_by_ticker", return_value=None):
            r = client.post("/api/chat", json={"ticker": "FAKE", "question": "test"})
        assert r.status_code == 404

    def test_llm_failure_returns_502(self, client):
        with patch("api.routes.get_filing_by_ticker", return_value=STORED_FILING), \
             patch("api.routes.rag_retrieve", return_value=CHUNKS), \
             patch("api.routes.ask_llm", new_callable=AsyncMock, side_effect=RuntimeError("LLM down")):
            r = client.post("/api/chat", json={"ticker": TICKER, "question": "test"})
        assert r.status_code == 502

    def test_falls_back_to_store_chunks_when_rag_empty(self, client):
        with patch("api.routes.get_filing_by_ticker", return_value=STORED_FILING), \
             patch("api.routes.rag_retrieve", return_value=[]), \
             patch("api.routes.ask_llm", new_callable=AsyncMock, return_value=LLM_RESULT):
            r = client.post("/api/chat", json={"ticker": TICKER, "question": "test"})
        assert r.status_code == 200


# ── Legacy Filing Endpoints ───────────────────────────────────────────────────

class TestFilings:
    def test_list_filings(self, client):
        mock_filing = {
            "id": FILING_ID, "ticker": TICKER, "company_name": "Apple Inc.",
            "filing_type": "10-K", "filed_date": "2023-11-03", "chunk_count": 2,
        }
        with patch("api.routes.list_filings", return_value=[mock_filing]), \
             patch("api.routes.get_filing_count", return_value=1):
            r = client.get("/api/filings")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["filings"][0]["ticker"] == TICKER

    def test_get_filing_detail_found(self, client):
        with patch("api.routes.get_filing", return_value=STORED_FILING):
            r = client.get(f"/api/filings/{FILING_ID}")
        assert r.status_code == 200
        assert r.json()["filing"]["ticker"] == TICKER

    def test_get_filing_detail_not_found(self, client):
        with patch("api.routes.get_filing", return_value=None):
            r = client.get("/api/filings/nonexistent-id")
        assert r.status_code == 404

    def test_fetch_filing_success(self, client):
        with patch("api.routes.fetch_and_extract", new_callable=AsyncMock, return_value=EDGAR_RESULT), \
             patch("api.routes.chunk_text", return_value=CHUNKS), \
             patch("api.routes.store_filing"), \
             patch("api.routes.rag_ingest"):
            r = client.post("/api/filings/fetch", json={"ticker": TICKER, "filing_type": "10-K"})
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_fetch_filing_not_found(self, client):
        with patch("api.routes.fetch_and_extract", new_callable=AsyncMock, return_value=None):
            r = client.post("/api/filings/fetch", json={"ticker": "FAKE", "filing_type": "10-K"})
        assert r.status_code == 404

    def test_fetch_filing_edgar_error(self, client):
        with patch("api.routes.fetch_and_extract", new_callable=AsyncMock,
                   side_effect=RuntimeError("EDGAR down")):
            r = client.post("/api/filings/fetch", json={"ticker": TICKER, "filing_type": "10-K"})
        assert r.status_code == 502


# ── Admin ─────────────────────────────────────────────────────────────────────

class TestAdmin:
    def test_refresh_tickers(self, client, mock_redis):
        with patch("api.routes.get_redis", return_value=mock_redis), \
             patch("api.routes.load_tickers_into_redis", new_callable=AsyncMock, return_value=13000):
            r = client.post("/api/admin/refresh-tickers")
        assert r.status_code == 200
        body = r.json()
        assert body["loaded"] == 13000

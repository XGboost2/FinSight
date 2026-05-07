"""Unit tests for services/sentiment.py — FinBERT scoring logic."""

import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ── _score_chunks ─────────────────────────────────────────────────────

class TestScoreChunks:
    def _import(self):
        from services.sentiment import _score_chunks, _empty_result
        return _score_chunks, _empty_result

    def test_empty_chunks_returns_empty_result(self):
        _score_chunks, _empty_result = self._import()
        result = _score_chunks([])
        assert result["score"] == 0.5
        assert result["label"] == "Neutral"
        assert result["chunk_count"] == 0
        assert result["top_sentences"] == []

    def test_positive_majority_gives_positive_label(self):
        _score_chunks, _ = self._import()
        mock_output = [[
            {"label": "positive", "score": 0.90},
            {"label": "negative", "score": 0.05},
            {"label": "neutral",  "score": 0.05},
        ]]
        chunks = [{"text": "Revenue grew strongly.", "item": "7"}]
        with patch("services.sentiment._get_pipeline") as mock_pipe:
            mock_pipe.return_value = MagicMock(return_value=mock_output)
            result = _score_chunks(chunks)
        assert result["label"] == "Positive"
        assert result["score"] > 0.6
        assert result["chunk_count"] == 1

    def test_negative_majority_gives_negative_label(self):
        _score_chunks, _ = self._import()
        mock_output = [[
            {"label": "positive", "score": 0.05},
            {"label": "negative", "score": 0.90},
            {"label": "neutral",  "score": 0.05},
        ]]
        chunks = [{"text": "Significant losses reported.", "item": "7"}]
        with patch("services.sentiment._get_pipeline") as mock_pipe:
            mock_pipe.return_value = MagicMock(return_value=mock_output)
            result = _score_chunks(chunks)
        assert result["label"] == "Negative"
        assert result["score"] < 0.4

    def test_scalar_score_formula(self):
        _score_chunks, _ = self._import()
        # avg_pos=0.7, avg_neg=0.1 → score = (0.7 - 0.1 + 1) / 2 = 0.8
        mock_output = [[
            {"label": "positive", "score": 0.70},
            {"label": "negative", "score": 0.10},
            {"label": "neutral",  "score": 0.20},
        ]]
        chunks = [{"text": "Strong results.", "item": "7"}]
        with patch("services.sentiment._get_pipeline") as mock_pipe:
            mock_pipe.return_value = MagicMock(return_value=mock_output)
            result = _score_chunks(chunks)
        assert abs(result["score"] - 0.8) < 0.01

    def test_top_sentences_capped_at_five(self):
        _score_chunks, _ = self._import()
        mock_output = [
            [{"label": "positive", "score": 0.8}, {"label": "negative", "score": 0.1}, {"label": "neutral", "score": 0.1}]
        ] * 10
        chunks = [{"text": f"Sentence {i}.", "item": "7"} for i in range(10)]
        with patch("services.sentiment._get_pipeline") as mock_pipe:
            mock_pipe.return_value = MagicMock(return_value=mock_output)
            result = _score_chunks(chunks)
        assert len(result["top_sentences"]) <= 5

    def test_aggregates_across_multiple_chunks(self):
        _score_chunks, _ = self._import()
        mock_output = [
            [{"label": "positive", "score": 0.8}, {"label": "negative", "score": 0.1}, {"label": "neutral", "score": 0.1}],
            [{"label": "positive", "score": 0.2}, {"label": "negative", "score": 0.7}, {"label": "neutral", "score": 0.1}],
        ]
        chunks = [
            {"text": "Revenue grew strongly.", "item": "7"},
            {"text": "Costs increased significantly.", "item": "7"},
        ]
        with patch("services.sentiment._get_pipeline") as mock_pipe:
            mock_pipe.return_value = MagicMock(return_value=mock_output)
            result = _score_chunks(chunks)
        assert result["chunk_count"] == 2
        assert abs(result["avg_positive"] - 0.5) < 0.01
        assert abs(result["avg_negative"] - 0.4) < 0.01

    def test_result_contains_required_keys(self):
        _score_chunks, _ = self._import()
        mock_output = [[
            {"label": "positive", "score": 0.5},
            {"label": "negative", "score": 0.3},
            {"label": "neutral",  "score": 0.2},
        ]]
        chunks = [{"text": "Some financial text.", "item": "7"}]
        with patch("services.sentiment._get_pipeline") as mock_pipe:
            mock_pipe.return_value = MagicMock(return_value=mock_output)
            result = _score_chunks(chunks)
        for key in ("score", "label", "avg_positive", "avg_negative", "avg_neutral",
                    "chunk_count", "top_sentences", "model", "source"):
            assert key in result, f"Missing key: {key}"


# ── get_or_score_sentiment ────────────────────────────────────────────

class TestGetOrScoreSentiment:
    @pytest.mark.asyncio
    async def test_returns_cached_result(self):
        from services.sentiment import get_or_score_sentiment
        cached = {"ticker": "AAPL", "filing_id": "abc", "score": 0.7, "label": "Positive",
                  "avg_positive": 0.6, "avg_negative": 0.1, "avg_neutral": 0.3,
                  "chunk_count": 5, "top_sentences": [], "model": "ProsusAI/finbert",
                  "source": "Item 7 — MD&A"}
        redis = MagicMock()
        redis.get.return_value = json.dumps(cached)

        result = await get_or_score_sentiment(redis, "AAPL", "abc")
        assert result["score"] == 0.7
        redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_scores_and_caches_on_cache_miss(self):
        from services.sentiment import get_or_score_sentiment
        scored = {"score": 0.65, "label": "Positive", "avg_positive": 0.6,
                  "avg_negative": 0.1, "avg_neutral": 0.3, "chunk_count": 8,
                  "top_sentences": [], "model": "ProsusAI/finbert", "source": "Item 7 — MD&A"}
        redis = MagicMock()
        redis.get.return_value = None

        with patch("rag.retriever.get_section_chunks", return_value=[{"text": "t", "item": "7"}]), \
             patch("services.sentiment._score_chunks", return_value=scored):
            result = await get_or_score_sentiment(redis, "AAPL", "abc123")

        assert result["ticker"] == "AAPL"
        assert result["filing_id"] == "abc123"
        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_bypasses_cache(self):
        from services.sentiment import get_or_score_sentiment
        scored = {"score": 0.5, "label": "Neutral", "avg_positive": 0.3,
                  "avg_negative": 0.2, "avg_neutral": 0.5, "chunk_count": 3,
                  "top_sentences": [], "model": "ProsusAI/finbert", "source": "Item 7 — MD&A"}
        redis = MagicMock()
        redis.get.return_value = json.dumps({"score": 0.99})  # stale cache

        with patch("rag.retriever.get_section_chunks", return_value=[{"text": "t", "item": "7"}]), \
             patch("services.sentiment._score_chunks", return_value=scored):
            result = await get_or_score_sentiment(redis, "AAPL", "abc123", refresh=True)

        assert result["score"] == 0.5   # fresh score, not cached 0.99

    @pytest.mark.asyncio
    async def test_ticker_added_to_result(self):
        from services.sentiment import get_or_score_sentiment
        scored = {"score": 0.6, "label": "Positive", "avg_positive": 0.5,
                  "avg_negative": 0.1, "avg_neutral": 0.4, "chunk_count": 5,
                  "top_sentences": [], "model": "ProsusAI/finbert", "source": "Item 7 — MD&A"}
        redis = MagicMock()
        redis.get.return_value = None

        with patch("rag.retriever.get_section_chunks", return_value=[{"text": "t", "item": "7"}]), \
             patch("services.sentiment._score_chunks", return_value=scored):
            result = await get_or_score_sentiment(redis, "nvda", "xyz")

        assert result["ticker"] == "NVDA"
        assert result["filing_id"] == "xyz"

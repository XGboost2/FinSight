"""Shared fixtures for FinSight backend tests."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import router


@pytest.fixture
def app():
    """Minimal FastAPI app with routes only — no lifespan/startup."""
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.get.return_value = None
    r.setex.return_value = True
    r.hget.return_value = None
    r.hexists.return_value = False
    return r


@pytest.fixture
def filing_record():
    return {
        "filing_id": "abc123def456",
        "filing_type": "10-K",
        "filed_date": "2025-11-01",
        "chunk_count": 120,
        "ingested_at": "2025-11-01T12:00:00+00:00",
    }

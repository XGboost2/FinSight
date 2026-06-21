import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from cache.event_store import list_events
from cache.filing_registry import (
    get_filing_record,
    is_filing_ingested,
    list_ingested,
    register_filing,
)
from rag import retriever
from services.edgar_pipeline import _store_8k_event
from services import edgar_pipeline


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.values = {}

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hexists(self, key, field):
        return field in self.hashes.get(key, {})

    def hvals(self, key):
        return list(self.hashes.get(key, {}).values())

    def scan_iter(self, match):
        prefix = match.removesuffix("*")
        return iter(key for key in self.hashes if key.startswith(prefix))

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, _ttl, value):
        self.values[key] = value

    def expire(self, _key, _ttl):
        return True


def test_registry_tracks_each_accession_and_keeps_latest_record():
    redis = FakeRedis()
    register_filing(
        redis,
        "TSLA",
        "new-filing",
        {
            "accession_number": "0001-26-000002",
            "filed_date": "2026-01-29",
            "chunk_count": 35,
        },
        "10-K",
    )
    register_filing(
        redis,
        "TSLA",
        "old-filing",
        {
            "accession_number": "0001-25-000001",
            "filed_date": "2025-01-30",
            "chunk_count": 34,
        },
        "10-K",
    )

    assert is_filing_ingested(redis, "TSLA", "10-K", "0001-26-000002")
    assert is_filing_ingested(redis, "TSLA", "10-K", "0001-25-000001")
    assert get_filing_record(redis, "TSLA", "10-K")["filing_id"] == "new-filing"
    assert {record["filing_id"] for record in list_ingested(redis, "10-K")} == {
        "new-filing",
        "old-filing",
    }


def test_8k_event_is_replaced_by_accession_instead_of_appended():
    redis = FakeRedis()
    _store_8k_event(
        redis,
        "TSLA",
        "0001-26-000010",
        "2026-04-22",
        "earnings",
        "Tesla reported quarterly earnings. Results improved.",
    )
    _store_8k_event(
        redis,
        "TSLA",
        "0001-26-000010",
        "2026-04-22",
        "guidance",
        "Tesla updated its forward guidance. The outlook changed.",
    )

    events = list_events(redis, "TSLA")
    assert len(events) == 1
    assert events[0]["accession_number"] == "0001-26-000010"
    assert events[0]["event_type"] == "guidance"


def test_qdrant_replacement_deletes_stale_chunk_points(monkeypatch):
    client = MagicMock()
    stale_id = retriever._point_id("filing-1", 2)
    client.scroll.return_value = (
        [
            SimpleNamespace(id=retriever._point_id("filing-1", 0)),
            SimpleNamespace(id=retriever._point_id("filing-1", 1)),
            SimpleNamespace(id=stale_id),
        ],
        None,
    )
    monkeypatch.setattr(retriever, "_client", lambda: client)

    chunks = [
        {"chunk_index": 0, "text": "first"},
        {"chunk_index": 1, "text": "second"},
    ]
    retriever.upsert_chunks(
        "filing-1",
        chunks,
        [[0.1], [0.2]],
        [([1], [1.0]), ([2], [1.0])],
    )

    client.upsert.assert_called_once()
    selector = client.delete.call_args.kwargs["points_selector"]
    assert selector.points == [stale_id]


async def test_force_reingests_exact_accession_with_stable_filing_id(monkeypatch):
    redis = FakeRedis()
    accession = "0001628280-26-003952"
    meta = {
        "accession_number": accession,
        "filing_date": "2026-01-29",
        "document_url": "https://example.test/filing",
        "items": "",
    }
    registered = []

    monkeypatch.setattr(edgar_pipeline, "get_redis", lambda: redis)
    monkeypatch.setattr(
        edgar_pipeline,
        "resolve_ticker_to_cik",
        AsyncMock(return_value={"cik": "0001318605", "company_name": "Tesla, Inc."}),
    )
    monkeypatch.setattr(
        edgar_pipeline,
        "fetch_filing_urls",
        AsyncMock(return_value=[meta]),
    )
    monkeypatch.setattr(
        edgar_pipeline,
        "download_filing_text",
        AsyncMock(return_value="Item 1. Business\n\nTesla makes vehicles."),
    )
    monkeypatch.setattr(
        edgar_pipeline,
        "chunk_text",
        lambda *_args, **_kwargs: [{"chunk_index": 0, "text": "Tesla makes vehicles."}],
    )
    monkeypatch.setattr(edgar_pipeline, "store_filing", lambda *_args: None)
    monkeypatch.setattr(edgar_pipeline, "rag_ingest", lambda *_args: 1)
    monkeypatch.setattr(edgar_pipeline, "delete_filing_chunks", lambda *_args: None)
    monkeypatch.setattr(edgar_pipeline, "delete_filing", lambda *_args: None)
    monkeypatch.setattr(
        edgar_pipeline,
        "register_filing",
        lambda _redis, ticker, filing_id, metadata, filing_type: registered.append(
            (ticker, filing_id, metadata, filing_type)
        ),
    )
    monkeypatch.setattr(edgar_pipeline, "is_filing_ingested", lambda *_args: True)

    skipped = await edgar_pipeline.run_edgar_pipeline("TSLA", ["10-K"])
    forced = await edgar_pipeline.run_edgar_pipeline("TSLA", ["10-K"], force=True)

    expected_id = hashlib.sha256(f"TSLA_10-K_{accession}".encode()).hexdigest()[:12]
    assert skipped["ten_k_ingested"] == 0
    assert forced["ten_k_ingested"] == 1
    assert registered == [
        (
            "TSLA",
            expected_id,
            {
                "accession_number": accession,
                "filed_date": "2026-01-29",
                "chunk_count": 1,
            },
            "10-K",
        )
    ]

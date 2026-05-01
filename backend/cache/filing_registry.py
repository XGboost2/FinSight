import json
from datetime import datetime, timezone

REGISTRY_KEY = "finsight:filings"


def is_ingested(redis_client, ticker: str) -> bool:
    """O(1) Redis check — gate for the embedding pipeline."""
    return bool(redis_client.hexists(REGISTRY_KEY, ticker.upper()))


def get_filing_record(redis_client, ticker: str) -> dict | None:
    raw = redis_client.hget(REGISTRY_KEY, ticker.upper())
    return json.loads(raw) if raw else None


def register_filing(redis_client, ticker: str, filing_id: str, meta: dict) -> None:
    """Write to registry after successful Qdrant upsert."""
    record = json.dumps({
        "filing_id": filing_id,
        "filed_date": meta.get("filed_date", ""),
        "chunk_count": meta.get("chunk_count", 0),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    })
    redis_client.hset(REGISTRY_KEY, ticker.upper(), record)


def list_ingested(redis_client) -> list[dict]:
    return [json.loads(v) for v in redis_client.hvals(REGISTRY_KEY)]

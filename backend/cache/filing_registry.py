import json
from datetime import datetime, timezone

REGISTRY_BASE = "finsight:registry"


def _key(filing_type: str) -> str:
    return f"{REGISTRY_BASE}:{filing_type.upper()}"


def is_ingested(redis_client, ticker: str, filing_type: str = "10-K") -> bool:
    """O(1) Redis check — gate for the embedding pipeline."""
    return bool(redis_client.hexists(_key(filing_type), ticker.upper()))


def get_filing_record(redis_client, ticker: str, filing_type: str = "10-K") -> dict | None:
    raw = redis_client.hget(_key(filing_type), ticker.upper())
    return json.loads(raw) if raw else None


def register_filing(
    redis_client,
    ticker: str,
    filing_id: str,
    meta: dict,
    filing_type: str = "10-K",
) -> None:
    """Write to registry after successful Qdrant upsert."""
    record = json.dumps({
        "filing_id": filing_id,
        "filing_type": filing_type.upper(),
        "filed_date": meta.get("filed_date", ""),
        "chunk_count": meta.get("chunk_count", 0),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    })
    redis_client.hset(_key(filing_type), ticker.upper(), record)


def list_ingested(redis_client, filing_type: str = "10-K") -> list[dict]:
    return [json.loads(v) for v in redis_client.hvals(_key(filing_type))]


def list_all_ingested(redis_client) -> list[dict]:
    """List ingested filings across all filing types."""
    results = []
    for ft in ("10-K", "10-Q", "8-K"):
        results.extend(list_ingested(redis_client, ft))
    return results

import json
from datetime import datetime, timezone

REGISTRY_BASE = "finsight:registry"
FILING_HISTORY_BASE = "finsight:filings"


def _key(filing_type: str) -> str:
    return f"{REGISTRY_BASE}:{filing_type.upper()}"


def _history_key(ticker: str, filing_type: str) -> str:
    return f"{FILING_HISTORY_BASE}:{filing_type.upper()}:{ticker.upper()}"


def is_ingested(redis_client, ticker: str, filing_type: str = "10-K") -> bool:
    """O(1) Redis check — gate for the embedding pipeline."""
    return bool(redis_client.hexists(_key(filing_type), ticker.upper()))


def is_filing_ingested(
    redis_client,
    ticker: str,
    filing_type: str,
    accession_number: str,
) -> bool:
    """Return whether one exact SEC filing accession has been ingested."""
    accession_number = accession_number.strip()
    if not accession_number:
        return False
    if redis_client.hexists(_history_key(ticker, filing_type), accession_number):
        return True

    # Backward compatibility for records created before filing history existed.
    latest = get_filing_record(redis_client, ticker, filing_type)
    return bool(latest and latest.get("accession_number") == accession_number)


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
    record = {
        "filing_id": filing_id,
        "ticker": ticker.upper(),
        "filing_type": filing_type.upper(),
        "accession_number": meta.get("accession_number", ""),
        "filed_date": meta.get("filed_date", ""),
        "chunk_count": meta.get("chunk_count", 0),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    for key, value in meta.items():
        record.setdefault(key, value)
    encoded = json.dumps(record)
    identity = record["accession_number"] or filing_id
    redis_client.hset(_history_key(ticker, filing_type), identity, encoded)

    current = get_filing_record(redis_client, ticker, filing_type)
    if not current or record["filed_date"] >= current.get("filed_date", ""):
        redis_client.hset(_key(filing_type), ticker.upper(), encoded)


def list_ingested(redis_client, filing_type: str = "10-K") -> list[dict]:
    """List every known filing, with legacy latest-only records as fallback."""
    records: dict[str, dict] = {}
    pattern = f"{FILING_HISTORY_BASE}:{filing_type.upper()}:*"
    for key in redis_client.scan_iter(match=pattern):
        for raw in redis_client.hvals(key):
            record = json.loads(raw)
            records[record["filing_id"]] = record

    for raw in redis_client.hvals(_key(filing_type)):
        record = json.loads(raw)
        records.setdefault(record["filing_id"], record)
    return list(records.values())


def list_all_ingested(redis_client) -> list[dict]:
    """List ingested filings across all filing types."""
    results = []
    for ft in ("10-K", "10-Q", "8-K"):
        results.extend(list_ingested(redis_client, ft))
    return results

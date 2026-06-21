import json


EVENT_TTL_SECONDS = 60 * 60 * 24 * 30


def _hash_key(ticker: str) -> str:
    return f"finsight:events:8-K:by-accession:{ticker.upper()}"


def _legacy_key(ticker: str) -> str:
    return f"finsight:events:8-K:{ticker.upper()}"


def _fingerprint(event: dict) -> tuple[str, str, str]:
    return (
        event.get("date", ""),
        event.get("event_type", ""),
        event.get("summary", ""),
    )


def store_event(redis_client, ticker: str, event: dict) -> None:
    """Atomically insert or replace one event by SEC accession number."""
    accession_number = event["accession_number"]
    key = _hash_key(ticker)
    redis_client.hset(key, accession_number, json.dumps(event))
    redis_client.expire(key, EVENT_TTL_SECONDS)


def list_events(redis_client, ticker: str) -> list[dict]:
    """Read accession-keyed events and merge legacy JSON-list data once."""
    events: dict[str, dict] = {}
    fingerprints: set[tuple[str, str, str]] = set()
    for raw in redis_client.hvals(_hash_key(ticker)):
        event = json.loads(raw)
        identity = event["accession_number"]
        events[identity] = event
        fingerprints.add(_fingerprint(event))

    legacy_raw = redis_client.get(_legacy_key(ticker))
    for index, event in enumerate(json.loads(legacy_raw) if legacy_raw else []):
        fingerprint = _fingerprint(event)
        if fingerprint in fingerprints:
            continue
        identity = event.get("accession_number") or f"legacy:{index}"
        events.setdefault(identity, event)
        fingerprints.add(fingerprint)

    return sorted(
        events.values(),
        key=lambda event: event.get("date", ""),
        reverse=True,
    )

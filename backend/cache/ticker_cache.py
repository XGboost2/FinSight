import json
import httpx
from config import get_settings

TICKERS_KEY = "finsight:tickers"
SEC_URL = "https://www.sec.gov/files/company_tickers.json"


async def load_tickers_into_redis(redis_client) -> int:
    """One SEC API call. Loads all ~13k companies into Redis hash. Returns count."""
    headers = {"User-Agent": get_settings().SEC_EDGAR_USER_AGENT}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(SEC_URL, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    pipe = redis_client.pipeline()
    for entry in data.values():
        ticker = entry["ticker"].upper()
        record = json.dumps({
            "name": entry["title"],
            "ticker": ticker,
            "cik": str(entry["cik_str"]).zfill(10),
        })
        pipe.hset(TICKERS_KEY, ticker, record)
    pipe.execute()
    return len(data)


def search_tickers(redis_client, query: str, limit: int = 8) -> list[dict]:
    """Pure Redis search — zero API calls. HGETALL + Python filter."""
    query = query.upper().strip()
    if not query:
        return []

    all_entries = redis_client.hgetall(TICKERS_KEY)
    ticker_matches: list[dict] = []
    name_matches: list[dict] = []

    for ticker_key, json_str in all_entries.items():
        record = json.loads(json_str)
        if ticker_key.startswith(query):
            ticker_matches.append(record)
        elif query in record["name"].upper():
            name_matches.append(record)

    return (ticker_matches + name_matches)[:limit]


def get_ticker_info(redis_client, ticker: str) -> dict | None:
    """O(1) Redis hash lookup. Returns {name, ticker, cik} or None."""
    raw = redis_client.hget(TICKERS_KEY, ticker.upper())
    return json.loads(raw) if raw else None

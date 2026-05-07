"""Deterministic EDGAR ingestion pipeline — no LLM, zero token cost.

Each step is a direct function call.
8-K classification uses EDGAR item numbers (free, more reliable than LLM).
"""

import hashlib
import json
import logging

from cache.filing_registry import is_ingested, register_filing
from cache.redis_client import get_redis
from ingestion.chunker import chunk_text
from ingestion.edgar import (
    download_filing_text,
    fetch_filing_urls,
    resolve_ticker_to_cik,
)
from rag.pipeline import ingest as rag_ingest
from services.store import store_filing

logger = logging.getLogger(__name__)

# How many of each filing type to fetch
_FILING_COUNTS = {"10-K": 2, "10-Q": 4, "8-K": 10}

# EDGAR item number → event type (no LLM needed)
_ITEM_MAP = {
    "2.02": "earnings",
    "5.02": "leadership",
    "1.01": "acquisition",
    "2.01": "acquisition",
    "7.01": "guidance",
    "8.01": "guidance",
    "1.03": "legal",
    "3.01": "legal",
    "4.01": "legal",
    "2.05": "legal",
    "2.06": "legal",
}

_KEYWORD_MAP = {
    "earnings":    ["earnings", "revenue", "quarter", "fiscal year", "eps"],
    "acquisition": ["acqui", "merger", "transaction", "purchase"],
    "legal":       ["lawsuit", "litigation", "settlement", "investigation", "subpoena"],
    "leadership":  ["ceo", "cfo", "president", "director", "appoint", "resign", "retire"],
    "guidance":    ["guidance", "outlook", "forecast", "preliminary"],
}


def _classify_8k(items_str: str, text: str) -> str:
    """Classify 8-K event type using EDGAR item numbers, with keyword fallback."""
    items = {i.strip() for i in items_str.split(",") if i.strip()}
    for item, event_type in _ITEM_MAP.items():
        if item in items:
            return event_type

    # Keyword fallback on first 2000 chars
    snippet = text[:2000].lower()
    for event_type, keywords in _KEYWORD_MAP.items():
        if any(kw in snippet for kw in keywords):
            return event_type

    return "other"


def _extract_readable_summary(text: str, event_type: str) -> str:
    """Extract first readable sentence from 8-K text, skipping XBRL header junk."""
    import re

    xbrl_patterns = re.compile(r'(0{6,}|aapl:|us-gaap:|true|false|NASDAQ)', re.I)
    # SEC form field labels — these are headers/labels, not prose
    form_header = re.compile(
        r'^(item\s+\d|date of|registrant|commission|pursuant|incorporated|exchange act'
        r'|securities act|check the|indicate by|yes\s*[\[|]|no\s*[\[|]|former name'
        r'|address|telephone|zip code|state or other|exact name|filed as)',
        re.I,
    )

    for line in text.split('\n'):
        line = line.strip()
        if len(line) < 50:
            continue
        # Form field labels always end with colon
        if line.endswith(':'):
            continue
        if form_header.search(line):
            continue
        alpha_ratio = sum(c.isalpha() or c.isspace() for c in line) / len(line)
        if alpha_ratio < 0.65:
            continue
        if xbrl_patterns.search(line):
            continue
        # Must read like prose — requires at least one sentence-ending punctuation
        if not re.search(r'[.!?]', line):
            continue
        clean = re.sub(r'\s+', ' ', line).strip()
        return clean[:250]

    fallbacks = {
        "earnings":    "Quarterly earnings results and financial performance disclosed.",
        "leadership":  "Executive leadership or board of directors change disclosed.",
        "acquisition": "Material acquisition, merger, or business combination disclosed.",
        "legal":       "Material legal, regulatory, or compliance event disclosed.",
        "guidance":    "Forward-looking guidance or strategic outlook update disclosed.",
        "other":       "Material corporate event disclosed via 8-K filing.",
    }
    return fallbacks.get(event_type, fallbacks["other"])


def _store_8k_event(redis_client, ticker: str, date: str, event_type: str, text: str) -> None:
    key = f"finsight:events:8-K:{ticker.upper()}"
    existing = json.loads(redis_client.get(key) or "[]")
    existing.append({
        "date": date,
        "event_type": event_type,
        "summary": _extract_readable_summary(text, event_type),
    })
    redis_client.setex(key, 60 * 60 * 24 * 30, json.dumps(existing))


async def run_edgar_pipeline(ticker: str, filing_types: list[str]) -> dict:
    """Fetch and ingest only the specified filing types. Skips already-cached types."""
    ticker = ticker.upper()
    redis = get_redis()

    result = {
        "ticker": ticker,
        "ten_k_ingested": 0,
        "ten_q_ingested": 0,
        "eight_k_ingested": 0,
        "total_chunks": 0,
        "errors": [],
    }

    company = await resolve_ticker_to_cik(ticker)
    if not company:
        result["errors"].append(f"Ticker {ticker} not found in SEC EDGAR")
        return result

    result["cik"] = company["cik"]
    result["company_name"] = company["company_name"]

    for filing_type in filing_types:
        count = _FILING_COUNTS.get(filing_type, 1)
        logger.info("Fetching %s ×%d for %s", filing_type, count, ticker)

        try:
            filings = await fetch_filing_urls(company["cik"], filing_type, count=count)
        except Exception as e:
            logger.error("Failed to fetch %s URLs for %s: %s", filing_type, ticker, e)
            result["errors"].append(f"{filing_type} URL fetch failed: {e}")
            continue

        for meta in filings:
            filing_id = hashlib.sha256(
                f"{ticker}_{filing_type}_{meta['filing_date']}".encode()
            ).hexdigest()[:12]

            # Skip if this specific filing already ingested (check by filing_id in Qdrant would
            # be ideal, but registry keyed by ticker+type is sufficient as a gate)
            if is_ingested(redis, ticker, filing_type) and filing_type != "8-K":
                logger.info("Skipping %s %s — already in registry", ticker, filing_type)
                break

            try:
                text = await download_filing_text(meta["document_url"])
            except Exception as e:
                logger.error("Download failed %s %s: %s", ticker, filing_type, e)
                result["errors"].append(f"{filing_type} download failed ({meta['filing_date']}): {e}")
                continue

            chunks = chunk_text(text, chunk_size=1000, chunk_overlap=200, source_id=filing_id)
            if not chunks:
                continue

            filing_data = {
                "id": filing_id,
                "ticker": ticker,
                "company_name": company["company_name"],
                "filing_type": filing_type,
                "filed_date": meta["filing_date"],
                "text": text,
            }
            store_filing(filing_id, filing_data, chunks)
            rag_ingest(filing_id, chunks)
            register_filing(redis, ticker, filing_id, {
                "filed_date": meta["filing_date"],
                "chunk_count": len(chunks),
            }, filing_type=filing_type)

            result["total_chunks"] += len(chunks)

            if filing_type == "10-K":
                result["ten_k_ingested"] += 1
            elif filing_type == "10-Q":
                result["ten_q_ingested"] += 1
            elif filing_type == "8-K":
                result["eight_k_ingested"] += 1
                event_type = _classify_8k(meta.get("items", ""), text)
                _store_8k_event(redis, ticker, meta["filing_date"], event_type, text)
                logger.info("8-K classified: %s %s → %s", ticker, meta["filing_date"], event_type)

        logger.info("%s %s done: %d chunks", ticker, filing_type, result["total_chunks"])

    return result

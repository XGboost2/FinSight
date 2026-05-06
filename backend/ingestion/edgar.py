"""FinSight AI — SEC EDGAR 10-K filing fetcher.

Fetches filings from SEC EDGAR using their EFTS API.
Respects SEC fair access policy: max 10 requests/sec, custom User-Agent.
"""

import asyncio
import hashlib
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from config import get_settings

logger = logging.getLogger(__name__)

# SEC EDGAR base URLs
EDGAR_COMPANY_TICKERS = "https://www.sec.gov/files/company_tickers.json"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

# Rate limit: SEC allows max 10 req/sec
_rate_limit_delay = 0.12  # ~8 req/sec to stay safe


async def _get_headers() -> dict[str, str]:
    """SEC requires User-Agent with company + contact email."""
    settings = get_settings()
    return {
        "User-Agent": settings.SEC_EDGAR_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }


async def resolve_ticker_to_cik(ticker: str) -> dict[str, Any] | None:
    """Resolve stock ticker to SEC CIK number.

    Returns dict with {cik, company_name} or None if not found.
    """
    headers = await _get_headers()
    async with httpx.AsyncClient() as client:
        await asyncio.sleep(_rate_limit_delay)
        resp = await client.get(EDGAR_COMPANY_TICKERS, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            cik = str(entry["cik_str"]).zfill(10)
            return {
                "cik": cik,
                "company_name": entry.get("title", ""),
            }

    logger.warning("Ticker %s not found in SEC EDGAR", ticker)
    return None


async def fetch_filing_urls(
    cik: str,
    filing_type: str = "10-K",
    count: int = 1,
) -> list[dict[str, str]]:
    """Fetch filing metadata from SEC EDGAR submissions API.

    Returns list of {accession_number, filing_date, primary_document_url}.
    """
    headers = await _get_headers()
    url = EDGAR_SUBMISSIONS.format(cik=cik)

    async with httpx.AsyncClient() as client:
        await asyncio.sleep(_rate_limit_delay)
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        submissions = resp.json()

    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])
    items_list = recent.get("items", [""] * len(forms))  # 8-K item numbers e.g. "2.02,9.01"

    results: list[dict[str, str]] = []
    for i, form in enumerate(forms):
        if form == filing_type and len(results) < count:
            accession = accession_numbers[i].replace("-", "")
            doc_url = f"{EDGAR_ARCHIVES}/{cik.lstrip('0')}/{accession}/{primary_docs[i]}"
            results.append({
                "accession_number": accession_numbers[i],
                "filing_date": filing_dates[i],
                "document_url": doc_url,
                "items": items_list[i] if i < len(items_list) else "",
            })

    logger.info(
        "Found %d %s filings for CIK %s", len(results), filing_type, cik
    )
    return results


async def download_filing_text(document_url: str) -> str:
    """Download a filing document and extract clean text.

    Handles both HTML and plain text filings.
    """
    headers = await _get_headers()

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        await asyncio.sleep(_rate_limit_delay)
        resp = await client.get(document_url, headers=headers)
        resp.raise_for_status()
        raw = resp.text

    # Strip HTML if present
    if "<html" in raw.lower() or "<body" in raw.lower():
        soup = BeautifulSoup(raw, "html.parser")

        # Remove script and style elements
        for tag in soup(["script", "style", "meta", "link"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
    else:
        text = raw

    # Clean up whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)  # max 2 consecutive newlines
    text = re.sub(r"[ \t]+", " ", text)      # collapse horizontal whitespace
    text = text.strip()

    logger.info(
        "Downloaded filing: %d chars from %s",
        len(text),
        document_url[:80],
    )
    return text


async def fetch_and_extract(
    ticker: str,
    filing_type: str = "10-K",
) -> dict[str, Any] | None:
    """Full pipeline: ticker → CIK → filing URL → clean text.

    Returns dict with {id, ticker, company_name, filing_type, filed_date, text}
    or None if filing not found.
    """
    # 1. Resolve ticker
    company = await resolve_ticker_to_cik(ticker)
    if not company:
        return None

    # 2. Get filing URL
    filings = await fetch_filing_urls(company["cik"], filing_type, count=1)
    if not filings:
        logger.warning("No %s filings found for %s", filing_type, ticker)
        return None

    filing_meta = filings[0]

    # 3. Download and extract text
    text = await download_filing_text(filing_meta["document_url"])

    # Generate stable ID from ticker + filing date
    filing_id = hashlib.sha256(
        f"{ticker}_{filing_type}_{filing_meta['filing_date']}".encode()
    ).hexdigest()[:12]

    return {
        "id": filing_id,
        "ticker": ticker.upper(),
        "company_name": company["company_name"],
        "filing_type": filing_type,
        "filed_date": filing_meta["filing_date"],
        "text": text,
    }

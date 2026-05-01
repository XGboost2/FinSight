"""FinSight AI — In-memory filing store.

Temporary store for Day 7. Replaced by Qdrant at Day 14.
Stores ingested filings and their chunks for retrieval.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# In-memory store: filing_id → {metadata + chunks}
_store: dict[str, dict[str, Any]] = {}


def store_filing(filing_id: str, metadata: dict, chunks: list[dict]) -> None:
    """Store a filing with its chunks."""
    _store[filing_id] = {
        **metadata,
        "chunks": chunks,
    }
    logger.info(
        "Stored filing %s: %s %s (%d chunks)",
        filing_id,
        metadata.get("ticker"),
        metadata.get("filing_type"),
        len(chunks),
    )


def get_filing(filing_id: str) -> dict[str, Any] | None:
    """Get filing metadata + chunks by ID."""
    return _store.get(filing_id)




def get_filing_by_ticker(ticker: str) -> dict[str, Any] | None:
    """Look up the most recently ingested filing for a ticker."""
    ticker = ticker.upper()
    matches = [
        (fid, data) for fid, data in _store.items()
        if data.get("ticker", "").upper() == ticker
    ]
    if not matches:
        return None
    # Return the most recently stored (last inserted wins)
    fid, data = matches[-1]
    return {"id": fid, **data}

def list_filings() -> list[dict[str, Any]]:
    """List all ingested filings (without chunk text to keep it light)."""
    results = []
    for fid, data in _store.items():
        results.append({
            "id": fid,
            "ticker": data.get("ticker", ""),
            "company_name": data.get("company_name", ""),
            "filing_type": data.get("filing_type", ""),
            "filed_date": data.get("filed_date", ""),
            "chunk_count": len(data.get("chunks", [])),
        })
    return results


def search_chunks(
    query: str,
    filing_id: str,
    top_k: int = 5,
) -> list[dict]:
    """Basic keyword search over chunks of a specific filing.

    Simple TF-based scoring: counts query term occurrences in each chunk.
    This is a placeholder — replaced by Qdrant hybrid search at Day 14.
    """
    filing = _store.get(filing_id)
    if not filing:
        return []

    chunks = filing.get("chunks", [])
    query_terms = query.lower().split()

    scored: list[tuple[float, dict]] = []
    for chunk in chunks:
        text_lower = chunk["text"].lower()
        # Simple term frequency score
        score = sum(text_lower.count(term) for term in query_terms)
        if score > 0:
            scored.append((score, chunk))

    # Sort by score descending, return top_k
    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def get_filing_count() -> int:
    """Return total number of stored filings."""
    return len(_store)

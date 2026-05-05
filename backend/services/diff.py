"""
YoY Diff service — compares current vs prior year 10-K sections.

Flow:
  1. Check Redis cache — return immediately if all sections cached (30d TTL)
  2. Fetch prior year 10-K from EDGAR (second result from fetch_filing_urls)
  3. Chunk + embed + store prior year in Qdrant (for future RAG queries)
  4. Extract Item 1, 1A, 7 from both filings using section parser
  5. Semantic diff per section: embed paragraphs → cosine similarity matrix
     → classify each paragraph as new / removed / changed / unchanged
  6. LLM call per section to summarise what materially changed
  7. Cache each section result independently in Redis
"""

import hashlib
import json
import logging

import numpy as np

from cache.filing_registry import register_filing
from ingestion.chunker import chunk_text
from ingestion.edgar import download_filing_text, fetch_filing_urls, resolve_ticker_to_cik
from ingestion.sections import extract_sections, split_paragraphs
from rag.embedder import embed_documents
from rag.pipeline import ingest as rag_ingest
from services.llm import _calc_cost, call_llm_raw
from services.store import store_filing

logger = logging.getLogger(__name__)

DIFF_TTL = 60 * 60 * 24 * 30   # 30 days

SECTIONS = {
    "item_1":  "Business Overview (Item 1)",
    "item_1a": "Risk Factors (Item 1A)",
    "item_7":  "MD&A (Item 7)",
}

# Cosine similarity thresholds
_UNCHANGED = 0.88   # paragraph is essentially the same
_CHANGED   = 0.50   # paragraph exists in both but content shifted


def _diff_key(ticker: str, section: str, filing_type: str = "10-K") -> str:
    return f"finsight:report:diff:{filing_type.upper()}:{ticker.upper()}:{section}"


def _cosine_matrix(a: list, b: list) -> np.ndarray:
    a_np = np.array(a, dtype=np.float32)
    b_np = np.array(b, dtype=np.float32)
    a_n = a_np / (np.linalg.norm(a_np, axis=1, keepdims=True) + 1e-8)
    b_n = b_np / (np.linalg.norm(b_np, axis=1, keepdims=True) + 1e-8)
    return a_n @ b_n.T


def _classify(
    cur_paras: list[str],
    pri_paras: list[str],
    cur_embs: list,
    pri_embs: list,
) -> dict:
    """Classify current paragraphs against prior year paragraphs."""
    if not cur_paras or not pri_paras:
        return {"new": cur_paras[:10], "removed": pri_paras[:10], "changed": [], "unchanged_count": 0}

    sim = _cosine_matrix(cur_embs, pri_embs)
    new_items, changed_items = [], []
    matched_prior: set[int] = set()
    unchanged = 0

    for i, para in enumerate(cur_paras):
        best_j = int(np.argmax(sim[i]))
        best_score = float(sim[i][best_j])

        if best_score >= _UNCHANGED:
            unchanged += 1
            matched_prior.add(best_j)
        elif best_score >= _CHANGED:
            changed_items.append({
                "current": para[:500],
                "prior":   pri_paras[best_j][:500],
                "similarity": round(best_score, 3),
            })
            matched_prior.add(best_j)
        else:
            new_items.append(para[:500])

    removed = [pri_paras[j][:500] for j in range(len(pri_paras)) if j not in matched_prior]

    return {
        "new":             new_items[:10],
        "removed":         removed[:10],
        "changed":         changed_items[:8],
        "unchanged_count": unchanged,
    }


async def _summarise(section_label: str, ticker: str, cur_year: str, pri_year: str, diff: dict) -> str:
    new_block     = "\n".join(f"- {p}" for p in diff["new"][:5])     or "None"
    removed_block = "\n".join(f"- {p}" for p in diff["removed"][:5]) or "None"
    changed_block = "\n".join(
        f"- BEFORE: {c['prior'][:200]}\n  AFTER:  {c['current'][:200]}"
        for c in diff["changed"][:3]
    ) or "None"

    prompt = f"""You are a senior equity analyst comparing {ticker}'s SEC 10-K filings.

Section: {section_label}
Comparing: {pri_year} (prior) → {cur_year} (current)

NEW content added this year:
{new_block}

REMOVED content from last year:
{removed_block}

CHANGED content (before → after):
{changed_block}

Write a concise 2-3 sentence summary of the most significant changes. Be specific — name new risks, resolved issues, and evolving concerns. Focus only on material changes."""

    text, tok_in, tok_out, model = await call_llm_raw(prompt, max_tokens=350)
    logger.info(
        "Diff LLM: ticker=%s section=%s model=%s cost=$%.4f",
        ticker, section_label, model, _calc_cost(model, tok_in, tok_out),
    )
    return text.strip()


async def get_or_compute_diff(
    redis_client,
    ticker: str,
    refresh: bool = False,
) -> dict:
    """Return cached diff or compute fresh. Fetches both years from EDGAR — no in-memory store dependency."""
    ticker = ticker.upper()

    # Cache check — all three sections must be present
    if not refresh:
        cached: dict[str, dict] = {}
        for key in SECTIONS:
            raw = redis_client.get(_diff_key(ticker, key))
            if raw:
                cached[key] = json.loads(raw)

        if len(cached) == len(SECTIONS):
            logger.info("Diff cache hit: %s", ticker)
            first = next(iter(cached.values()))
            return _build(ticker, first.get("current_year", ""), first.get("prior_year", ""), cached)

    # Fetch BOTH years from EDGAR — avoids in-memory store dependency after restarts
    company = await resolve_ticker_to_cik(ticker)
    if not company:
        raise ValueError(f"Cannot resolve ticker {ticker}")

    filing_urls = await fetch_filing_urls(company["cik"], "10-K", count=2)
    if len(filing_urls) < 2:
        raise ValueError(f"No prior year 10-K available for {ticker}")

    current_meta = filing_urls[0]
    prior_meta   = filing_urls[1]
    current_year = current_meta["filing_date"][:4]
    prior_year   = prior_meta["filing_date"][:4]

    logger.info("Fetching current year 10-K: %s filed %s", ticker, current_meta["filing_date"])
    current_text = await download_filing_text(current_meta["document_url"])

    logger.info("Fetching prior year 10-K: %s filed %s", ticker, prior_meta["filing_date"])
    prior_text = await download_filing_text(prior_meta["document_url"])

    # Ingest prior year into Qdrant + store
    prior_id = hashlib.sha256(
        f"{ticker}_10-K_{prior_meta['filing_date']}".encode()
    ).hexdigest()[:12]

    prior_chunks = chunk_text(prior_text, chunk_size=1000, chunk_overlap=200, source_id=prior_id)
    store_filing(prior_id, {
        "id": prior_id, "ticker": ticker,
        "company_name": company["company_name"],
        "filing_type": "10-K", "filed_date": prior_meta["filing_date"],
        "text": prior_text,
    }, prior_chunks)
    rag_ingest(prior_id, prior_chunks)
    register_filing(redis_client, ticker, prior_id, {
        "filed_date": prior_meta["filing_date"],
        "chunk_count": len(prior_chunks),
    }, filing_type="10-K-PRIOR")
    logger.info("Prior year ingested: %s %s (%d chunks)", ticker, prior_year, len(prior_chunks))

    # Extract sections from both filings
    cur_sections  = extract_sections(current_text)
    pri_sections  = extract_sections(prior_text)

    results: dict[str, dict] = {}

    for key, label in SECTIONS.items():
        cur_text = cur_sections.get(key, "")
        pri_text = pri_sections.get(key, "")

        if not cur_text or not pri_text:
            logger.warning("Section %s missing for %s", key, ticker)
            results[key] = _empty_section(label, cur_year, prior_year)
            continue

        cur_paras = split_paragraphs(cur_text)
        pri_paras = split_paragraphs(pri_text)
        logger.info("Diff %s %s: current=%d pri=%d paragraphs", ticker, key, len(cur_paras), len(pri_paras))

        cur_embs = embed_documents(cur_paras)
        pri_embs = embed_documents(pri_paras)

        diff = _classify(cur_paras, pri_paras, cur_embs, pri_embs)
        summary = await _summarise(label, ticker, current_year, prior_year, diff)

        results[key] = {
            "section": label,
            "current_year": current_year,
            "prior_year": prior_year,
            "summary": summary,
            **diff,
        }

        redis_client.setex(_diff_key(ticker, key), DIFF_TTL, json.dumps(results[key]))
        logger.info("Diff cached: %s %s (30d)", ticker, key)

    return _build(ticker, current_year, prior_year, results)


def _empty_section(label: str, cur_year: str, prior_year: str) -> dict:
    return {
        "section": label, "current_year": cur_year, "prior_year": prior_year,
        "summary": "Section not found in one or both filings.",
        "new": [], "removed": [], "changed": [], "unchanged_count": 0,
    }


def _build(ticker: str, cur_year: str, prior_year: str, results: dict) -> dict:
    return {
        "ticker": ticker,
        "current_year": cur_year,
        "prior_year": prior_year,
        "item_1":  results.get("item_1",  _empty_section(SECTIONS["item_1"],  cur_year, prior_year)),
        "item_1a": results.get("item_1a", _empty_section(SECTIONS["item_1a"], cur_year, prior_year)),
        "item_7":  results.get("item_7",  _empty_section(SECTIONS["item_7"],  cur_year, prior_year)),
    }

"""FinSight AI — REST API routes.

All endpoints return Pydantic models. Never raw dicts.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Query

from config import get_settings
from cache.filing_registry import (
    get_filing_record,
    is_ingested,
    list_ingested,
    register_filing,
)
from cache.redis_client import get_redis
from cache.ticker_cache import get_ticker_info, load_tickers_into_redis, search_tickers
from ingestion.chunker import chunk_text
from ingestion.edgar import fetch_and_extract
from models.schemas import (
    AnalysisReport,
    ChatRequest,
    ChatResponse,
    CompanyInfo,
    CompareRequest,
    ChangedParagraph,
    CompareResponse,
    DashboardResponse,
    FetchFilingRequest,
    FilingInfo,
    FilingListResponse,
    FilingResponse,
    HealthResponse,
    IngestResponse,
    SearchResponse,
    SectionDiff,
    SourceChunk,
    YoYDiffResponse,
)
from rag.pipeline import ingest as rag_ingest, retrieve as rag_retrieve
from services.comparison import get_or_generate_comparison
from services.dashboard import get_or_extract_dashboard
from services.diff import get_or_compute_diff
from services.report import get_or_generate_report
from ingestion.xbrl import get_revenue_trend
from services.llm import ask_llm
from services.store import (
    get_filing,
    get_filing_by_ticker,
    get_filing_count,
    list_filings,
    store_filing,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["FinSight"])


# ── Company Search (pure Redis — zero SEC API calls) ─────────────────


@router.get("/companies/search", response_model=SearchResponse)
async def search_companies(q: str = Query(..., min_length=1)) -> SearchResponse:
    """Search companies by name or ticker. Pure Redis, zero API calls."""
    logger.info("Company search: q=%r", q)
    redis = get_redis()
    results = search_tickers(redis, q, limit=8)
    logger.info("Company search: q=%r → %d results", q, len(results))
    return SearchResponse(
        results=[CompanyInfo(**r) for r in results],
        total=len(results),
    )


@router.get("/companies/{ticker}/info", response_model=CompanyInfo)
async def get_company_info(ticker: str) -> CompanyInfo:
    logger.info("Company info request: %s", ticker)
    redis = get_redis()
    info = get_ticker_info(redis, ticker)
    if not info:
        logger.warning("Company info not found: %s", ticker)
        raise HTTPException(404, f"Ticker '{ticker}' not found in Redis. Cache may be loading.")
    logger.info("Company info found: %s → %s", ticker, info.get("name", ""))
    return CompanyInfo(**info)


# ── Ingest Pipeline ──────────────────────────────────────────────────


async def _run_ingest(ticker: str, force: bool = False) -> dict:
    """Shared ingest logic: registry gate → EDGAR → chunk → Qdrant → dashboard."""
    ticker = ticker.upper()
    redis = get_redis()

    if is_ingested(redis, ticker) and not force:
        record = get_filing_record(redis, ticker)
        filing = get_filing_by_ticker(ticker)
        logger.info("Ingest skipped (already exists): %s chunks=%d", ticker, record["chunk_count"])
        return {
            "ticker": ticker,
            "filing_id": record["filing_id"],
            "chunk_count": record["chunk_count"],
            "already_existed": True,
            "company_name": filing.get("company_name", "") if filing else "",
            "filed_date": record.get("filed_date", ""),
        }

    logger.info("Ingest start: %s", ticker)
    result = await fetch_and_extract(ticker, "10-K")
    if not result:
        logger.warning("Ingest: no 10-K found for %s", ticker)
        raise HTTPException(404, f"No 10-K filing found for '{ticker}'")

    chunks = chunk_text(
        text=result["text"],
        chunk_size=1000,
        chunk_overlap=200,
        source_id=result["id"],
    )
    if not chunks:
        logger.error("Ingest: chunking produced 0 chunks for %s", ticker)
        raise HTTPException(422, "Filing text could not be chunked")

    store_filing(result["id"], result, chunks)
    rag_ingest(result["id"], chunks)

    register_filing(redis, ticker, result["id"], {
        "filed_date": result.get("filed_date", ""),
        "chunk_count": len(chunks),
    })

    await get_or_extract_dashboard(redis, ticker, result["id"], chunks)

    logger.info(
        "Ingest complete: %s filing_id=%s chunks=%d filed=%s",
        ticker, result["id"], len(chunks), result.get("filed_date", ""),
    )
    return {
        "ticker": ticker,
        "filing_id": result["id"],
        "chunk_count": len(chunks),
        "already_existed": False,
        "company_name": result.get("company_name", ""),
        "filed_date": result.get("filed_date", ""),
    }


@router.post("/companies/{ticker}/ingest", response_model=IngestResponse)
async def ingest_company(ticker: str, force: bool = False) -> IngestResponse:
    """Fetch, chunk, embed and cache a company's 10-K. Idempotent. Use ?force=true to re-ingest."""
    try:
        data = await _run_ingest(ticker, force=force)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ingest failed for %s: %s", ticker, e, exc_info=True)
        raise HTTPException(502, f"Ingest failed: {e}")
    return IngestResponse(**data)


# ── Dashboard ────────────────────────────────────────────────────────


@router.get("/companies/{ticker}/dashboard", response_model=DashboardResponse)
async def get_dashboard(ticker: str) -> DashboardResponse:
    """Return cached dashboard metrics. Triggers extraction if cache expired."""
    ticker = ticker.upper()
    logger.info("Dashboard request: %s", ticker)
    redis = get_redis()

    if not is_ingested(redis, ticker):
        logger.warning("Dashboard: %s not ingested", ticker)
        raise HTTPException(404, f"No filing for '{ticker}'. Call /ingest first.")

    record = get_filing_record(redis, ticker)
    filing = get_filing_by_ticker(ticker)
    fallback = filing.get("chunks", []) if filing else []

    metrics = await get_or_extract_dashboard(redis, ticker, record["filing_id"], fallback)
    logger.info("Dashboard served: %s", ticker)
    return DashboardResponse(**{k: v for k, v in metrics.items() if k != "ticker"}, ticker=ticker)


# ── Analysis Report ──────────────────────────────────────────────────


@router.get("/companies/{ticker}/report", response_model=AnalysisReport)
async def get_report(ticker: str, refresh: bool = False) -> AnalysisReport:
    """Generate comprehensive 10-K analysis report: findings table, bull/bear cases, verdict."""
    ticker = ticker.upper()
    logger.info("Report request: %s refresh=%s", ticker, refresh)
    redis = get_redis()

    if not is_ingested(redis, ticker):
        logger.warning("Report: %s not ingested", ticker)
        raise HTTPException(404, f"No filing for '{ticker}'. Call /ingest first.")

    record = get_filing_record(redis, ticker)
    filing = get_filing_by_ticker(ticker)
    fallback = filing.get("chunks", []) if filing else []

    try:
        report = await get_or_generate_report(redis, ticker, record["filing_id"], fallback, refresh=refresh)
    except Exception as e:
        logger.error("Report failed for %s: %s", ticker, e, exc_info=True)
        raise HTTPException(502, f"Report generation failed: {e}")

    logger.info("Report served: %s", ticker)
    return AnalysisReport(**report)


# ── YoY Diff ────────────────────────────────────────────────────────


@router.get("/companies/{ticker}/diff", response_model=YoYDiffResponse)
async def get_yoy_diff(ticker: str, refresh: bool = False) -> YoYDiffResponse:
    """Year-over-year 10-K diff: Business (Item 1), Risk Factors (Item 1A), MD&A (Item 7).

    Fetches prior year 10-K from EDGAR, stores in Qdrant, computes semantic diff,
    and summarises changes with LLM. Results cached 30 days in Redis.
    Use ?refresh=true to force recompute.
    """
    ticker = ticker.upper()
    logger.info("YoY diff request: %s refresh=%s", ticker, refresh)
    redis = get_redis()

    if not is_ingested(redis, ticker):
        raise HTTPException(404, f"No filing for '{ticker}'. Call /ingest first.")

    try:
        result = await get_or_compute_diff(redis, ticker, refresh=refresh)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error("Diff failed for %s: %s", ticker, e, exc_info=True)
        raise HTTPException(502, f"Diff failed: {e}")

    def _to_section(d: dict) -> SectionDiff:
        if not d:
            return SectionDiff()
        changed = [ChangedParagraph(**c) if isinstance(c, dict) else c for c in d.get("changed", [])]
        return SectionDiff(**{**d, "changed": changed})

    logger.info("YoY diff served: %s (%s vs %s)", ticker, result["current_year"], result["prior_year"])
    return YoYDiffResponse(
        ticker=result["ticker"],
        current_year=result["current_year"],
        prior_year=result["prior_year"],
        item_1=_to_section(result.get("item_1")),
        item_1a=_to_section(result.get("item_1a")),
        item_7=_to_section(result.get("item_7")),
    )


# ── Comparison Engine ────────────────────────────────────────────────


@router.post("/companies/compare", response_model=CompareResponse)
async def compare_companies(request: CompareRequest) -> CompareResponse:
    """Compare two companies head-to-head. Triggers ingest for any missing tickers."""
    if len(request.tickers) != 2:
        raise HTTPException(400, "Exactly 2 tickers required")

    t1, t2 = request.tickers[0].upper(), request.tickers[1].upper()
    logger.info("Comparison request: %s vs %s", t1, t2)
    redis = get_redis()

    try:
        data1 = await _run_ingest(t1)
        data2 = await _run_ingest(t2)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ingest failed during comparison %s vs %s: %s", t1, t2, e, exc_info=True)
        raise HTTPException(502, f"Ingest failed during comparison: {e}")

    metrics1 = await get_or_extract_dashboard(redis, t1, data1["filing_id"])
    metrics2 = await get_or_extract_dashboard(redis, t2, data2["filing_id"])

    result = await get_or_generate_comparison(
        redis, t1, t2, data1["filing_id"], data2["filing_id"], metrics1, metrics2
    )

    info1 = get_ticker_info(redis, t1)
    info2 = get_ticker_info(redis, t2)
    trends1 = await get_revenue_trend(info1["cik"]) if info1 and info1.get("cik") else []
    trends2 = await get_revenue_trend(info2["cik"]) if info2 and info2.get("cik") else []

    logger.info("Comparison complete: %s vs %s", t1, t2)
    return CompareResponse(**result, trends1=trends1, trends2=trends2)


# ── Admin ────────────────────────────────────────────────────────────


@router.get("/admin/costs")
async def get_costs() -> dict:
    """Return LLM API cost breakdown for today, this week, and this month."""
    from datetime import datetime, timezone
    from cache.cost_tracker import get_costs_for_period, get_last_n_days

    redis = get_redis()
    now = datetime.now(timezone.utc)

    week_num = now.isocalendar()[1]
    return {
        "today":    get_costs_for_period(redis, "daily",   now.strftime("%Y-%m-%d")),
        "week":     get_costs_for_period(redis, "weekly",  f"{now.year}-W{week_num:02d}"),
        "month":    get_costs_for_period(redis, "monthly", now.strftime("%Y-%m")),
        "last_7_days": get_last_n_days(redis, 7),
    }


@router.post("/admin/refresh-tickers")
async def refresh_tickers() -> dict:
    """Manually trigger ticker cache refresh (normally runs at 2am UTC)."""
    logger.info("Manual ticker refresh triggered")
    redis = get_redis()
    count = await load_tickers_into_redis(redis)
    logger.info("Ticker refresh complete: %d companies loaded", count)
    return {"loaded": count, "message": f"Refreshed {count} tickers into Redis"}


# ── Legacy Filing Endpoints ──────────────────────────────────────────


@router.post("/filings/fetch", response_model=FilingResponse)
async def fetch_filing(request: FetchFilingRequest) -> FilingResponse:
    logger.info("Fetch filing: ticker=%s type=%s", request.ticker, request.filing_type)

    try:
        result = await fetch_and_extract(request.ticker, request.filing_type)
    except Exception as e:
        logger.error("EDGAR fetch failed for %s: %s", request.ticker, e, exc_info=True)
        raise HTTPException(502, f"SEC EDGAR fetch failed: {e}")

    if not result:
        logger.warning("No %s found for %s", request.filing_type, request.ticker)
        raise HTTPException(404, f"No {request.filing_type} found for '{request.ticker}'")

    chunks = chunk_text(text=result["text"], chunk_size=1000, chunk_overlap=200, source_id=result["id"])
    if not chunks:
        logger.error("Chunking failed for %s", request.ticker)
        raise HTTPException(422, "Filing text could not be chunked")

    store_filing(result["id"], result, chunks)
    rag_ingest(result["id"], chunks)

    logger.info(
        "Filing fetched and ingested: ticker=%s id=%s chunks=%d",
        request.ticker, result["id"], len(chunks),
    )
    return FilingResponse(
        success=True,
        filing=FilingInfo(
            id=result["id"],
            ticker=result["ticker"],
            company_name=result["company_name"],
            filing_type=result["filing_type"],
            filed_date=result["filed_date"],
            chunk_count=len(chunks),
            status="ready",
        ),
        message="Filing ingested successfully",
    )


@router.get("/filings", response_model=FilingListResponse)
async def get_filings() -> FilingListResponse:
    filings_data = list_filings()
    logger.info("Filings list: %d total", len(filings_data))
    filings = [
        FilingInfo(
            id=f["id"],
            ticker=f["ticker"],
            company_name=f["company_name"],
            filing_type=f["filing_type"],
            filed_date=f["filed_date"],
            chunk_count=f["chunk_count"],
            status="ready",
        )
        for f in filings_data
    ]
    return FilingListResponse(filings=filings, total=len(filings))


@router.get("/filings/{filing_id}")
async def get_filing_detail(filing_id: str) -> FilingResponse:
    logger.info("Filing detail request: %s", filing_id)
    data = get_filing(filing_id)
    if not data:
        logger.warning("Filing not found: %s", filing_id)
        raise HTTPException(404, "Filing not found")
    logger.info("Filing detail served: %s ticker=%s", filing_id, data.get("ticker", ""))
    return FilingResponse(
        success=True,
        filing=FilingInfo(
            id=filing_id,
            ticker=data["ticker"],
            company_name=data.get("company_name", ""),
            filing_type=data["filing_type"],
            filed_date=data.get("filed_date", ""),
            chunk_count=len(data.get("chunks", [])),
            status="ready",
        ),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    logger.info("Chat request: ticker=%s question=%r", request.ticker, request.question[:80])
    redis = get_redis()
    if not is_ingested(redis, request.ticker):
        logger.warning("Chat: no filing for %s", request.ticker)
        raise HTTPException(404, f"No filing for '{request.ticker}'. Ingest first.")

    record = get_filing_record(redis, request.ticker)
    filing_id = record["filing_id"]

    # Multi-query retrieval — original question + section-targeted rephrasing
    # prevents "outlook" questions from only matching risk factor chunks
    section_queries = {
        "outlook": "management discussion analysis future outlook guidance strategy",
        "risk":    "risk factors material risks regulatory competition",
        "revenue": "revenue growth financial performance results of operations",
        "future":  "management discussion analysis future outlook guidance strategy",
        "plan":    "management discussion analysis strategy future plans",
        "expect":  "management discussion analysis outlook expectations guidance",
    }
    extra_query = next(
        (v for k, v in section_queries.items() if k in request.question.lower()), None
    )

    seen: set = set()
    relevant_chunks = []
    for q in ([request.question] + ([extra_query] if extra_query else [])):
        for c in rag_retrieve(q, filing_id, top_k=5):
            if c["chunk_index"] not in seen:
                seen.add(c["chunk_index"])
                relevant_chunks.append(c)

    context = "\n\n---\n\n".join(
        f"[Chunk {c['chunk_index']}]\n{c['text']}" for c in relevant_chunks
    )

    try:
        llm_result = await ask_llm(request.question, context, model=request.model)
    except Exception as e:
        logger.error("LLM call failed for ticker=%s: %s", request.ticker, e, exc_info=True)
        raise HTTPException(502, f"LLM call failed: {e}")

    logger.info(
        "Chat complete: ticker=%s model=%s tokens_in=%d tokens_out=%d cost=$%.6f latency=%.1fms",
        request.ticker,
        llm_result["model_used"],
        llm_result["tokens_in"],
        llm_result["tokens_out"],
        llm_result["cost_usd"],
        llm_result["latency_ms"],
    )

    sources = [
        SourceChunk(chunk_index=c["chunk_index"], text_preview=c["text"][:200])
        for c in relevant_chunks
    ]

    return ChatResponse(
        answer=llm_result["answer"],
        sources=sources,
        model_used=llm_result["model_used"],
        tokens_in=llm_result["tokens_in"],
        tokens_out=llm_result["tokens_out"],
        cost_usd=llm_result["cost_usd"],
        latency_ms=llm_result["latency_ms"],
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    redis_ok = False
    qdrant_ok = False

    try:
        redis = get_redis()
        redis.ping()
        redis_ok = True
    except Exception as e:
        logger.warning("Health check: Redis unavailable — %s", e)

    try:
        from qdrant_client import QdrantClient
        qc = QdrantClient(url=get_settings().QDRANT_URL)
        qc.get_collections()
        qdrant_ok = True
    except Exception as e:
        logger.warning("Health check: Qdrant unavailable — %s", e)

    return HealthResponse(
        filings_loaded=get_filing_count(),
        redis_ok=redis_ok,
        qdrant_ok=qdrant_ok,
    )

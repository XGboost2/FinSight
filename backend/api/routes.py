"""FinSight AI — REST API routes.

All endpoints return Pydantic models. Never raw dicts.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Query

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
    ChatRequest,
    ChatResponse,
    CompanyInfo,
    CompareRequest,
    CompareResponse,
    DashboardResponse,
    FetchFilingRequest,
    FilingInfo,
    FilingListResponse,
    FilingResponse,
    HealthResponse,
    IngestResponse,
    SearchResponse,
    SourceChunk,
)
from rag.pipeline import ingest as rag_ingest, retrieve as rag_retrieve
from services.comparison import get_or_generate_comparison
from services.dashboard import get_or_extract_dashboard
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
    redis = get_redis()
    results = search_tickers(redis, q, limit=8)
    return SearchResponse(
        results=[CompanyInfo(**r) for r in results],
        total=len(results),
    )


@router.get("/companies/{ticker}/info", response_model=CompanyInfo)
async def get_company_info(ticker: str) -> CompanyInfo:
    redis = get_redis()
    info = get_ticker_info(redis, ticker)
    if not info:
        raise HTTPException(404, f"Ticker '{ticker}' not found in Redis. Cache may be loading.")
    return CompanyInfo(**info)


# ── Ingest Pipeline ──────────────────────────────────────────────────


async def _run_ingest(ticker: str) -> dict:
    """Shared ingest logic: registry gate → EDGAR → chunk → Qdrant → dashboard."""
    ticker = ticker.upper()
    redis = get_redis()

    if is_ingested(redis, ticker):
        record = get_filing_record(redis, ticker)
        filing = get_filing_by_ticker(ticker)
        return {
            "ticker": ticker,
            "filing_id": record["filing_id"],
            "chunk_count": record["chunk_count"],
            "already_existed": True,
            "company_name": filing.get("company_name", "") if filing else "",
            "filed_date": record.get("filed_date", ""),
        }

    result = await fetch_and_extract(ticker, "10-K")
    if not result:
        raise HTTPException(404, f"No 10-K filing found for '{ticker}'")

    chunks = chunk_text(
        text=result["text"],
        chunk_size=1000,
        chunk_overlap=200,
        source_id=result["id"],
    )
    if not chunks:
        raise HTTPException(422, "Filing text could not be chunked")

    store_filing(result["id"], result, chunks)
    rag_ingest(result["id"], chunks)

    register_filing(redis, ticker, result["id"], {
        "filed_date": result.get("filed_date", ""),
        "chunk_count": len(chunks),
    })

    await get_or_extract_dashboard(redis, ticker, result["id"], chunks)

    return {
        "ticker": ticker,
        "filing_id": result["id"],
        "chunk_count": len(chunks),
        "already_existed": False,
        "company_name": result.get("company_name", ""),
        "filed_date": result.get("filed_date", ""),
    }


@router.post("/companies/{ticker}/ingest", response_model=IngestResponse)
async def ingest_company(ticker: str) -> IngestResponse:
    """Fetch, chunk, embed and cache a company's 10-K. Idempotent."""
    try:
        data = await _run_ingest(ticker)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ingest failed for %s: %s", ticker, e)
        raise HTTPException(502, f"Ingest failed: {e}")
    return IngestResponse(**data)


# ── Dashboard ────────────────────────────────────────────────────────


@router.get("/companies/{ticker}/dashboard", response_model=DashboardResponse)
async def get_dashboard(ticker: str) -> DashboardResponse:
    """Return cached dashboard metrics. Triggers extraction if cache expired."""
    ticker = ticker.upper()
    redis = get_redis()

    if not is_ingested(redis, ticker):
        raise HTTPException(404, f"No filing for '{ticker}'. Call /ingest first.")

    record = get_filing_record(redis, ticker)
    filing = get_filing_by_ticker(ticker)
    fallback = filing.get("chunks", []) if filing else []

    metrics = await get_or_extract_dashboard(redis, ticker, record["filing_id"], fallback)
    return DashboardResponse(**{k: v for k, v in metrics.items() if k != "ticker"}, ticker=ticker)


# ── Comparison Engine ────────────────────────────────────────────────


@router.post("/companies/compare", response_model=CompareResponse)
async def compare_companies(request: CompareRequest) -> CompareResponse:
    """Compare two companies head-to-head. Triggers ingest for any missing tickers."""
    if len(request.tickers) != 2:
        raise HTTPException(400, "Exactly 2 tickers required")

    t1, t2 = request.tickers[0].upper(), request.tickers[1].upper()
    redis = get_redis()

    try:
        data1 = await _run_ingest(t1)
        data2 = await _run_ingest(t2)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Ingest failed during comparison: {e}")

    metrics1 = await get_or_extract_dashboard(redis, t1, data1["filing_id"])
    metrics2 = await get_or_extract_dashboard(redis, t2, data2["filing_id"])

    result = await get_or_generate_comparison(
        redis, t1, t2, data1["filing_id"], data2["filing_id"], metrics1, metrics2
    )
    return CompareResponse(**result)


# ── Admin ────────────────────────────────────────────────────────────


@router.post("/admin/refresh-tickers")
async def refresh_tickers() -> dict:
    """Manually trigger ticker cache refresh (normally runs at 2am UTC)."""
    redis = get_redis()
    count = await load_tickers_into_redis(redis)
    return {"loaded": count, "message": f"Refreshed {count} tickers into Redis"}


# ── Legacy Filing Endpoints ──────────────────────────────────────────


@router.post("/filings/fetch", response_model=FilingResponse)
async def fetch_filing(request: FetchFilingRequest) -> FilingResponse:
    logger.info("Fetching %s filing for %s", request.filing_type, request.ticker)

    try:
        result = await fetch_and_extract(request.ticker, request.filing_type)
    except Exception as e:
        logger.error("EDGAR fetch failed for %s: %s", request.ticker, e)
        raise HTTPException(502, f"SEC EDGAR fetch failed: {e}")

    if not result:
        raise HTTPException(404, f"No {request.filing_type} found for '{request.ticker}'")

    chunks = chunk_text(text=result["text"], chunk_size=1000, chunk_overlap=200, source_id=result["id"])
    if not chunks:
        raise HTTPException(422, "Filing text could not be chunked")

    store_filing(result["id"], result, chunks)
    rag_ingest(result["id"], chunks)

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
    data = get_filing(filing_id)
    if not data:
        raise HTTPException(404, "Filing not found")
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
    filing = get_filing_by_ticker(request.ticker)
    if not filing:
        raise HTTPException(404, f"No filing for '{request.ticker}'. Ingest first.")
    filing_id = filing["id"]

    relevant_chunks = rag_retrieve(request.question, filing_id, top_k=5)
    if not relevant_chunks:
        relevant_chunks = filing.get("chunks", [])[:5]

    context = "\n\n---\n\n".join(
        f"[Chunk {c['chunk_index']}]\n{c['text']}" for c in relevant_chunks
    )

    try:
        llm_result = await ask_llm(request.question, context)
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise HTTPException(502, f"LLM call failed: {e}")

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
    try:
        redis = get_redis()
        redis.ping()
        redis_ok = True
    except Exception:
        pass
    return HealthResponse(filings_loaded=get_filing_count(), redis_ok=redis_ok)

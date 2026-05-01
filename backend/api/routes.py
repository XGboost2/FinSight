"""FinSight AI — REST API routes.

All endpoints return Pydantic models. Never raw dicts.
"""

import logging

from fastapi import APIRouter, HTTPException

from ingestion.edgar import fetch_and_extract
from ingestion.chunker import chunk_text
from services.store import store_filing, get_filing, list_filings, get_filing_count
from rag.pipeline import ingest as rag_ingest, retrieve as rag_retrieve
from services.llm import ask_llm
from models.schemas import (
    FetchFilingRequest,
    FilingResponse,
    FilingInfo,
    FilingListResponse,
    ChatRequest,
    ChatResponse,
    SourceChunk,
    HealthResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["FinSight"])


@router.post("/filings/fetch", response_model=FilingResponse)
async def fetch_filing(request: FetchFilingRequest) -> FilingResponse:
    """Fetch a SEC filing by ticker and ingest it.

    Downloads the latest 10-K (or specified type), extracts text,
    chunks it, and stores for Q&A.
    """
    logger.info("Fetching %s filing for %s", request.filing_type, request.ticker)

    try:
        result = await fetch_and_extract(request.ticker, request.filing_type)
    except Exception as e:
        logger.error("EDGAR fetch failed for %s: %s", request.ticker, str(e))
        raise HTTPException(status_code=502, detail=f"SEC EDGAR fetch failed: {str(e)}")

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No {request.filing_type} filing found for ticker '{request.ticker}'"
        )

    # Chunk the filing text
    chunks = chunk_text(
        text=result["text"],
        chunk_size=1000,
        chunk_overlap=200,
        source_id=result["id"],
    )

    if not chunks:
        raise HTTPException(status_code=422, detail="Filing text could not be chunked")

    # Store filing + chunks
    store_filing(result["id"], result, chunks)

    # Embed chunks and store in Qdrant for semantic search
    rag_ingest(result["id"], chunks)

    filing_info = FilingInfo(
        id=result["id"],
        ticker=result["ticker"],
        company_name=result["company_name"],
        filing_type=result["filing_type"],
        filed_date=result["filed_date"],
        chunk_count=len(chunks),
        status="ready",
    )

    return FilingResponse(success=True, filing=filing_info, message="Filing ingested successfully")


@router.get("/filings", response_model=FilingListResponse)
async def get_filings() -> FilingListResponse:
    """List all ingested filings."""
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
    """Get details of a specific filing."""
    data = get_filing(filing_id)
    if not data:
        raise HTTPException(status_code=404, detail="Filing not found")

    filing_info = FilingInfo(
        id=filing_id,
        ticker=data["ticker"],
        company_name=data.get("company_name", ""),
        filing_type=data["filing_type"],
        filed_date=data.get("filed_date", ""),
        chunk_count=len(data.get("chunks", [])),
        status="ready",
    )
    return FilingResponse(success=True, filing=filing_info)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Ask a question about an ingested filing.

    Retrieves relevant chunks, sends to LLM with the question,
    returns answer with source citations.
    """
    filing = get_filing(request.filing_id)
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found. Ingest it first via /api/filings/fetch")

    # Retrieve relevant chunks via semantic search (RAG)
    relevant_chunks = rag_retrieve(request.question, request.filing_id, top_k=5)

    if not relevant_chunks:
        # Fallback: use first few chunks from in-memory store
        relevant_chunks = filing.get("chunks", [])[:5]

    # Build context from chunks
    context = "\n\n---\n\n".join(
        f"[Chunk {c['chunk_index']}]\n{c['text']}" for c in relevant_chunks
    )

    # Call LLM
    try:
        llm_result = await ask_llm(request.question, context)
    except Exception as e:
        logger.error("LLM call failed: %s", str(e))
        raise HTTPException(status_code=502, detail=f"LLM call failed: {str(e)}")

    # Build source citations
    sources = [
        SourceChunk(
            chunk_index=c["chunk_index"],
            text_preview=c["text"][:200],
        )
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
    """Health check with filing count."""
    return HealthResponse(filings_loaded=get_filing_count())

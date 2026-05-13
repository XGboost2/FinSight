"""FinSight AI — FastAPI entry point."""

import logging
import time
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from limiter import limiter

from cache.redis_client import get_redis
from cache.ticker_cache import load_tickers_into_redis, TICKERS_KEY
from config import get_settings
from jobs.refresh_tickers import refresh_ticker_index
from rag.retriever import ensure_collection
from api.routes import router as api_router
from logging_config import setup_logging
from services.observability import init_langfuse, flush as langfuse_flush

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("FinSight AI starting up (env=%s)", settings.ENVIRONMENT)
    init_langfuse()
    logger.info("LLM: Anthropic=%s OpenAI=%s",
                "ok" if settings.ANTHROPIC_API_KEY else "missing",
                "ok" if settings.OPENAI_API_KEY else "missing")

    scheduler = AsyncIOScheduler()

    try:
        ensure_collection()
        logger.info("Qdrant collection ready")
    except Exception as e:
        logger.error("Qdrant startup failed: %s", e)

    try:
        redis = get_redis()
        if not redis.exists(TICKERS_KEY):
            logger.info("Ticker cache empty — loading companies from SEC EDGAR")
            count = await load_tickers_into_redis(redis)
            logger.info("Loaded %d companies into Redis", count)
        else:
            logger.info("Redis ticker cache ready")

        scheduler.add_job(refresh_ticker_index, "cron", hour=2, args=[redis])
        scheduler.start()
        logger.info("Ticker refresh scheduled at 02:00 UTC daily")
    except Exception as e:
        logger.error("Redis startup failed (search unavailable): %s", e)

    yield

    scheduler.shutdown(wait=False)
    langfuse_flush()
    logger.info("FinSight AI shutting down")


app = FastAPI(
    title="FinSight AI",
    description="Financial Risk Intelligence Platform — SEC EDGAR 10-K analysis with LLM-powered Q&A",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception: %s %s — %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc,
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "app": "FinSight AI",
        "version": "0.2.0",
        "description": "Financial Risk Intelligence Platform",
        "docs": "/docs",
    }

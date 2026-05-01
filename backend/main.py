"""FinSight AI — FastAPI entry point."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cache.redis_client import get_redis
from cache.ticker_cache import load_tickers_into_redis, TICKERS_KEY
from config import get_settings
from jobs.refresh_tickers import refresh_ticker_index
from api.routes import router as api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("🚀 FinSight AI starting up (env=%s)", settings.ENVIRONMENT)
    logger.info("   LLM: Anthropic=%s OpenAI=%s",
                "✅" if settings.ANTHROPIC_API_KEY else "❌",
                "✅" if settings.OPENAI_API_KEY else "❌")

    scheduler = AsyncIOScheduler()

    try:
        redis = get_redis()
        if not redis.exists(TICKERS_KEY):
            logger.info("Ticker cache empty — loading ~13k companies from SEC EDGAR...")
            count = await load_tickers_into_redis(redis)
            logger.info("Loaded %d companies into Redis", count)
        else:
            logger.info("Redis ticker cache ready")

        scheduler.add_job(refresh_ticker_index, "cron", hour=2, args=[redis])
        scheduler.start()
        logger.info("Ticker refresh scheduled at 2am UTC daily")
    except Exception as e:
        logger.error("Redis startup failed (search unavailable): %s", e)

    yield

    scheduler.shutdown(wait=False)
    logger.info("👋 FinSight AI shutting down")


app = FastAPI(
    title="FinSight AI",
    description="Financial Risk Intelligence Platform — SEC EDGAR 10-K analysis with LLM-powered Q&A",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "app": "FinSight AI",
        "version": "0.2.0",
        "description": "Financial Risk Intelligence Platform",
        "docs": "/docs",
    }

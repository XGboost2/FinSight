"""FinSight AI — FastAPI entry point.

Financial Risk Intelligence Platform.
Analyses SEC EDGAR 10-K filings using LLM-powered Q&A.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from api.routes import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    settings = get_settings()
    logger.info("🚀 FinSight AI starting up (env=%s)", settings.ENVIRONMENT)
    logger.info("   LLM: Anthropic=%s OpenAI=%s",
                "✅" if settings.ANTHROPIC_API_KEY else "❌",
                "✅" if settings.OPENAI_API_KEY else "❌")
    logger.info("   EDGAR User-Agent: %s", settings.SEC_EDGAR_USER_AGENT)
    yield
    logger.info("👋 FinSight AI shutting down")


app = FastAPI(
    title="FinSight AI",
    description="Financial Risk Intelligence Platform — SEC EDGAR 10-K analysis with LLM-powered Q&A",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint — basic info."""
    return {
        "app": "FinSight AI",
        "version": "0.1.0",
        "description": "Financial Risk Intelligence Platform",
        "docs": "/docs",
    }

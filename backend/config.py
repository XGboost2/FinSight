"""FinSight AI — Application configuration via Pydantic Settings.

Loads from .env file automatically. Never commit real .env values.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central config — all env vars in one place."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "FinSight AI"
    ENVIRONMENT: str = "development"  # development | staging | production
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # --- LLM ---
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    KIMI_API_KEY: str = ""
    KIMI_BASE_URL: str = "https://api.moonshot.ai/v1"
    LOCAL_LLM_BASE_URL: str = "http://host.docker.internal:11434/v1"
    LOCAL_LLM_MODEL: str = "qwen3.5:0.8b"
    LOCAL_LLM_API_KEY: str = "local"

    # --- SEC EDGAR ---
    # Format: "AppName your@email.com" — required by SEC fair access policy
    SEC_EDGAR_USER_AGENT: str = "FinSight kuralarasu.venkatesh@gmail.com"

    # --- Vector DB (Day 14+) ---
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_HNSW_M: int = 16
    QDRANT_HNSW_EF_CONSTRUCT: int = 100
    QDRANT_HNSW_FULL_SCAN_THRESHOLD: int = 10000
    QDRANT_HNSW_EF_SEARCH: int = 128
    QDRANT_API_KEY: str = ""

    # --- Graph DB for uploaded-document RAG ---
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "neo4j"

    # --- Retrieval ---
    # SEC filings use Qdrant dense+sparse hybrid retrieval with section filters.
    # Uploaded documents use MarkItDown -> PageIndex-style structure -> Neo4j.
    HYPER_EXTRACT_ENABLED: bool = True
    HYPER_EXTRACT_TEMPLATE: str = "finance/ownership_graph"
    HYPER_EXTRACT_TEMPLATES: str = "finance/ownership_graph,finance/event_timeline,finance/risk_factor_set,general/concept_graph"
    HYPER_EXTRACT_LANGUAGE: str = "en"
    HYPER_EXTRACT_MAX_CHUNKS: int = 8

    # --- Document Uploads ---
    DOCUMENT_UPLOAD_MAX_BYTES: int = 25 * 1024 * 1024

    # --- Local Multimodal Service ---
    MULTIMODAL_SERVICE_URL: str = "http://localhost:8010"
    MULTIMODAL_TIMEOUT_SECONDS: float = 120.0
    MULTIMODAL_IMAGE_MAX_BYTES: int = 10 * 1024 * 1024
    MULTIMODAL_AUDIO_MAX_BYTES: int = 25 * 1024 * 1024

    # --- Observability (Day 49+) ---
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"

    # --- News ---
    FINNHUB_API_KEY: str = ""

    # --- Trading 212 (Invest/Stocks ISA only; beta API) ---
    TRADING212_API_KEY_ID: str = ""
    TRADING212_API_SECRET: str = ""
    TRADING212_BASE_URL: str = "https://demo.trading212.com/api/v0"
    # Safety pin: code refuses to place orders against the live host unless True.
    TRADING212_ALLOW_LIVE: bool = False

    # --- Cache (Day 49+) ---
    REDIS_URL: str = "redis://localhost:6379"

    # --- Sessions ---
    SESSION_TTL_SECONDS: int = 3600  # 60 minutes inactivity


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — call this everywhere instead of Settings()."""
    return Settings()

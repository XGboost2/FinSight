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

    # --- SEC EDGAR ---
    # Format: "AppName your@email.com" — required by SEC fair access policy
    SEC_EDGAR_USER_AGENT: str = "FinSight kuralarasu.venkatesh@gmail.com"

    # --- Vector DB (Day 14+) ---
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # --- Observability (Day 49+) ---
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"
    
    # --- News ---
    FINNHUB_API_KEY: str = ""

    # --- Cache (Day 49+) ---
    REDIS_URL: str = "redis://localhost:6379"

    # --- Sessions ---
    SESSION_TTL_SECONDS: int = 3600  # 60 minutes inactivity


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — call this everywhere instead of Settings()."""
    return Settings()

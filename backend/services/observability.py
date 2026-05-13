"""LangFuse observability — tracing for every LLM call, retrieval, and pipeline run.

Initialise once at startup via init_langfuse().
All @observe decorators in llm.py, report.py, pipeline.py are no-ops when keys are absent.
"""

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def init_langfuse():
    """Initialise LangFuse client. Returns client or None if keys not configured."""
    from config import get_settings
    s = get_settings()

    if not s.LANGFUSE_SECRET_KEY or not s.LANGFUSE_PUBLIC_KEY:
        logger.info("LangFuse: no keys set — tracing disabled (set LANGFUSE_SECRET_KEY + LANGFUSE_PUBLIC_KEY to enable)")
        return None

    # Set env vars so @observe decorator picks them up automatically
    os.environ["LANGFUSE_SECRET_KEY"] = s.LANGFUSE_SECRET_KEY
    os.environ["LANGFUSE_PUBLIC_KEY"] = s.LANGFUSE_PUBLIC_KEY
    os.environ["LANGFUSE_HOST"]       = s.LANGFUSE_BASE_URL

    from langfuse import Langfuse
    client = Langfuse(
        secret_key=s.LANGFUSE_SECRET_KEY,
        public_key=s.LANGFUSE_PUBLIC_KEY,
        host=s.LANGFUSE_BASE_URL,
    )
    logger.info("LangFuse: tracing enabled → %s", s.LANGFUSE_BASE_URL)
    return client


def flush():
    """Flush pending traces to LangFuse. Call at app shutdown."""
    client = init_langfuse()
    if client:
        try:
            client.flush()
            logger.info("LangFuse: flushed pending traces")
        except Exception as e:
            logger.warning("LangFuse flush failed: %s", e)

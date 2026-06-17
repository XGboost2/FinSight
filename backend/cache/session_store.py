"""
Redis-backed user session management and per-session chat memory.

Session lifecycle:
  Any request with X-Session-ID → auto-create if missing → slide TTL
  Inactivity timeout → key expires → next request → 401 → frontend redirects home

Chat history per session:
  finsight:chat:{session_id}:{ticker}  →  Redis list of JSON messages
  TTL mirrors session TTL — expires together with the session

Answer cache per session:
  finsight:chat_cache:{session_id}:{sha256(ticker:question)[:20]}  →  answer string
  Same question in same session → instant Redis hit, no LLM call
"""

import hashlib
import json
import logging
from datetime import datetime, timezone

from config import get_settings

logger = logging.getLogger(__name__)

CHAT_HISTORY_MAX = 20  # max messages kept (10 turns)


def _session_ttl() -> int:
    return get_settings().SESSION_TTL_SECONDS


# ── Session CRUD ───────────────────────────────────────────────────────────────

def get_or_create_session(redis, session_id: str) -> bool:
    """Auto-create session if missing, slide TTL if exists. Returns True always."""
    key = f"finsight:session:{session_id}"
    if redis.exists(key):
        redis.expire(key, _session_ttl())
    else:
        redis.setex(key, _session_ttl(), json.dumps({
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        logger.info("Session auto-created: %s (TTL=%ds)", session_id, _session_ttl())
    return True


def validate_and_refresh(redis, session_id: str) -> bool:
    """Returns True if session is valid and slides the TTL."""
    key = f"finsight:session:{session_id}"
    if not redis.exists(key):
        return False
    redis.expire(key, _session_ttl())
    return True


def session_exists(redis, session_id: str) -> bool:
    """Check if session key still exists (no TTL slide)."""
    return bool(redis.exists(f"finsight:session:{session_id}"))


def delete_session(redis, session_id: str) -> None:
    redis.delete(f"finsight:session:{session_id}")
    logger.info("Session deleted: %s", session_id)


# ── Chat history (Redis list) ─────────────────────────────────────────────────

def _history_key(session_id: str, ticker: str) -> str:
    return f"finsight:chat:{session_id}:{ticker.upper()}"


def get_chat_history(redis, session_id: str, ticker: str) -> list[dict]:
    """Return conversation history for this session + ticker."""
    key = _history_key(session_id, ticker)
    raw_msgs = redis.lrange(key, -CHAT_HISTORY_MAX, -1)
    history = []
    for raw in raw_msgs or []:
        try:
            msg = json.loads(raw)
        except Exception:
            logger.warning("Skipping malformed chat history message: session=%s ticker=%s", session_id, ticker)
            continue
        content = msg.get("content")
        if msg.get("role") in {"user", "assistant"} and isinstance(content, str) and content.strip():
            history.append({"role": msg["role"], "content": content.strip()})
    return history


def append_chat_turn(
    redis,
    session_id: str,
    ticker: str,
    question: str,
    answer: str,
) -> None:
    """Append a user+assistant turn to history. Guard against orphaned writes."""
    if not session_exists(redis, session_id):
        logger.debug("Session expired, discarding chat turn: %s", session_id)
        return
    question = question.strip()
    answer = answer.strip()
    if not question or not answer:
        logger.warning("Skipping empty chat turn write: session=%s ticker=%s", session_id, ticker)
        return

    key = _history_key(session_id, ticker)
    pipe = redis.pipeline()
    pipe.rpush(key, json.dumps({"role": "user", "content": question}))
    pipe.rpush(key, json.dumps({"role": "assistant", "content": answer}))
    pipe.ltrim(key, -CHAT_HISTORY_MAX, -1)
    pipe.expire(key, _session_ttl())
    pipe.execute()


# ── Answer cache ───────────────────────────────────────────────────────────────

def _cache_key(session_id: str, ticker: str, question: str) -> str:
    h = hashlib.sha256(f"{ticker.upper()}:{question}".encode()).hexdigest()[:20]
    return f"finsight:chat_cache:{session_id}:{h}"


def get_cached_answer(redis, session_id: str, ticker: str, question: str) -> str | None:
    return redis.get(_cache_key(session_id, ticker, question))


def set_cached_answer(redis, session_id: str, ticker: str, question: str, answer: str) -> None:
    if not session_exists(redis, session_id):
        return
    if not answer.strip():
        return
    redis.setex(_cache_key(session_id, ticker, question), _session_ttl(), answer)

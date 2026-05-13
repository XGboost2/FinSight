"""Shared SlowAPI rate limiter instance.

Import this in main.py (to attach to app) and routes.py (to decorate endpoints).
Backed by Redis so limits are shared across Uvicorn workers.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from config import get_settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_settings().REDIS_URL,
    default_limits=["300/minute"],
)

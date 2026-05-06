"""Celery application — Redis as broker and result backend.

DB layout:
  Redis DB 0 — FinSight app data (finsight:* keys)
  Redis DB 1 — Celery broker queues + task results
"""

from celery import Celery
from config import get_settings


def _celery_redis_url() -> str:
    """Use Redis DB 1 for all Celery data, keeping DB 0 for app keys."""
    base = get_settings().REDIS_URL.rstrip("/")
    # strip existing db suffix if present (e.g. /0) then append /1
    if base.endswith("/0"):
        base = base[:-2]
    return f"{base}/1"


_url = _celery_redis_url()

celery_app = Celery(
    "finsight",
    broker=_url,
    backend=_url,
    include=["tasks.edgar_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # Named queue so it's visible as finsight.tasks in Flower
    task_default_queue="finsight.tasks",
)

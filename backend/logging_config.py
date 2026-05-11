"""Logging setup — call setup_logging() once at startup.

Log files:
  finsight.log  — all app logs (root)
  llm.log       — LLM calls only (model, tokens, cost, latency)
  tasks.log     — Celery task lifecycle + worker logs
"""

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"


def _rotating(filename: str) -> logging.handlers.RotatingFileHandler:
    """10 MB per file, 5 backups → max 50 MB per log."""
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / filename, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(FMT, datefmt=DATEFMT))
    return handler


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(FMT, datefmt=DATEFMT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(_rotating("finsight.log"))

    # LLM calls — services.llm only, also propagates to finsight.log
    llm_logger = logging.getLogger("services.llm")
    llm_logger.addHandler(_rotating("llm.log"))

    # Celery tasks — tasks.* + celery internals, also propagates to finsight.log
    for name in ("tasks", "celery", "celery.task", "celery.worker", "celery.app.trace"):
        logging.getLogger(name).addHandler(_rotating("tasks.log"))

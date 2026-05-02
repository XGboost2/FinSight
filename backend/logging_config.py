"""Logging setup — call setup_logging() once at startup."""

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "finsight.log"
FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(FMT, datefmt=DATEFMT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    # 10 MB per file, keep 5 backups → max 50 MB on disk
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_handler)

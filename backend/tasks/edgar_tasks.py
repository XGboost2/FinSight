"""Celery tasks for EDGAR filing ingestion."""

import logging

from celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    name="tasks.ingest_company_filings",
)
def ingest_company_filings(
    self,
    ticker: str,
    filing_types: list[str] | None = None,
    force: bool = False,
) -> dict:
    """
    Background task: run EDGAR agent for a ticker.
    Only fetches filing types in filing_types (defaults to all three).
    """
    ticker = ticker.upper()
    filing_types = filing_types or ["10-K", "10-Q", "8-K"]
    logger.info("Celery task start: ingest %s types=%s task_id=%s", ticker, filing_types, self.request.id)

    self.update_state(state="PROGRESS", meta={"ticker": ticker, "step": f"Starting EDGAR agent for {', '.join(filing_types)}…"})

    try:
        import asyncio
        from services.edgar_pipeline import run_edgar_pipeline
        from services.dashboard import get_or_extract_dashboard
        from cache.redis_client import get_redis
        from services.store import get_filing_by_ticker

        self.update_state(state="PROGRESS", meta={"ticker": ticker, "step": f"Fetching {', '.join(filing_types)} from SEC EDGAR…"})
        result = asyncio.run(run_edgar_pipeline(ticker, filing_types, force=force))

        redis = get_redis()
        from cache.filing_registry import get_filing_record
        record = get_filing_record(redis, ticker, "10-K")

        # Generate dashboard
        self.update_state(state="PROGRESS", meta={"ticker": ticker, "step": "Generating dashboard…"})
        try:
            if record:
                filing = get_filing_by_ticker(ticker)
                from ingestion.chunker import chunk_text
                text = (filing or {}).get("text", "")
                if text:
                    chunks = chunk_text(text, chunk_size=1000, chunk_overlap=200, source_id=record["filing_id"])
                    asyncio.run(get_or_extract_dashboard(redis, ticker, record["filing_id"], chunks))
        except Exception as e:
            logger.warning("Dashboard generation failed: %s", e)
            result.setdefault("errors", []).append(f"Dashboard: {e}")

        # Pre-generate analysis report so first tab load is instant
        self.update_state(state="PROGRESS", meta={"ticker": ticker, "step": "Pre-generating analysis report…"})
        try:
            if record:
                from services.report import get_or_generate_report
                asyncio.run(get_or_generate_report(
                    redis, ticker, record["filing_id"], refresh=False
                ))
                logger.info("Report pre-generated for %s", ticker)
        except Exception as e:
            logger.warning("Report pre-generation failed: %s", e)
            result.setdefault("errors", []).append(f"Report: {e}")

        # Pre-fetch news so first News tab load is instant
        self.update_state(state="PROGRESS", meta={"ticker": ticker, "step": "Fetching latest news…"})
        try:
            from ingestion.news import get_or_fetch_news
            asyncio.run(get_or_fetch_news(redis, ticker, refresh=False))
            logger.info("News pre-cached for %s", ticker)
        except Exception as e:
            logger.warning("News pre-cache failed: %s", e)
            result.setdefault("errors", []).append(f"News: {e}")

        logger.info("Celery task complete: %s → %s", ticker, result)
        return result

    except Exception as exc:
        logger.error("Celery task failed: %s — %s", ticker, exc, exc_info=True)
        raise self.retry(exc=exc, countdown=30, max_retries=2)

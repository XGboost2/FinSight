import logging
from cache.ticker_cache import load_tickers_into_redis

logger = logging.getLogger(__name__)


async def refresh_ticker_index(redis_client) -> None:
    """Daily 2am UTC. Same as startup load — upserts only, nothing deleted."""
    count = await load_tickers_into_redis(redis_client)
    logger.info("Ticker refresh complete: %d companies in Redis", count)

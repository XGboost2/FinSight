import redis
from functools import lru_cache
from config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().REDIS_URL, decode_responses=True)

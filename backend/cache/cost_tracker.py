"""
Cost tracker — records every LLM call cost to Redis.
Aggregates by day, week, month for budget monitoring.

Redis key schema:
  finsight:costs:{period}:{label}   HASH
    {model}:cost       → float (USD)
    {model}:calls      → int
    {model}:tokens_in  → int
    {model}:tokens_out → int

Periods:  daily:2026-05-04  |  weekly:2026-W18  |  monthly:2026-05
TTLs:     daily 90d         |  weekly 365d       |  monthly 730d
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_TTL = {
    "daily":   60 * 60 * 24 * 90,   # 90 days
    "weekly":  60 * 60 * 24 * 365,  # 1 year
    "monthly": 60 * 60 * 24 * 730,  # 2 years
}


def _period_labels(dt: datetime) -> dict[str, str]:
    week_num = dt.isocalendar()[1]
    return {
        "daily":   dt.strftime("%Y-%m-%d"),
        "weekly":  f"{dt.year}-W{week_num:02d}",
        "monthly": dt.strftime("%Y-%m"),
    }


def _key(period: str, label: str) -> str:
    return f"finsight:costs:{period}:{label}"


def record_cost(
    redis_client,
    model: str,
    cost_usd: float,
    tokens_in: int,
    tokens_out: int,
) -> None:
    """Record a single LLM call. Called after every ask_llm / call_llm_raw."""
    try:
        now = datetime.now(timezone.utc)
        periods = _period_labels(now)

        pipe = redis_client.pipeline()
        for period, label in periods.items():
            key = _key(period, label)
            pipe.hincrbyfloat(key, f"{model}:cost", cost_usd)
            pipe.hincrby(key, f"{model}:calls", 1)
            pipe.hincrby(key, f"{model}:tokens_in", tokens_in)
            pipe.hincrby(key, f"{model}:tokens_out", tokens_out)
            pipe.hincrbyfloat(key, "total:cost", cost_usd)
            pipe.hincrby(key, "total:calls", 1)
            pipe.expire(key, _TTL[period])
        pipe.execute()
    except Exception as e:
        logger.warning("Cost tracking failed (non-critical): %s", e)


def get_costs_for_period(redis_client, period: str, label: str) -> dict:
    """Return aggregated costs for a specific period label."""
    try:
        raw = redis_client.hgetall(_key(period, label))
        if not raw:
            return {"total_cost": 0.0, "total_calls": 0, "by_model": {}}

        by_model: dict = {}
        total_cost = float(raw.get("total:cost", 0))
        total_calls = int(raw.get("total:calls", 0))

        # Collect unique model names from keys like "deepseek-chat:cost"
        models = {k.split(":")[0] for k in raw if ":" in k and not k.startswith("total")}
        for model in models:
            by_model[model] = {
                "cost":       round(float(raw.get(f"{model}:cost", 0)), 6),
                "calls":      int(raw.get(f"{model}:calls", 0)),
                "tokens_in":  int(raw.get(f"{model}:tokens_in", 0)),
                "tokens_out": int(raw.get(f"{model}:tokens_out", 0)),
            }

        return {
            "total_cost":  round(total_cost, 6),
            "total_calls": total_calls,
            "by_model":    by_model,
        }
    except Exception as e:
        logger.warning("Cost retrieval failed: %s", e)
        return {"total_cost": 0.0, "total_calls": 0, "by_model": {}}


def get_last_n_days(redis_client, n: int = 7) -> list[dict]:
    """Return daily costs for the last N days."""
    from datetime import timedelta
    today = datetime.now(timezone.utc)
    result = []
    for i in range(n):
        dt = today - timedelta(days=i)
        label = dt.strftime("%Y-%m-%d")
        data = get_costs_for_period(redis_client, "daily", label)
        result.append({"date": label, **data})
    return result

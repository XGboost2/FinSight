"""Trading 212 broker client — deterministic API layer, no LLM.

Wraps the Trading 212 Public API (beta). Auth is HTTP Basic with the API Key
as username and API Secret as password, Base64-encoded per the official docs.

Defaults to the demo (paper trading) host. Order placement refuses to hit the
live host unless TRADING212_ALLOW_LIVE is explicitly set — a financial write
action must never fall through to real money by accident.

API notes baked into this module:
  - Instruments list is rate-limited to 1 req / 50s → cached in Redis.
  - Sell orders use a NEGATIVE quantity (core API convention).
  - Market orders are NOT idempotent in beta — duplicate POSTs duplicate orders.
"""

import base64
import json
import logging

import httpx

from config import get_settings
from cache.redis_client import get_redis

logger = logging.getLogger(__name__)

_INSTRUMENTS_KEY = "finsight:t212:instruments"
_INSTRUMENTS_TTL = 60 * 60 * 6  # endpoint refreshes every 10min; 6h cache is ample
_TIMEOUT = 30.0


class Trading212Error(RuntimeError):
    """Raised when the Trading 212 API rejects a request or is misconfigured."""


def _auth_header() -> dict[str, str]:
    settings = get_settings()
    key_id = settings.TRADING212_API_KEY_ID
    secret = settings.TRADING212_API_SECRET
    if not key_id or not secret:
        raise Trading212Error(
            "Trading 212 credentials missing — set TRADING212_API_KEY_ID and "
            "TRADING212_API_SECRET in .env"
        )
    token = base64.b64encode(f"{key_id}:{secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _base_url() -> str:
    return get_settings().TRADING212_BASE_URL.rstrip("/")


async def _request(method: str, path: str, json_body: dict | None = None) -> dict | list:
    """Single HTTP round-trip with auth, raising Trading212Error on failure."""
    url = f"{_base_url()}{path}"
    headers = _auth_header()
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            response = await client.request(method, url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            raise Trading212Error(f"Trading 212 request failed: {exc}") from exc

    if response.status_code == 401:
        raise Trading212Error(
            "Trading 212 returned 401 — check the API key is for an Invest/Stocks ISA "
            "practice account and was generated in the demo environment."
        )
    if response.status_code >= 400:
        raise Trading212Error(
            f"Trading 212 {method} {path} -> {response.status_code}: {response.text[:200]}"
        )
    if not response.content:
        return {}
    return response.json()


# ── Read endpoints ───────────────────────────────────────────────────────────

async def get_account_summary() -> dict:
    """Cash + investment metrics, including available funds (main currency)."""
    return await _request("GET", "/equity/account/summary")  # type: ignore[return-value]


async def get_positions() -> list[dict]:
    """All open positions with quantity, average price, current P/L."""
    result = await _request("GET", "/equity/positions")
    return result if isinstance(result, list) else []


async def get_instruments() -> list[dict]:
    """All tradable instruments. Cached in Redis (source endpoint is 1 req / 50s)."""
    redis = get_redis()
    try:
        cached = redis.get(_INSTRUMENTS_KEY)
        if cached:
            return json.loads(cached)
    except Exception as exc:  # cache failures must not break the main flow
        logger.warning("Instrument cache read failed: %s", exc)

    instruments = await _request("GET", "/equity/metadata/instruments")
    instruments = instruments if isinstance(instruments, list) else []
    try:
        redis.setex(_INSTRUMENTS_KEY, _INSTRUMENTS_TTL, json.dumps(instruments))
    except Exception as exc:
        logger.warning("Instrument cache write failed: %s", exc)
    return instruments


async def resolve_instrument(query: str) -> dict | None:
    """Map a free-text query ('apple', 'AAPL') to a Trading 212 instrument.

    Resolution order: exact ticker/short-name match → exact name → name contains.
    Returns the raw instrument dict (with its 'ticker' field, e.g. 'AAPL_US_EQ').
    """
    q = query.strip().lower()
    if not q:
        return None
    instruments = await get_instruments()

    def field(inst: dict, *names: str) -> str:
        for name in names:
            value = inst.get(name)
            if isinstance(value, str) and value:
                return value.lower()
        return ""

    exact = [
        inst for inst in instruments
        if q in {field(inst, "ticker"), field(inst, "shortName", "shortname")}
    ]
    if exact:
        return exact[0]

    by_name = [inst for inst in instruments if field(inst, "name") == q]
    if by_name:
        return by_name[0]

    contains = [inst for inst in instruments if q in field(inst, "name")]
    return contains[0] if contains else None


# ── Write endpoints ──────────────────────────────────────────────────────────

def _assert_safe_to_trade() -> None:
    """Refuse to place orders against the live host unless explicitly allowed."""
    settings = get_settings()
    is_demo = "demo.trading212.com" in settings.TRADING212_BASE_URL
    if not is_demo and not settings.TRADING212_ALLOW_LIVE:
        raise Trading212Error(
            "Refusing to place a LIVE order. Base URL is not the demo host and "
            "TRADING212_ALLOW_LIVE is false. Set it to true to trade real money."
        )


async def place_market_order(
    ticker: str,
    quantity: float,
    extended_hours: bool = False,
) -> dict:
    """Place a market order. Positive quantity buys, negative sells.

    WARNING: not idempotent in the beta API — calling twice places two orders.
    """
    _assert_safe_to_trade()
    if quantity == 0:
        raise Trading212Error("quantity must be non-zero (positive buy, negative sell)")

    body: dict = {"ticker": ticker, "quantity": quantity}
    if extended_hours:
        body["extendedHours"] = True

    result = await _request("POST", "/equity/orders/market", json_body=body)
    logger.info(
        "Trading 212 market order placed: ticker=%s quantity=%s order_id=%s",
        ticker,
        quantity,
        (result or {}).get("id") if isinstance(result, dict) else None,
    )
    return result  # type: ignore[return-value]

"""Trading 212 broker client tests — no network, no live key required.

Covers the safety-critical, deterministic logic: auth encoding, instrument
resolution, the live-trade guard, and order validation. The LLM tool loop in
trading_agent is intentionally not exercised here (it needs a model).
"""

import base64
from types import SimpleNamespace

import pytest

from services import trading212
from services.trading212 import Trading212Error


def _settings(**overrides):
    base = {
        "TRADING212_API_KEY_ID": "key-id",
        "TRADING212_API_SECRET": "secret-val",
        "TRADING212_BASE_URL": "https://demo.trading212.com/api/v0",
        "TRADING212_ALLOW_LIVE": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ── auth ──────────────────────────────────────────────────────────────────────

def test_auth_header_is_base64_basic(monkeypatch):
    monkeypatch.setattr(trading212, "get_settings", lambda: _settings())
    header = trading212._auth_header()
    expected = base64.b64encode(b"key-id:secret-val").decode()
    assert header == {"Authorization": f"Basic {expected}"}


def test_auth_header_raises_without_credentials(monkeypatch):
    monkeypatch.setattr(
        trading212, "get_settings",
        lambda: _settings(TRADING212_API_KEY_ID="", TRADING212_API_SECRET=""),
    )
    with pytest.raises(Trading212Error):
        trading212._auth_header()


# ── instrument resolution ─────────────────────────────────────────────────────

_INSTRUMENTS = [
    {"ticker": "AAPL_US_EQ", "shortName": "AAPL", "name": "Apple Inc.", "currencyCode": "USD"},
    {"ticker": "MSFT_US_EQ", "shortName": "MSFT", "name": "Microsoft Corporation", "currencyCode": "USD"},
    {"ticker": "AAPL_DE_EQ", "shortName": "APC", "name": "Apple Inc. (Xetra)", "currencyCode": "EUR"},
]


async def test_resolve_by_short_symbol(monkeypatch):
    monkeypatch.setattr(trading212, "get_instruments", _async(_INSTRUMENTS))
    inst = await trading212.resolve_instrument("aapl")
    assert inst["ticker"] == "AAPL_US_EQ"


async def test_resolve_by_full_name(monkeypatch):
    monkeypatch.setattr(trading212, "get_instruments", _async(_INSTRUMENTS))
    inst = await trading212.resolve_instrument("Microsoft Corporation")
    assert inst["ticker"] == "MSFT_US_EQ"


async def test_resolve_by_name_contains(monkeypatch):
    monkeypatch.setattr(trading212, "get_instruments", _async(_INSTRUMENTS))
    inst = await trading212.resolve_instrument("apple")
    assert inst["ticker"] == "AAPL_US_EQ"  # exact short/name beats the Xetra contains-match


async def test_resolve_unknown_returns_none(monkeypatch):
    monkeypatch.setattr(trading212, "get_instruments", _async(_INSTRUMENTS))
    assert await trading212.resolve_instrument("nonexistentco") is None


# ── live-trade safety guard ───────────────────────────────────────────────────

def test_safe_to_trade_allows_demo(monkeypatch):
    monkeypatch.setattr(trading212, "get_settings", lambda: _settings())
    trading212._assert_safe_to_trade()  # no raise


def test_safe_to_trade_blocks_live_by_default(monkeypatch):
    monkeypatch.setattr(
        trading212, "get_settings",
        lambda: _settings(TRADING212_BASE_URL="https://live.trading212.com/api/v0"),
    )
    with pytest.raises(Trading212Error, match="LIVE"):
        trading212._assert_safe_to_trade()


def test_safe_to_trade_allows_live_when_opted_in(monkeypatch):
    monkeypatch.setattr(
        trading212, "get_settings",
        lambda: _settings(
            TRADING212_BASE_URL="https://live.trading212.com/api/v0",
            TRADING212_ALLOW_LIVE=True,
        ),
    )
    trading212._assert_safe_to_trade()  # no raise


# ── order validation ──────────────────────────────────────────────────────────

async def test_market_order_rejects_zero_quantity(monkeypatch):
    monkeypatch.setattr(trading212, "get_settings", lambda: _settings())
    with pytest.raises(Trading212Error, match="non-zero"):
        await trading212.place_market_order("AAPL_US_EQ", 0)


async def test_market_order_blocked_on_live_before_network(monkeypatch):
    monkeypatch.setattr(
        trading212, "get_settings",
        lambda: _settings(TRADING212_BASE_URL="https://live.trading212.com/api/v0"),
    )
    # _request is never reached; the guard fires first.
    monkeypatch.setattr(trading212, "_request", _boom)
    with pytest.raises(Trading212Error, match="LIVE"):
        await trading212.place_market_order("AAPL_US_EQ", 10)


async def test_market_order_posts_signed_quantity_on_demo(monkeypatch):
    monkeypatch.setattr(trading212, "get_settings", lambda: _settings())
    captured = {}

    async def fake_request(method, path, json_body=None):
        captured.update(method=method, path=path, body=json_body)
        return {"id": 12345, "status": "SUBMITTED"}

    monkeypatch.setattr(trading212, "_request", fake_request)
    result = await trading212.place_market_order("AAPL_US_EQ", -5)  # sell 5

    assert captured["method"] == "POST"
    assert captured["path"] == "/equity/orders/market"
    assert captured["body"] == {"ticker": "AAPL_US_EQ", "quantity": -5}
    assert result["id"] == 12345


# ── helpers ───────────────────────────────────────────────────────────────────

def _async(return_value):
    async def _fn(*_args, **_kwargs):
        return return_value
    return _fn


async def _boom(*_args, **_kwargs):
    raise AssertionError("network must not be reached when the safety guard fires")

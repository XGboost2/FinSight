"""Technical analysis service — price indicators + LLM verdict.

Flow:
  1. Redis cache check (1h TTL — intraday data)
  2. Fetch 1 year daily OHLCV via yfinance (no API key)
  3. Compute RSI(14), MACD(12,26,9), SMA50, SMA200, Bollinger Bands, Volume ratio
  4. Classify each indicator as buy / neutral / sell
  5. LLM generates a 3-sentence technical verdict grounded in the numbers
  6. Return structured dict with all indicators + verdict
"""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

TECHNICAL_TTL = 60 * 60          # 1h — intraday data changes
_CACHE_KEY    = "finsight:technical:{ticker}"


# ── Indicator computation ────────────────────────────────────────────────

def _rsi(close, period: int = 14) -> float:
    delta = close.diff().dropna()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    last_loss = loss.iloc[-1]
    last_gain = gain.iloc[-1]
    if last_loss == 0:
        return 100.0
    if last_gain == 0:
        return 0.0
    rs = last_gain / last_loss
    return round(100 - (100 / (1 + rs)), 2)


def _macd(close) -> tuple[float, float, float]:
    ema12   = close.ewm(span=12, adjust=False).mean()
    ema26   = close.ewm(span=26, adjust=False).mean()
    line    = ema12 - ema26
    signal  = line.ewm(span=9, adjust=False).mean()
    hist    = line - signal
    return round(line.iloc[-1], 4), round(signal.iloc[-1], 4), round(hist.iloc[-1], 4)


def _bollinger(close) -> tuple[float, float, float]:
    sma20  = close.rolling(20).mean()
    std20  = close.rolling(20).std()
    upper  = (sma20 + 2 * std20).iloc[-1]
    lower  = (sma20 - 2 * std20).iloc[-1]
    mid    = sma20.iloc[-1]
    return round(upper, 2), round(mid, 2), round(lower, 2)


def _signal_rsi(rsi: float) -> str:
    if rsi >= 70: return "sell"
    if rsi <= 30: return "buy"
    if rsi >= 60: return "neutral"
    return "neutral"


def _signal_macd(hist: float) -> str:
    if hist > 0:  return "buy"
    if hist < 0:  return "sell"
    return "neutral"


def _signal_ma(price: float, ma: float) -> str:
    if price > ma * 1.02:  return "buy"
    if price < ma * 0.98:  return "sell"
    return "neutral"


def _signal_bb(price: float, upper: float, lower: float) -> str:
    if price >= upper: return "sell"
    if price <= lower: return "buy"
    return "neutral"


def _signal_volume(ratio: float) -> str:
    if ratio >= 1.5: return "buy"
    if ratio <= 0.5: return "sell"
    return "neutral"


def _compute_indicators(ticker: str) -> dict | None:
    import yfinance as yf
    df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
    if df is None or len(df) < 210:
        return None

    close  = df["Close"].squeeze()
    volume = df["Volume"].squeeze()
    price  = round(float(close.iloc[-1]), 2)

    rsi_val                   = _rsi(close)
    macd_line, macd_sig, hist = _macd(close)
    sma50                     = round(float(close.rolling(50).mean().iloc[-1]), 2)
    sma200                    = round(float(close.rolling(200).mean().iloc[-1]), 2)
    bb_upper, bb_mid, bb_low  = _bollinger(close)
    vol_20d_avg               = float(volume.rolling(20).mean().iloc[-1])
    vol_ratio                 = round(float(volume.iloc[-1]) / vol_20d_avg, 2)

    indicators = [
        {
            "name":   "RSI (14)",
            "value":  str(rsi_val),
            "signal": _signal_rsi(rsi_val),
            "note":   (
                f"Overbought (>{70})" if rsi_val >= 70 else
                f"Oversold (<{30})"   if rsi_val <= 30 else
                f"Neutral territory ({rsi_val})"
            ),
        },
        {
            "name":   "MACD",
            "value":  f"{macd_line:+.3f} / Signal {macd_sig:.3f}",
            "signal": _signal_macd(hist),
            "note":   f"Histogram {hist:+.3f} — {'bullish crossover' if hist > 0 else 'bearish crossover'}",
        },
        {
            "name":   "50-day SMA",
            "value":  f"${sma50}",
            "signal": _signal_ma(price, sma50),
            "note":   f"Price ${price} is {'above' if price > sma50 else 'below'} 50-day SMA",
        },
        {
            "name":   "200-day SMA",
            "value":  f"${sma200}",
            "signal": _signal_ma(price, sma200),
            "note":   f"Price ${price} is {'above' if price > sma200 else 'below'} 200-day SMA — {'uptrend' if price > sma200 else 'downtrend'}",
        },
        {
            "name":   "Bollinger Bands",
            "value":  f"U:{bb_upper} / M:{bb_mid} / L:{bb_low}",
            "signal": _signal_bb(price, bb_upper, bb_low),
            "note":   (
                "Near upper band — overbought pressure" if price >= bb_upper * 0.99 else
                "Near lower band — oversold pressure"  if price <= bb_low  * 1.01 else
                "Within bands — no extreme pressure"
            ),
        },
        {
            "name":   "Volume vs 20d Avg",
            "value":  f"{vol_ratio:.2f}x",
            "signal": _signal_volume(vol_ratio),
            "note":   f"{'High' if vol_ratio >= 1.5 else 'Low' if vol_ratio <= 0.5 else 'Normal'} volume — {vol_ratio:.2f}x 20-day average",
        },
    ]

    counts = {"buy": 0, "neutral": 0, "sell": 0}
    for ind in indicators:
        counts[ind["signal"]] += 1

    overall = (
        "Bullish"        if counts["buy"] >= 4 else
        "Mildly Bullish" if counts["buy"] == 3 else
        "Bearish"        if counts["sell"] >= 4 else
        "Mildly Bearish" if counts["sell"] == 3 else
        "Neutral"
    )

    return {
        "price":          price,
        "rsi":            rsi_val,
        "macd_line":      macd_line,
        "macd_signal":    macd_sig,
        "macd_hist":      hist,
        "sma50":          sma50,
        "sma200":         sma200,
        "bb_upper":       bb_upper,
        "bb_mid":         bb_mid,
        "bb_lower":       bb_low,
        "volume_ratio":   vol_ratio,
        "indicators":     indicators,
        "signal_counts":  counts,
        "overall_signal": overall,
    }


# ── LLM verdict ─────────────────────────────────────────────────────────

async def _llm_verdict(ticker: str, data: dict) -> str:
    from services.llm import call_llm_raw
    inds = "\n".join(
        f"- {i['name']}: {i['value']} ({i['signal'].upper()}) — {i['note']}"
        for i in data["indicators"]
    )
    prompt = f"""You are a technical analyst. Write a 3-sentence verdict for {ticker} based on these indicators:

{inds}

Overall signal: {data['overall_signal']} ({data['signal_counts']['buy']} buy / {data['signal_counts']['neutral']} neutral / {data['signal_counts']['sell']} sell signals)
Current price: ${data['price']}

Rules:
- Be specific — reference actual indicator values
- Mention the most important signal (RSI overbought/oversold, MACD crossover, or MA crossover)
- End with a one-sentence risk note
- No markdown, no headers, plain text only"""

    try:
        raw, _, _, _ = await call_llm_raw(prompt, max_tokens=200)
        return raw.strip()
    except Exception as e:
        logger.warning("Technical LLM verdict failed: %s", e)
        return f"{ticker} shows {data['overall_signal'].lower()} technicals with {data['signal_counts']['buy']} bullish and {data['signal_counts']['sell']} bearish signals."


# ── Public API ───────────────────────────────────────────────────────────

async def get_or_fetch_technicals(redis_client, ticker: str, refresh: bool = False) -> dict:
    key = _CACHE_KEY.format(ticker=ticker.upper())

    if not refresh:
        cached = redis_client.get(key)
        if cached:
            logger.info("Technical cache hit: %s", ticker)
            return json.loads(cached)

    data = await asyncio.to_thread(_compute_indicators, ticker)
    if not data:
        return {"ticker": ticker.upper(), "error": "Insufficient price history or data unavailable"}

    data["verdict"] = await _llm_verdict(ticker, data)
    data["ticker"]  = ticker.upper()

    redis_client.setex(key, TECHNICAL_TTL, json.dumps(data))
    logger.info("Technicals computed: %s overall=%s", ticker, data["overall_signal"])
    return data

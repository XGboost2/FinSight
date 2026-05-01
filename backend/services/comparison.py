import json
import logging
import time

from config import get_settings

logger = logging.getLogger(__name__)

COMPARE_PREFIX = "finsight:compare:"
COMPARE_TTL = 60 * 60 * 24 * 7  # 7 days
POWER_MODEL = "claude-sonnet-4-20250514"

_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
}


def _compare_key(t1: str, t2: str) -> str:
    tickers = sorted([t1.upper(), t2.upper()])
    return COMPARE_PREFIX + f"{tickers[0]}_{tickers[1]}"


def _cost(model: str, tok_in: int, tok_out: int) -> float:
    p = _PRICING.get(model, {"input": 0.0, "output": 0.0})
    return round((tok_in * p["input"] + tok_out * p["output"]) / 1_000_000, 6)


async def get_or_generate_comparison(
    redis_client,
    ticker1: str,
    ticker2: str,
    filing_id1: str,
    filing_id2: str,
    metrics1: dict,
    metrics2: dict,
) -> dict:
    key = _compare_key(ticker1, ticker2)
    cached = redis_client.get(key)
    if cached:
        logger.info("Compare cache hit: %s vs %s", ticker1, ticker2)
        return json.loads(cached)

    result = await _generate_comparison(ticker1, ticker2, filing_id1, filing_id2, metrics1, metrics2)
    redis_client.setex(key, COMPARE_TTL, json.dumps(result))
    return result


async def _generate_comparison(
    ticker1: str,
    ticker2: str,
    filing_id1: str,
    filing_id2: str,
    metrics1: dict,
    metrics2: dict,
) -> dict:
    from rag.pipeline import retrieve

    query = "revenue growth net income margin risk factors competitive positioning strategy"
    chunks1 = retrieve(query, filing_id1, top_k=5)
    chunks2 = retrieve(query, filing_id2, top_k=5)

    ctx1 = "\n\n".join(c["text"] for c in chunks1)[:4000]
    ctx2 = "\n\n".join(c["text"] for c in chunks2)[:4000]

    t1, t2 = ticker1.upper(), ticker2.upper()

    prompt = f"""You are a senior financial analyst. Compare {t1} and {t2} based on their SEC 10-K filings.

=== {t1} METRICS ===
{json.dumps({k: v for k, v in metrics1.items() if k != 'ticker'}, indent=2)}

=== {t1} FILING EXCERPTS ===
{ctx1}

=== {t2} METRICS ===
{json.dumps({k: v for k, v in metrics2.items() if k != 'ticker'}, indent=2)}

=== {t2} FILING EXCERPTS ===
{ctx2}

Return ONLY valid JSON with exactly these keys:
{{
  "financial_head_to_head": "2-3 sentence financial comparison focusing on revenue scale, margin quality, and growth trajectory",
  "pros_cons": {{
    "{t1}": {{"pros": ["specific pro 1", "specific pro 2"], "cons": ["specific con 1", "specific con 2"]}},
    "{t2}": {{"pros": ["specific pro 1", "specific pro 2"], "cons": ["specific con 1", "specific con 2"]}}
  }},
  "strategic_positioning": "2-3 sentences on competitive moat and strategic differentiators for each company",
  "verdict": "1-2 sentence conclusion on which company shows stronger near-term fundamentals and why"
}}

Return only JSON. No markdown."""

    settings = get_settings()
    start = time.perf_counter()

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=POWER_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        tok_in = response.usage.input_tokens
        tok_out = response.usage.output_tokens

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        analysis = json.loads(raw.strip())

        logger.info(
            "Comparison: model=%s tok_in=%d tok_out=%d cost=$%.4f latency=%.0fms",
            POWER_MODEL, tok_in, tok_out,
            _cost(POWER_MODEL, tok_in, tok_out),
            (time.perf_counter() - start) * 1000,
        )
    except Exception as e:
        logger.error("Comparison LLM failed %s vs %s: %s", t1, t2, e)
        analysis = {
            "financial_head_to_head": f"Comparison unavailable: {e}",
            "pros_cons": {
                t1: {"pros": [], "cons": []},
                t2: {"pros": [], "cons": []},
            },
            "strategic_positioning": "",
            "verdict": "",
        }

    return {
        "ticker1": t1,
        "ticker2": t2,
        "metrics1": metrics1,
        "metrics2": metrics2,
        "analysis": analysis,
    }

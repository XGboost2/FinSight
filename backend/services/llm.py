"""FinSight AI — LLM integration (Anthropic Claude + OpenAI fallback).

Every call logs: model, tokens_in, tokens_out, cost_usd, latency_ms.
"""

import logging
import time
from typing import Any

from config import get_settings
from cache.cost_tracker import record_cost

logger = logging.getLogger(__name__)

# Cost per 1M tokens (USD) — update as pricing changes
_PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat":     {"input": 0.07,  "output": 0.28},
    "deepseek-reasoner": {"input": 0.55,  "output": 2.19},
    "claude-haiku-4-5":  {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
    "claude-opus-4-7":   {"input": 15.00, "output": 75.00},
    "gpt-4o-mini":       {"input": 0.15,  "output": 0.60},
    "gpt-4o":            {"input": 2.50,  "output": 10.00},
}


def _provider(model: str) -> str:
    if model.startswith("deepseek"):
        return "deepseek"
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return "openai"
    return "deepseek"

# System prompt for financial analysis
SYSTEM_PROMPT = """You are FinSight AI, a financial analyst assistant helping users understand SEC 10-K filings.

Rules:
- Ground every claim in the provided filing text
- Cite specific sections or quotes to support your answer
- Translate casual questions into financial concepts: "future outlook" → MD&A guidance; "doing well?" → revenue/profit trends; "any red flags?" → risk factors
- If the retrieved text does not directly answer the question, say what it does cover and which filing section (e.g. Item 7 MD&A) would contain the answer
- Never say "I cannot find this" without explaining what the provided text covers instead
- Be concise but thorough. Use bullet points for lists."""


def _calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate USD cost for an LLM call."""
    pricing = _PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000
    return round(cost, 6)


CHEAP_MODEL = "deepseek-chat"
POWER_MODEL = "deepseek-reasoner"

# Signals that a question needs multi-step reasoning
_POWER_KEYWORDS = {
    "compare", "versus", "vs", "difference", "trend", "over the years",
    "analyse", "analyze", "why", "explain", "impact", "risk assessment",
    "summarise", "summarize", "outlook", "strategy", "forecast",
}


def _route_model(query: str) -> str:
    """Use deepseek-reasoner for complex multi-step questions, deepseek-chat for simple lookups."""
    q = query.lower()
    if any(kw in q for kw in _POWER_KEYWORDS) or len(query) > 200:
        return POWER_MODEL
    return CHEAP_MODEL


async def ask_llm(
    query: str,
    context: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Send a question + filing context to the LLM.

    Tries Anthropic Claude first, falls back to OpenAI if no key.

    Returns:
        {answer, model_used, tokens_in, tokens_out, cost_usd, latency_ms}
    """
    settings = get_settings()
    start = time.perf_counter()

    # Build the user message with context
    user_message = f"""Based on the following SEC filing excerpt, answer the question.

--- FILING TEXT ---
{context[:15000]}
--- END FILING TEXT ---

Question: {query}"""

    routed_model = model or _route_model(query)
    provider = _provider(routed_model)
    logger.info("Model router: query_len=%d → %s (%s)", len(query), routed_model, provider)

    if provider == "deepseek" and settings.DEEPSEEK_API_KEY:
        result = await _call_deepseek(user_message, routed_model, settings)
    elif provider == "anthropic" and settings.ANTHROPIC_API_KEY:
        result = await _call_anthropic(user_message, routed_model, settings)
    elif provider == "openai" and settings.OPENAI_API_KEY:
        result = await _call_openai(user_message, routed_model, settings)
    else:
        logger.warning("No API key for provider=%s model=%s — falling back", provider, routed_model)
        if settings.DEEPSEEK_API_KEY:
            result = await _call_deepseek(user_message, CHEAP_MODEL, settings)
        elif settings.ANTHROPIC_API_KEY:
            result = await _call_anthropic(user_message, "claude-haiku-4-5", settings)
        elif settings.OPENAI_API_KEY:
            result = await _call_openai(user_message, "gpt-4o-mini", settings)
        else:
            result = _mock_response(query)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    result["latency_ms"] = elapsed_ms

    # Log per coding standards
    logger.info(
        "LLM call: model=%s tokens_in=%d tokens_out=%d cost_usd=%.6f latency_ms=%.1f",
        result["model_used"],
        result["tokens_in"],
        result["tokens_out"],
        result["cost_usd"],
        result["latency_ms"],
    )

    try:
        from cache.redis_client import get_redis
        record_cost(get_redis(), result["model_used"], result["cost_usd"], result["tokens_in"], result["tokens_out"])
    except Exception:
        pass  # cost tracking is non-critical

    return result


async def call_llm_raw(
    prompt: str,
    max_tokens: int = 2500,
    model: str | None = None,
) -> tuple[str, int, int, str]:
    """
    Raw LLM call — no system prompt, no context injection.
    Use for structured JSON extraction (report, dashboard, sentiment).
    Returns: (text, tokens_in, tokens_out, model_name)
    """
    settings = get_settings()
    provider = _provider(model) if model else None

    text, tok_in, tok_out, m = "", 0, 0, model or CHEAP_MODEL

    if (not model or provider == "deepseek") and settings.DEEPSEEK_API_KEY:
        from openai import AsyncOpenAI
        m = model or CHEAP_MODEL
        client = AsyncOpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL)
        resp = await client.chat.completions.create(
            model=m, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text, tok_in, tok_out = resp.choices[0].message.content or "", resp.usage.prompt_tokens, resp.usage.completion_tokens

    elif (not model or provider == "anthropic") and settings.ANTHROPIC_API_KEY:
        import anthropic
        m = model or "claude-haiku-4-5"
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model=m, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text, tok_in, tok_out = resp.content[0].text, resp.usage.input_tokens, resp.usage.output_tokens

    elif (not model or provider == "openai") and settings.OPENAI_API_KEY:
        from openai import AsyncOpenAI
        m = model or "gpt-4o-mini"
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=m, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text, tok_in, tok_out = resp.choices[0].message.content or "", resp.usage.prompt_tokens, resp.usage.completion_tokens

    else:
        raise RuntimeError("No LLM API key configured")

    try:
        from cache.redis_client import get_redis
        record_cost(get_redis(), m, _calc_cost(m, tok_in, tok_out), tok_in, tok_out)
    except Exception:
        pass  # cost tracking is non-critical

    return text, tok_in, tok_out, m


async def _call_anthropic(
    user_message: str,
    model: str,
    settings: Any,
) -> dict[str, Any]:
    """Call Anthropic Claude API."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens

    return {
        "answer": response.content[0].text,
        "model_used": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": _calc_cost(model, tokens_in, tokens_out),
    }


async def _call_deepseek(
    user_message: str,
    model: str,
    settings: Any,
) -> dict[str, Any]:
    """Call DeepSeek API (OpenAI-compatible, ~10x cheaper than Claude Haiku)."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )

    response = await client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    usage = response.usage
    tokens_in = usage.prompt_tokens if usage else 0
    tokens_out = usage.completion_tokens if usage else 0

    return {
        "answer": response.choices[0].message.content or "",
        "model_used": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": _calc_cost(model, tokens_in, tokens_out),
    }


async def _call_openai(
    user_message: str,
    model: str,
    settings: Any,
) -> dict[str, Any]:
    """Call OpenAI API."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    usage = response.usage
    tokens_in = usage.prompt_tokens if usage else 0
    tokens_out = usage.completion_tokens if usage else 0

    return {
        "answer": response.choices[0].message.content or "",
        "model_used": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": _calc_cost(model, tokens_in, tokens_out),
    }


def _mock_response(query: str) -> dict[str, Any]:
    """Mock LLM response for development without API keys."""
    return {
        "answer": (
            f"[MOCK MODE — no API key configured]\n\n"
            f"Your question: \"{query}\"\n\n"
            f"To get real answers, set ANTHROPIC_API_KEY or OPENAI_API_KEY in your .env file."
        ),
        "model_used": "mock",
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
    }

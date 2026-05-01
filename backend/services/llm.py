"""FinSight AI — LLM integration (Anthropic Claude + OpenAI fallback).

Every call logs: model, tokens_in, tokens_out, cost_usd, latency_ms.
"""

import logging
import time
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)

# Cost per 1M tokens (USD) — update as pricing changes
_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

# System prompt for financial analysis
SYSTEM_PROMPT = """You are FinSight AI, a financial analyst assistant.
You answer questions ONLY based on the provided SEC filing text.
Rules:
- Ground every claim in the provided filing text
- Cite specific sections or quotes from the filing
- If the answer is not in the provided text, say "I cannot find this information in the provided filing."
- Be concise but thorough
- Use bullet points for lists of risk factors or metrics"""


def _calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate USD cost for an LLM call."""
    pricing = _PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000
    return round(cost, 6)


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

    # Try Anthropic Claude first
    if settings.ANTHROPIC_API_KEY:
        result = await _call_anthropic(user_message, model or "claude-3-5-haiku-20241022", settings)
    elif settings.OPENAI_API_KEY:
        result = await _call_openai(user_message, model or "gpt-4o-mini", settings)
    else:
        # Mock response for development without API keys
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
    return result


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

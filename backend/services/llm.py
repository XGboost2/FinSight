"""FinSight AI — LLM integration (Kimi primary, DeepSeek secondary, Claude/OpenAI fallback).

Every call logs: model, tokens_in, tokens_out, cost_usd, latency_ms.
"""

import logging
import time
from typing import Any

import httpx

from config import get_settings
from cache.cost_tracker import record_cost

try:
    from langfuse import observe, get_client as _lf
except ImportError:
    def observe(*args, **kwargs):        # type: ignore
        def decorator(fn): return fn
        return decorator if args and callable(args[0]) else decorator
    class _LfStub:                       # type: ignore
        def update_current_span(self, **_): pass
        def update_current_generation(self, **_): pass
        def get_current_trace_id(self) -> str | None: return None
    _stub = _LfStub()
    def _lf(): return _stub              # type: ignore

logger = logging.getLogger(__name__)

_httpx_client: httpx.AsyncClient | None = None
_CHAT_ROLES = {"user", "assistant"}


def _get_httpx_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None or _httpx_client.is_closed:
        _httpx_client = httpx.AsyncClient(timeout=60)
    return _httpx_client


def _sanitize_conversation(history: list[dict] | None, user_message: str) -> list[dict]:
    """Build provider-safe chat messages from Redis history plus the current prompt."""
    messages: list[dict] = []
    dropped = 0
    for msg in (history or [])[-20:]:
        role = msg.get("role")
        content = msg.get("content")
        if role not in _CHAT_ROLES or not isinstance(content, str) or not content.strip():
            dropped += 1
            continue
        messages.append({"role": role, "content": content.strip()})

    if dropped:
        logger.warning("Dropped %d invalid/empty chat history messages before LLM call", dropped)

    messages.append({"role": "user", "content": user_message})
    return messages


# Cost per 1M tokens (USD) — update as pricing changes
_PRICING: dict[str, dict[str, float]] = {
    "kimi-k2.6":         {"input": 0.15,   "output": 0.60},   # verify at platform.moonshot.ai/docs
    "deepseek-v4-flash": {"input": 0.14,   "output": 0.28},   # cache miss; cache hit $0.0028
    "deepseek-v4-pro":   {"input": 1.74,   "output": 3.48},   # full price (discount expired 2026-05-31)
    "claude-haiku-4-5":  {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
    "claude-opus-4-7":   {"input": 15.00, "output": 75.00},
    "gpt-4o-mini":       {"input": 0.15,  "output": 0.60},
    "gpt-4o":            {"input": 2.50,  "output": 10.00},
}


def _provider(model: str) -> str:
    if model.startswith("local:"):
        return "local"
    if model.startswith("kimi") or model.startswith("moonshot"):
        return "kimi"
    if model.startswith("deepseek"):
        return "deepseek"
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return "openai"
    return "kimi"

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


CHEAP_MODEL = "kimi-k2.6"   # primary — simple lookups, structured extraction
POWER_MODEL = "kimi-k2.6"   # primary — complex reasoning (same model, 256k context)
CHEAP_FALLBACK = "deepseek-v4-flash"  # secondary if Kimi unavailable
KIMI_MAX_TOKENS = 2048
DEFAULT_MAX_TOKENS = 1024

# Signals that a question needs multi-step reasoning
_POWER_KEYWORDS = {
    "compare", "versus", "vs", "difference", "trend", "over the years",
    "analyse", "analyze", "why", "explain", "impact", "risk assessment",
    "summarise", "summarize", "outlook", "strategy", "forecast",
}


def _route_model(query: str) -> str:
    """Route to Kimi for all queries — POWER_KEYWORDS logged but same model used."""
    q = query.lower()
    if any(kw in q for kw in _POWER_KEYWORDS) or len(query) > 200:
        return POWER_MODEL
    return CHEAP_MODEL


def _provider_has_key(provider: str, settings: Any) -> bool:
    if provider == "kimi":
        return bool(settings.KIMI_API_KEY)
    if provider == "deepseek":
        return bool(settings.DEEPSEEK_API_KEY)
    if provider == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    if provider == "openai":
        return bool(settings.OPENAI_API_KEY)
    return False


def _local_base_urls(settings: Any) -> list[str]:
    """Try both Docker-host and native-host Ollama endpoints automatically."""
    base_urls = [settings.LOCAL_LLM_BASE_URL]
    for candidate in (
        "http://host.docker.internal:11434/v1",
        "http://localhost:11434/v1",
    ):
        if candidate not in base_urls:
            base_urls.append(candidate)
    return base_urls


def _normalize_local_model_name(model: str | None, settings: Any) -> str:
    """Return a bare local model name without a local: prefix."""
    candidate = (model or settings.LOCAL_LLM_MODEL).strip()
    return candidate.removeprefix("local:")


def _chat_message_text(message: Any) -> str:
    """Extract text from OpenAI-compatible chat messages across providers."""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
            else:
                text = getattr(part, "text", None) or getattr(part, "content", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        if parts:
            return "\n".join(parts)

    for attr in ("reasoning_content", "reasoning", "refusal"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return ""


async def _call_provider(
    provider: str,
    user_message: str,
    model: str,
    settings: Any,
    conversation: list[dict],
) -> dict[str, Any]:
    if provider == "kimi":
        return await _call_kimi(user_message, model, settings, conversation)
    if provider == "deepseek":
        return await _call_deepseek(user_message, model, settings, conversation)
    if provider == "anthropic":
        return await _call_anthropic(user_message, model, settings, conversation)
    if provider == "openai":
        return await _call_openai(user_message, model, settings, conversation)
    if provider == "local":
        return await _call_local(user_message, model, settings, conversation)
    raise RuntimeError(f"Unsupported LLM provider: {provider}")


def _fallback_models(primary_model: str, settings: Any, route_mode: str) -> list[str]:
    if route_mode == "local":
        candidate = _normalize_local_model_name(primary_model, settings)
        return [f"local:{candidate}"]

    candidates = [
        primary_model,
        CHEAP_FALLBACK,
        f"local:{settings.LOCAL_LLM_MODEL}",
        "claude-haiku-4-5",
        "gpt-4o-mini",
        CHEAP_MODEL,
    ]
    models: list[str] = []
    for candidate in candidates:
        if candidate in models:
            continue
        provider = _provider(candidate)
        if provider == "local" or _provider_has_key(provider, settings):
            models.append(candidate)
    return models


@observe(as_type="generation")
async def ask_llm(
    query: str,
    context: str,
    model: str | None = None,
    llm_mode: str = "cloud",
    ticker: str | None = None,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Send a question + filing context to the LLM.

    Tries Anthropic Claude first, falls back to OpenAI if no key.

    Returns:
        {answer, model_used, tokens_in, tokens_out, cost_usd, latency_ms}
    """
    _lf().update_current_span(
        name=f"chat/{ticker}" if ticker else "chat",
        metadata={"ticker": ticker, "tags": "chat"},
    )
    settings = get_settings()
    start = time.perf_counter()

    # Build the user message with context
    user_message = f"""Based on the following SEC filing excerpt, answer the question.

--- FILING TEXT ---
{context[:15000]}
--- END FILING TEXT ---

Question: {query}"""

    # Build messages array: system → valid history turns → current question.
    conversation = _sanitize_conversation(history, user_message)

    route_mode = llm_mode if llm_mode in {"cloud", "local"} else "cloud"
    routed_model = model or (_route_model(query) if route_mode == "cloud" else "")
    if route_mode == "local":
        routed_model = f"local:{_normalize_local_model_name(routed_model, settings)}"

    provider = _provider(routed_model)
    logger.info("Model router: query_len=%d history=%d → %s (%s)",
                len(query), len(history or []), routed_model, provider)

    result: dict[str, Any] | None = None
    failures: list[str] = []
    for candidate_model in _fallback_models(routed_model, settings, route_mode):
        candidate_provider = _provider(candidate_model)
        try:
            candidate = await _call_provider(
                candidate_provider,
                user_message,
                candidate_model,
                settings,
                conversation,
            )
        except Exception as exc:
            failures.append(f"{candidate_model}: {exc}")
            logger.warning("LLM provider failed: model=%s provider=%s error=%s",
                           candidate_model, candidate_provider, exc)
            continue

        answer = (candidate.get("answer") or "").strip()
        if not answer:
            failures.append(f"{candidate_model}: empty answer")
            logger.warning("LLM provider returned empty answer: model=%s provider=%s tokens_out=%s",
                           candidate_model, candidate_provider, candidate.get("tokens_out"))
            continue

        candidate["answer"] = answer
        result = candidate
        break

    if result is None:
        if route_mode == "local":
            detail = " | ".join(failures) if failures else settings.LOCAL_LLM_BASE_URL
            raise RuntimeError(f"Local LLM unavailable for model {routed_model}. Tried: {detail}")
        if failures:
            logger.error("All configured LLM providers failed or returned empty output: %s", " | ".join(failures))
        else:
            logger.warning("No configured LLM API keys — using mock response")
        result = _mock_response(query)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    result["latency_ms"] = elapsed_ms
    result["llm_mode"] = route_mode

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
        pass

    _lf().update_current_generation(
        name=f"ask-llm/{result['model_used']}",
        model=result["model_used"],
        input=user_message,
        output=result["answer"],
        usage_details={"input": result["tokens_in"], "output": result["tokens_out"]},
        metadata={"cost_usd": result["cost_usd"], "latency_ms": result["latency_ms"], "query_len": len(query)},
    )

    result["trace_id"] = _lf().get_current_trace_id()
    return result


@observe(as_type="generation")
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

    if (not model or provider == "kimi") and settings.KIMI_API_KEY:
        from openai import AsyncOpenAI
        m = model or CHEAP_MODEL
        client = AsyncOpenAI(api_key=settings.KIMI_API_KEY, base_url=settings.KIMI_BASE_URL)
        resp = await client.chat.completions.create(
            model=m, max_tokens=max(max_tokens, KIMI_MAX_TOKENS),
            messages=[{"role": "user", "content": prompt}],
        )
        text = _chat_message_text(resp.choices[0].message)
        tok_in, tok_out = resp.usage.prompt_tokens, resp.usage.completion_tokens

    elif (not model or provider == "deepseek") and settings.DEEPSEEK_API_KEY:
        m = model or CHEAP_FALLBACK
        extra = {"thinking": {"type": "disabled"}} if m == "deepseek-v4-flash" else {}
        _hc = _get_httpx_client()
        _r = await _hc.post(
            f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}"},
            json={"model": m, "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": prompt}], **extra},
        )
        _r.raise_for_status()
        _data = _r.json()
        _msg = _data["choices"][0]["message"]
        text = _msg.get("content") or _msg.get("reasoning_content") or ""
        tok_in  = _data["usage"]["prompt_tokens"]
        tok_out = _data["usage"]["completion_tokens"]

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
        pass

    _lf().update_current_generation(
        name=f"call-llm-raw/{m}",
        model=m,
        input={"prompt_preview": prompt[:500], "prompt_chars": len(prompt)},
        output=text[:2000],
        usage_details={"input": tok_in, "output": tok_out},
        metadata={"cost_usd": _calc_cost(m, tok_in, tok_out), "max_tokens": max_tokens},
    )

    return text, tok_in, tok_out, m


async def _call_anthropic(
    user_message: str,
    model: str,
    settings: Any,
    conversation: list[dict] | None = None,
) -> dict[str, Any]:
    """Call Anthropic Claude API."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    messages = conversation or [{"role": "user", "content": user_message}]
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
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


async def _call_kimi(
    user_message: str,
    model: str,
    settings: Any,
    conversation: list[dict] | None = None,
) -> dict[str, Any]:
    """Call Kimi (Moonshot AI) API — OpenAI-compatible, 256k context window."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.KIMI_API_KEY,
        base_url=settings.KIMI_BASE_URL,
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += conversation or [{"role": "user", "content": user_message}]

    response = await client.chat.completions.create(
        model=model,
        max_tokens=KIMI_MAX_TOKENS,
        messages=messages,
    )

    usage = response.usage
    tokens_in = usage.prompt_tokens if usage else 0
    tokens_out = usage.completion_tokens if usage else 0

    return {
        "answer": _chat_message_text(response.choices[0].message),
        "model_used": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": _calc_cost(model, tokens_in, tokens_out),
    }


async def _call_deepseek(
    user_message: str,
    model: str,
    settings: Any,
    conversation: list[dict] | None = None,
) -> dict[str, Any]:
    """Call DeepSeek API (OpenAI-compatible, ~10x cheaper than Claude Haiku)."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += conversation or [{"role": "user", "content": user_message}]

    response = await client.chat.completions.create(
        model=model,
        max_tokens=DEFAULT_MAX_TOKENS,
        messages=messages,
    )

    usage = response.usage
    tokens_in = usage.prompt_tokens if usage else 0
    tokens_out = usage.completion_tokens if usage else 0

    return {
        "answer": _chat_message_text(response.choices[0].message),
        "model_used": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": _calc_cost(model, tokens_in, tokens_out),
    }


async def _call_openai(
    user_message: str,
    model: str,
    settings: Any,
    conversation: list[dict] | None = None,
) -> dict[str, Any]:
    """Call OpenAI API."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += conversation or [{"role": "user", "content": user_message}]

    response = await client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=messages,
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


async def _call_local(
    user_message: str,
    model: str,
    settings: Any,
    conversation: list[dict] | None = None,
) -> dict[str, Any]:
    """Call a local OpenAI-compatible server, typically Ollama or LM Studio."""
    from openai import AsyncOpenAI

    local_model = model.removeprefix("local:") or settings.LOCAL_LLM_MODEL
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += conversation or [{"role": "user", "content": user_message}]

    failures: list[str] = []
    for base_url in _local_base_urls(settings):
        client = AsyncOpenAI(
            api_key=settings.LOCAL_LLM_API_KEY or "local",
            base_url=base_url,
        )
        try:
            response = await client.chat.completions.create(
                model=local_model,
                max_tokens=DEFAULT_MAX_TOKENS,
                messages=messages,
            )
        except Exception as exc:
            failures.append(f"{base_url}: {exc}")
            continue

        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        return {
            "answer": _chat_message_text(response.choices[0].message),
            "model_used": local_model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": 0.0,
        }

    raise RuntimeError(
        f"Local LLM unavailable for model {local_model}. Tried: {', '.join(failures) or settings.LOCAL_LLM_BASE_URL}"
    )


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

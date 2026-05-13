#!/usr/bin/env python3
"""
DeepEval baseline runner for FinSight RAG pipeline.

Hits the live /api/chat endpoint, collects {question, answer, contexts},
runs DeepEval faithfulness + answer_relevancy, saves results, and diffs against baseline.

Usage:
    python run_eval.py                        # run and compare to baseline
    python run_eval.py --set-baseline         # run and save as new baseline
    python run_eval.py --ticker AAPL          # run only questions for one ticker
    python run_eval.py --dry-run              # print questions, no API calls
    python run_eval.py --judge deepseek       # use DeepSeek as judge (default)
    python run_eval.py --judge claude         # use Claude Haiku as judge

Requirements (install separately — not part of backend):
    pip install deepeval httpx python-dotenv
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

load_dotenv(PROJECT_ROOT / ".env")

BASE_URL = os.getenv("FINSIGHT_URL", "http://localhost:8000")
QUESTIONS_FILE = SCRIPT_DIR / "questions.json"
BASELINE_FILE = SCRIPT_DIR / "baseline_scores.json"
RESULTS_DIR = SCRIPT_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

THRESHOLDS = {
    "faithfulness": 0.85,         # generator grounding — high bar for financial data
    "answer_relevancy": 0.75,     # answer addresses the question
    "hallucination": 0.25,        # lower is better — max 25% contradicted contexts
    "contextual_relevancy": 0.30, # hard metric — section routing limits noise but can't eliminate it
    "contextual_precision": 0.50, # relevant chunks ranked first — achievable with section routing
    "contextual_recall": 0.80,    # retriever finds relevant chunks — already strong
}

# ── Custom judge model ────────────────────────────────────────────────────────

class DeepSeekJudge:
    """
    Custom DeepEvalBaseLLM wrapper for DeepSeek with max_tokens=8192.
    Required because DeepEval's default OpenAI client sends no max_tokens override,
    which causes JSON truncation on large context windows (e.g. MSFT 10 chunks).
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._built = False
        return cls._instance

    def _build(self):
        if self._built:
            return
        from deepeval.models.base_model import DeepEvalBaseLLM
        from openai import OpenAI, AsyncOpenAI

        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("ERROR: DEEPSEEK_API_KEY not set")
            sys.exit(1)

        sync_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
        async_client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

        class _Model(DeepEvalBaseLLM):
            def load_model(self):
                return sync_client

            def get_model_name(self) -> str:
                return "deepseek-chat"

            def generate(self, prompt: str, *args, **kwargs) -> str:
                resp = sync_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8192,
                )
                return resp.choices[0].message.content

            async def a_generate(self, prompt: str, *args, **kwargs) -> str:
                resp = await async_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8192,
                )
                return resp.choices[0].message.content

        self._model = _Model()
        self._built = True

    def get(self):
        self._build()
        return self._model


class ClaudeJudge:
    """Custom DeepEvalBaseLLM wrapper for Claude Haiku."""

    def _build(self):
        from deepeval.models.base_model import DeepEvalBaseLLM
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not set")
            sys.exit(1)

        client = anthropic.Anthropic(api_key=api_key)
        async_client = anthropic.AsyncAnthropic(api_key=api_key)

        class _Model(DeepEvalBaseLLM):
            def load_model(self):
                return client

            def get_model_name(self) -> str:
                return "claude-haiku-4-5-20251001"

            def generate(self, prompt: str, *args, **kwargs) -> str:
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text

            async def a_generate(self, prompt: str, *args, **kwargs) -> str:
                msg = await async_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text

        return _Model()

    def get(self):
        return self._build()


def build_metrics(judge: str):
    from deepeval.metrics import (
        FaithfulnessMetric,
        AnswerRelevancyMetric,
        HallucinationMetric,
        ContextualRelevancyMetric,
        ContextualPrecisionMetric,
        ContextualRecallMetric,
    )

    if judge == "claude":
        model = ClaudeJudge().get()
    else:
        model = DeepSeekJudge().get()

    print(f"Judge: {model.get_model_name()}")

    metrics = [
        FaithfulnessMetric(threshold=THRESHOLDS["faithfulness"], model=model, include_reason=False, verbose_mode=False),
        AnswerRelevancyMetric(threshold=THRESHOLDS["answer_relevancy"], model=model, include_reason=False, verbose_mode=False),
        HallucinationMetric(threshold=THRESHOLDS["hallucination"], model=model, include_reason=False, verbose_mode=False),
        ContextualRelevancyMetric(threshold=THRESHOLDS["contextual_relevancy"], model=model, include_reason=False, verbose_mode=False),
    ]

    # Precision + recall only run when ground_truth is present
    metrics += [
        ContextualPrecisionMetric(threshold=THRESHOLDS["contextual_precision"], model=model, include_reason=False, verbose_mode=False),
        ContextualRecallMetric(threshold=THRESHOLDS["contextual_recall"], model=model, include_reason=False, verbose_mode=False),
    ]

    return metrics

# ── API calls ─────────────────────────────────────────────────────────────────

async def check_ingested(client: httpx.AsyncClient, ticker: str) -> bool:
    try:
        r = await client.get(f"{BASE_URL}/api/health")
        r.raise_for_status()
    except Exception:
        print(f"  WARN: backend unreachable at {BASE_URL}")
        return False
    try:
        r = await client.get(f"{BASE_URL}/api/companies/{ticker}/dashboard")
        return r.status_code == 200
    except Exception:
        return False


async def ask(client: httpx.AsyncClient, ticker: str, question: str) -> dict | None:
    try:
        r = await client.post(
            f"{BASE_URL}/api/chat",
            json={"ticker": ticker, "question": question, "include_context": True},
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
        return {
            "answer": data["answer"],
            "contexts": data.get("contexts") or [],
            "model_used": data.get("model_used", ""),
            "trace_id": data.get("trace_id"),
        }
    except httpx.HTTPStatusError as e:
        print(f"  ERROR {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

# ── Collection ────────────────────────────────────────────────────────────────

async def collect_responses(questions: list[dict], ticker_filter: str | None) -> list[dict]:
    rows = []
    async with httpx.AsyncClient() as client:
        tickers = {q["ticker"] for q in questions}
        if ticker_filter:
            tickers = {ticker_filter.upper()}

        ingested = {}
        for t in tickers:
            ok = await check_ingested(client, t)
            ingested[t] = ok
            print(f"  {t}: {'ready' if ok else 'NOT INGESTED — skipping'}")
        print()

        for q in questions:
            ticker = q["ticker"]
            if ticker_filter and ticker != ticker_filter.upper():
                continue
            if not ingested.get(ticker):
                print(f"  [{q['id']}] SKIP {ticker} — not ingested")
                continue

            print(f"  [{q['id']}] {ticker}: {q['question'][:70]}...")
            result = await ask(client, ticker, q["question"])

            if result is None:
                print(f"         → FAILED")
                continue

            if not result["contexts"]:
                print(f"         → WARNING: no contexts returned")

            rows.append({
                "id": q["id"],
                "ticker": ticker,
                "user_input": q["question"],
                "response": result["answer"],
                "retrieved_contexts": result["contexts"],
                "reference": q.get("ground_truth"),
                "model_used": result["model_used"],
                "trace_id": result["trace_id"],
            })
            print(f"         → OK (model={result['model_used']}, contexts={len(result['contexts'])})")

    return rows

# ── Eval ──────────────────────────────────────────────────────────────────────

def run_deepeval(rows: list[dict], judge: str = "deepseek") -> dict:
    from deepeval.test_case import LLMTestCase
    from deepeval import evaluate
    from deepeval.evaluate.configs import DisplayConfig, CacheConfig, AsyncConfig, ErrorConfig

    samples = [r for r in rows if r["retrieved_contexts"]]
    if not samples:
        print("ERROR: no samples with contexts — cannot run eval")
        sys.exit(1)

    print(f"\nRunning DeepEval on {len(samples)} samples...")
    metrics = build_metrics(judge)

    test_cases = [
        LLMTestCase(
            input=s["user_input"],
            actual_output=s["response"],
            retrieval_context=s["retrieved_contexts"],
            context=s["retrieved_contexts"],
            expected_output=s["reference"] if s["reference"] else None,
        )
        for s in samples
    ]

    results = evaluate(
        test_cases,
        metrics,
        display_config=DisplayConfig(print_results=False, show_indicator=True),
        async_config=AsyncConfig(run_async=True, max_concurrent=5),
        cache_config=CacheConfig(write_cache=True, use_cache=True),
        error_config=ErrorConfig(ignore_errors=True),
    )

    # extract per-metric mean scores from results.test_results[].metrics_data
    metric_scores: dict[str, list[float]] = {}
    for tr in results.test_results:
        if not tr.metrics_data:
            continue
        for md in tr.metrics_data:
            metric_scores.setdefault(md.name, [])
            if md.score is not None:
                metric_scores[md.name].append(md.score)

    # metric_scores keys are DeepEval display names e.g. "Faithfulness", "Answer Relevancy"
    scores = {
        display_name.lower().replace(" ", "_"): round(sum(vals) / len(vals), 4) if vals else float("nan")
        for display_name, vals in metric_scores.items()
    }

    return scores

# ── Baseline comparison ───────────────────────────────────────────────────────

def compare_to_baseline(scores: dict) -> bool:
    passed = True
    if BASELINE_FILE.exists():
        baseline = json.loads(BASELINE_FILE.read_text())
        print("\nBaseline comparison:")
        for metric, score in scores.items():
            base = baseline.get(metric, "N/A")
            delta = f"{score - base:+.4f}" if isinstance(base, float) else "N/A"
            threshold = THRESHOLDS.get(metric, 0.0)
            lower_is_better = metric == "hallucination"
            passing = score <= threshold if lower_is_better else score >= threshold
            status = "PASS" if passing else "FAIL"
            print(f"  {metric:<25} {score:.4f}  (baseline={base}, delta={delta}) [{status}]")
            if not passing:
                passed = False
    else:
        print("\nNo baseline yet — run with --set-baseline to create one.")
        for metric, score in scores.items():
            threshold = THRESHOLDS.get(metric, 0.0)
            lower_is_better = metric == "hallucination"
            passing = score <= threshold if lower_is_better else score >= threshold
            status = "PASS" if passing else "FAIL"
            print(f"  {metric:<25} {score:.4f}  threshold={threshold} [{status}]")
            if not passing:
                passed = False
    return passed


def save_results(rows: list[dict], scores: dict):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out = RESULTS_DIR / f"{ts}.json"
    out.write_text(json.dumps({"scores": scores, "rows": rows, "timestamp": ts}, indent=2))
    print(f"\nResults saved → {out.relative_to(PROJECT_ROOT)}")

# ── CLI ───────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="FinSight DeepEval baseline runner")
    parser.add_argument("--set-baseline", action="store_true", help="Save scores as new baseline")
    parser.add_argument("--ticker", help="Run only questions for this ticker")
    parser.add_argument("--dry-run", action="store_true", help="Print questions, no API calls")
    parser.add_argument(
        "--judge",
        choices=["claude", "deepseek"],
        default="deepseek",
        help="LLM judge (default: deepseek)",
    )
    args = parser.parse_args()

    questions = json.loads(QUESTIONS_FILE.read_text())
    print(f"Loaded {len(questions)} questions from {QUESTIONS_FILE.name}")

    if args.dry_run:
        for q in questions:
            print(f"  [{q['id']}] {q['ticker']}: {q['question']}")
        return

    print(f"\nChecking ticker ingest status at {BASE_URL}...")
    rows = await collect_responses(questions, ticker_filter=args.ticker)

    if not rows:
        print("No responses collected — are the tickers ingested?")
        sys.exit(1)

    scores = run_deepeval(rows, judge=args.judge)
    print(f"\nScores: {scores}")

    save_results(rows, scores)

    if args.set_baseline:
        BASELINE_FILE.write_text(json.dumps(scores, indent=2))
        print(f"Baseline saved → {BASELINE_FILE.relative_to(PROJECT_ROOT)}")
        return

    passed = compare_to_baseline(scores)
    if not passed:
        print("\nFAIL: one or more metrics below threshold — fix retrieval before adding features")
        sys.exit(1)
    else:
        print("\nPASS: all metrics above threshold")


if __name__ == "__main__":
    asyncio.run(main())

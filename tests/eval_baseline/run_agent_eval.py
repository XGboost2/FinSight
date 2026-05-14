#!/usr/bin/env python3
"""
DeepEval agent pipeline evaluator for FinSight.

Evaluates the full LangGraph multi-agent pipeline output — not the RAG chat endpoint.
For each ticker: fetches the analysis report, retrieves filing context, and runs
DeepEval metrics against the combined agent output.

Metrics:
  Faithfulness       — do agent claims stay within filing evidence?
  Hallucination      — do claims contradict filing text?
  Answer Relevancy   — is the analysis relevant to the task?
  GEval specificity  — are bull/bear points evidence-backed, not generic?

Usage:
    python run_agent_eval.py                    # evaluate all tickers
    python run_agent_eval.py --ticker AAPL      # single ticker
    python run_agent_eval.py --set-baseline     # save as new baseline
    python run_agent_eval.py --refresh          # force fresh agent run (bypass cache)
    python run_agent_eval.py --judge claude     # use Claude as judge

Requirements:
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

SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

load_dotenv(PROJECT_ROOT / ".env")

BASE_URL       = os.getenv("FINSIGHT_URL", "http://localhost:8000")
BASELINE_FILE  = SCRIPT_DIR / "agent_baseline_scores.json"
RESULTS_DIR    = SCRIPT_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Tickers that must be ingested before running
TICKERS = ["AAPL", "MSFT", "TSLA", "GOOGL", "AMZN"]

# RAG queries used to build retrieval context (mirrors what agents retrieve)
CONTEXT_QUERIES = [
    "business overview revenue products services segments",
    "material risk factors regulatory competition cybersecurity supply chain",
    "financial performance results of operations revenue growth",
]

AGENT_THRESHOLDS = {
    "faithfulness":       0.75,  # agent synthesises, not quotes — slightly lower than RAG
    "answer_relevancy":   0.80,  # agent output should be highly task-relevant
    "hallucination":      0.40,  # agents cite XBRL + yfinance data not in RAG context — adjusted threshold
    "agent_specificity":  0.70,  # GEval — bull/bear must cite numbers, not generic claims
}


# ── Judge models (reused from run_eval.py pattern) ────────────────────────────

class DeepSeekJudge:
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

        sync_client  = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
        async_client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

        class _Model(DeepEvalBaseLLM):
            def load_model(self): return sync_client
            def get_model_name(self): return "deepseek-chat"

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
    def get(self):
        from deepeval.models.base_model import DeepEvalBaseLLM
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not set")
            sys.exit(1)

        client       = anthropic.Anthropic(api_key=api_key)
        async_client = anthropic.AsyncAnthropic(api_key=api_key)

        class _Model(DeepEvalBaseLLM):
            def load_model(self): return client
            def get_model_name(self): return "claude-haiku-4-5-20251001"

            def generate(self, prompt: str, *args, **kwargs) -> str:
                msg = client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text

            async def a_generate(self, prompt: str, *args, **kwargs) -> str:
                msg = await async_client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text

        return _Model()


def build_metrics(judge_name: str):
    from deepeval.metrics import (
        FaithfulnessMetric,
        AnswerRelevancyMetric,
        HallucinationMetric,
    )
    from deepeval.metrics import GEval
    try:
        from deepeval.test_case import SingleTurnParams as _EvalParams
    except ImportError:
        from deepeval.test_case import LLMTestCaseParams as _EvalParams  # type: ignore[no-redef]

    model = ClaudeJudge().get() if judge_name == "claude" else DeepSeekJudge().get()
    print(f"Judge: {model.get_model_name()}")

    return [
        FaithfulnessMetric(
            threshold=AGENT_THRESHOLDS["faithfulness"],
            model=model,
            include_reason=False,
            verbose_mode=False,
        ),
        AnswerRelevancyMetric(
            threshold=AGENT_THRESHOLDS["answer_relevancy"],
            model=model,
            include_reason=False,
            verbose_mode=False,
        ),
        HallucinationMetric(
            threshold=AGENT_THRESHOLDS["hallucination"],
            model=model,
            include_reason=False,
            verbose_mode=False,
        ),
        GEval(
            name="Agent Specificity",
            criteria=(
                "Evaluate whether the bull case and bear case points are specific and evidence-backed. "
                "A GOOD output: references exact numbers (e.g. revenue figures, percentages, margins), "
                "names specific business segments or products, and cites concrete filing evidence. "
                "A BAD output: uses generic statements like 'strong growth', 'competitive risks', "
                "or 'regulatory challenges' without specific evidence or numbers."
            ),
            evaluation_params=[_EvalParams.ACTUAL_OUTPUT],
            threshold=AGENT_THRESHOLDS["agent_specificity"],
            model=model,
            verbose_mode=False,
        ),
    ]


# ── API calls ─────────────────────────────────────────────────────────────────

async def fetch_analysis(client: httpx.AsyncClient, ticker: str, refresh: bool) -> dict | None:
    """Fetch the full agent analysis report."""
    params = {"refresh": "true"} if refresh else {}
    try:
        r = await client.get(
            f"{BASE_URL}/api/companies/{ticker}/analysis",
            params=params,
            timeout=httpx.Timeout(600.0, connect=15.0),
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        print(f"  ERROR {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        print(f"  ERROR fetching analysis: {type(e).__name__}: {e}")
        return None


async def fetch_context(client: httpx.AsyncClient, ticker: str) -> list[str]:
    """
    Fetch filing chunks via the chat endpoint to use as retrieval context.
    Runs 3 targeted queries and deduplicates returned chunks.
    """
    seen: set[str] = set()
    chunks: list[str] = []

    for query in CONTEXT_QUERIES:
        try:
            r = await client.post(
                f"{BASE_URL}/api/chat",
                json={"ticker": ticker, "question": query, "include_context": True},
                timeout=httpx.Timeout(60.0, connect=15.0),
            )
            r.raise_for_status()
            data = r.json()
            for ctx in data.get("contexts", []):
                text = ctx.strip() if isinstance(ctx, str) else str(ctx)
                if text and text not in seen:
                    seen.add(text)
                    chunks.append(text)
        except Exception as e:
            print(f"  WARN: context fetch failed for '{query[:40]}': {e}")

    return chunks


def build_agent_output(report: dict) -> str:
    """Combine key report fields into a single evaluable text block."""
    parts = []

    if report.get("company_overview"):
        parts.append(f"Overview: {report['company_overview']}")

    if report.get("trend_narrative"):
        parts.append(f"Financial trend: {report['trend_narrative']}")

    bull = report.get("bull_case", [])
    if bull:
        parts.append("Bull case:\n" + "\n".join(f"- {p}" for p in bull))

    bear = report.get("bear_case", [])
    if bear:
        parts.append("Bear case:\n" + "\n".join(f"- {p}" for p in bear))

    risks = report.get("risk_factors", [])
    if risks:
        parts.append("Key risks:\n" + "\n".join(f"- {r}" for r in risks))

    if report.get("management_themes"):
        parts.append(f"Management themes: {report['management_themes']}")

    if report.get("verdict"):
        parts.append(f"Verdict: {report['verdict']}")

    return "\n\n".join(parts)


# ── Collection ────────────────────────────────────────────────────────────────

async def collect(tickers: list[str], refresh: bool) -> list[dict]:
    rows = []

    async with httpx.AsyncClient() as client:
        # Check backend is up
        try:
            r = await client.get(f"{BASE_URL}/api/health", timeout=httpx.Timeout(30.0, connect=10.0))
            r.raise_for_status()
        except Exception as e:
            print(f"ERROR: backend not reachable at {BASE_URL} — {type(e).__name__}: {e}")
            sys.exit(1)

        for ticker in tickers:
            print(f"\n[{ticker}] fetching analysis{'  (refresh)' if refresh else ''}...")
            report_data = await fetch_analysis(client, ticker, refresh)

            if not report_data:
                print(f"  SKIP: no report returned")
                continue

            report = report_data.get("report") or report_data
            if not report or report.get("error"):
                print(f"  SKIP: report error — {report.get('error') if report else 'empty'}")
                continue

            pipeline = report.get("pipeline", "unknown")
            bull_n   = len(report.get("bull_case", []))
            bear_n   = len(report.get("bear_case", []))
            print(f"  report ok: pipeline={pipeline}, bull={bull_n}, bear={bear_n}")

            print(f"  fetching context chunks ({len(CONTEXT_QUERIES)} queries)...")
            chunks = await fetch_context(client, ticker)
            print(f"  got {len(chunks)} unique chunks")

            if not chunks:
                print(f"  WARN: no context chunks — faithfulness/hallucination metrics will be skipped")

            agent_output = build_agent_output(report)
            if not agent_output.strip():
                print(f"  SKIP: empty agent output")
                continue

            rows.append({
                "ticker":    ticker,
                "pipeline":  pipeline,
                "input":     f"Perform comprehensive equity analysis for {ticker} based on its SEC 10-K filing.",
                "output":    agent_output,
                "contexts":  chunks,
                "bull_n":    bull_n,
                "bear_n":    bear_n,
                "risk_score": report.get("risk_score"),
            })

    return rows


# ── Eval ──────────────────────────────────────────────────────────────────────

def run_deepeval(rows: list[dict], judge_name: str) -> dict:
    from deepeval.test_case import LLMTestCase
    from deepeval import evaluate
    from deepeval.evaluate.configs import DisplayConfig, CacheConfig, AsyncConfig, ErrorConfig

    print(f"\nRunning DeepEval on {len(rows)} agent test cases...")
    metrics = build_metrics(judge_name)

    test_cases = [
        LLMTestCase(
            input=r["input"],
            actual_output=r["output"],
            retrieval_context=r["contexts"] or None,
            context=r["contexts"] or None,
        )
        for r in rows
    ]

    results = evaluate(
        test_cases,
        metrics,
        display_config=DisplayConfig(print_results=False, show_indicator=True),
        async_config=AsyncConfig(run_async=True, max_concurrent=3),
        cache_config=CacheConfig(write_cache=True, use_cache=True),
        error_config=ErrorConfig(ignore_errors=True),
    )

    metric_scores: dict[str, list[float]] = {}
    for tr in results.test_results:
        if not tr.metrics_data:
            continue
        for md in tr.metrics_data:
            metric_scores.setdefault(md.name, [])
            if md.score is not None:
                metric_scores[md.name].append(md.score)

    return {
        name.lower().replace(" ", "_"): round(sum(vals) / len(vals), 4) if vals else float("nan")
        for name, vals in metric_scores.items()
    }


# ── Baseline comparison ───────────────────────────────────────────────────────

def compare_to_baseline(scores: dict) -> bool:
    passed = True

    if BASELINE_FILE.exists():
        baseline = json.loads(BASELINE_FILE.read_text())
        print("\nBaseline comparison:")
        for metric, score in scores.items():
            base      = baseline.get(metric, "N/A")
            delta     = f"{score - base:+.4f}" if isinstance(base, float) else "N/A"
            threshold = AGENT_THRESHOLDS.get(metric, 0.0)
            lower_is_better = metric == "hallucination"
            passing   = score <= threshold if lower_is_better else score >= threshold
            status    = "PASS" if passing else "FAIL"
            print(f"  {metric:<25} {score:.4f}  (baseline={base}, delta={delta}) [{status}]")
            if not passing:
                passed = False
    else:
        print("\nNo baseline — run with --set-baseline to create one.")
        for metric, score in scores.items():
            threshold = AGENT_THRESHOLDS.get(metric, 0.0)
            lower_is_better = metric == "hallucination"
            passing   = score <= threshold if lower_is_better else score >= threshold
            status    = "PASS" if passing else "FAIL"
            print(f"  {metric:<25} {score:.4f}  threshold={threshold} [{status}]")
            if not passing:
                passed = False

    return passed


def save_results(rows: list[dict], scores: dict):
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out = RESULTS_DIR / f"agent_{ts}.json"
    out.write_text(json.dumps({"scores": scores, "rows": rows, "timestamp": ts}, indent=2))
    print(f"\nResults saved → {out.relative_to(PROJECT_ROOT)}")


# ── CLI ───────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="FinSight agent pipeline DeepEval runner")
    parser.add_argument("--set-baseline", action="store_true", help="Save scores as new baseline")
    parser.add_argument("--ticker", help="Evaluate a single ticker only")
    parser.add_argument("--refresh", action="store_true", help="Force fresh agent run (bypass cache)")
    parser.add_argument(
        "--judge",
        choices=["deepseek", "claude"],
        default="deepseek",
        help="LLM judge model (default: deepseek)",
    )
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else TICKERS
    print(f"Agent eval: {tickers} | judge={args.judge} | refresh={args.refresh}")
    print(f"Backend: {BASE_URL}")

    rows = await collect(tickers, refresh=args.refresh)

    if not rows:
        print("No agent outputs collected — are the tickers ingested?")
        sys.exit(1)

    print(f"\nCollected {len(rows)} agent reports:")
    for r in rows:
        print(f"  {r['ticker']}: pipeline={r['pipeline']}, bull={r['bull_n']}, bear={r['bear_n']}, risk={r['risk_score']}")

    scores = run_deepeval(rows, args.judge)
    print(f"\nScores: {scores}")

    save_results(rows, scores)

    if args.set_baseline:
        BASELINE_FILE.write_text(json.dumps(scores, indent=2))
        print(f"Baseline saved → {BASELINE_FILE.relative_to(PROJECT_ROOT)}")
        return

    passed = compare_to_baseline(scores)
    if not passed:
        print("\nFAIL: agent quality below threshold — review agent prompts or retrieval")
        sys.exit(1)
    else:
        print("\nPASS: all agent metrics above threshold")


if __name__ == "__main__":
    asyncio.run(main())

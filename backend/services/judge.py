"""LLM-as-judge — evaluates ReportOutput quality on 4 dimensions using the cheap model.

Scores are pushed to Langfuse as trace-level scores so every pipeline run has
an objective quality signal in the dashboard. Never raises — a failed evaluation
returns zeros and logs a warning rather than breaking the pipeline.
"""

import json
import logging

from agents.contracts import JudgeOutput, ReportOutput
from services.llm import call_llm_raw, CHEAP_MODEL

try:
    from langfuse import get_client as _lf
except ImportError:
    class _LfStub:  # type: ignore
        def get_current_trace_id(self) -> str | None: return None
        def create_score(self, **_): pass
    _stub = _LfStub()
    def _lf(): return _stub  # type: ignore

logger = logging.getLogger(__name__)

_PROMPT = """\
You are an objective financial report evaluator. Score the following SEC 10-K analysis on 4 dimensions.

REPORT
Ticker: {ticker}
Company: {company_name}
Bull case: {bull_case}
Bear case: {bear_case}
Verdict: {verdict}
Debate winner: {debate_winner}
Risk score: {risk_score}
Risk factors: {risk_factors}

CITATIONS FROM 10-K FILING (supporting evidence)
{citations}

Score each dimension 0.0–1.0. Return ONLY valid JSON, no prose:
{{
  "faithfulness": <float, are report claims backed by the citations above?>,
  "risk_coverage": <float, are identified risks specific and filing-grounded, not generic?>,
  "debate_quality": <float, are bull/bear arguments distinct, grounded, and non-overlapping?>,
  "recommendation_clarity": <float, is the verdict actionable and well-reasoned?>,
  "rationale": "<one sentence on the weakest dimension>"
}}\
"""


async def evaluate_report(report: ReportOutput | dict) -> JudgeOutput:
    """Score a report and push scores to Langfuse. Returns JudgeOutput(zeros) on any failure."""
    if isinstance(report, dict):
        try:
            report = ReportOutput(**report)
        except Exception as exc:
            logger.warning("judge: could not parse report dict: %s", exc)
            return JudgeOutput()

    citations_text = "\n".join(
        f"[{c.item or 'SEC'}] {c.text[:200]}" for c in (report.citations or [])[:10]
    ) or "No citations available."

    prompt = _PROMPT.format(
        ticker=report.ticker,
        company_name=report.company_name,
        bull_case="; ".join(report.bull_case[:3]) or "N/A",
        bear_case="; ".join(report.bear_case[:3]) or "N/A",
        verdict=(report.verdict or "N/A")[:500],
        debate_winner=report.debate_winner or "N/A",
        risk_score=report.risk_score,
        risk_factors="; ".join(report.risk_factors[:5]) or "N/A",
        citations=citations_text,
    )

    try:
        raw, tok_in, tok_out, model_used = await call_llm_raw(
            prompt, max_tokens=300, model=CHEAP_MODEL
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

        data = json.loads(raw)
        result = JudgeOutput(
            faithfulness=float(data.get("faithfulness", 0.0)),
            risk_coverage=float(data.get("risk_coverage", 0.0)),
            debate_quality=float(data.get("debate_quality", 0.0)),
            recommendation_clarity=float(data.get("recommendation_clarity", 0.0)),
            rationale=str(data.get("rationale", "")),
            model=model_used,
            tokens_in=tok_in,
            tokens_out=tok_out,
        )
        result.overall = round(
            (result.faithfulness + result.risk_coverage +
             result.debate_quality + result.recommendation_clarity) / 4,
            3,
        )
    except Exception as exc:
        logger.warning("judge: evaluation failed: %s", exc)
        return JudgeOutput()

    _push_scores(report.ticker, result)
    return result


def _push_scores(ticker: str, judge: JudgeOutput) -> None:
    from services.observability import init_langfuse

    client = init_langfuse()
    if not client:
        return

    trace_id = _lf().get_current_trace_id()
    if not trace_id:
        logger.debug("judge: no active Langfuse trace — scores not pushed")
        return

    dimensions = {
        "judge.faithfulness": judge.faithfulness,
        "judge.risk_coverage": judge.risk_coverage,
        "judge.debate_quality": judge.debate_quality,
        "judge.recommendation_clarity": judge.recommendation_clarity,
        "judge.overall": judge.overall,
    }
    for name, value in dimensions.items():
        try:
            client.create_score(
                trace_id=trace_id,
                name=name,
                value=value,
                comment=f"{ticker}: {judge.rationale}" if name == "judge.overall" else None,
            )
        except Exception as exc:
            logger.warning("judge: Langfuse score push failed (%s): %s", name, exc)

    logger.info(
        "judge scores: ticker=%s overall=%.2f faithfulness=%.2f risk=%.2f debate=%.2f clarity=%.2f model=%s",
        ticker, judge.overall, judge.faithfulness, judge.risk_coverage,
        judge.debate_quality, judge.recommendation_clarity, judge.model,
    )

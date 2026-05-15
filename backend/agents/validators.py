"""
Semantic validators for debate agent outputs.

Each validate_* function returns a list of human-readable issues.
Empty list = output is good. Non-empty = re-prompt the agent with these issues.
"""

from agents.contracts import (
    BullCase,
    BearCase,
    PortfolioSignal,
    ReportOutput,
)


def validate_bull_case(output: BullCase, ticker: str) -> list[str]:
    issues: list[str] = []

    if len(output.points) < 3:
        issues.append(
            f"Expected 3-5 bull points, got {len(output.points)}. "
            "Add more specific, evidence-backed reasons to be bullish."
        )

    short_points = [p for p in output.points if len(p) < 30]
    if short_points:
        issues.append(
            f"{len(short_points)} point(s) are too vague/short (under 30 chars). "
            "Each point must cite specific evidence: exact numbers, segment names, or competitive moats."
        )

    if not output.key_catalyst or len(output.key_catalyst) < 10:
        issues.append(
            "key_catalyst is missing or too short. "
            "Identify the single strongest reason to buy with specific evidence."
        )

    if output.confidence == 0.5 and len(output.points) > 0:
        issues.append(
            "confidence is exactly 0.5 (the default). "
            "Based on the evidence strength, set a more precise confidence level."
        )

    return issues


def validate_bear_case(output: BearCase, ticker: str, bull_points: list[str]) -> list[str]:
    issues: list[str] = []

    if len(output.points) < 3:
        issues.append(
            f"Expected 3-5 bear points, got {len(output.points)}. "
            "Add more counter-arguments that directly challenge the bull case."
        )

    short_points = [p for p in output.points if len(p) < 30]
    if short_points:
        issues.append(
            f"{len(short_points)} point(s) are too vague/short (under 30 chars). "
            "Each point must cite specific risk factors, news, or technical warnings."
        )

    if not output.key_risk or len(output.key_risk) < 10:
        issues.append(
            "key_risk is missing or too short. "
            "Identify the single biggest unresolved threat with specific evidence."
        )

    if output.confidence == 0.5 and len(output.points) > 0:
        issues.append(
            "confidence is exactly 0.5 (the default). "
            "Set a more precise confidence based on the strength of your counter-evidence."
        )

    return issues


def validate_report(output: ReportOutput, ticker: str) -> list[str]:
    issues: list[str] = []

    if not output.company_overview or len(output.company_overview) < 20:
        issues.append(
            "company_overview is missing or too short. "
            "Write 2-3 sentences describing what the company does."
        )

    if not output.verdict or len(output.verdict) < 30:
        issues.append(
            "verdict is missing or too short. "
            "Write 2-3 sentences acknowledging both bull and bear cases before concluding."
        )

    if len(output.findings_table) < 3:
        issues.append(
            f"findings_table has only {len(output.findings_table)} rows, need at least 3. "
            "Include rows for Revenue, Profitability, and Risk at minimum."
        )

    empty_values = [r for r in output.findings_table if not r.value or r.value in ("N/A", "n/a", "")]
    if empty_values:
        issues.append(
            f"{len(empty_values)} findings row(s) have empty/N/A values. "
            "Use exact XBRL numbers from the data provided."
        )

    bad_signals = [r for r in output.findings_table if r.signal not in ("positive", "caution", "negative", "neutral")]
    if bad_signals:
        issues.append(
            f"{len(bad_signals)} findings row(s) have invalid signal values. "
            "signal must be exactly one of: positive, caution, negative, neutral."
        )

    if not output.risk_factors:
        issues.append("risk_factors list is empty. Include 2-3 key risk factors.")

    if not output.management_themes or len(output.management_themes) < 15:
        issues.append(
            "management_themes is missing or too short. "
            "Summarise key management discussion themes in 2 sentences."
        )

    return issues


def validate_portfolio_signal(output: PortfolioSignal, ticker: str) -> list[str]:
    issues: list[str] = []

    if output.signal not in ("BUY", "HOLD", "SELL"):
        issues.append(
            f"signal is '{output.signal}', must be exactly BUY, HOLD, or SELL."
        )

    if len(output.key_factors) < 2:
        issues.append(
            f"key_factors has {len(output.key_factors)} items, need at least 3. "
            "List the most important factors driving your recommendation."
        )

    if not output.rationale or len(output.rationale) < 30:
        issues.append(
            "rationale is missing or too short. "
            "Explain the recommendation in 2-3 sentences weighing all signals."
        )

    if not output.risk_reward or output.risk_reward not in ("Favorable", "Balanced", "Unfavorable"):
        issues.append(
            f"risk_reward is '{output.risk_reward}', must be Favorable, Balanced, or Unfavorable."
        )

    if output.confidence == 0.5 and output.signal != "HOLD":
        issues.append(
            "confidence is exactly 0.5 (the default) for a non-HOLD signal. "
            "A BUY or SELL recommendation should reflect stronger conviction."
        )

    return issues

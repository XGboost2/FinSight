"""
AnalysisState — typed state dict for the LangGraph analysis pipeline.

Uses Pydantic contracts from agents.contracts for all inter-node data.
Each node reads what it needs and returns a partial state update.
The `errors` field uses Annotated[list, operator.add] so parallel nodes
can each append failures without overwriting each other.
"""

import operator
from typing import Annotated, TypedDict

from agents.contracts import (
    BullCase,
    BearCase,
    FundamentalsOutput,
    NewsOutput,
    ReportOutput,
    RiskOutput,
    SentimentOutput,
    TechnicalOutput,
)


class AnalysisState(TypedDict):
    # ── Inputs (set before graph starts) ─────────────────────────────
    ticker: str
    filing_id: str
    company_info: dict           # from Redis ticker cache {name, cik, ...}

    # ── Typed analyst node outputs (set by parallel nodes) ───────────
    fundamentals: FundamentalsOutput | None
    risk: RiskOutput | None
    sentiment: SentimentOutput | None
    news: NewsOutput | None
    technical: TechnicalOutput | None

    # ── Typed debate node outputs (set sequentially) ─────────────────
    bull_case: BullCase | None
    bear_case: BearCase | None

    # ── Final output ──────────────────────────────────────────────────
    report: ReportOutput | None

    # ── Error accumulator (append-only, merged across parallel nodes) ─
    errors: Annotated[list[str], operator.add]

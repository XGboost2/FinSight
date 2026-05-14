"""
FinSight analysis pipeline — LangGraph StateGraph.

Topology:
          ┌────────┬────┬──────────┬────┬───────────┐
          ▼        ▼              ▼        ▼           ▼
  ┌──────────┐ ┌──────┐ ┌─────────┐ ┌──────┐ ┌───────────┐
  │fundament │ │ risk │ │sentiment│ │ news │ │ technical │
  │   als    │ │      │ │         │ │      │ │           │
  └──────────┘ └──────┘ └─────────┘ └──────┘ └───────────┘
          └────────┴────┴──────────┴────┴───────────┘
                                ▼
                        ┌──────────────┐
                        │   node_bull  │  ← BullResearcher agent
                        └──────────────┘
                                ▼
                        ┌──────────────┐
                        │   node_bear  │  ← BearResearcher agent
                        └──────────────┘
                                ▼
                        ┌──────────────┐
                        │  node_report │  ← ReportWriter agent
                        └──────────────┘
                                ▼
                              END

Analyst nodes run in parallel. Bull → Bear → Report run sequentially so each
agent can read the previous one's typed output. A failed analyst node does not
block the pipeline — the debate agents get empty defaults.
"""

import asyncio
import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.nodes import (
    node_fundamentals,
    node_news,
    node_risk,
    node_sentiment,
    node_technical,
    node_bull,
    node_bear,
    node_report,
)
from agents.state import AnalysisState

logger = logging.getLogger(__name__)

_graph = None
_graph_lock = asyncio.Lock()

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _build() -> Any:
    g = StateGraph(AnalysisState)

    # Analyst nodes (parallel)
    g.add_node("fundamentals", node_fundamentals)
    g.add_node("risk",         node_risk)
    g.add_node("sentiment",    node_sentiment)
    g.add_node("news",         node_news)
    g.add_node("technical",    node_technical)

    # Debate nodes (sequential)
    g.add_node("bull",   node_bull)
    g.add_node("bear",   node_bear)
    g.add_node("report", node_report)

    # Fan-out: START → all 5 analyst nodes simultaneously
    g.add_edge(START, "fundamentals")
    g.add_edge(START, "risk")
    g.add_edge(START, "sentiment")
    g.add_edge(START, "news")
    g.add_edge(START, "technical")

    # Fan-in: all 5 → bull (LangGraph waits for all before proceeding)
    g.add_edge("fundamentals", "bull")
    g.add_edge("risk",         "bull")
    g.add_edge("sentiment",    "bull")
    g.add_edge("news",         "bull")
    g.add_edge("technical",    "bull")

    # Sequential debate chain
    g.add_edge("bull",   "bear")
    g.add_edge("bear",   "report")
    g.add_edge("report", END)

    return g.compile()


async def get_graph() -> Any:
    global _graph
    if _graph is None:
        async with _graph_lock:
            if _graph is None:
                _graph = _build()
                logger.info("LangGraph analysis pipeline compiled (pydantic-ai agents)")
    return _graph


async def run_analysis(ticker: str, filing_id: str, company_info: dict) -> dict:
    """
    Execute the full analysis pipeline for a ticker.
    Returns the final AnalysisState after all nodes complete.
    The report lives at state["report"].
    """
    if not _TICKER_RE.match(ticker.upper()):
        raise ValueError(f"Invalid ticker format: {ticker}")
    graph = await get_graph()

    initial_state: AnalysisState = {
        "ticker":       ticker.upper(),
        "filing_id":    filing_id,
        "company_info": company_info or {},
        "fundamentals": None,
        "risk":         None,
        "sentiment":    None,
        "news":         None,
        "technical":    None,
        "bull_case":    None,
        "bear_case":    None,
        "report":       None,
        "errors":       [],
    }

    logger.info("LangGraph pipeline starting: ticker=%s filing_id=%s", ticker, filing_id)
    final_state = await graph.ainvoke(initial_state)

    if final_state.get("errors"):
        logger.warning(
            "Pipeline completed with %d errors for %s: %s",
            len(final_state["errors"]), ticker, final_state["errors"],
        )

    # Serialize Pydantic contracts to plain dicts for JSON-safe return
    report = final_state.get("report")
    if report is not None and hasattr(report, "model_dump"):
        final_state = dict(final_state)
        final_state["report"] = report.model_dump()

    return final_state

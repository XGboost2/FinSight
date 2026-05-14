"""
FinSight analysis pipeline — LangGraph StateGraph.

Topology:
                        ┌──────────────────┐
                        │      START       │
                        └──────────────────┘
                   ┌────────┬────┬────┬────┐
                   ▼        ▼        ▼        ▼
          ┌──────────┐ ┌──────┐ ┌─────────┐ ┌──────┐
          │fundamenta│ │ risk │ │sentiment│ │ news │
          │   ls     │ │      │ │         │ │      │
          └──────────┘ └──────┘ └─────────┘ └──────┘
                   └────────┴────┴────┴────┘
                                ▼
                        ┌──────────────┐
                        │  synthesize  │
                        └──────────────┘
                                ▼
                              END

All four analysis nodes run in parallel. LangGraph waits for all to complete
before running synthesize. Each node isolates its own errors — a failed news
fetch does not block the report generation.
"""

import asyncio
import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.nodes import node_fundamentals, node_news, node_risk, node_sentiment, node_synthesize
from agents.state import AnalysisState

logger = logging.getLogger(__name__)

_graph = None
_graph_lock = asyncio.Lock()

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _build() -> Any:
    g = StateGraph(AnalysisState)

    # Register nodes
    g.add_node("fundamentals", node_fundamentals)
    g.add_node("risk",         node_risk)
    g.add_node("sentiment",    node_sentiment)
    g.add_node("news",         node_news)
    g.add_node("synthesize",   node_synthesize)

    # Fan-out: START → all 4 parallel nodes simultaneously
    g.add_edge(START, "fundamentals")
    g.add_edge(START, "risk")
    g.add_edge(START, "sentiment")
    g.add_edge(START, "news")

    # Fan-in: all 4 nodes → synthesize (LangGraph waits for all before proceeding)
    g.add_edge("fundamentals", "synthesize")
    g.add_edge("risk",         "synthesize")
    g.add_edge("sentiment",    "synthesize")
    g.add_edge("news",         "synthesize")

    g.add_edge("synthesize", END)

    return g.compile()


async def get_graph() -> Any:
    global _graph
    if _graph is None:
        async with _graph_lock:
            if _graph is None:
                _graph = _build()
                logger.info("LangGraph analysis pipeline compiled")
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
        "ticker": ticker.upper(),
        "filing_id": filing_id,
        "company_info": company_info or {},
        "xbrl": {},
        "fundamentals_chunks": [],
        "risk_chunks": [],
        "sentiment": {},
        "news": {},
        "events": [],
        "report": {},
        "errors": [],
    }

    logger.info("LangGraph pipeline starting: ticker=%s filing_id=%s", ticker, filing_id)
    final_state = await graph.ainvoke(initial_state)

    if final_state.get("errors"):
        logger.warning(
            "LangGraph pipeline completed with %d errors for %s: %s",
            len(final_state["errors"]), ticker, final_state["errors"],
        )

    # Serialize Pydantic contracts to plain dicts for JSON-safe return
    report = final_state.get("report")
    if report is not None and hasattr(report, "model_dump"):
        final_state = dict(final_state)
        final_state["report"] = report.model_dump()

    return final_state

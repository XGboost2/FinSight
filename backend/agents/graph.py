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
                        ┌──────────────┐
                        │  portfolio   │  ← PortfolioSignal agent (BUY/HOLD/SELL)
                        └──────────────┘
                                ▼
                              END

Analyst nodes run in parallel. Bull → Bear → Report run sequentially so each
agent can read the previous one's typed output. A failed analyst node does not
block the pipeline — the debate agents get empty defaults.

Checkpoint resumption:
  Each run is keyed by thread_id = "finsight:{ticker}:{filing_id}".
  If the pipeline crashes mid-run (e.g. LLM timeout), the next call with the
  same ticker+filing resumes from the last completed node via AsyncRedisSaver.
  refresh=True uses a UUID-suffixed thread_id to guarantee a clean run.
"""

import asyncio
import logging
import re
from typing import Any
from uuid import uuid4

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
    node_portfolio,
)
from agents.state import AnalysisState

logger = logging.getLogger(__name__)

_graph = None
_graph_lock = asyncio.Lock()

_checkpointer = None
_checkpointer_lock = asyncio.Lock()

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


async def _get_checkpointer():
    """Singleton AsyncRedisSaver — created once, reused for all graph invocations."""
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    async with _checkpointer_lock:
        if _checkpointer is not None:
            return _checkpointer
        try:
            import redis.asyncio as aioredis
            from langgraph.checkpoint.redis.aio import AsyncRedisSaver
            from config import get_settings

            # Separate async client — checkpointer needs decode_responses=False
            # because LangGraph serialises checkpoint data as binary (msgpack).
            async_redis = aioredis.from_url(
                get_settings().REDIS_URL,
                decode_responses=False,
            )
            saver = AsyncRedisSaver(async_redis)
            await saver.asetup()
            _checkpointer = saver
            logger.info("LangGraph AsyncRedisSaver initialised")
        except Exception as e:
            logger.warning(
                "Checkpoint Redis unavailable (%s) — pipeline runs without crash recovery", e
            )
            _checkpointer = None  # explicitly mark as failed so we don't retry every call
    return _checkpointer


def _build(checkpointer=None) -> Any:
    g = StateGraph(AnalysisState)

    # Analyst nodes (parallel)
    g.add_node("fundamentals", node_fundamentals)
    g.add_node("risk",         node_risk)
    g.add_node("sentiment",    node_sentiment)
    g.add_node("news",         node_news)
    g.add_node("technical",    node_technical)

    # Debate nodes (sequential)
    g.add_node("bull",      node_bull)
    g.add_node("bear",      node_bear)
    g.add_node("report",    node_report)
    g.add_node("portfolio", node_portfolio)

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

    # Sequential debate chain → portfolio signal
    g.add_edge("bull",      "bear")
    g.add_edge("bear",      "report")
    g.add_edge("report",    "portfolio")
    g.add_edge("portfolio", END)

    return g.compile(checkpointer=checkpointer)


async def get_graph() -> Any:
    global _graph
    if _graph is None:
        async with _graph_lock:
            if _graph is None:
                checkpointer = await _get_checkpointer()
                _graph = _build(checkpointer=checkpointer)
                logger.info(
                    "LangGraph analysis pipeline compiled (checkpointer=%s)",
                    "AsyncRedisSaver" if checkpointer else "none",
                )
    return _graph


async def run_analysis(
    ticker: str,
    filing_id: str,
    company_info: dict,
    refresh: bool = False,
) -> dict:
    """
    Execute the full analysis pipeline for a ticker.
    Returns the final AnalysisState after all nodes complete.
    The report lives at state["report"].

    thread_id is stable per ticker+filing so a crashed run can resume.
    refresh=True appends a UUID suffix to force a clean run.
    """
    if not _TICKER_RE.match(ticker.upper()):
        raise ValueError(f"Invalid ticker format: {ticker}")
    graph = await get_graph()

    thread_id = f"finsight:{ticker.upper()}:{filing_id}"
    if refresh:
        thread_id = f"{thread_id}:{uuid4().hex[:8]}"

    config: dict = {"configurable": {"thread_id": thread_id}} if _checkpointer else {}

    initial_state: AnalysisState = {
        "ticker":         ticker.upper(),
        "filing_id":      filing_id,
        "company_info":   company_info or {},
        "fundamentals":   None,
        "risk":           None,
        "sentiment":      None,
        "news":           None,
        "technical":      None,
        "bull_case":      None,
        "bear_case":      None,
        "report":         None,
        "portfolio_signal": None,
        "errors":         [],
    }

    logger.info(
        "LangGraph pipeline starting: ticker=%s filing_id=%s thread_id=%s",
        ticker, filing_id, thread_id if config else "none",
    )
    final_state = await graph.ainvoke(initial_state, config=config)

    if final_state.get("errors"):
        logger.warning(
            "Pipeline completed with %d errors for %s: %s",
            len(final_state["errors"]), ticker, final_state["errors"],
        )

    # Serialize Pydantic contracts to plain dicts for JSON-safe return
    final_state = dict(final_state)
    report = final_state.get("report")
    if report is not None and hasattr(report, "model_dump"):
        final_state["report"] = report.model_dump()

    ps = final_state.get("portfolio_signal")
    if ps is not None and hasattr(ps, "model_dump"):
        ps_dict = ps.model_dump()
        final_state["portfolio_signal"] = ps_dict
        if isinstance(final_state["report"], dict):
            final_state["report"]["portfolio_signal"] = ps_dict

    return final_state

"""Tool-calling trading agent — natural language → Trading 212 orders.

Unlike the analyst agents (synthesis-only, single LLM call, no tool loops), this
agent genuinely loops: it decides which broker tools to call and in what order to
turn "buy 10 shares of apple" into a placed order. This is the one place where a
ReAct-style tool loop earns its extra cost — the steps can't be pre-computed.

Safety: execution is gated by a two-stage `confirm` flag. With confirm=False the
agent plans the order and returns it for review without touching money. The broker
client adds a second, independent guard against live-host orders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from agents.analyst_agents import _make_model
from services import trading212

logger = logging.getLogger(__name__)


@dataclass
class TradeDeps:
    """Per-run state. confirm=True authorises real order placement."""
    confirm: bool = False


_SYSTEM_PROMPT = (
    "You are FinSight's trading assistant for a Trading 212 account (paper/demo "
    "by default). Translate the user's instruction into equity orders.\n\n"
    "Workflow for any trade:\n"
    "1. Call resolve_instrument to get the exact Trading 212 ticker.\n"
    "2. For a BUY, call get_account to confirm there are sufficient free funds.\n"
    "3. Call place_market_order. Positive quantity buys, negative quantity sells.\n\n"
    "Rules:\n"
    "- If an instrument cannot be resolved, say so and do not guess a ticker.\n"
    "- Always state the resolved ticker and the exact signed quantity you used.\n"
    "- If place_market_order returns status NOT_EXECUTED, report the proposed order "
    "and tell the user to confirm — never claim a trade happened when it did not.\n"
    "- Be concise. Report order id and status on success."
)

_trading_agent: Agent[TradeDeps, str] | None = None


def get_trading_agent() -> Agent[TradeDeps, str]:
    global _trading_agent
    if _trading_agent is not None:
        return _trading_agent

    agent: Agent[TradeDeps, str] = Agent(
        model=_make_model(),
        deps_type=TradeDeps,
        retries=2,
        system_prompt=_SYSTEM_PROMPT,
    )

    @agent.tool
    async def resolve_instrument(ctx: RunContext[TradeDeps], query: str) -> dict:
        """Resolve a company name or symbol to a Trading 212 instrument."""
        inst = await trading212.resolve_instrument(query)
        if not inst:
            return {"error": f"No tradable instrument found for '{query}'"}
        return {
            "ticker": inst.get("ticker"),
            "name": inst.get("name"),
            "currency": inst.get("currencyCode") or inst.get("currency"),
        }

    @agent.tool
    async def get_account(ctx: RunContext[TradeDeps]) -> dict:
        """Account cash/investment summary in the main account currency."""
        return await trading212.get_account_summary()

    @agent.tool
    async def get_open_positions(ctx: RunContext[TradeDeps]) -> list[dict]:
        """Current open positions (for sell sizing and portfolio questions)."""
        return await trading212.get_positions()

    @agent.tool
    async def place_market_order(
        ctx: RunContext[TradeDeps],
        ticker: str,
        quantity: float,
    ) -> dict:
        """Place a market order. Positive quantity buys, negative sells.

        Only executes when the run was started with confirm=True; otherwise it
        returns the proposed order for the user to confirm.
        """
        if not ctx.deps.confirm:
            logger.info("Trade proposed (unconfirmed): %s qty=%s", ticker, quantity)
            return {
                "status": "NOT_EXECUTED",
                "reason": "confirmation_required",
                "proposed_order": {"ticker": ticker, "quantity": quantity},
            }
        result = await trading212.place_market_order(ticker, quantity)
        return {"status": "EXECUTED", "order": result}

    _trading_agent = agent
    return agent


async def run_trade(instruction: str, confirm: bool = False) -> str:
    """Run the trading agent against a natural-language instruction.

    confirm=False (default) plans the order without executing.
    confirm=True authorises real order placement.
    """
    agent = get_trading_agent()
    result = await agent.run(instruction, deps=TradeDeps(confirm=confirm))
    logger.info("run_trade done: confirm=%s instruction=%r", confirm, instruction[:80])
    return result.output

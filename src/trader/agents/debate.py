"""Parallel bull vs bear debate agents."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from trader.agents.client import AnthropicAgent, load_prompt
from trader.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Case:
    ticker: str
    side: str  # "bull" | "bear"
    text: str


def _user_payload(ticker: str, ctx: dict) -> str:
    return f"Ticker: {ticker}\n\nContext:\n{json.dumps(ctx, indent=2, default=str)}"


async def _one_case(
    agent: AnthropicAgent, ticker: str, ctx: dict, *, side: str
) -> Case:
    system = load_prompt(side)
    resp = await agent.complete(
        model=settings.model_debate,
        system=system,
        user=_user_payload(ticker, ctx),
        max_tokens=800,
    )
    return Case(ticker=ticker, side=side, text=resp["text"])


async def debate(
    agent: AnthropicAgent, ticker_contexts: dict[str, dict]
) -> dict[str, dict[str, str]]:
    """Return {ticker: {"bull": str, "bear": str}} for every input ticker."""
    tasks = []
    for ticker, ctx in ticker_contexts.items():
        tasks.append(_one_case(agent, ticker, ctx, side="bull"))
        tasks.append(_one_case(agent, ticker, ctx, side="bear"))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: dict[str, dict[str, str]] = {t: {} for t in ticker_contexts}
    for r in results:
        if isinstance(r, Exception):
            logger.warning("debate call failed: %s", r)
            continue
        out[r.ticker][r.side] = r.text
    return out

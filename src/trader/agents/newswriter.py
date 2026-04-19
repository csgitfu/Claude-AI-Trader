"""Daily News Scan: markdown report mirroring the reference format."""

from __future__ import annotations

import json
from datetime import date

from trader.agents.client import AnthropicAgent, load_prompt
from trader.config import settings


async def write(
    agent: AnthropicAgent,
    *,
    as_of: date,
    holdings_with_sectors: list[dict],
    sector_pct: dict[str, float],
    market_headlines: list[dict],
    holding_headlines: dict[str, list[dict]],
    macro: dict,
    portfolio_commentary: str = "",
) -> str:
    system = load_prompt("newswriter")
    payload = {
        "as_of": as_of.isoformat(),
        "holdings": holdings_with_sectors,
        "sector_pct": {k: round(v, 4) for k, v in sector_pct.items()},
        "macro": macro,
        "market_headlines": market_headlines,
        "holding_headlines": holding_headlines,
        "portfolio_commentary": portfolio_commentary,
    }
    resp = await agent.complete(
        model=settings.model_newswriter,
        system=system,
        user=json.dumps(payload, default=str),
        max_tokens=2000,
    )
    return resp["text"]

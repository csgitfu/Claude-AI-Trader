"""Final selector: picks 15 names with weights, subject to constraint enforcement."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from trader.agents.client import AnthropicAgent, load_prompt
from trader.agents.probability import Estimate
from trader.config import settings
from trader.portfolio.risk import Proposal, enforce

logger = logging.getLogger(__name__)

TOOL = {
    "name": "build_portfolio",
    "description": "Select exactly 15 stocks with target weights summing to 1.0.",
    "input_schema": {
        "type": "object",
        "properties": {
            "picks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "weight": {"type": "number", "minimum": 0, "maximum": 0.25},
                        "sector": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["ticker", "weight", "sector", "rationale"],
                },
            },
            "commentary": {"type": "string"},
        },
        "required": ["picks", "commentary"],
    },
}


@dataclass
class Selection:
    proposals: list[Proposal]
    commentary: str
    rationales: dict[str, str]


def _payload(estimates: list[Estimate], current: dict[str, float], macro: dict) -> dict:
    return {
        "candidates": [
            {
                "ticker": e.ticker,
                "p_up": round(e.p_up, 3),
                "p_flat": round(e.p_flat, 3),
                "p_down": round(e.p_down, 3),
                "expected_return": round(e.expected_return, 4),
                "implied_vol": round(e.implied_vol, 3),
                "conviction": e.conviction,
                "summary": e.summary,
            }
            for e in estimates
        ],
        "current_holdings": current,
        "macro": macro,
        "constraints": {
            "portfolio_size": settings.portfolio_size,
            "max_weight_per_name": settings.max_weight_per_name,
            "max_weight_per_sector": settings.max_weight_per_sector,
            "min_sectors": settings.min_sectors,
        },
    }


async def select(
    agent: AnthropicAgent,
    estimates: list[Estimate],
    current_weights: dict[str, float],
    macro: dict,
    sector_of: dict[str, str],
) -> Selection:
    system = load_prompt("selector")
    resp = await agent.complete(
        model=settings.model_selector,
        system=system,
        user=json.dumps(_payload(estimates, current_weights, macro), default=str),
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "build_portfolio"},
        max_tokens=3000,
    )
    if not resp["tool_use"]:
        raise RuntimeError("selector returned no tool_use")
    data = resp["tool_use"]["input"]

    raw_picks = []
    for p in data.get("picks", []):
        tkr = p["ticker"].upper()
        raw_picks.append(
            Proposal(
                ticker=tkr,
                weight=float(p["weight"]),
                sector=p.get("sector") or sector_of.get(tkr, "Unknown"),
                rationale=p.get("rationale", ""),
            )
        )
    projected = enforce(raw_picks)
    return Selection(
        proposals=projected,
        commentary=data.get("commentary", ""),
        rationales={p.ticker: p.rationale for p in projected},
    )

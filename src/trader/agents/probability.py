"""Probability-weighted return model per ticker. Output normalized post-hoc."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from trader.agents.client import AnthropicAgent, load_prompt
from trader.config import settings

logger = logging.getLogger(__name__)

TOOL = {
    "name": "probability_estimate",
    "description": "Emit a 6-month probability-weighted return distribution for one stock.",
    "input_schema": {
        "type": "object",
        "properties": {
            "p_up_6m": {"type": "number", "minimum": 0, "maximum": 1},
            "p_flat_6m": {"type": "number", "minimum": 0, "maximum": 1},
            "p_down_6m": {"type": "number", "minimum": 0, "maximum": 1},
            "expected_return": {"type": "number"},
            "implied_vol": {"type": "number", "minimum": 0.05, "maximum": 2.0},
            "conviction": {"type": "integer", "minimum": 1, "maximum": 5},
            "summary": {"type": "string"},
        },
        "required": [
            "p_up_6m",
            "p_flat_6m",
            "p_down_6m",
            "expected_return",
            "implied_vol",
            "conviction",
        ],
    },
}


@dataclass
class Estimate:
    ticker: str
    p_up: float
    p_flat: float
    p_down: float
    expected_return: float
    implied_vol: float
    conviction: int
    summary: str


def _normalize(e: Estimate) -> Estimate:
    total = e.p_up + e.p_flat + e.p_down
    if total <= 0:
        e.p_up, e.p_flat, e.p_down = 1 / 3, 1 / 3, 1 / 3
    else:
        e.p_up, e.p_flat, e.p_down = e.p_up / total, e.p_flat / total, e.p_down / total
    # sanity clamps
    e.implied_vol = max(0.10, min(1.50, e.implied_vol))
    e.expected_return = max(-0.9, min(1.5, e.expected_return))
    e.conviction = max(1, min(5, int(e.conviction)))
    return e


async def _one(agent: AnthropicAgent, ticker: str, payload: dict) -> Estimate | None:
    system = load_prompt("probability")
    resp = await agent.complete(
        model=settings.model_probability,
        system=system,
        user=json.dumps(payload, default=str),
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "probability_estimate"},
        max_tokens=800,
    )
    if not resp["tool_use"]:
        return None
    d = resp["tool_use"]["input"]
    return _normalize(
        Estimate(
            ticker=ticker,
            p_up=float(d["p_up_6m"]),
            p_flat=float(d["p_flat_6m"]),
            p_down=float(d["p_down_6m"]),
            expected_return=float(d["expected_return"]),
            implied_vol=float(d["implied_vol"]),
            conviction=int(d["conviction"]),
            summary=d.get("summary", ""),
        )
    )


async def estimate(
    agent: AnthropicAgent, payloads: dict[str, dict]
) -> list[Estimate]:
    results = await asyncio.gather(
        *(_one(agent, t, p) for t, p in payloads.items()), return_exceptions=True
    )
    out: list[Estimate] = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("probability failed: %s", r)
        elif r is not None:
            out.append(r)
    return out

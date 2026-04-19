"""Haiku-powered 0–100 scorer. Batched, tool-use structured output."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from trader.agents.client import AnthropicAgent, load_prompt
from trader.config import settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 25

TOOL = {
    "name": "score_stock",
    "description": "Emit a score for each ticker in the batch.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "one_liner": {"type": "string"},
                        "flags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["ticker", "score", "one_liner"],
                },
            }
        },
        "required": ["scores"],
    },
}


@dataclass
class Score:
    ticker: str
    score: int
    one_liner: str
    flags: list[str]


def _format_batch(batch: list[dict]) -> str:
    lines = ["Score each of the following tickers. Return exactly one entry per ticker."]
    for row in batch:
        lines.append(json.dumps(row, default=str))
    return "\n".join(lines)


async def _score_batch(agent: AnthropicAgent, system: str, batch: list[dict]) -> list[Score]:
    resp = await agent.complete(
        model=settings.model_scorer,
        system=system,
        user=_format_batch(batch),
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "score_stock"},
        max_tokens=2000,
    )
    if not resp["tool_use"]:
        logger.warning("scorer: no tool_use returned; dropping batch of %d", len(batch))
        return []
    out = []
    for entry in resp["tool_use"]["input"].get("scores", []):
        out.append(
            Score(
                ticker=entry["ticker"].upper(),
                score=int(entry["score"]),
                one_liner=entry.get("one_liner", ""),
                flags=entry.get("flags", []),
            )
        )
    return out


async def score_universe(agent: AnthropicAgent, rows: list[dict]) -> list[Score]:
    system = load_prompt("scorer")
    batches = [rows[i : i + BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    logger.info("scoring %d tickers in %d batches", len(rows), len(batches))
    results = await asyncio.gather(*(_score_batch(agent, system, b) for b in batches))
    return [s for batch in results for s in batch]


def build_input_rows(
    tickers: list[str],
    fundamentals: dict[str, dict],
    momentum: dict[str, dict],
    realized_vol: dict[str, float],
) -> list[dict]:
    rows = []
    for t in tickers:
        f = fundamentals.get(t) or {}
        m = momentum.get(t) or {}
        rows.append(
            {
                "ticker": t,
                "sector": f.get("sector"),
                "industry": f.get("industry"),
                "marketCap": f.get("marketCap"),
                "trailingPE": f.get("trailingPE"),
                "forwardPE": f.get("forwardPE"),
                "ps": f.get("priceToSalesTrailing12Months"),
                "grossMargin": f.get("grossMargins"),
                "profitMargin": f.get("profitMargins"),
                "roe": f.get("returnOnEquity"),
                "debtEquity": f.get("debtToEquity"),
                "revenueGrowth": f.get("revenueGrowth"),
                "earningsGrowth": f.get("earningsGrowth"),
                "beta": f.get("beta"),
                "ret_1m": m.get("1m"),
                "ret_6m": m.get("6m"),
                "ret_12m": m.get("12m"),
                "ann_vol": realized_vol.get(t),
            }
        )
    return rows

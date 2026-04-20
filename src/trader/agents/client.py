"""Shared Anthropic client: rate-limited, token-accounted, prompt-cached.

- Concurrency capped by `settings.agent_concurrency` via an asyncio.Semaphore.
- Exponential backoff on 429 / 5xx via tenacity.
- Every call appended to `logs/YYYY-MM-DD.jsonl` with token counts and cost estimate.
- System prompts go through `cache_control` to cut per-call input cost.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from trader.config import settings

logger = logging.getLogger(__name__)

# Rough public-listed pricing per 1M tokens (input / output). Update as needed.
_PRICES = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}


def _estimate_cost(model: str, in_tok: int, out_tok: int) -> float:
    in_p, out_p = _PRICES.get(model, (3.0, 15.0))
    return (in_tok / 1e6) * in_p + (out_tok / 1e6) * out_p


class AnthropicAgent:
    def __init__(self, api_key: str | None = None, concurrency: int | None = None):
        key = api_key or settings.anthropic_api_key
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self._client = AsyncAnthropic(api_key=key)
        self._sem = asyncio.Semaphore(concurrency or settings.agent_concurrency)
        self.total_cost = 0.0
        self.total_in = 0
        self.total_out = 0

    def _log(self, entry: dict) -> None:
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        fp: Path = settings.logs_dir / f"{datetime.now(timezone.utc).date().isoformat()}.jsonl"
        with fp.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(4),
        wait=wait_exponential(min=2, max=30),
        reraise=True,
    )
    async def _call(self, **kwargs: Any):
        return await self._client.messages.create(**kwargs)

    async def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        max_tokens: int = 1500,
        cache_system: bool = True,
    ) -> dict:
        """Send a single message; return {text, tool_use, usage, cost}."""
        sys_block: list[dict] | str
        if cache_system:
            sys_block = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        else:
            sys_block = system

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": sys_block,
            "messages": [{"role": "user", "content": user}],
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        t0 = time.time()
        async with self._sem:
            msg = await self._call(**kwargs)
        dt = time.time() - t0

        text_parts: list[str] = []
        tool_use: dict | None = None
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            elif getattr(block, "type", None) == "tool_use":
                tool_use = {"name": block.name, "input": block.input}

        usage = getattr(msg, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) if usage else 0
        out_tok = getattr(usage, "output_tokens", 0) if usage else 0
        cost = _estimate_cost(model, in_tok, out_tok)
        self.total_cost += cost
        self.total_in += in_tok
        self.total_out += out_tok

        self._log(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "model": model,
                "latency_s": round(dt, 2),
                "in_tokens": in_tok,
                "out_tokens": out_tok,
                "cost_usd": round(cost, 4),
                "tool": tool_use["name"] if tool_use else None,
            }
        )

        return {
            "text": "\n".join(text_parts).strip(),
            "tool_use": tool_use,
            "usage": {"in": in_tok, "out": out_tok},
            "cost": cost,
        }


def load_prompt(name: str) -> str:
    path = settings.prompts_dir / f"{name}.md"
    return path.read_text()

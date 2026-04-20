"""Telegram bot publisher.

Uses the raw HTTP API (no python-telegram-bot dependency). Splits long messages
into 4000-char chunks (Telegram limit is 4096). Uses plain-text `parse_mode=None`
by default to avoid Markdown escaping headaches with financial symbols.
"""

from __future__ import annotations

import logging

import requests

from trader.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000

FOOTER = "\n\n_Educational simulation. Not investment advice._"


def _enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def _chunks(text: str) -> list[str]:
    if len(text) <= MAX_LEN:
        return [text]
    out = []
    remaining = text
    while len(remaining) > MAX_LEN:
        # prefer splitting at a newline
        cut = remaining.rfind("\n", 0, MAX_LEN)
        if cut <= 0:
            cut = MAX_LEN
        out.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        out.append(remaining)
    return out


def send(text: str, *, dry_run: bool = False) -> bool:
    if dry_run or not _enabled():
        logger.info("telegram: dry_run or not configured; skipping (%d chars)", len(text))
        return False
    url = API_BASE.format(token=settings.telegram_bot_token, method="sendMessage")
    body = text + FOOTER
    for chunk in _chunks(body):
        resp = requests.post(
            url,
            data={"chat_id": settings.telegram_chat_id, "text": chunk, "disable_web_page_preview": True},
            timeout=20,
        )
        if not resp.ok:
            logger.error("telegram send failed: %s %s", resp.status_code, resp.text[:400])
            return False
    return True


def send_error(exc: BaseException, context: str = "") -> None:
    if not _enabled():
        return
    text = f"🚨 Claude-AI-Trader error ({context}): {type(exc).__name__}: {exc}"
    send(text)

"""News gathering: yfinance per-ticker headlines + Google News RSS for market wraps."""

from __future__ import annotations

import logging
from urllib.parse import quote

import feedparser
import yfinance as yf

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def ticker_headlines(ticker: str, limit: int = 10) -> list[dict]:
    try:
        items = yf.Ticker(ticker).news or []
    except Exception as exc:
        logger.warning("yfinance news failed for %s: %s", ticker, exc)
        items = []
    out = []
    for it in items[:limit]:
        # yfinance shape changes across versions; coerce defensively
        content = it.get("content") or it
        title = content.get("title") or it.get("title") or ""
        publisher = (content.get("provider") or {}).get("displayName") or it.get("publisher") or ""
        link = content.get("canonicalUrl", {}).get("url") or it.get("link") or ""
        if title:
            out.append({"title": title, "publisher": publisher, "link": link})
    return out


def rss_headlines(query: str, limit: int = 10) -> list[dict]:
    feed = feedparser.parse(GOOGLE_NEWS_RSS.format(q=quote(query)))
    out = []
    for entry in feed.entries[:limit]:
        out.append(
            {
                "title": getattr(entry, "title", ""),
                "publisher": getattr(entry, "source", {}).get("title", "")
                if isinstance(getattr(entry, "source", {}), dict)
                else "",
                "link": getattr(entry, "link", ""),
            }
        )
    return out


def market_headlines(limit: int = 20) -> list[dict]:
    return rss_headlines("stock market", limit=limit)

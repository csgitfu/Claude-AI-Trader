"""News gathering: yfinance per-ticker headlines + Google News RSS for market wraps."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from urllib.parse import quote
from urllib.request import urlopen, Request

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
    url = GOOGLE_NEWS_RSS.format(q=quote(query))
    out = []
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        ns = {"source": "http://www.google.com/schemas/rss/1.0/modules/source/"}
        items = root.findall(".//item")
        for item in items[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source_el = item.find("source")
            publisher = source_el.text.strip() if source_el is not None and source_el.text else ""
            if title:
                out.append({"title": title, "publisher": publisher, "link": link})
    except Exception as exc:
        logger.warning("RSS fetch failed for %r: %s", query, exc)
    return out


def market_headlines(limit: int = 20) -> list[dict]:
    return rss_headlines("stock market", limit=limit)

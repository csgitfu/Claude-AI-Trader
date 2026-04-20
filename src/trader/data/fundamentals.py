"""Per-ticker fundamentals with a persistent last-good cache fallback.

yfinance fundamentals are flaky; on every fetch failure we return whatever we
stored most recently. The cache survives across runs because it's committed to
the repo at `data/fundamentals_cache.json`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import yfinance as yf

from trader.config import settings

logger = logging.getLogger(__name__)

FIELDS = [
    "sector",
    "industry",
    "marketCap",
    "trailingPE",
    "forwardPE",
    "priceToSalesTrailing12Months",
    "grossMargins",
    "profitMargins",
    "returnOnEquity",
    "debtToEquity",
    "freeCashflow",
    "revenueGrowth",
    "earningsGrowth",
    "dividendYield",
    "beta",
]


def _load_cache() -> dict:
    if settings.fundamentals_cache_path.exists():
        return json.loads(settings.fundamentals_cache_path.read_text())
    return {}


def _save_cache(cache: dict) -> None:
    settings.fundamentals_cache_path.parent.mkdir(parents=True, exist_ok=True)
    settings.fundamentals_cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))


def fetch_one(ticker: str, cache: dict | None = None) -> dict:
    cache = _load_cache() if cache is None else cache
    try:
        info = yf.Ticker(ticker).info or {}
        snap = {k: info.get(k) for k in FIELDS if info.get(k) is not None}
        if snap:
            snap["_asof"] = datetime.now(timezone.utc).isoformat()
            cache[ticker] = snap
            return snap
    except Exception as exc:
        logger.warning("fundamentals fetch failed for %s: %s", ticker, exc)
    return cache.get(ticker, {})


def fetch_many(tickers: list[str]) -> dict[str, dict]:
    cache = _load_cache()
    out: dict[str, dict] = {}
    for t in tickers:
        out[t] = fetch_one(t, cache)
    _save_cache(cache)
    return out


def sector_map(tickers: list[str]) -> dict[str, str]:
    fund = fetch_many(tickers)
    return {t: (fund.get(t) or {}).get("sector") or "Unknown" for t in tickers}

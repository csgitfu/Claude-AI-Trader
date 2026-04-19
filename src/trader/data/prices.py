"""Batched price fetches via yfinance.

Single-ticker `Ticker.info` calls are fragile and rate-limited. `yf.download`
with a list of tickers makes one HTTP request and returns a wide DataFrame.
"""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
def download_history(tickers: list[str], period: str = "1y") -> pd.DataFrame:
    """Return a wide Close-price DataFrame indexed by date, columns=tickers."""
    data = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if data is None or data.empty:
        raise RuntimeError(f"yfinance returned empty frame for {len(tickers)} tickers")

    if isinstance(data.columns, pd.MultiIndex):
        closes = {}
        for t in tickers:
            if t in data.columns.get_level_values(0):
                closes[t] = data[t]["Close"]
        return pd.DataFrame(closes).dropna(how="all")
    return data[["Close"]].rename(columns={"Close": tickers[0]})


def latest_close(tickers: list[str]) -> dict[str, float]:
    hist = download_history(tickers, period="5d")
    latest = hist.ffill().iloc[-1]
    return {t: float(latest[t]) for t in tickers if t in latest.index and pd.notna(latest[t])}


def realized_vol(prices: pd.DataFrame, window: int = 90) -> dict[str, float]:
    rets = prices.pct_change().dropna(how="all")
    tail = rets.tail(window)
    ann = tail.std() * (252 ** 0.5)
    return {t: float(v) for t, v in ann.items() if pd.notna(v)}


def momentum(prices: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Return 1m/6m/12m trailing returns per ticker."""
    out: dict[str, dict[str, float]] = {}
    if prices.empty:
        return out
    last = prices.ffill().iloc[-1]
    for t in prices.columns:
        row: dict[str, float] = {}
        for label, lookback in (("1m", 21), ("6m", 126), ("12m", 252)):
            if len(prices) > lookback and pd.notna(prices[t].iloc[-lookback - 1]):
                row[label] = float(last[t] / prices[t].iloc[-lookback - 1] - 1.0)
        if row:
            out[t] = row
    return out

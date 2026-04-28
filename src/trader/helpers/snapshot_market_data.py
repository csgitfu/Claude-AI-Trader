"""Snapshot prices, fundamentals, momentum, volatility to JSON.

Modes:
  --mode full              All universe tickers (for weekly rebalance)
  --mode holdings-only     Current ledger holdings + SPY (for daily scan)

Usage:
    python -m trader.helpers.snapshot_market_data --mode full --out data/runs/2026-04-28/market_data.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trader import universe
from trader.config import settings
from trader.data import fundamentals, prices
from trader.portfolio.ledger import Ledger


def _resolve_tickers(mode: str, override: str | None) -> list[str]:
    if override:
        return [t.strip() for t in override.split(",") if t.strip()]
    if mode == "full":
        df = universe.fetch_universe()
        return universe.tickers(df) + ["SPY"]
    if mode == "holdings-only":
        if settings.ledger_path.exists():
            led = Ledger.load()
            return list(led.positions) + ["SPY"]
        return ["SPY"]
    raise ValueError(f"unknown mode: {mode}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["full", "holdings-only"], required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tickers", help="comma-separated override (test use)")
    args = p.parse_args(argv)

    tickers = _resolve_tickers(args.mode, args.tickers)
    hist = prices.download_history(tickers, period="1y")

    spy_close = None
    if "SPY" in hist.columns:
        spy_close = float(hist["SPY"].ffill().iloc[-1])
        hist = hist.drop(columns=["SPY"])

    if hist.empty or len(hist.columns) == 0:
        closes: dict = {}
        mom: dict = {}
        vol: dict = {}
    else:
        closes = prices.latest_close(list(hist.columns))
        mom = prices.momentum(hist)
        vol = prices.realized_vol(hist)

    fund: dict = {}
    if args.mode == "full":
        fund = fundamentals.fetch_many([t for t in tickers if t != "SPY"])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "closes": closes,
        "momentum": mom,
        "vol": vol,
        "fundamentals": fund,
        "spy_close": spy_close,
    }, indent=2, default=str))
    print(f"wrote market data for {len(closes)} tickers to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

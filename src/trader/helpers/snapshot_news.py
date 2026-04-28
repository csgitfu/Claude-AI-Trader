"""Snapshot market and per-ticker headlines, plus macro indicators.

Usage:
    python -m trader.helpers.snapshot_news \\
        --mode {full|holdings-only} \\
        --out-news data/runs/<date>/news.json \\
        --out-macro data/runs/<date>/macro.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trader.config import settings
from trader.data import macro, news
from trader.portfolio.ledger import Ledger


def _resolve_tickers(mode: str, override: str | None, shortlist_path: str | None) -> list[str]:
    if override:
        return [t.strip() for t in override.split(",") if t.strip()]
    if mode == "full":
        if shortlist_path:
            return json.loads(Path(shortlist_path).read_text())["tickers"]
        return []
    if mode == "holdings-only":
        if settings.ledger_path.exists():
            return list(Ledger.load().positions)
        return []
    raise ValueError(mode)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["full", "holdings-only"], required=True)
    p.add_argument("--out-news", required=True)
    p.add_argument("--out-macro", required=True)
    p.add_argument("--tickers", help="comma-separated override (test use)")
    p.add_argument("--shortlist", help="path to shortlist.json (full mode)")
    args = p.parse_args(argv)

    tickers = _resolve_tickers(args.mode, args.tickers, args.shortlist)

    market = news.market_headlines(limit=15)
    per_ticker = {t: news.ticker_headlines(t, limit=8) for t in tickers}

    Path(args.out_news).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_news).write_text(json.dumps({
        "market": market,
        "tickers": per_ticker,
    }, indent=2, default=str))

    snap = macro.snapshot()
    Path(args.out_macro).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_macro).write_text(json.dumps(snap, indent=2, default=str))

    print(f"wrote {len(per_ticker)} tickers' headlines to {args.out_news}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

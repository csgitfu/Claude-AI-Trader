"""Command-line interface: `python -m trader <subcommand>`.

Note: weekly_rebalance and daily_scan moved to .claude/commands/ slash commands
that run as Claude Code routines. Use /trader-daily and /trader-rebalance instead.
"""

from __future__ import annotations

import argparse
import logging
import sys

from trader.config import settings
from trader.portfolio import performance
from trader.portfolio.ledger import Ledger, seed
from trader.publish import telegram


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trader")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Seed ledger.json with STARTING_NAV")
    sub.add_parser("performance", help="Print TWRR/Sharpe/MaxDD vs SPY")
    sub.add_parser("ping-telegram", help="Send a test Telegram message")
    sub.add_parser("backfill-universe", help="Force-refresh IWB holdings cache")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _build_parser().parse_args(argv)

    if args.cmd == "init":
        if settings.ledger_path.exists():
            print(f"ledger already exists at {settings.ledger_path}")
            return 0
        seed(settings.starting_nav)
        print(f"seeded ledger at {settings.ledger_path} with NAV {settings.starting_nav}")
        return 0

    if args.cmd == "performance":
        ledger = Ledger.load()
        m = performance.compute(ledger)
        print(performance.format_markdown(m))
        return 0

    if args.cmd == "ping-telegram":
        ok = telegram.send("🤖 Claude-AI-Trader — ping")
        print("sent" if ok else "not sent (check token/chat_id)")
        return 0 if ok else 1

    if args.cmd == "backfill-universe":
        from trader import universe as u

        df = u.fetch_universe(force=True)
        print(f"fetched {len(df)} IWB rows")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())

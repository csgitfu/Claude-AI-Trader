"""Command-line interface: `python -m trader <subcommand>`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from trader import pipeline
from trader.config import settings
from trader.portfolio.ledger import seed
from trader.publish import telegram


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trader")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Seed ledger.json with STARTING_NAV")

    w = sub.add_parser("weekly", help="Full rebalance pipeline")
    w.add_argument("--dry-run", action="store_true")

    d = sub.add_parser("daily", help="Mark-to-market + news scan (no rebalance)")
    d.add_argument("--dry-run", action="store_true")

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

    try:
        if args.cmd == "init":
            if settings.ledger_path.exists():
                print(f"ledger already exists at {settings.ledger_path}")
                return 0
            seed(settings.starting_nav)
            print(f"seeded ledger at {settings.ledger_path} with NAV {settings.starting_nav}")
            return 0

        if args.cmd == "weekly":
            asyncio.run(pipeline.weekly_rebalance(dry_run=args.dry_run))
            return 0

        if args.cmd == "daily":
            asyncio.run(pipeline.daily_scan(dry_run=args.dry_run))
            return 0

        if args.cmd == "performance":
            print(pipeline.performance_report())
            return 0

        if args.cmd == "ping-telegram":
            ok = telegram.send("🤖 Claude-AI-Trader — ping")
            print("sent" if ok else "not sent (check token/chat_id or dry_run)")
            return 0 if ok else 1

        if args.cmd == "backfill-universe":
            from trader import universe as u

            df = u.fetch_universe(force=True)
            print(f"fetched {len(df)} IWB rows")
            return 0

        return 2
    except Exception as exc:
        telegram.send_error(exc, context=args.cmd)
        raise


if __name__ == "__main__":
    sys.exit(main())

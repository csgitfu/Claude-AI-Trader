"""Trading-day gates for the daily and weekly slash commands.

Usage:
    python -m trader.helpers.gate {daily|rebalance}

Exit codes:
  0  proceed
  1  skip (non-trading day or kill switch)
"""

from __future__ import annotations

import os
import sys

from trader.calendar_ import is_trading_day, last_trading_day_was_friday


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] not in ("daily", "rebalance"):
        print("usage: gate {daily|rebalance}", file=sys.stderr)
        return 2

    if os.environ.get("KILL_SWITCH") == "1":
        print("KILL_SWITCH is set; aborting before any LLM work.", file=sys.stderr)
        return 1

    mode = args[0]
    if mode == "daily":
        if not is_trading_day():
            print("UTC date is not a NYSE trading day; skipping daily.", file=sys.stderr)
            return 1
        return 0

    # rebalance
    if os.environ.get("FORCE_REBALANCE") == "1":
        print("FORCE_REBALANCE set; bypassing day-of-week check.", file=sys.stderr)
        return 0
    if not last_trading_day_was_friday():
        print(
            "Saturday rebalance requires Friday to have been a trading day; skipping.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

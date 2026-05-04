"""Mark current ledger to market using prices from market_data.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from trader.config import settings
from trader.portfolio.ledger import Ledger


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--market", required=True)
    args = p.parse_args(argv)

    if not settings.ledger_path.exists():
        print("no ledger; nothing to mark.")
        return 0

    market = json.loads(Path(args.market).read_text())
    closes: dict[str, float] = market["closes"]
    spy = market.get("spy_close")

    led = Ledger.load()
    nav_point = led.mark_to_market(
        closes, spy=spy, as_of=datetime.now(timezone.utc).date().isoformat()
    )
    led.save()
    fresh = len(led.positions) - len(nav_point.stale)
    suffix = f"; stale={nav_point.stale}" if nav_point.stale else ""
    print(f"marked {fresh}/{len(led.positions)} positions fresh; nav={nav_point.nav:.2f}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

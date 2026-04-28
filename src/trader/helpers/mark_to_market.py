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
    mtm_prices = {t: closes[t] for t in led.positions if t in closes}
    nav_point = led.mark_to_market(mtm_prices, spy=spy, as_of=datetime.now(timezone.utc).date().isoformat())
    led.save()
    print(f"marked {len(mtm_prices)} positions; nav={nav_point.nav:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

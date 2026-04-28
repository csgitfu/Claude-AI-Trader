"""Apply selector proposal to the ledger.

Reads:
  --selection data/runs/<date>/selection.json
  --market    data/runs/<date>/market_data.json (for current prices)
Writes:
  data/runs/<date>/trades.json (always)
  data/ledger.json (only if EXECUTE=1 and no kill switch)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from trader.config import settings
from trader.portfolio import simulate
from trader.portfolio.ledger import Ledger, seed
from trader.portfolio.risk import Proposal


def _git_drifted() -> bool:
    """Return True if remote has commits we don't have locally."""
    try:
        subprocess.run(["git", "fetch"], check=True, capture_output=True)
        r = subprocess.run(
            ["git", "rev-list", "HEAD..@{u}", "--count"],
            check=True, capture_output=True, text=True,
        )
        return int(r.stdout.strip()) > 0
    except subprocess.CalledProcessError:
        return False  # no upstream configured — treat as not drifted


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--selection", required=True)
    p.add_argument("--market", required=True)
    p.add_argument("--trades-out", required=True)
    args = p.parse_args(argv)

    if os.environ.get("KILL_SWITCH") == "1":
        print(json.dumps({"error": "kill_switch"}), file=sys.stderr)
        return 1

    sel = json.loads(Path(args.selection).read_text())
    market = json.loads(Path(args.market).read_text())
    closes = market["closes"]

    proposals = [Proposal(**p) for p in sel["picks"]]
    pick_prices = {p.ticker: closes[p.ticker] for p in proposals if p.ticker in closes}

    execute = os.environ.get("EXECUTE", str(int(settings.execute))) == "1"

    ledger = Ledger.load() if settings.ledger_path.exists() else seed(settings.starting_nav)
    trades = simulate.plan_trades(ledger, proposals, pick_prices, sel.get("rationales", {}))

    Path(args.trades_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.trades_out).write_text(json.dumps([t.__dict__ for t in trades], indent=2, default=str))

    if not execute:
        print("EXECUTE=0; paper mode, ledger unchanged.")
        return 0

    if _git_drifted():
        print(json.dumps({"error": "git_drift"}), file=sys.stderr)
        return 1

    simulate.apply(ledger, trades)
    for p in proposals:
        if p.ticker in ledger.positions:
            ledger.positions[p.ticker].sector = p.sector
    ledger.save()
    print(f"applied {len(trades)} trades to ledger")
    return 0


if __name__ == "__main__":
    sys.exit(main())

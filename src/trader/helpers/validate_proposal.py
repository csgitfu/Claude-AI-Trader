"""Validate selector proposal against risk caps before ledger mutation.

Exit codes:
  0  proposal passes all caps
  1  cap violation (details in stderr)

Caps checked:
  - per-name weight (always)
  - per-sector weight (always)
  - min distinct sectors (always)
  - one-way turnover vs current ledger (only if --ledger and --market are
    provided AND the ledger has at least one position; first-run portfolios
    are exempt)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from trader.config import settings
from trader.portfolio.ledger import Ledger


def _violations(picks: list[dict]) -> list[str]:
    errs: list[str] = []
    sector_w: dict[str, float] = defaultdict(float)

    for p in picks:
        w = float(p["weight"])
        if w > settings.max_weight_per_name + 1e-9:
            errs.append(
                f"per_name cap: {p['ticker']} weight={w:.4f} > {settings.max_weight_per_name}"
            )
        sector_w[p["sector"]] += w

    for sector, w in sector_w.items():
        if w > settings.max_weight_per_sector + 1e-9:
            errs.append(
                f"per_sector cap: {sector} weight={w:.4f} > {settings.max_weight_per_sector}"
            )

    if len(sector_w) < settings.min_sectors:
        errs.append(
            f"min_sectors: {len(sector_w)} distinct sectors < {settings.min_sectors}"
        )
    return errs


def _turnover(old_weights: dict[str, float], new_weights: dict[str, float]) -> float:
    """One-way portfolio turnover, treating cash residual as a position.

    Sum of weight deltas on each side equals total movement; divide by 2 to get
    one-way turnover (so a full rotation = 1.0, not 2.0).
    """
    cash_old = max(0.0, 1.0 - sum(old_weights.values()))
    cash_new = max(0.0, 1.0 - sum(new_weights.values()))
    all_t = set(old_weights) | set(new_weights)
    name_delta = sum(abs(new_weights.get(t, 0.0) - old_weights.get(t, 0.0)) for t in all_t)
    cash_delta = abs(cash_new - cash_old)
    return (name_delta + cash_delta) / 2.0


def _turnover_violation(ledger_path: str, market_path: str, picks: list[dict]) -> str | None:
    ledger = Ledger.load(Path(ledger_path))
    if not ledger.positions:
        return None  # first-run portfolio is exempt

    market = json.loads(Path(market_path).read_text())
    prices = market.get("closes", {})
    old_w = ledger.current_weights(prices)
    new_w = {p["ticker"]: float(p["weight"]) for p in picks}

    t = _turnover(old_w, new_w)
    if t > settings.max_turnover_per_run + 1e-9:
        return f"turnover cap: {t:.4f} > {settings.max_turnover_per_run}"
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", required=True)
    p.add_argument("--ledger", help="optional path to ledger.json for turnover check")
    p.add_argument("--market", help="optional path to market_data.json for current prices")
    args = p.parse_args(argv)

    sel = json.loads(Path(args.in_path).read_text())
    picks = sel.get("picks", [])
    if not picks:
        print(json.dumps({"error": "empty_proposal"}), file=sys.stderr)
        return 1

    errs = _violations(picks)

    if args.ledger and args.market:
        t_err = _turnover_violation(args.ledger, args.market, picks)
        if t_err:
            errs.append(t_err)

    if errs:
        print(json.dumps({"error": "cap_violation", "details": errs}), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Validate selector proposal against risk caps before ledger mutation.

Exit codes:
  0  proposal passes all caps
  1  cap violation (details in stderr)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from trader.config import settings


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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", required=True)
    args = p.parse_args(argv)

    sel = json.loads(Path(args.in_path).read_text())
    picks = sel.get("picks", [])
    if not picks:
        print(json.dumps({"error": "empty_proposal"}), file=sys.stderr)
        return 1

    errs = _violations(picks)
    if errs:
        print(json.dumps({"error": "cap_violation", "details": errs}), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

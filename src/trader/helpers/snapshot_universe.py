"""Write Russell 1000 universe snapshot to data/runs/<date>/universe.json.

Usage:
    python -m trader.helpers.snapshot_universe --out data/runs/2026-04-28/universe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trader import universe


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    df = universe.fetch_universe()
    tickers = universe.tickers(df)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"tickers": tickers}, indent=2))
    print(f"wrote {len(tickers)} tickers to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

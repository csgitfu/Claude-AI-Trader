"""Pick top-N tickers by score and write shortlist.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--n", type=int, default=50)
    args = p.parse_args(argv)

    raw = json.loads(Path(args.in_path).read_text())
    rows = sorted(raw["scores"], key=lambda r: r["score"], reverse=True)
    tickers = [r["ticker"] for r in rows[: args.n]]

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"tickers": tickers}, indent=2))
    print(f"wrote top-{len(tickers)} shortlist")
    return 0


if __name__ == "__main__":
    sys.exit(main())

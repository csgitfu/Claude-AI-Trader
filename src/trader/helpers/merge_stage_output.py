"""Merge validated per-subagent outputs into a single stage JSON file.

Stage shapes:
  scorer        merge .scores arrays
  debater       dict keyed by ticker → {bull, bear}
  prob-estimator dict keyed by ticker → estimate object
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=["scorer", "debater", "prob-estimator"], required=True)
    p.add_argument("--out", required=True)
    p.add_argument("inputs", nargs="+")
    args = p.parse_args(argv)

    payloads = [json.loads(Path(f).read_text()) for f in args.inputs]

    if args.stage == "scorer":
        merged = {"scores": [row for p in payloads for row in p["scores"]]}
    elif args.stage == "debater":
        merged = {p["ticker"]: {"bull": p["bull"], "bear": p["bear"]} for p in payloads}
    elif args.stage == "prob-estimator":
        merged = {p["ticker"]: p for p in payloads}
    else:
        print(f"unknown stage: {args.stage}", file=sys.stderr)
        return 2

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(merged, indent=2, default=str))
    print(f"merged {len(payloads)} payloads -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

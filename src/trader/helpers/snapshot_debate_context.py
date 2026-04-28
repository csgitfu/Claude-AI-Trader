"""Assemble per-ticker debate context from prior stage outputs.

Reads:
  - shortlist.json     (tickers list)
  - market_data.json   (fundamentals, momentum, vol)
  - news.json          (per-ticker headlines)
  - macro.json         (macro snapshot)

Writes:
  - debate_context.json {ticker: {fundamentals, momentum, ann_vol, headlines, macro}}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--shortlist", required=True)
    p.add_argument("--market", required=True)
    p.add_argument("--news", required=True)
    p.add_argument("--macro", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    tickers = json.loads(Path(args.shortlist).read_text())["tickers"]
    market = json.loads(Path(args.market).read_text())
    news_ = json.loads(Path(args.news).read_text())
    macro_ = json.loads(Path(args.macro).read_text())

    fund = market.get("fundamentals", {})
    mom = market.get("momentum", {})
    vol = market.get("vol", {})
    headlines = news_.get("tickers", {})

    ctx = {
        t: {
            "fundamentals": fund.get(t, {}),
            "momentum": mom.get(t, {}),
            "ann_vol": vol.get(t),
            "headlines": headlines.get(t, []),
            "macro": macro_,
        }
        for t in tickers
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(ctx, indent=2, default=str))
    print(f"wrote debate context for {len(ctx)} tickers")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Send report to Telegram and commit+push state to git."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from trader.config import settings
from trader.publish import telegram


def _git(*args: str) -> int:
    return subprocess.run(["git", *args], capture_output=True, text=True).returncode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--report", required=True)
    p.add_argument("--run-date", required=True)  # YYYY-MM-DD; for commit message
    args = p.parse_args(argv)

    text = Path(args.report).read_text()
    Path(settings.reports_dir).mkdir(parents=True, exist_ok=True)
    final = settings.reports_dir / f"{args.run_date}.md"
    final.write_text(text)

    try:
        telegram.send(text)
    except Exception as e:
        print(f"telegram send failed: {e}", file=sys.stderr)
        # non-fatal; continue to commit

    _git("add", "data/", "reports/")
    rc = _git("commit", "-m", f"trader: run {args.run_date}")
    if rc != 0:
        print("nothing to commit (clean working tree)")
    push_rc = _git("push")
    if push_rc != 0:
        print("git push failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

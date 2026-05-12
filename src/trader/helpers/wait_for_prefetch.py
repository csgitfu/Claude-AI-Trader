"""Wait for the GH Actions prefetch commit for a given RUN_DATE to land on origin/main.

Used as Stage 2.5 in CCR routines. Prefetch (daily-scan.yml or
weekly-rebalance.yml) and the CCR routine are scheduled with a buffer between
them, but GH Actions cron drifts unreliably. If CCR fires before prefetch
pushes, the data files won't be on disk and CCR has no outbound network to
fall back to — polling origin/main until the prefetch commit appears
eliminates that race.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time


def _commit_present(kind: str, run_date: str) -> bool:
    """True iff origin/main has a commit matching `prefetch: <kind> <run_date>`."""
    subprocess.run(
        ["git", "fetch", "origin", "main"],
        capture_output=True,
        text=True,
        check=False,
    )
    pattern = f"prefetch: {kind} {run_date}"
    result = subprocess.run(
        ["git", "log", "-1", "origin/main", f"--grep={pattern}", "--pretty=oneline"],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--kind", required=True, choices=["daily", "rebalance"])
    p.add_argument("--run-date", required=True,
                   help="YYYY-MM-DD; matches the prefetch commit message")
    p.add_argument("--timeout", type=int, default=1800,
                   help="Total seconds to wait before failing (default 1800 = 30min)")
    p.add_argument("--interval", type=int, default=60,
                   help="Seconds between polls (default 60)")
    args = p.parse_args(argv)

    pattern = f"prefetch: {args.kind} {args.run_date}"
    deadline = time.monotonic() + args.timeout
    while True:
        if _commit_present(args.kind, args.run_date):
            print(f"prefetch commit '{pattern}' present on origin/main")
            subprocess.run(["git", "pull", "--rebase"], check=False)
            return 0
        if time.monotonic() >= deadline:
            print(
                f"timeout: prefetch commit '{pattern}' did not appear on origin/main "
                f"within {args.timeout}s",
                file=sys.stderr,
            )
            return 1
        print(
            f"waiting for prefetch commit '{pattern}' on origin/main; "
            f"sleeping {args.interval}s"
        )
        sys.stdout.flush()
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())

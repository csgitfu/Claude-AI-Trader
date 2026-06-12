"""Wait for the GH Actions prefetch commit for a given RUN_DATE to land on origin/main.

Used as Stage 2.5 in CCR routines. Prefetch (daily-scan.yml or
weekly-rebalance.yml) and the CCR routine are scheduled with a buffer between
them, but GH Actions cron drifts unreliably. If CCR fires before prefetch
pushes, the data files won't be on disk and CCR has no outbound network to
fall back to — polling origin/main until the prefetch commit appears
eliminates that race.

When CCR is triggered directly via the API dispatch (event-driven mode), the
repo clone already contains the prefetch files; the fast-path below exits
immediately without polling.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import time

# Files that must exist on disk for each prefetch kind before the CCR session
# can proceed.  Mirrors what daily-scan.yml / weekly-rebalance.yml commit.
_PREFETCH_FILES: dict[str, list[str]] = {
    "daily": ["market_data.json", "news.json", "macro.json"],
    "rebalance": ["market_data_full.json", "news.json", "macro.json"],
}


def _files_present(kind: str, run_date: str) -> bool:
    """True if all expected prefetch output files already exist on disk."""
    run_dir = pathlib.Path("data/runs") / run_date
    return all((run_dir / name).exists() for name in _PREFETCH_FILES[kind])


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

    # Fast-path: when CCR is triggered by event dispatch rather than a cron
    # schedule, the fresh repo clone already contains all prefetch files.
    # Exit immediately so the session doesn't spend time polling.
    if _files_present(args.kind, args.run_date):
        print(
            f"prefetch files already present for {args.kind} {args.run_date}"
            " — skipping wait"
        )
        return 0

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

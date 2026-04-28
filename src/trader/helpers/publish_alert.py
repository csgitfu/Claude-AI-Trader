"""Send a short-form Telegram alert.

Used by slash commands when a stage fails or a cap violation is detected.
Sibling of publish_report; no git push.
"""

from __future__ import annotations

import argparse
import sys

from trader.config import settings
from trader.publish import telegram

_PREFIXES = {
    "failure": "[FAILURE]",
    "cap_violation": "[CAP VIOLATION]",
    "heartbeat": "[HEARTBEAT]",
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--type", dest="alert_type", choices=list(_PREFIXES), required=True)
    p.add_argument("--message", required=True)
    args = p.parse_args(argv)

    if args.alert_type == "heartbeat" and not settings.enable_heartbeat:
        return 0

    text = f"{_PREFIXES[args.alert_type]} {args.message}"
    try:
        telegram.send(text)
    except Exception as e:
        print(f"alert send failed: {e}", file=sys.stderr)
        return 0  # non-fatal; don't escalate alerting failures
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Extract and validate JSON from a subagent's free-text reply.

Invoked by the orchestrator as:
    python -m trader.helpers.parse_subagent_output --schema <name> --input <text>

Exit codes:
  0  validated JSON printed to stdout
  1  extraction or validation failed; error JSON printed to stderr
  2  unknown schema name
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from pydantic import ValidationError

from trader.helpers.schemas import SCHEMA_REGISTRY

_FENCE = re.compile(r"```json\s*\n(.+?)\n```", re.DOTALL)


def _emit_err(payload: dict) -> None:
    """Emit error JSON to stderr with trailing newline."""
    json.dump(payload, sys.stderr)
    sys.stderr.write("\n")


def extract_first_block(text: str) -> str | None:
    m = _FENCE.search(text)
    return m.group(1) if m else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True)
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)

    model = SCHEMA_REGISTRY.get(args.schema)
    if model is None:
        print(f"unknown schema: {args.schema}", file=sys.stderr)
        return 2

    block = extract_first_block(args.input)
    if block is None:
        _emit_err({"error": "no_fence", "details": "no ```json fenced block found"})
        return 1

    try:
        raw = json.loads(block)
    except json.JSONDecodeError as e:
        _emit_err({"error": "parse", "details": str(e)})
        return 1

    try:
        validated = model.model_validate(raw)
    except ValidationError as e:
        _emit_err({"error": "schema", "details": e.errors()})
        return 1

    json.dump(validated.model_dump(), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

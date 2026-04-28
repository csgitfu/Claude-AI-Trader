import json
import subprocess
import sys

import pytest

CMD = [sys.executable, "-m", "trader.helpers.parse_subagent_output"]


def run(args: list[str], stdin_text: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        CMD + args,
        input=stdin_text,
        capture_output=True,
        text=True,
    )


VALID_SCORER_REPLY = '''Here is the result:

```json
{"scores": [{"ticker": "AAPL", "score": 78, "one_liner": "ok", "flags": []}]}
```

Done.
'''


def test_extracts_and_validates_well_formed():
    r = run(["--schema", "scorer", "--input", VALID_SCORER_REPLY])
    assert r.returncode == 0, r.stderr
    parsed = json.loads(r.stdout)
    assert parsed["scores"][0]["ticker"] == "AAPL"


def test_rejects_missing_fence():
    r = run(["--schema", "scorer", "--input", "no fenced block here"])
    assert r.returncode == 1
    err = json.loads(r.stderr)
    assert err["error"] == "no_fence"


def test_rejects_malformed_json():
    bad = "```json\n{not valid json\n```"
    r = run(["--schema", "scorer", "--input", bad])
    assert r.returncode == 1
    err = json.loads(r.stderr)
    assert err["error"] == "parse"


def test_rejects_schema_violation():
    # score over 100
    bad = '```json\n{"scores":[{"ticker":"AAPL","score":150,"one_liner":"x","flags":[]}]}\n```'
    r = run(["--schema", "scorer", "--input", bad])
    assert r.returncode == 1
    err = json.loads(r.stderr)
    assert err["error"] == "schema"


def test_takes_first_block_when_multiple():
    text = (
        '```json\n{"scores":[{"ticker":"AAPL","score":50,"one_liner":"x","flags":[]}]}\n```\n'
        '```json\n{"scores":[{"ticker":"MSFT","score":60,"one_liner":"y","flags":[]}]}\n```'
    )
    r = run(["--schema", "scorer", "--input", text])
    assert r.returncode == 0
    parsed = json.loads(r.stdout)
    assert parsed["scores"][0]["ticker"] == "AAPL"


def test_unknown_schema():
    r = run(["--schema", "bogus", "--input", VALID_SCORER_REPLY])
    assert r.returncode == 2

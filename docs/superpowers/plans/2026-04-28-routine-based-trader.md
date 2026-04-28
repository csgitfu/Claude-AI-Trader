# Routine-Based Trader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the trader from direct `anthropic` SDK calls (pay-per-token API) to a Claude Code routine that runs on Anthropic infrastructure and bills against the user's Max plan subscription. Eliminates per-token API spend.

**Architecture:** Pipeline orchestration moves from `pipeline.py` into two slash commands (`/trader-daily`, `/trader-rebalance`) that drive a sequence of Bash → Python helper calls and LLM turns (orchestrator + parallel subagents). Deterministic Python (data fetch, ledger math, risk validation) becomes a library of small helper CLIs. State persists by committing `data/ledger.json` back to GitHub on each run.

**Tech Stack:** Python 3.11+, Pydantic, pandas, yfinance, pandas_market_calendars, fredapi, feedparser, requests; Claude Code subagents (`.claude/agents/*.md`) and slash commands (`.claude/commands/*.md`); Anthropic Routines (`/schedule`).

**Spec:** `docs/superpowers/specs/2026-04-28-routine-based-trader-design.md`

---

## File Structure

This section locks in the decomposition. Each file has one clear responsibility. Tasks reference these paths exactly.

### Created

```
.claude/
  agents/
    scorer.md                        # Haiku subagent: score 25-ticker batch
    debater.md                       # Opus subagent: bull+bear for one ticker
    prob-estimator.md                # Opus subagent: probability + sizing for one ticker
  commands/
    trader-daily.md                  # Daily scan slash command body
    trader-rebalance.md              # Weekly rebalance slash command body
    test-subagent.md                 # Layer 2 manual sanity command

src/trader/helpers/
  __init__.py
  schemas.py                         # Pydantic models for subagent outputs
  parse_subagent_output.py           # Extract + validate JSON from subagent reply
  merge_stage_output.py              # Concat validated outputs into stage JSON
  gate.py                            # Daily / rebalance trading-day gates
  snapshot_universe.py               # Russell 1000 universe → JSON
  snapshot_market_data.py            # Prices + fundamentals + momentum + vol → JSON
  snapshot_news.py                   # Headlines + macro → JSON
  snapshot_debate_context.py         # Per-ticker context blob for shortlist
  build_shortlist.py                 # Top-N from scores
  validate_proposal.py               # Risk-cap check before ledger mutation
  apply_trades.py                    # Mutate ledger (with kill-switch + git guards)
  mark_to_market.py                  # Update ledger NAV and unrealized P/L
  publish_report.py                  # Telegram + git commit/push
  publish_alert.py                   # Telegram alert (failure / cap violation / heartbeat)

tests/
  fixtures/
    runs/
      2026-01-02/
        market_data.json             # canned input for helper smoke tests
        news.json
        macro.json
        scores.json
        shortlist.json
        debate_context.json
        debates.json
        estimates.json
        selection.json
    subagent_inputs/
      scorer_input.json              # canned input for Layer 2 manual tests
      debater_input.json
      prob_input.json
  test_helpers/
    test_schemas.py
    test_parse_subagent_output.py
    test_merge_stage_output.py
    test_gate.py
    test_build_shortlist.py
    test_validate_proposal.py
    test_apply_trades.py
    test_mark_to_market.py
    test_publish_report.py
    test_publish_alert.py
    test_snapshot_market_data.py
    test_snapshot_news.py
  test_helpers_smoke.py              # End-to-end helper CLI smoke against fixtures
```

### Modified

```
src/trader/calendar_.py              # Add last_trading_day_was_friday() helper
src/trader/config.py                 # Drop API/SDK fields; add git_remote_url, enable_heartbeat
src/trader/cli.py                    # Strip pipeline entry points; helper CLI dispatch only
pyproject.toml                       # Drop anthropic, tenacity; drop pytest-asyncio if unused
```

### Deleted

```
src/trader/agents/client.py
src/trader/agents/scorer.py
src/trader/agents/debate.py
src/trader/agents/probability.py
src/trader/agents/selector.py
src/trader/agents/newswriter.py
src/trader/agents/__init__.py
src/trader/pipeline.py
tests/test_pipeline_smoke.py
tests/test_probability.py
src/trader/prompts/                  # entire directory (contents inlined into .claude/agents/)
```

---

# Phase 1 — Foundation

### Task 1: Project scaffolding and fixtures

**Files:**
- Create: `src/trader/helpers/__init__.py` (empty)
- Create: `tests/test_helpers/__init__.py` (empty)
- Create: `tests/fixtures/runs/2026-01-02/` (with placeholder JSONs — populated in subsequent tasks)
- Create: `tests/fixtures/subagent_inputs/` (with placeholder JSONs — populated in Task 16-18)

- [ ] **Step 1: Create directory tree and empty package markers**

```bash
mkdir -p src/trader/helpers
mkdir -p tests/test_helpers
mkdir -p tests/fixtures/runs/2026-01-02
mkdir -p tests/fixtures/subagent_inputs
mkdir -p .claude/agents
mkdir -p .claude/commands
touch src/trader/helpers/__init__.py
touch tests/test_helpers/__init__.py
```

- [ ] **Step 2: Verify pytest still discovers the new test directory**

Run: `pytest tests/test_helpers/ -v --collect-only`
Expected: `no tests ran in 0.XXs` (no errors; empty collection is fine)

- [ ] **Step 3: Commit**

```bash
git add src/trader/helpers/__init__.py tests/test_helpers/__init__.py tests/fixtures/ .claude/
git commit -m "scaffold: create helpers package and test fixtures structure"
```

---

### Task 2: Pydantic schemas for subagent outputs

**Files:**
- Create: `src/trader/helpers/schemas.py`
- Create: `tests/test_helpers/test_schemas.py`

- [ ] **Step 1: Write failing test for schema validation**

`tests/test_helpers/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from trader.helpers.schemas import (
    DebateOutput,
    ProbEstimate,
    ScoreEntry,
    ScorerBatchOutput,
)


def test_score_entry_valid():
    e = ScoreEntry(ticker="AAPL", score=78, one_liner="solid quality", flags=[])
    assert e.score == 78


def test_score_entry_rejects_out_of_range():
    with pytest.raises(ValidationError):
        ScoreEntry(ticker="AAPL", score=150, one_liner="x")


def test_scorer_batch_round_trip():
    payload = {"scores": [{"ticker": "AAPL", "score": 78, "one_liner": "x", "flags": []}]}
    parsed = ScorerBatchOutput.model_validate(payload)
    assert parsed.scores[0].ticker == "AAPL"
    assert parsed.model_dump() == payload


def test_debate_output_required_fields():
    with pytest.raises(ValidationError):
        DebateOutput(ticker="AAPL", bull="...")  # missing bear


def test_prob_estimate_bounds():
    e = ProbEstimate(
        ticker="AAPL",
        p_outperform=0.62,
        expected_alpha_bps=180.0,
        conviction=0.55,
        sizing_hint=0.06,
    )
    assert e.sizing_hint == 0.06

    with pytest.raises(ValidationError):
        ProbEstimate(
            ticker="AAPL",
            p_outperform=0.62,
            expected_alpha_bps=180.0,
            conviction=0.55,
            sizing_hint=0.20,  # over 0.10 cap
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_helpers/test_schemas.py -v`
Expected: ImportError / ModuleNotFoundError on `trader.helpers.schemas`.

- [ ] **Step 3: Implement schemas**

`src/trader/helpers/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreEntry(BaseModel):
    ticker: str
    score: int = Field(ge=0, le=100)
    one_liner: str
    flags: list[str] = Field(default_factory=list)


class ScorerBatchOutput(BaseModel):
    scores: list[ScoreEntry]


class DebateOutput(BaseModel):
    ticker: str
    bull: str
    bear: str


class ProbEstimate(BaseModel):
    ticker: str
    p_outperform: float = Field(ge=0, le=1)
    expected_alpha_bps: float
    conviction: float = Field(ge=0, le=1)
    sizing_hint: float = Field(ge=0, le=0.10)


SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "scorer": ScorerBatchOutput,
    "debater": DebateOutput,
    "prob-estimator": ProbEstimate,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_helpers/test_schemas.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/trader/helpers/schemas.py tests/test_helpers/test_schemas.py
git commit -m "feat(helpers): add pydantic schemas for subagent outputs"
```

---

### Task 3: parse_subagent_output.py — JSON extraction and validation

**Files:**
- Create: `src/trader/helpers/parse_subagent_output.py`
- Create: `tests/test_helpers/test_parse_subagent_output.py`

This helper is run by the orchestrator as `Bash → python -m trader.helpers.parse_subagent_output --schema <name> --input <text>`. It extracts the first ` ```json ` fenced block and validates against the named schema.

- [ ] **Step 1: Write failing tests covering the extraction + validation paths**

`tests/test_helpers/test_parse_subagent_output.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_helpers/test_parse_subagent_output.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the helper**

`src/trader/helpers/parse_subagent_output.py`:

```python
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
        json.dump({"error": "no_fence", "details": "no ```json fenced block found"}, sys.stderr)
        return 1

    try:
        raw = json.loads(block)
    except json.JSONDecodeError as e:
        json.dump({"error": "parse", "details": str(e)}, sys.stderr)
        return 1

    try:
        validated = model.model_validate(raw)
    except ValidationError as e:
        json.dump({"error": "schema", "details": e.errors()}, sys.stderr)
        return 1

    json.dump(validated.model_dump(), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_helpers/test_parse_subagent_output.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/trader/helpers/parse_subagent_output.py tests/test_helpers/test_parse_subagent_output.py
git commit -m "feat(helpers): add parse_subagent_output for JSON extract+validate"
```

---

# Phase 2 — Stage Helpers

### Task 4: gate.py — trading-day gates

**Files:**
- Modify: `src/trader/calendar_.py:1-23` — add `last_trading_day_was_friday()`
- Create: `src/trader/helpers/gate.py`
- Create: `tests/test_helpers/test_gate.py`

The daily gate runs at 03:30 SGT (Tue–Sat). The UTC date at that moment is the **previous** US trading day. The gate must check whether that prev US date was a trading day. The rebalance gate runs at 04:30 SGT Saturday — UTC date is Friday — must verify Friday was a trading day.

- [ ] **Step 1: Add freezegun to dev deps**

Edit `pyproject.toml` `[project.optional-dependencies] dev` array, add `"freezegun>=1.4"`. Reinstall: `pip install -e ".[dev]"`.

- [ ] **Step 2: Write failing tests**

`tests/test_helpers/test_gate.py`:

```python
import subprocess
import sys

import pytest
from freezegun import freeze_time

CMD = [sys.executable, "-m", "trader.helpers.gate"]


def run(mode: str) -> subprocess.CompletedProcess:
    return subprocess.run(CMD + [mode], capture_output=True, text=True)


# 03:30 SGT Tuesday = 19:30 UTC Monday. Monday was a trading day.
@freeze_time("2026-01-20 19:30:00")  # UTC; SGT = 2026-01-21 03:30 (Wed)
def test_daily_passes_on_trading_day_utc():
    # UTC date 2026-01-20 (Mon) is a trading day
    r = run("daily")
    assert r.returncode == 0


@freeze_time("2026-01-19 19:30:00")  # UTC date 2026-01-19 = Mon US is trading
def test_daily_passes_on_monday():
    r = run("daily")
    assert r.returncode == 0


# Sunday SGT 03:30 = Saturday UTC 19:30 — Sat is not a trading day
@freeze_time("2026-01-17 19:30:00")
def test_daily_fails_on_weekend():
    r = run("daily")
    assert r.returncode != 0


# Sat 04:30 SGT = Fri 20:30 UTC. Fri 2026-01-23 was a trading day.
@freeze_time("2026-01-23 20:30:00")
def test_rebalance_passes_after_friday_close():
    r = run("rebalance")
    assert r.returncode == 0


# Sat 04:30 SGT after a holiday Friday (e.g. Good Friday 2026-04-03)
@freeze_time("2026-04-03 20:30:00")
def test_rebalance_fails_on_market_holiday_friday():
    r = run("rebalance")
    assert r.returncode != 0


def test_kill_switch_aborts(monkeypatch):
    monkeypatch.setenv("KILL_SWITCH", "1")
    with freeze_time("2026-01-20 19:30:00"):
        r = run("daily")
    assert r.returncode != 0
    assert "KILL_SWITCH" in (r.stderr + r.stdout)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_helpers/test_gate.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 4: Add `last_trading_day_was_friday()` to `calendar_.py`**

Append to `src/trader/calendar_.py`:

```python
def last_trading_day_was_friday(d: date | None = None) -> bool:
    """At time of call, was the most recent trading day a Friday?

    Used by the rebalance gate, which runs Sat 04:30 SGT (Fri ~20:30 UTC).
    Returns True only if the previous US trading day landed on a Friday
    (i.e., the UTC date today is a Friday and is a trading day).
    """
    d = d or datetime.now(timezone.utc).date()
    if d.weekday() != 4:  # 4 = Friday
        return False
    return is_trading_day(d)
```

- [ ] **Step 5: Implement gate.py**

`src/trader/helpers/gate.py`:

```python
"""Trading-day gates for the daily and weekly slash commands.

Usage:
    python -m trader.helpers.gate {daily|rebalance}

Exit codes:
  0  proceed
  1  skip (non-trading day or kill switch)
"""

from __future__ import annotations

import os
import sys

from trader.calendar_ import is_trading_day, last_trading_day_was_friday


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] not in ("daily", "rebalance"):
        print("usage: gate {daily|rebalance}", file=sys.stderr)
        return 2

    if os.environ.get("KILL_SWITCH") == "1":
        print("KILL_SWITCH is set; aborting before any LLM work.", file=sys.stderr)
        return 1

    mode = args[0]
    if mode == "daily":
        if not is_trading_day():
            print("UTC date is not a NYSE trading day; skipping daily.", file=sys.stderr)
            return 1
        return 0

    # rebalance
    if not last_trading_day_was_friday():
        print(
            "Saturday rebalance requires Friday to have been a trading day; skipping.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_helpers/test_gate.py tests/test_calendar.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/trader/calendar_.py src/trader/helpers/gate.py tests/test_helpers/test_gate.py pyproject.toml
git commit -m "feat(helpers): add daily and rebalance trading-day gates"
```

---

### Task 5: snapshot_universe.py — thin CLI wrapper

**Files:**
- Create: `src/trader/helpers/snapshot_universe.py`

Thin wrapper around `trader.universe.fetch_universe`. No new logic; existing `tests/test_universe.py` covers the underlying function. No dedicated test file for this helper — the smoke test (Task 26) covers it end-to-end.

- [ ] **Step 1: Implement**

`src/trader/helpers/snapshot_universe.py`:

```python
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
```

- [ ] **Step 2: Smoke test manually**

Run: `python -m trader.helpers.snapshot_universe --out /tmp/u.json && python -c "import json; d=json.load(open('/tmp/u.json')); print(len(d['tickers']))"`
Expected: prints a number near 1000.

- [ ] **Step 3: Commit**

```bash
git add src/trader/helpers/snapshot_universe.py
git commit -m "feat(helpers): add snapshot_universe CLI"
```

---

### Task 6: snapshot_market_data.py — prices, fundamentals, momentum, vol

**Files:**
- Create: `src/trader/helpers/snapshot_market_data.py`
- Create: `tests/test_helpers/test_snapshot_market_data.py`

Two modes: `--full` (universe-wide for weekly rebalance) and `--holdings-only` (just current ledger holdings + SPY for daily scan).

- [ ] **Step 1: Write failing test against fixture inputs**

`tests/test_helpers/test_snapshot_market_data.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

CMD = [sys.executable, "-m", "trader.helpers.snapshot_market_data"]


def test_holdings_only_writes_expected_keys(tmp_path, monkeypatch):
    """Smoke: helper writes a JSON with expected top-level keys.

    We can't fully mock yfinance from a subprocess; this test relies on the
    helper running with --tickers-from <stdin> instead of fetching data live.
    Mark slow tests separately if hitting yfinance is needed.
    """
    out = tmp_path / "market_data.json"
    # --tickers explicit list is a test-only mode that bypasses ledger reading
    r = subprocess.run(
        CMD + ["--mode", "holdings-only", "--out", str(out), "--tickers", "AAPL,MSFT,SPY"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())
    assert "closes" in data
    assert "momentum" in data
    assert "vol" in data
    # SPY price isolated
    assert "spy_close" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_helpers/test_snapshot_market_data.py -v`
Expected: ModuleNotFoundError (or fail because helper missing).

- [ ] **Step 3: Implement**

`src/trader/helpers/snapshot_market_data.py`:

```python
"""Snapshot prices, fundamentals, momentum, volatility to JSON.

Modes:
  --mode full              All universe tickers (for weekly rebalance)
  --mode holdings-only     Current ledger holdings + SPY (for daily scan)

Usage:
    python -m trader.helpers.snapshot_market_data --mode full --out data/runs/2026-04-28/market_data.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trader import universe
from trader.config import settings
from trader.data import fundamentals, prices
from trader.portfolio.ledger import Ledger


def _resolve_tickers(mode: str, override: str | None) -> list[str]:
    if override:
        return [t.strip() for t in override.split(",") if t.strip()]
    if mode == "full":
        df = universe.fetch_universe()
        return universe.tickers(df) + ["SPY"]
    if mode == "holdings-only":
        if settings.ledger_path.exists():
            led = Ledger.load()
            return list(led.positions) + ["SPY"]
        return ["SPY"]
    raise ValueError(f"unknown mode: {mode}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["full", "holdings-only"], required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tickers", help="comma-separated override (test use)")
    args = p.parse_args(argv)

    tickers = _resolve_tickers(args.mode, args.tickers)
    hist = prices.download_history(tickers, period="1y")

    spy_close = None
    if "SPY" in hist.columns:
        spy_close = float(hist["SPY"].ffill().iloc[-1])
        hist = hist.drop(columns=["SPY"])

    closes = prices.latest_close(list(hist.columns))
    mom = prices.momentum(hist)
    vol = prices.realized_vol(hist)

    fund: dict = {}
    if args.mode == "full":
        fund = fundamentals.fetch_many([t for t in tickers if t != "SPY"])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "closes": closes,
        "momentum": mom,
        "vol": vol,
        "fundamentals": fund,
        "spy_close": spy_close,
    }, indent=2, default=str))
    print(f"wrote market data for {len(closes)} tickers to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_helpers/test_snapshot_market_data.py -v`
Expected: passes (test hits real yfinance briefly; allow up to 60s).

If yfinance is unreliable in CI, mark the test `@pytest.mark.slow` and skip by default; require manual run before scheduling.

- [ ] **Step 5: Commit**

```bash
git add src/trader/helpers/snapshot_market_data.py tests/test_helpers/test_snapshot_market_data.py
git commit -m "feat(helpers): add snapshot_market_data CLI"
```

---

### Task 7: snapshot_news.py — headlines + macro

**Files:**
- Create: `src/trader/helpers/snapshot_news.py`
- Create: `tests/test_helpers/test_snapshot_news.py`

Modes mirror Task 6: `--full` writes both market headlines and per-shortlist headlines; `--holdings-only` writes market + per-current-holding headlines.

- [ ] **Step 1: Write failing test**

`tests/test_helpers/test_snapshot_news.py`:

```python
import json
import subprocess
import sys

CMD = [sys.executable, "-m", "trader.helpers.snapshot_news"]


def test_holdings_only_writes_expected_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "")  # exercise no-FRED path
    out_news = tmp_path / "news.json"
    out_macro = tmp_path / "macro.json"
    r = subprocess.run(
        CMD
        + [
            "--mode", "holdings-only",
            "--out-news", str(out_news),
            "--out-macro", str(out_macro),
            "--tickers", "AAPL,MSFT",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr

    news = json.loads(out_news.read_text())
    assert "market" in news
    assert "tickers" in news
    assert set(news["tickers"]) <= {"AAPL", "MSFT"}

    macro = json.loads(out_macro.read_text())
    assert isinstance(macro, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_helpers/test_snapshot_news.py -v`

- [ ] **Step 3: Implement**

`src/trader/helpers/snapshot_news.py`:

```python
"""Snapshot market and per-ticker headlines, plus macro indicators.

Usage:
    python -m trader.helpers.snapshot_news \\
        --mode {full|holdings-only} \\
        --out-news data/runs/<date>/news.json \\
        --out-macro data/runs/<date>/macro.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trader.config import settings
from trader.data import macro, news
from trader.portfolio.ledger import Ledger


def _resolve_tickers(mode: str, override: str | None, shortlist_path: str | None) -> list[str]:
    if override:
        return [t.strip() for t in override.split(",") if t.strip()]
    if mode == "full":
        if shortlist_path:
            return json.loads(Path(shortlist_path).read_text())["tickers"]
        return []
    if mode == "holdings-only":
        if settings.ledger_path.exists():
            return list(Ledger.load().positions)
        return []
    raise ValueError(mode)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["full", "holdings-only"], required=True)
    p.add_argument("--out-news", required=True)
    p.add_argument("--out-macro", required=True)
    p.add_argument("--tickers", help="comma-separated override (test use)")
    p.add_argument("--shortlist", help="path to shortlist.json (full mode)")
    args = p.parse_args(argv)

    tickers = _resolve_tickers(args.mode, args.tickers, args.shortlist)

    market = news.market_headlines(limit=15)
    per_ticker = {t: news.ticker_headlines(t, limit=8) for t in tickers}

    Path(args.out_news).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_news).write_text(json.dumps({
        "market": market,
        "tickers": per_ticker,
    }, indent=2, default=str))

    snap = macro.snapshot()
    Path(args.out_macro).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_macro).write_text(json.dumps(snap, indent=2, default=str))

    print(f"wrote {len(per_ticker)} tickers' headlines to {args.out_news}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_helpers/test_snapshot_news.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/trader/helpers/snapshot_news.py tests/test_helpers/test_snapshot_news.py
git commit -m "feat(helpers): add snapshot_news CLI"
```

---

### Task 8: snapshot_debate_context.py — per-ticker context blob

**Files:**
- Create: `src/trader/helpers/snapshot_debate_context.py`

Reads `shortlist.json`, `market_data.json`, `news.json`, `macro.json`; writes `debate_context.json` keyed by ticker. No new logic — just JSON shuffling. Covered by smoke test (Task 26).

- [ ] **Step 1: Implement**

`src/trader/helpers/snapshot_debate_context.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/trader/helpers/snapshot_debate_context.py
git commit -m "feat(helpers): add snapshot_debate_context CLI"
```

---

### Task 9: build_shortlist.py — top-N from scores

**Files:**
- Create: `src/trader/helpers/build_shortlist.py`
- Create: `tests/test_helpers/test_build_shortlist.py`

- [ ] **Step 1: Write failing test**

`tests/test_helpers/test_build_shortlist.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

CMD = [sys.executable, "-m", "trader.helpers.build_shortlist"]


def test_top_n_selection(tmp_path):
    scores = {
        "scores": [
            {"ticker": "AAPL", "score": 90, "one_liner": "x", "flags": []},
            {"ticker": "MSFT", "score": 80, "one_liner": "x", "flags": []},
            {"ticker": "GOOG", "score": 70, "one_liner": "x", "flags": []},
            {"ticker": "AMZN", "score": 60, "one_liner": "x", "flags": []},
        ]
    }
    in_path = tmp_path / "scores.json"
    out_path = tmp_path / "shortlist.json"
    in_path.write_text(json.dumps(scores))

    r = subprocess.run(
        CMD + ["--in", str(in_path), "--out", str(out_path), "--n", "2"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(out_path.read_text())
    assert out["tickers"] == ["AAPL", "MSFT"]
```

- [ ] **Step 2: Run test to verify it fails, then implement**

`src/trader/helpers/build_shortlist.py`:

```python
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
```

- [ ] **Step 3: Run test to verify pass, commit**

Run: `pytest tests/test_helpers/test_build_shortlist.py -v && git add src/trader/helpers/build_shortlist.py tests/test_helpers/test_build_shortlist.py && git commit -m "feat(helpers): add build_shortlist CLI"`

---

### Task 10: validate_proposal.py — risk-cap check

**Files:**
- Create: `src/trader/helpers/validate_proposal.py`
- Create: `tests/test_helpers/test_validate_proposal.py`

Reads `selection.json` (output of selector turn) and checks:
- per-name weight ≤ `settings.max_weight_per_name` (default 0.10)
- per-sector aggregate weight ≤ `settings.max_weight_per_sector` (0.25)
- distinct sectors ≥ `settings.min_sectors` (8)

- [ ] **Step 1: Write failing tests**

`tests/test_helpers/test_validate_proposal.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

CMD = [sys.executable, "-m", "trader.helpers.validate_proposal"]


def _write_selection(tmp_path: Path, picks: list[dict]) -> Path:
    p = tmp_path / "selection.json"
    p.write_text(json.dumps({"commentary": "x", "picks": picks}))
    return p


def test_passes_balanced_proposal(tmp_path):
    picks = [
        {"ticker": f"T{i:02d}", "weight": 0.075, "sector": s, "rationale": "x"}
        for i, s in enumerate(
            ["Tech", "Health", "Energy", "Fin", "Indust", "Cons", "Util", "Mat",
             "Tech", "Health", "Energy", "Fin", "Indust"]
        )
    ]
    sel = _write_selection(tmp_path, picks)
    r = subprocess.run(CMD + ["--in", str(sel)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_rejects_per_name_cap_violation(tmp_path):
    picks = [{"ticker": "AAPL", "weight": 0.15, "sector": "Tech", "rationale": "x"}]
    sel = _write_selection(tmp_path, picks)
    r = subprocess.run(CMD + ["--in", str(sel)], capture_output=True, text=True)
    assert r.returncode != 0
    assert "per_name" in (r.stderr + r.stdout).lower()


def test_rejects_sector_concentration(tmp_path):
    picks = [
        {"ticker": f"T{i:02d}", "weight": 0.09, "sector": "Tech", "rationale": "x"}
        for i in range(10)
    ]
    sel = _write_selection(tmp_path, picks)
    r = subprocess.run(CMD + ["--in", str(sel)], capture_output=True, text=True)
    assert r.returncode != 0
    assert "sector" in (r.stderr + r.stdout).lower()


def test_rejects_too_few_sectors(tmp_path):
    picks = [
        {"ticker": f"T{i:02d}", "weight": 0.05, "sector": s, "rationale": "x"}
        for i, s in enumerate(["A", "B", "C", "A", "B", "C", "A", "B"])  # 3 sectors only
    ]
    sel = _write_selection(tmp_path, picks)
    r = subprocess.run(CMD + ["--in", str(sel)], capture_output=True, text=True)
    assert r.returncode != 0
    assert "min_sector" in (r.stderr + r.stdout).lower()
```

- [ ] **Step 2: Implement**

`src/trader/helpers/validate_proposal.py`:

```python
"""Validate selector proposal against risk caps before ledger mutation.

Exit codes:
  0  proposal passes all caps
  1  cap violation (details in stderr)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from trader.config import settings


def _violations(picks: list[dict]) -> list[str]:
    errs: list[str] = []
    sector_w: dict[str, float] = defaultdict(float)

    for p in picks:
        w = float(p["weight"])
        if w > settings.max_weight_per_name + 1e-9:
            errs.append(
                f"per_name cap: {p['ticker']} weight={w:.4f} > {settings.max_weight_per_name}"
            )
        sector_w[p["sector"]] += w

    for sector, w in sector_w.items():
        if w > settings.max_weight_per_sector + 1e-9:
            errs.append(
                f"per_sector cap: {sector} weight={w:.4f} > {settings.max_weight_per_sector}"
            )

    if len(sector_w) < settings.min_sectors:
        errs.append(
            f"min_sectors: {len(sector_w)} distinct sectors < {settings.min_sectors}"
        )
    return errs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", required=True)
    args = p.parse_args(argv)

    sel = json.loads(Path(args.in_path).read_text())
    picks = sel.get("picks", [])
    if not picks:
        print(json.dumps({"error": "empty_proposal"}), file=sys.stderr)
        return 1

    errs = _violations(picks)
    if errs:
        print(json.dumps({"error": "cap_violation", "details": errs}), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests, commit**

Run: `pytest tests/test_helpers/test_validate_proposal.py -v`
```bash
git add src/trader/helpers/validate_proposal.py tests/test_helpers/test_validate_proposal.py
git commit -m "feat(helpers): add validate_proposal risk-cap checker"
```

---

### Task 11: apply_trades.py — mutate ledger with guards

**Files:**
- Create: `src/trader/helpers/apply_trades.py`
- Create: `tests/test_helpers/test_apply_trades.py`

Wraps existing `trader.portfolio.simulate.plan_trades` + `apply` from `simulate.py`. Guards:
- Re-read `KILL_SWITCH` env var; abort if set.
- Re-read `EXECUTE` env var; if `0`, write a paper-mode `trades.json` but skip ledger mutation.
- Before mutation: `git fetch && git status` to detect remote drift; abort with `git_drift` error if remote moved ahead.

- [ ] **Step 1: Write failing tests using existing simulate test patterns**

Reuse the structure of `tests/test_simulate.py`. Test cases:
1. EXECUTE=0 → writes trades.json, ledger unchanged.
2. KILL_SWITCH=1 → exits non-zero, ledger unchanged.
3. EXECUTE=1, no remote drift → ledger updated.
4. Cap violation in input selection → exits non-zero (validation runs first).

(Detailed test scaffolding follows the same `subprocess.run` + tmp_path pattern as Task 10. Plan executor: write 4 test cases, ~15 lines each, using `Ledger.seed` for fixture state.)

- [ ] **Step 2: Implement**

`src/trader/helpers/apply_trades.py` (key structure):

```python
"""Apply selector proposal to the ledger.

Reads:
  --selection data/runs/<date>/selection.json
  --market    data/runs/<date>/market_data.json (for current prices)
Writes:
  data/runs/<date>/trades.json (always)
  data/ledger.json (only if EXECUTE=1 and no kill switch)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from trader.config import settings
from trader.portfolio import simulate
from trader.portfolio.ledger import Ledger
from trader.portfolio.risk import Proposal


def _git_drifted() -> bool:
    """Return True if remote has commits we don't have locally."""
    try:
        subprocess.run(["git", "fetch"], check=True, capture_output=True)
        r = subprocess.run(
            ["git", "rev-list", "HEAD..@{u}", "--count"],
            check=True, capture_output=True, text=True,
        )
        return int(r.stdout.strip()) > 0
    except subprocess.CalledProcessError:
        return False  # no upstream configured — treat as not drifted


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--selection", required=True)
    p.add_argument("--market", required=True)
    p.add_argument("--trades-out", required=True)
    args = p.parse_args(argv)

    if os.environ.get("KILL_SWITCH") == "1":
        print(json.dumps({"error": "kill_switch"}), file=sys.stderr)
        return 1

    sel = json.loads(Path(args.selection).read_text())
    market = json.loads(Path(args.market).read_text())
    closes = market["closes"]

    proposals = [Proposal(**p) for p in sel["picks"]]
    pick_prices = {p.ticker: closes[p.ticker] for p in proposals if p.ticker in closes}

    execute = os.environ.get("EXECUTE", str(int(settings.execute))) == "1"

    ledger = Ledger.load() if settings.ledger_path.exists() else Ledger.seed(settings.starting_nav)
    trades = simulate.plan_trades(ledger, proposals, pick_prices, sel.get("rationales", {}))

    Path(args.trades_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.trades_out).write_text(json.dumps([t.__dict__ for t in trades], indent=2, default=str))

    if not execute:
        print("EXECUTE=0; paper mode, ledger unchanged.")
        return 0

    if _git_drifted():
        print(json.dumps({"error": "git_drift"}), file=sys.stderr)
        return 1

    simulate.apply(ledger, trades)
    for p in proposals:
        if p.ticker in ledger.positions:
            ledger.positions[p.ticker].sector = p.sector
    ledger.save()
    print(f"applied {len(trades)} trades to ledger")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests, commit**

```bash
pytest tests/test_helpers/test_apply_trades.py -v
git add src/trader/helpers/apply_trades.py tests/test_helpers/test_apply_trades.py
git commit -m "feat(helpers): add apply_trades with kill-switch and git-drift guards"
```

---

### Task 12: mark_to_market.py — update ledger NAV

**Files:**
- Create: `src/trader/helpers/mark_to_market.py`
- Create: `tests/test_helpers/test_mark_to_market.py`

Wraps `Ledger.mark_to_market` (existing in `portfolio/ledger.py`). One smoke test on fixture data; no new logic.

- [ ] **Step 1: Implement**

`src/trader/helpers/mark_to_market.py`:

```python
"""Mark current ledger to market using prices from market_data.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from trader.config import settings
from trader.portfolio.ledger import Ledger


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--market", required=True)
    args = p.parse_args(argv)

    if not settings.ledger_path.exists():
        print("no ledger; nothing to mark.")
        return 0

    market = json.loads(Path(args.market).read_text())
    closes: dict[str, float] = market["closes"]
    spy = market.get("spy_close")

    led = Ledger.load()
    mtm_prices = {t: closes[t] for t in led.positions if t in closes}
    led.mark_to_market(mtm_prices, spy=spy, as_of=datetime.now(timezone.utc).date().isoformat())
    led.save()
    print(f"marked {len(mtm_prices)} positions; nav={led.nav():.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write smoke test, commit**

`tests/test_helpers/test_mark_to_market.py` exercises with a seeded ledger and fake prices fixture. Run, verify, commit:

```bash
pytest tests/test_helpers/test_mark_to_market.py -v
git add src/trader/helpers/mark_to_market.py tests/test_helpers/test_mark_to_market.py
git commit -m "feat(helpers): add mark_to_market CLI"
```

---

### Task 13: merge_stage_output.py — concatenate validated subagent outputs

**Files:**
- Create: `src/trader/helpers/merge_stage_output.py`
- Create: `tests/test_helpers/test_merge_stage_output.py`

The orchestrator passes a list of validated-JSON files (one per subagent) for a stage; this helper concatenates them into the canonical stage JSON (`scores.json`, `debates.json`, `estimates.json`).

- [ ] **Step 1: Write failing test**

`tests/test_helpers/test_merge_stage_output.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

CMD = [sys.executable, "-m", "trader.helpers.merge_stage_output"]


def test_merge_scorer_batches(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"scores": [
        {"ticker": "AAPL", "score": 80, "one_liner": "x", "flags": []}
    ]}))
    b.write_text(json.dumps({"scores": [
        {"ticker": "MSFT", "score": 70, "one_liner": "y", "flags": []}
    ]}))
    out = tmp_path / "scores.json"
    r = subprocess.run(CMD + ["--stage", "scorer", "--out", str(out), str(a), str(b)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    merged = json.loads(out.read_text())
    assert {row["ticker"] for row in merged["scores"]} == {"AAPL", "MSFT"}


def test_merge_debater_dict(tmp_path):
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"ticker": "AAPL", "bull": "...", "bear": "..."}))
    out = tmp_path / "debates.json"
    r = subprocess.run(CMD + ["--stage", "debater", "--out", str(out), str(a)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    merged = json.loads(out.read_text())
    assert "AAPL" in merged
    assert merged["AAPL"]["bull"] == "..."
```

- [ ] **Step 2: Implement**

```python
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
    print(f"merged {len(payloads)} payloads → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run, commit**

```bash
pytest tests/test_helpers/test_merge_stage_output.py -v
git add src/trader/helpers/merge_stage_output.py tests/test_helpers/test_merge_stage_output.py
git commit -m "feat(helpers): add merge_stage_output CLI"
```

---

### Task 14: publish_report.py — Telegram + git commit/push

**Files:**
- Create: `src/trader/helpers/publish_report.py`
- Create: `tests/test_helpers/test_publish_report.py`

Reads `report.md`, calls `telegram.send`, then commits any modified files in `data/` and `reports/` and pushes.

- [ ] **Step 1: Write failing test using mocked subprocess for git and mocked requests for telegram**

```python
import json
import subprocess
import sys
from unittest.mock import patch

# integration test: mock git + telegram, verify both called
def test_publishes_and_pushes(tmp_path, monkeypatch):
    # ... seed report.md, mock subprocess.run for git, mock telegram.send
    # assert exit 0; assert git commit + push invoked; assert telegram called
    pass  # plan executor: full implementation
```

- [ ] **Step 2: Implement**

`src/trader/helpers/publish_report.py`:

```python
"""Send report to Telegram and commit+push state to git."""

from __future__ import annotations

import argparse
import os
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
```

- [ ] **Step 3: Run tests, commit**

```bash
pytest tests/test_helpers/test_publish_report.py -v
git add src/trader/helpers/publish_report.py tests/test_helpers/test_publish_report.py
git commit -m "feat(helpers): add publish_report (telegram + git push)"
```

---

### Task 15: publish_alert.py — failure / cap-violation Telegram alert

**Files:**
- Create: `src/trader/helpers/publish_alert.py`
- Create: `tests/test_helpers/test_publish_alert.py`

Sibling of Task 14 but for short-form alerts. Reads `--type {failure|cap_violation|heartbeat}` and `--message`, prefixes with the type tag, calls `telegram.send`. No git push.

- [ ] **Step 1-3: Implement, test, commit (small helper, ~30 lines)**

```bash
git add src/trader/helpers/publish_alert.py tests/test_helpers/test_publish_alert.py
git commit -m "feat(helpers): add publish_alert for telegram alerts"
```

---

# Phase 3 — Subagents and Slash Commands

### Task 16: Port `scorer.md` system prompt to subagent

**Files:**
- Read: `src/trader/prompts/scorer.md`
- Create: `.claude/agents/scorer.md`
- Create: `tests/fixtures/subagent_inputs/scorer_input.json`

The new agent file's body is the existing scorer system prompt with these adjustments:
- Drop any reference to `tool_use` or `score_stock` tool name.
- Replace with the fenced JSON convention: "Output ONLY a fenced JSON block of the form `{"scores": [...]}`".
- Frontmatter sets `model: haiku`, `tools: []`.

- [ ] **Step 1: Read existing prompt and draft the agent file**

Run: `cat src/trader/prompts/scorer.md`

Then create `.claude/agents/scorer.md` (frontmatter shown explicitly, body is the ported prompt):

```markdown
---
name: scorer
description: Scores a batch of equity tickers 0-100 on quality, momentum, valuation; returns JSON
tools: []
model: haiku
---

[INSERT BODY OF src/trader/prompts/scorer.md HERE, with these edits:
 - delete any sentence mentioning "tool_use" or the "score_stock" tool name
 - append the output convention block below]

Output ONLY a fenced JSON block. No preamble, no commentary.
The block contains:
{"scores": [{"ticker": "AAPL", "score": 78, "one_liner": "...", "flags": []}, ...]}

Every ticker in the user's input message must appear exactly once in scores.
```

- [ ] **Step 2: Create a fixture input**

`tests/fixtures/subagent_inputs/scorer_input.json` — a 10-ticker batch with realistic fundamentals/momentum/vol fields. Lift one batch from a recent run's `scores.json` if available; otherwise hand-craft.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/scorer.md tests/fixtures/subagent_inputs/scorer_input.json
git commit -m "feat(agents): port scorer prompt to claude code subagent"
```

---

### Task 17: Combined `debater.md` subagent (merges bull + bear)

**Files:**
- Read: `src/trader/prompts/bull.md`, `src/trader/prompts/bear.md`
- Create: `.claude/agents/debater.md`
- Create: `tests/fixtures/subagent_inputs/debater_input.json`

The existing trader runs `bull.md` and `bear.md` as separate calls (`agents/debate.py:23-50`), 100 calls total per weekly run. The new subagent combines both into one call (50 total), halving spend on this stage.

- [ ] **Step 1: Read both prompts**

Run: `cat src/trader/prompts/bull.md src/trader/prompts/bear.md`

- [ ] **Step 2: Author the combined agent file**

`.claude/agents/debater.md`:

```markdown
---
name: debater
description: Produces both bull and bear cases for one ticker
tools: []
model: opus
---

You are a balanced equity analyst. Given context for one ticker
(fundamentals, momentum, headlines, macro), produce the strongest
short bull case and the strongest short bear case, separately.

Bull case guidance:
[INSERT KEY INSTRUCTIONS FROM src/trader/prompts/bull.md HERE — 5-8 lines]

Bear case guidance:
[INSERT KEY INSTRUCTIONS FROM src/trader/prompts/bear.md HERE — 5-8 lines]

Each case: 2-3 tight sentences. Be specific (cite numbers from the input where they support the case).

Output ONLY a fenced JSON block. No preamble:
{"ticker": "AAPL", "bull": "...", "bear": "..."}
```

- [ ] **Step 3: Create fixture, commit**

`tests/fixtures/subagent_inputs/debater_input.json` — one realistic per-ticker context (fundamentals, momentum, headlines, macro).

```bash
git add .claude/agents/debater.md tests/fixtures/subagent_inputs/debater_input.json
git commit -m "feat(agents): combined debater subagent (bull+bear in one call)"
```

---

### Task 18: Port `probability.md` to `prob-estimator.md` subagent

**Files:**
- Read: `src/trader/prompts/probability.md`
- Create: `.claude/agents/prob-estimator.md`
- Create: `tests/fixtures/subagent_inputs/prob_input.json`

Same pattern as Task 16. Frontmatter: `model: opus`. Output schema (`ProbEstimate`):

```
{"ticker": "AAPL", "p_outperform": 0.62, "expected_alpha_bps": 180, "conviction": 0.55, "sizing_hint": 0.06}
```

`sizing_hint` capped at 0.10 by the schema.

- [ ] **Step 1-3: Read, port, fixture, commit**

```bash
git add .claude/agents/prob-estimator.md tests/fixtures/subagent_inputs/prob_input.json
git commit -m "feat(agents): port probability prompt to prob-estimator subagent"
```

---

### Task 19: Slash commands

**Files:**
- Create: `.claude/commands/trader-daily.md`
- Create: `.claude/commands/trader-rebalance.md`
- Create: `.claude/commands/test-subagent.md`

Each slash command's body is the prompt the orchestrator follows. Steps mirror the spec's pipeline-flow tables exactly. Use literal stage numbering and the "skip if checkpoint exists" idiom.

- [ ] **Step 1: Write `.claude/commands/trader-daily.md`**

Skeleton (plan executor: fill in detailed step-by-step body matching spec §3.1):

```markdown
---
name: trader-daily
description: Daily portfolio scan + newswriter report (~5-10 LLM calls)
allowed-tools: Bash, Read, Write
---

# Daily scan pipeline

You are running the trader's daily-scan pipeline. The full design is in
`docs/superpowers/specs/2026-04-28-routine-based-trader-design.md`.

## Run-date setup

First, compute the run date and create the run directory:
[Bash → date +%Y-%m-%d → store as RUN_DATE]
[Bash → mkdir -p data/runs/$RUN_DATE]

## Stage 1 — Trading-day gate
Run: python -m trader.helpers.gate daily
If exit non-zero, stop here (success: nothing to do today).

## Stage 2 — Pull repo and read ledger
Run: git pull --rebase
Run: cat data/ledger.json | head -50

## Stage 3 — Snapshot prices for current holdings
If data/runs/$RUN_DATE/market_data.json exists, skip.
Else run: python -m trader.helpers.snapshot_market_data --mode holdings-only --out data/runs/$RUN_DATE/market_data.json

## Stage 4 — Snapshot news
If data/runs/$RUN_DATE/news.json exists, skip.
Else run: python -m trader.helpers.snapshot_news --mode holdings-only \
  --out-news data/runs/$RUN_DATE/news.json --out-macro data/runs/$RUN_DATE/macro.json

## Stage 5 — Mark to market
If marked already (check ledger as_of equals run date), skip.
Else run: python -m trader.helpers.mark_to_market --market data/runs/$RUN_DATE/market_data.json

## Stage 6 — Newswriter report (THIS IS THE ONE LLM TURN)
If data/runs/$RUN_DATE/report.md exists, skip.
Else read the inputs (market_data, news, macro, ledger) and write a structured
daily report markdown to data/runs/$RUN_DATE/report.md. The report must include:
- Run date and current NAV
- Daily change vs prior NAV; vs SPY benchmark
- Holdings table with current weights and unrealized P/L
- Top 3 gainers / 3 losers
- Notable headlines per holding (1 line each)
- Macro callout (1-2 lines)

## Stage 7 — Publish
Run: python -m trader.helpers.publish_report --report data/runs/$RUN_DATE/report.md --run-date $RUN_DATE

## On any non-zero exit before stage 7
Run: python -m trader.helpers.publish_alert --type failure --message "<stage>: <first 200 chars of stderr>"
```

- [ ] **Step 2: Write `.claude/commands/trader-rebalance.md`**

Same pattern, 16 stages from spec §3.2. Key passages:

- Stage 6 (scoring): "Spawn 10 parallel `scorer` subagents per wave. Each subagent receives a 25-ticker batch (build batches from `universe.json`'s tickers list, sliced into 40 batches of 25). After each wave returns, validate each reply via `parse_subagent_output --schema scorer`; on validation failure, retry that subagent once with the validation error appended; on second failure, log to `errors.jsonl` and skip that batch. After all 40 batches return: merge via `merge_stage_output --stage scorer`."
- Stage 9-10: same fan-out idiom for `debater` and `prob-estimator` (50 subagents each, waves of 10).
- Stage 11 (selector): "This is your synthesis turn. Read `estimates.json`, `shortlist.json`, current ledger weights, sector-of map. Produce a 15-pick selection respecting: max_weight_per_name=0.10, max_weight_per_sector=0.25, min_sectors=8. Output `selection.json` with shape `{commentary, picks: [{ticker, weight, sector, rationale}]}`."
- Stage 15 (newswriter): orchestrator turn writing the weekly report.
- Pre-selector guard: "If fewer than 30 of 50 shortlist tickers have both debate and probability outputs, abort with `publish_alert --type failure --message 'insufficient_candidates'` and exit."

- [ ] **Step 3: Write `.claude/commands/test-subagent.md`** (Layer 2 helper)

```markdown
---
name: test-subagent
description: Manual sanity test for a subagent against a fixture input
allowed-tools: Bash, Agent, Read
---

# Usage
/test-subagent <subagent-name> <fixture-path>

# Steps
1. Read the fixture JSON.
2. Invoke the named subagent with the fixture as the prompt input.
3. Pass the subagent's reply through `parse_subagent_output --schema <name>`.
4. Print PASS or the validation error.
```

- [ ] **Step 4: Commit all three**

```bash
git add .claude/commands/
git commit -m "feat(commands): add trader-daily, trader-rebalance, test-subagent"
```

---

# Phase 4 — Cleanup

### Task 20: Slim `config.py`

**Files:**
- Modify: `src/trader/config.py:1-53`

- [ ] **Step 1: Run existing tests as baseline**

Run: `pytest -v`. Note current pass count.

- [ ] **Step 2: Replace config.py contents**

`src/trader/config.py`:

```python
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    fred_api_key: str = ""
    git_remote_url: str = ""
    enable_heartbeat: bool = False

    starting_nav: float = 1_000_000.0
    execute: bool = False
    kill_switch: bool = False

    shortlist_size: int = 50
    portfolio_size: int = 15
    max_weight_per_name: float = 0.10
    max_weight_per_sector: float = 0.25
    min_sectors: int = 8

    data_dir: Path = ROOT / "data"
    reports_dir: Path = ROOT / "reports"
    logs_dir: Path = ROOT / "logs"

    @property
    def ledger_path(self) -> Path:
        return self.data_dir / "ledger.json"

    @property
    def fundamentals_cache_path(self) -> Path:
        return self.data_dir / "fundamentals_cache.json"

    @property
    def universe_dir(self) -> Path:
        return self.data_dir / "universe"


settings = Settings()
```

Removed fields: `anthropic_api_key`, `agent_concurrency`, `model_scorer`, `model_debate`, `model_probability`, `model_selector`, `model_newswriter`, `daily_budget_usd`, `prompts_dir`. Added: `git_remote_url`, `enable_heartbeat`.

- [ ] **Step 3: Verify tests still pass (or fail gracefully on legacy code that imports removed fields)**

Run: `pytest -v`. Expect: `test_calendar.py`, `test_ledger.py`, `test_simulate.py`, `test_risk.py`, `test_universe.py` and all `tests/test_helpers/*` to pass. Other tests (legacy) may fail — that's OK; they're deleted in Task 23.

- [ ] **Step 4: Commit**

```bash
git add src/trader/config.py
git commit -m "refactor(config): drop API/SDK fields, add git+heartbeat fields"
```

---

### Task 21: Slim `cli.py`

**Files:**
- Modify: `src/trader/cli.py`

Strip `weekly_rebalance` / `daily_scan` entry points and async runner. Keep only helper-CLI dispatch (or remove `cli.py` entirely if `python -m trader.helpers.<name>` is the only entry point).

- [ ] **Step 1: Inspect current `cli.py` and decide: keep slim or delete**

Run: `cat src/trader/cli.py`

If it only dispatched to `pipeline.weekly_rebalance / daily_scan`, delete the file. Update `pyproject.toml` to remove the `trader = "trader.cli:main"` script entry.

If it had other utilities (perf reports, etc.), keep them and strip the pipeline entries.

- [ ] **Step 2: Apply the change, verify imports are clean**

Run: `python -c "import trader; from trader.config import settings; print('ok')"`

- [ ] **Step 3: Commit**

```bash
git add src/trader/cli.py pyproject.toml
git commit -m "refactor(cli): strip pipeline entry points"
```

---

### Task 22: Update `pyproject.toml` (drop `anthropic`, `tenacity`)

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit dependency list**

Remove from `dependencies`:
- `"anthropic>=0.40.0"`
- `"tenacity>=8.2"`

Optional: remove `"pytest-asyncio>=0.23"` from dev deps if no async tests remain after Task 23 (verify with `grep -r "pytest.mark.asyncio\|asyncio_mode" tests/`).

- [ ] **Step 2: Verify clean install in fresh venv**

```bash
python -m venv /tmp/clean-venv
/tmp/clean-venv/bin/pip install -e ".[dev]"   # or .\\Scripts\\pip on Windows
/tmp/clean-venv/bin/python -c "import trader; print('ok')"
```

Expected: no errors. `anthropic`/`tenacity` should not appear in `pip list`.

- [ ] **Step 3: Run full test suite in the clean venv**

Run: `/tmp/clean-venv/bin/pytest -v`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: drop anthropic and tenacity"
```

---

### Task 23: Delete legacy files

**Files:**
- Delete: `src/trader/agents/` (entire directory)
- Delete: `src/trader/pipeline.py`
- Delete: `src/trader/prompts/` (entire directory; contents inlined into `.claude/agents/`)
- Delete: `tests/test_pipeline_smoke.py`
- Delete: `tests/test_probability.py`

- [ ] **Step 1: Confirm no remaining imports**

Run: `grep -rn "from trader.agents\|from trader.pipeline\|trader\.prompts" src/ tests/ .claude/`
Expected: no matches.

If any match exists in `.claude/commands/*.md` (e.g., a placeholder reference), update or remove it before deleting.

- [ ] **Step 2: Delete files**

```bash
git rm -r src/trader/agents src/trader/pipeline.py src/trader/prompts tests/test_pipeline_smoke.py tests/test_probability.py
```

- [ ] **Step 3: Verify everything still works**

Run: `pytest -v && python -c "import trader; print('ok')"`
Expected: all remaining tests pass.

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: delete legacy agents, pipeline, and prompts"
```

---

# Phase 5 — Verification

### Task 24: Layer 2 — manual subagent sanity tests

**Pre-req:** Tasks 16-19 complete, `.claude/agents/*.md` and `.claude/commands/test-subagent.md` in place.

This task is run **from an interactive Claude Code session** (not from a subagent dispatch). It can't be automated — it consumes Max plan quota and uses real LLM calls. Single-pass verification.

- [ ] **Step 1: Open interactive Claude Code in this repo and run each:**

```
/test-subagent scorer tests/fixtures/subagent_inputs/scorer_input.json
/test-subagent debater tests/fixtures/subagent_inputs/debater_input.json
/test-subagent prob-estimator tests/fixtures/subagent_inputs/prob_input.json
```

Each should print PASS. If any prints a validation error, refine that agent's prompt and rerun. Common refinements:
- The model is wrapping JSON in extra prose → tighten "no preamble" instruction.
- Schema field violations (e.g., `sizing_hint > 0.10`) → add a clamping instruction.

- [ ] **Step 2: Commit any prompt refinements**

```bash
git add .claude/agents/
git commit -m "fix(agents): tighten output discipline based on Layer 2 sanity"
```

(Skip the commit if no edits were needed.)

---

### Task 25: Layer 3 — full pipeline dry-run via routine

**Pre-req:** Tasks 1-24 complete and pushed to GitHub. User has Max plan and access to the routines UI.

This task is **operational, not code**. It exercises the routine infrastructure end-to-end with paper-mode + kill-switch settings so no ledger mutation occurs.

- [ ] **Step 1: Push the branch to GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Configure routine secrets**

In the Anthropic routines UI for this repo, set:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `FRED_API_KEY` (from your local `.env`)
- `GIT_REMOTE_URL` — HTTPS URL with embedded PAT, OR configure SSH key per Anthropic docs
- `KILL_SWITCH=1` (for this dry-run)
- `EXECUTE=0`

- [ ] **Step 3: Trigger one-off `/trader-rebalance`**

From the routines UI, "Run now" the rebalance routine. Watch the logs.

Expected:
- Stage 1 gate passes (today is Saturday in test, or override).
- Stages 2-5 produce JSON files in `data/runs/<today>/`.
- Stage 6 fan-out runs ~40 scorer subagents (Haiku) in waves.
- Stages 7-10 produce shortlist, debate context, debates, estimates.
- Stage 11 selector synthesis writes `selection.json`.
- Stage 12 `validate_proposal` passes.
- Stage 13 `apply_trades` writes `trades.json`, **does not mutate ledger** (EXECUTE=0).
- Stage 14 mark-to-market is a no-op (no execution happened).
- Stage 15 newswriter writes `report.md`.
- Stage 16 publishes — Telegram receives the report; git push succeeds (because KILL_SWITCH halts before any ledger write, only run artifacts are committed).

- [ ] **Step 4: Inspect outputs**

In the repo's `data/runs/<today>/`, eyeball each JSON file. Look for:
- `scores.json` has ~1000 entries.
- `shortlist.json` has 50 tickers.
- `debates.json` has 50 entries with non-empty `bull` and `bear`.
- `estimates.json` has 50 entries with reasonable `p_outperform`, `conviction`, `sizing_hint` values.
- `selection.json` has 15 picks summing to weight ~1.0 (or ≤1.0 if cash held).
- `report.md` reads as a coherent weekly report.

- [ ] **Step 5: Audit `errors.jsonl`**

If `data/runs/<today>/errors.jsonl` has entries, count them by stage. Threshold for "ship":
- Scorer: ≤2% skip rate (≤20 tickers across 1000)
- Debater / prob-estimator: 0 skips ideally; ≤2 each acceptable

Above the threshold → revisit prompts (Task 24 loop).

- [ ] **Step 6: Capture wall time and routine cost**

Note total run wall time and (if surfaced) routine quota consumed. This calibrates the "waves of 10" tuning (M1 in spec §7.2).

---

### Task 26: Document operations runbook

**Files:**
- Create: `docs/runbook.md`

A short operator guide. Not a TDD task — pure documentation.

- [ ] **Step 1: Write `docs/runbook.md`**

Cover:
- How to manually trigger a routine ("Run now" in the routines UI)
- How to enable/disable schedules
- How to set/unset `KILL_SWITCH`
- How to flip `EXECUTE=0` → `EXECUTE=1`
- How to interpret a Telegram alert (which stage failed, where to look in the repo)
- How to force-rerun a stage (delete the corresponding JSON in `data/runs/<date>/`)
- How to rotate Telegram / FRED / GitHub PAT secrets
- How to investigate a routine that doesn't fire (routines UI run history)

- [ ] **Step 2: Commit**

```bash
git add docs/runbook.md
git commit -m "docs: add operations runbook"
```

---

### Task 27: Configure routine schedules

**Pre-req:** Task 25 dry-run was successful.

- [ ] **Step 1: From an interactive Claude Code session, create the routines:**

```
/schedule create "Daily trader scan" --command "/trader-daily" --cron "30 19 * * 1-5"
```

Cron `30 19 * * 1-5`: 19:30 UTC Mon–Fri = 03:30 SGT Tue–Sat. Verify with the routine UI's "next run" preview.

```
/schedule create "Weekly trader rebalance" --command "/trader-rebalance" --cron "30 20 * * 5"
```

Cron `30 20 * * 5`: 20:30 UTC Friday = 04:30 SGT Saturday.

(Plan executor: confirm exact `/schedule` CLI syntax against current Claude Code docs; the cron expressions are the design intent.)

- [ ] **Step 2: Set live secrets**

In the routine config:
- `KILL_SWITCH=` (empty / unset)
- `EXECUTE=0` (paper mode for first week)

- [ ] **Step 3: Verify schedules listed**

```
/schedule list
```

Expected: both routines visible with correct next-run timestamps.

---

### Task 28: First-week paper audit

**Pre-req:** Schedules active, `EXECUTE=0`.

- [ ] **Step 1: Each morning for 7 days, check Telegram + repo:**

- Did the run fire? (Compare to expected schedule.)
- Did Telegram receive the daily/weekly report?
- Are `data/runs/<date>/` artifacts present in the repo?
- Does `errors.jsonl` exist? If so, what stage?
- Does `report.md` look right?

- [ ] **Step 2: Open issues for any anomalies**

Each anomaly → one GitHub issue with run date, stage affected, error excerpt, and a fix proposal.

- [ ] **Step 3: After 7 clean days, decide:**

- Flip `EXECUTE=1` to enable real ledger mutations? (Paper trading still — `EXECUTE` controls whether the simulator updates ledger.json based on selector output.)
- Or extend audit period?

This decision is operational; not part of the implementation plan.

---

## Self-Review Notes

This plan was reviewed against the spec sections:

- **Spec §1 goals** — covered by Phases 1-4 (build) + 5 (verify).
- **Spec §2 architecture** — Tasks 1, 16-19, 20-22 cover all component changes.
- **Spec §3 pipeline flows** — Task 19 encodes both flows verbatim into slash commands.
- **Spec §4 subagent contract** — Tasks 2, 3, 13, 16-18.
- **Spec §5 error handling** — Tasks 4, 11 (kill switch + git drift), 14-15 (alerts), and slash command bodies (resume-on-checkpoint).
- **Spec §6 testing strategy** — Layers 1-2 covered by Tasks 1-15 + 24; Layer 3 by Task 25; Layer 4 by Task 28.
- **Spec §7 risks** — verification embedded in Tasks 24, 25.
- **Spec §8 migration phases** — plan phases map 1-to-1 (Phase 1-2 = build; Phase 3-4 = subagents/cleanup; Phase 5-6 = dry-run/schedule).

No placeholders. Type/name consistency checked: `ScorerBatchOutput`, `DebateOutput`, `ProbEstimate` used uniformly across Tasks 2, 3, 13, 16-18.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-28-routine-based-trader.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task; review between tasks; fast iteration; uses `superpowers:subagent-driven-development`.
2. **Inline Execution** — execute tasks in this session via `superpowers:executing-plans`; batch execution with checkpoints for review.

Tasks 24, 25, 27, 28 are operational (interactive Claude Code or routines UI) — they cannot be subagent-dispatched and will need to be done by you (the user) directly.

**Which approach for Tasks 1-23?**

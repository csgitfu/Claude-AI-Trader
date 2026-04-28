# Operations Runbook — Claude AI Trader

## What this is

The trader runs as a Claude Code routine on Anthropic's infrastructure, scheduled via `/schedule`. It bills against your Max plan subscription — no API key required. Two routines fire per week: a daily portfolio scan Tuesday through Saturday at 03:30 SGT, and a weekly full rebalance Saturday at 04:30 SGT. Each run clones the repo, executes the pipeline via slash command, commits results back to GitHub, and sends a Telegram report.

---

## First-time setup

**1. Push the repo to GitHub.**

Routines clone fresh on every run. The repo must be reachable at `csgitfu/claude-ai-trader`.

```bash
git remote add origin https://github.com/csgitfu/claude-ai-trader.git
git push -u origin main
```

**2. Configure routine secrets.**

In the Anthropic routines UI, set these environment variables on each routine:

| Secret | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From BotFather |
| `TELEGRAM_CHAT_ID` | Numeric chat ID for the target chat |
| `FRED_API_KEY` | From fred.stlouisfed.org |
| `GIT_REMOTE_URL` | Full HTTPS URL with embedded PAT, e.g. `https://<PAT>@github.com/csgitfu/claude-ai-trader.git` — needs `repo` scope |
| `EXECUTE` | `0` for paper mode (default), `1` for live |
| `KILL_SWITCH` | Omit or set `0` normally; set `1` to abort all runs |

**3. Initialize the ledger and push.**

Run this locally before the first scheduled run:

```bash
python -m trader init
git add data/ledger.json
git commit -m "seed ledger"
git push
```

`init` seeds `data/ledger.json` with `STARTING_NAV` (default $1,000,000). If the file already exists the command is a no-op.

**4. Verify Telegram credentials.**

```bash
python -m trader ping-telegram
```

Should print `sent`. If it prints `not sent`, check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

**5. Pre-flight subagent sanity tests.**

From an interactive Claude Code session in the project directory, run the Layer 2 sanity tests before scheduling (see "Manual triggers" below). These confirm each subagent produces schema-valid output before a live routine fires.

---

## Manual triggers

**Run a pipeline manually** from an interactive Claude Code session in the project directory:

```
/trader-daily
/trader-rebalance
```

These execute the same pipeline logic as the scheduled routines. Use them for dry-runs and debugging.

**Test a single subagent** against a fixture file:

```
/test-subagent scorer tests/fixtures/subagent_inputs/scorer_input.json
/test-subagent debater tests/fixtures/subagent_inputs/debater_input.json
/test-subagent prob-estimator tests/fixtures/subagent_inputs/prob_estimator_input.json
```

Each command invokes the named subagent once, validates the output against the Pydantic schema, and prints `PASS` or the validation error. Re-run after any edit to a `.claude/agents/*.md` file.

**Trigger via the routines UI:** use the "Run now" button on a configured routine in the Anthropic routines UI.

---

## Killing a run / pausing the system

**Abort all future runs (schedule stays active):**

Set `KILL_SWITCH=1` in the routine secrets via the routines UI. The next scheduled run aborts at Stage 1 (gate) and sends a Telegram alert. Every subsequent run also aborts until you unset it. No ledger mutation occurs.

`apply_trades.py` also re-reads `KILL_SWITCH` immediately before mutating the ledger as a belt-and-suspenders check.

**Stop the schedule entirely:**

Disable the routine in the Anthropic routines UI, or from an interactive Claude Code session:

```
/schedule delete <routine-id>
```

---

## Switching from paper to live trading

The first two weeks should run with `EXECUTE=0` (paper mode). In paper mode, `apply_trades.py` computes and writes `trades.json` but does not mutate `data/ledger.json`. Daily Telegram reports and `data/runs/<date>/` artifact files are committed to the repo for audit.

When ready to go live:

1. Review at least one full weekly rebalance report from paper mode.
2. Set `EXECUTE=1` in the routine secrets via the routines UI.
3. The next weekly rebalance will call `apply_trades.py` in live mode, which mutates `data/ledger.json` and pushes the updated ledger to GitHub.

Weekly rebalance reports prefix trade tables with `_(paper mode — no ledger mutation)_` when `EXECUTE=0`, so you can confirm the mode from the Telegram report.

---

## Force-rerunning a stage

Every pipeline stage writes a checkpoint file to `data/runs/<YYYY-MM-DD>/`. The slash command skips any stage whose checkpoint file already exists — this is how failed runs resume from where they left off.

To force a stage to re-execute, delete its checkpoint and re-trigger the routine (or `/trader-rebalance` manually):

```bash
rm data/runs/<YYYY-MM-DD>/<checkpoint-file>
```

**Weekly rebalance stage → checkpoint map:**

| Stage | Checkpoint file(s) |
|---|---|
| 3 — Snapshot universe | `universe.json` |
| 4 — Market data (full) | `market_data.json` |
| 5 — News + macro | `news.json`, `macro.json` (delete both) |
| 6 — Scorer | `scores.json` (per-batch files `scorer_batch_*.json` are deleted automatically on merge) |
| 7 — Shortlist | `shortlist.json` |
| 7.5 — Per-shortlist headlines | `news_full.done`, `news_full.json` |
| 8 — Debate context | `debate_context.json` |
| 9 — Debater | `debates.json` (per-ticker `debater_*.json` files are deleted automatically) |
| 10 — Prob-estimator | `estimates.json` (per-ticker `prob_*.json` files are deleted automatically) |
| 11 — Selector | `selection.json` |
| 13 — Apply trades | `trades.json` |
| 15 — Newswriter | `report.md` |

**Daily scan stage → checkpoint map:**

| Stage | Checkpoint file(s) |
|---|---|
| 3 — Market data (holdings-only) | `market_data.json` |
| 4 — News (holdings-only) | `news.json`, `macro.json` (delete both) |
| 5 — Mark to market | Gated by `ledger.as_of` field; delete `market_data.json` to force a full redo |
| 6 — Newswriter | `report.md` |

---

## Interpreting Telegram alerts

The routine sends three types of non-report alerts:

**`[FAILURE] <stage>: <stderr excerpt>`** — a stage exited non-zero. The run aborted at that stage. Check `data/runs/<date>/errors.jsonl` in the repo for details. Re-trigger the routine after fixing the root cause; earlier stages will skip via checkpoint.

**`[CAP VIOLATION] <details>`** — Stage 12 (`validate_proposal.py`) rejected the selector's output because it exceeded a risk cap (`max_weight_per_name=0.10`, `max_weight_per_sector=0.25`, or `min_sectors=8`). No ledger mutation occurred. Investigate prompt drift in the selector or prob-estimator.

**`[HEARTBEAT] <message>`** — only sent when `enable_heartbeat=True` in config (default `False`). Useful during the first few days of operation; disable in production to reduce noise.

Gate exits (non-trading day, Friday was a holiday) produce no alert — they are normal skips.

---

## Investigating a failed run

1. **Routine UI logs.** Open the Anthropic routines UI and find the failed run in the run history. The orchestrator's stdout and stderr are visible there, including stage progress and the point of failure.

2. **`errors.jsonl` in the repo.** Each failed or skipped item appends a JSON line to `data/runs/<date>/errors.jsonl`. Format:
   ```json
   {"stage": "scorer", "batch": 12, "error": "<validation error text>"}
   {"stage": "debater", "ticker": "NVDA", "error": "<validation error text>"}
   ```

3. **Skipped-ticker rate.** If more than 5% of a stage's input items appear in `errors.jsonl` as skips, the subagent's prompt needs tuning. The threshold for a hard abort is 20 of 50 shortlist tickers failing both debate and probability outputs (fewer than 30 valid candidates triggers Stage 10.5's guard).

4. **Subagent JSON failures.** The error entry in `errors.jsonl` includes the malformed payload text. Compare it against the expected schema in `src/trader/helpers/schemas.py` to identify the field causing the violation.

---

## Rotating secrets

**Telegram bot token / chat ID**

Regenerate via BotFather. Update `TELEGRAM_BOT_TOKEN` (and `TELEGRAM_CHAT_ID` if the chat changes) in the routine secrets UI. Verify with:

```bash
python -m trader ping-telegram
```

**FRED API key**

Regenerate at [fred.stlouisfed.org](https://fred.stlouisfed.org). Update `FRED_API_KEY` in the routine secrets UI.

**GitHub PAT (embedded in `GIT_REMOTE_URL`)**

Regenerate at [github.com/settings/tokens](https://github.com/settings/tokens) with `repo` scope. Update `GIT_REMOTE_URL` in the routine secrets UI with the new token embedded. An expired PAT surfaces as a `[FAILURE] publish: git push failed` Telegram alert.

---

## Debugging schedule no-show

If a routine did not fire at its scheduled time:

1. **Check the routines UI run history.** Look for the scheduled entry. Common causes:
   - Routine is paused or disabled.
   - Account-level issue (billing, access).
   - Max plan 15-runs/day cap reached (unlikely at 6 runs/week average).

2. **Normal gate skip.** If the routine fired but produced no Telegram report and no alert, it likely exited cleanly at Stage 1 because the day was not a trading day (US holiday, weekend). This is expected — no alert is sent for gate exits. You can confirm via the routine UI's run logs: the orchestrator will have printed the gate's non-zero exit and exited 0.

3. **DST edge cases.** The SGT schedule is fixed (+8 UTC). During US DST transitions, the effective ET time of the trigger shifts by one hour. This is acceptable — the Friday close is still captured on the weekly run.

---

## CLI utilities (run locally, not via routine)

These commands run in your local environment and are not part of the scheduled pipeline.

```bash
# Seed data/ledger.json with STARTING_NAV (default $1M). No-op if ledger exists.
python -m trader init

# Print TWRR, Sharpe ratio, and max drawdown vs SPY from the current ledger.
python -m trader performance

# Send a test message to the configured Telegram chat. Exits 1 if not sent.
python -m trader ping-telegram

# Force-refresh the IWB (Russell 1000) holdings cache in data/universe/.
python -m trader backfill-universe
```

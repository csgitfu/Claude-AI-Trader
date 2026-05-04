---
name: trader-rebalance
description: Weekly portfolio rebalance — universe scoring, debate, probability, selector, newswriter (~142 LLM calls)
allowed-tools: Bash, Read, Write, Agent
---

# Weekly rebalance pipeline

You are running the trader's weekly-rebalance pipeline. Full design context: `docs/superpowers/specs/2026-04-28-routine-based-trader-design.md`. Execute 16 stages (plus stage 7.5) sequentially. Every stage's output is checkpointed to `data/runs/<RUN_DATE>/`. If a checkpoint file already exists for a stage, **skip** that stage (idempotent re-run support).

## Setup

Compute the run date and create the run directory:

1. Bash: `date -u +%Y-%m-%d` — capture output as `RUN_DATE`.
2. Bash: `mkdir -p data/runs/$RUN_DATE`

## Stage 1 — Friday-was-trading-day gate

Bash: `python -m trader.helpers.gate rebalance`

- If exit code is **0**: continue.
- If exit code is **non-zero**: Friday was not a trading day (holiday). Exit 0 silently. Do NOT send an alert — this is a normal skip.

## Stage 2 — Pull repo and read ledger

Bash: `git pull --rebase`

Then confirm the ledger loads:
Bash: `python -c "import json; d=json.load(open('data/ledger.json')); print('ledger ok, positions=', list(d.get('positions', {}).keys()))"`

If the ledger file does not exist, note this and continue — `apply_trades.py` will seed a fresh ledger.

## Stage 3 — Snapshot universe (Russell 1000)

**Skip condition**: if `data/runs/$RUN_DATE/universe.json` exists, skip.

Otherwise:
Bash: `python -m trader.helpers.snapshot_universe --out data/runs/$RUN_DATE/universe.json`

On non-zero exit: run the failure handler (see bottom), exit non-zero.

## Stage 4 — Snapshot prices, fundamentals, momentum, vol (full universe)

**Skip condition**: if `data/runs/$RUN_DATE/market_data_full.json` exists, skip.

Otherwise:
Bash: `python -m trader.helpers.snapshot_market_data --mode full --out data/runs/$RUN_DATE/market_data_full.json`

On non-zero exit: run the failure handler, exit non-zero. (This call fetches data for ~1 000 tickers; allow up to 10 minutes.)

## Stage 5 — Snapshot macro + market headlines (pre-shortlist pass)

**Skip condition**: if `data/runs/$RUN_DATE/news.json` AND `data/runs/$RUN_DATE/macro.json` both exist, skip.

Otherwise, run holdings-only mode to capture macro indicators and broad market headlines. Per-shortlist headlines will be added in Stage 7.5 after the shortlist is known.
Bash: `python -m trader.helpers.snapshot_news --mode holdings-only --out-news data/runs/$RUN_DATE/news.json --out-macro data/runs/$RUN_DATE/macro.json`

On non-zero exit: run the failure handler, exit non-zero.

## Stage 6 — Score 1 000 tickers (scorer fan-out, Haiku subagents)

**Skip condition**: if `data/runs/$RUN_DATE/scores.json` exists, skip.

Otherwise, execute the full scorer fan-out:

### 6a — Build batches

Read `data/runs/$RUN_DATE/universe.json`. Extract the `tickers` list (≈ 1 000 entries). Slice into batches of exactly 25 tickers each. With 1 000 tickers this produces 40 batches (the last batch may have fewer if the universe is not exactly divisible by 25).

For each batch, also pull the matching rows from `data/runs/$RUN_DATE/market_data_full.json` (closes, momentum, vol, fundamentals) to include as context in the subagent prompt.

### 6b — Wave execution (5 subagents per wave, 8 waves for 40 batches)

Process batches in waves of 5. For each wave:

1. **Spawn 5 `scorer` subagents in parallel** within a single assistant turn. Each subagent call must be:
   - `subagent_type`: `scorer`
   - `prompt`: a fenced JSON block containing that batch's tickers and market data:
     ```
     Process this batch of tickers:
     ```json
     {"tickers": [<25-ticker-market-data-rows>]}
     ```
     ```

2. Wait for all 5 subagent replies to return before proceeding.

3. For each reply, validate via:
   Bash: `python -m trader.helpers.parse_subagent_output --schema scorer --input "<reply-text>"`

   - If exit 0: save the validated JSON to a temp file `data/runs/$RUN_DATE/scorer_batch_<N>.json`.
   - If exit non-zero (validation failure): **retry that subagent once** with this appended prompt: `"Your previous reply failed validation: <error-from-stderr>. Return ONLY the fenced JSON block with no preamble or commentary."`
     - If the retry succeeds: save the validated output.
     - If the retry also fails: log `{"stage": "scorer", "batch": <N>, "error": <stderr>}` to `data/runs/$RUN_DATE/errors.jsonl` (append mode), skip this batch.

4. After all 5 wave replies are processed, continue to the next wave.

### 6c — Merge

After all 40 batches are processed:
Bash: `python -m trader.helpers.merge_stage_output --stage scorer --out data/runs/$RUN_DATE/scores.json data/runs/$RUN_DATE/scorer_batch_*.json`

Then remove the per-batch temp files:
Bash: `rm -f data/runs/$RUN_DATE/scorer_batch_*.json`

On merge non-zero exit: run the failure handler, exit non-zero.

## Stage 7 — Build shortlist (top 50)

**Skip condition**: if `data/runs/$RUN_DATE/shortlist.json` exists, skip.

Otherwise:
Bash: `python -m trader.helpers.build_shortlist --in data/runs/$RUN_DATE/scores.json --out data/runs/$RUN_DATE/shortlist.json --n 50`

On non-zero exit: run the failure handler, exit non-zero.

## Stage 7.5 — Per-shortlist headlines (news update)

**Skip condition**: if `data/runs/$RUN_DATE/news_full.done` exists, skip. Otherwise:

Bash: `python -m trader.helpers.snapshot_news --mode full --shortlist data/runs/$RUN_DATE/shortlist.json --out-news data/runs/$RUN_DATE/news_full.json --out-macro data/runs/$RUN_DATE/_discard_macro.json && echo "done" > data/runs/$RUN_DATE/news_full.done`

This writes per-shortlist-ticker headline entries to `news_full.json` (separate from Stage 5's `news.json`). The macro JSON is discarded (macro was already captured in Stage 5 to `macro.json` which is unchanged). Stages 8 and 15 prefer `news_full.json` over `news.json` when it exists.

On non-zero exit: log a warning to `data/runs/$RUN_DATE/errors.jsonl` and continue — missing per-shortlist headlines degrade report quality but do not abort the run.

## Stage 8 — Snapshot debate context (per-shortlist ticker)

**Skip condition**: if `data/runs/$RUN_DATE/debate_context.json` exists, skip.

Otherwise:
Bash: `python -m trader.helpers.snapshot_debate_context --shortlist data/runs/$RUN_DATE/shortlist.json --market data/runs/$RUN_DATE/market_data_full.json --news "$([ -f data/runs/$RUN_DATE/news_full.json ] && echo data/runs/$RUN_DATE/news_full.json || echo data/runs/$RUN_DATE/news.json)" --macro data/runs/$RUN_DATE/macro.json --out data/runs/$RUN_DATE/debate_context.json`

On non-zero exit: run the failure handler, exit non-zero.

## Stage 9 — Debate 50 tickers (debater fan-out, Opus subagents)

**Skip condition**: if `data/runs/$RUN_DATE/debates.json` exists, skip.

Otherwise:

### 9a — Prepare per-ticker prompts

Read `data/runs/$RUN_DATE/debate_context.json`. This is a dict keyed by ticker. Extract one context blob per ticker (50 total).

### 9b — Wave execution (5 subagents per wave, 10 waves)

Process all 50 tickers in waves of 5:

1. **Spawn 5 `debater` subagents in parallel** within a single assistant turn. Each subagent call:
   - `subagent_type`: `debater`
   - `prompt`:
     ```
     Analyze this ticker:
     ```json
     <single-ticker-context-blob-from-debate_context.json>
     ```
     ```

2. Wait for all 5 replies.

3. For each reply, validate via:
   Bash: `python -m trader.helpers.parse_subagent_output --schema debater --input "<reply-text>"`

   - If exit 0: save validated JSON to `data/runs/$RUN_DATE/debater_<TICKER>.json`.
   - If exit non-zero: retry once with: `"Your previous reply failed validation: <error>. Return ONLY the fenced JSON block."`
     - Retry succeeds: save output.
     - Retry fails: log `{"stage": "debater", "ticker": "<TICKER>", "error": <stderr>}` to `errors.jsonl`, skip this ticker.

4. Continue to next wave.

### 9c — Merge

After all 50 tickers processed:
Bash: `python -m trader.helpers.merge_stage_output --stage debater --out data/runs/$RUN_DATE/debates.json data/runs/$RUN_DATE/debater_*.json`

Bash: `rm -f data/runs/$RUN_DATE/debater_*.json`

On merge non-zero exit: run the failure handler, exit non-zero.

## Stage 10 — Probability estimates (prob-estimator fan-out, Opus subagents)

**Skip condition**: if `data/runs/$RUN_DATE/estimates.json` exists, skip.

Otherwise:

### 10a — Prepare per-ticker payloads

Read `data/runs/$RUN_DATE/debates.json` (keyed by ticker, each with `bull` and `bear` fields) and `data/runs/$RUN_DATE/debate_context.json` (per-ticker context with momentum, ann_vol, fundamentals, macro). For each shortlist ticker, build a combined payload:

```json
{
  "ticker": "<TICKER>",
  "bull": "<from debates.json>",
  "bear": "<from debates.json>",
  "momentum": <from debate_context.json>,
  "ann_vol": <from debate_context.json>,
  "fundamentals_summary": <from debate_context.json fundamentals>,
  "macro": <from debate_context.json macro>
}
```

Skip tickers that have no entry in `debates.json` (they were skipped in Stage 9).

### 10b — Wave execution (5 subagents per wave, 10 waves)

Process all available tickers (≤ 50) in waves of 5:

1. **Spawn 5 `prob-estimator` subagents in parallel** within a single assistant turn. Each subagent call:
   - `subagent_type`: `prob-estimator`
   - `prompt`:
     ```
     Estimate probability and sizing for this ticker:
     ```json
     <combined-payload-for-one-ticker>
     ```
     ```

2. Wait for all 5 replies.

3. For each reply, validate via:
   Bash: `python -m trader.helpers.parse_subagent_output --schema prob-estimator --input "<reply-text>"`

   - If exit 0: save validated JSON to `data/runs/$RUN_DATE/prob_<TICKER>.json`.
   - If exit non-zero: retry once with: `"Your previous reply failed validation: <error>. Return ONLY the fenced JSON block."`
     - Retry succeeds: save output.
     - Retry fails: log `{"stage": "prob-estimator", "ticker": "<TICKER>", "error": <stderr>}` to `errors.jsonl`, skip.

### 10c — Merge

After all waves complete:
Bash: `python -m trader.helpers.merge_stage_output --stage prob-estimator --out data/runs/$RUN_DATE/estimates.json data/runs/$RUN_DATE/prob_*.json`

Bash: `rm -f data/runs/$RUN_DATE/prob_*.json`

On merge non-zero exit: run the failure handler, exit non-zero.

## Stage 10.5 — Pre-selector guard (candidate count check)

Read `data/runs/$RUN_DATE/estimates.json`. Count how many tickers have a complete entry (i.e., are present in both `estimates.json` and `debates.json`).

If the count is **fewer than 30**:
- Bash: `python -m trader.helpers.publish_alert --type failure --message "insufficient_candidates: only <N> of 50 shortlist tickers produced full debate+probability output; selector aborted"`
- Exit non-zero. Do NOT proceed to Stage 11.

If count ≥ 30: continue.

## Stage 11 — Selector synthesis (orchestrator turn)

**Skip condition**: if `data/runs/$RUN_DATE/selection.json` exists, skip.

Otherwise, this is your synthesis turn. Read the following into your context:

- Read: `data/runs/$RUN_DATE/estimates.json` — probability, conviction, sizing hints per ticker
- Read: `data/runs/$RUN_DATE/debates.json` — bull/bear cases per ticker
- Read: `data/ledger.json` — current positions, weights, and the `trades` array (used for position age)
- Read: `data/runs/$RUN_DATE/market_data_full.json` — closes and fundamentals (use `fundamentals[ticker]["sector"]` for sector classification)
- Read: `data/runs/$RUN_DATE/shortlist.json` — the 50 candidates

### 11a — Classify current holdings (hold-bias)

Theses run on a 4–12 week horizon (per `prob-estimator`); you are rebalancing weekly. To prevent thrashing positions before they have a chance to play out, classify each current holding from `ledger.json` before considering new picks.

For each ticker `t` currently in `ledger.positions`:

1. **Compute holding age in days**: scan `ledger.trades` for the most recent trade where `ticker == t` and `side == "buy"`. `holding_age_days = (today_utc - that_trade.ts).days`. If no buy trade is found (shouldn't happen, but be defensive), treat age as `0`.

2. **Look up this run's signal** for `t`:
   - `in_shortlist = t in shortlist.tickers`
   - `p = estimates[t].p_outperform` (or `None` if missing)
   - `bear = debates[t].bear` (or `None` if missing)

3. **Classify**:
   - **Rotate out** if any of the following:
     - `not in_shortlist` (scorer dropped it from top 50 — quality breakdown)
     - `p` is `None` (no estimate produced — treat as no signal)
     - `p < 0.40` (active sell signal, regardless of age)
     - the `bear` case explicitly states the entry thesis has broken (e.g., guidance cut, accounting issue, fundamental inversion). Use judgment; do not treat normal bearish framing as a thesis break.
   - **Retain** if:
     - `holding_age_days < 28` AND `p >= 0.40` (catalyst-window protection — give new theses ≥ 4 weeks)
     - OR `holding_age_days >= 28` AND `p >= 0.50` (mature position, normal hold threshold)

4. **Sizing for retained positions**:
   - Default to the position's current weight (from `ledger.current_weights` semantics — use `closes` to compute).
   - Allow a small drift toward `estimates[t].sizing_hint`: new weight = midpoint of (current weight, sizing_hint), clamped to `[0.02, 0.10]`. This lets sizing nudge each week without forcing a full re-allocation.
   - If `sizing_hint == 0` for a retained position (typically because alpha turned non-positive), trim to `max(0.02, current * 0.5)` rather than rotating out — let the position decay over 1–2 weeks if the signal stays weak.

### 11b — Fill remaining slots from the shortlist

After classification you have:
- `retained` — current positions to keep (with proposed new weights)
- `rotate_out` — current positions to drop
- `target_count = 15` — total portfolio size

Slots to fill from shortlist: `15 - len(retained)`.

Rank the non-retained shortlist tickers by composite score `p_outperform × conviction × max(0, expected_alpha_bps)`. Walk the ranked list top-down, adding tickers as new picks at their `sizing_hint`, while respecting:
- `max_weight_per_name = 0.10`
- `max_weight_per_sector = 0.25` (counting both retained + new picks toward sector totals)
- `min_sectors = 8` distinct sectors across the final 15
- Sum of weights ≤ 1.0 (cash residual is acceptable)
- `max_turnover_per_run = 0.40` (one-way turnover vs current ledger). If the proposed turnover exceeds this, you MUST keep additional borderline holdings rather than rotate them — Stage 12 will hard-reject otherwise.

If a sector cap forces a sizing_hint to compress, prefer to add another sector rather than over-concentrate.

### 11c — Commentary requirements

The `commentary` field must explicitly state:
- How many positions were retained, how many rotated out, and how many new picks were added.
- The dominant reason for any rotation (e.g., "rotated 3 names: 1 fell off shortlist, 2 had p_outperform < 0.40").
- Whether sizing tilts changed the cash residual.

Write the selection to `data/runs/$RUN_DATE/selection.json` using the Write tool. The file must have this exact shape:

```json
{
  "commentary": "<2-3 sentence qualitative summary covering retain/rotate counts and portfolio thesis>",
  "picks": [
    {"ticker": "AAPL", "weight": 0.07, "sector": "Technology", "rationale": "<1 sentence>"},
    ...
  ],
  "rationales": {
    "AAPL": "<1-2 sentences from bull case + conviction>"
  }
}
```

Exactly 15 picks. Every pick must appear in both `rationales` and `picks`.

## Stage 12 — Validate proposal against risk caps

Bash: `python -m trader.helpers.validate_proposal --in data/runs/$RUN_DATE/selection.json --ledger data/ledger.json --market data/runs/$RUN_DATE/market_data.json`

- If exit 0: continue.
- If exit non-zero (cap violation, including turnover):
  - Bash: `python -m trader.helpers.publish_alert --type failure --message "cap_violation: <stderr from validate_proposal>"`
  - Exit non-zero. **Do not proceed to Stage 13.** The ledger must not be mutated on a cap violation.

The turnover cap (`max_turnover_per_run = 0.40`, configurable via env var `MAX_TURNOVER_PER_RUN`) is automatically skipped on the first run when the ledger has no positions. If you hit the cap, Stage 11 over-rotated — re-run after deleting `selection.json` and apply stronger hold-bias.

## Stage 13 — Apply trades to ledger

Bash: `python -m trader.helpers.apply_trades --selection data/runs/$RUN_DATE/selection.json --market data/runs/$RUN_DATE/market_data_full.json --trades-out data/runs/$RUN_DATE/trades.json`

- `apply_trades.py` re-checks `KILL_SWITCH` internally before any ledger mutation.
- If `EXECUTE=0` is set in the environment: the helper writes `trades.json` in paper mode and leaves the ledger unchanged; this is expected and exit code is 0.
- On non-zero exit: run the failure handler, exit non-zero.

## Stage 14 — Mark to market

**Skip condition**: read `data/ledger.json`; if its `as_of` field equals `$RUN_DATE`, skip.

Otherwise:
Bash: `python -m trader.helpers.mark_to_market --market data/runs/$RUN_DATE/market_data_full.json`

On non-zero exit: run the failure handler, exit non-zero.

## Stage 15 — Newswriter report (orchestrator turn)

**Skip condition**: if `data/runs/$RUN_DATE/report-rebalance.md` exists, skip. (The rebalance writes a distinct filename so the daily report — `report.md` — does not collide on Friday/Saturday when both pipelines run on the same UTC date.)

Otherwise, read the following into your context:

- Read: `data/runs/$RUN_DATE/market_data_full.json`
- Read: `data/runs/$RUN_DATE/news_full.json` if it exists, otherwise `data/runs/$RUN_DATE/news.json`
- Read: `data/runs/$RUN_DATE/macro.json`
- Read: `data/runs/$RUN_DATE/debates.json`
- Read: `data/runs/$RUN_DATE/estimates.json`
- Read: `data/runs/$RUN_DATE/selection.json`
- Read: `data/runs/$RUN_DATE/trades.json`
- Read: `data/ledger.json`

Write a weekly rebalance report to `data/runs/$RUN_DATE/report-rebalance.md` using the Write tool. The report must contain these sections in order:

1. **Header**: `# Weekly Rebalance Report — {RUN_DATE}`
2. **Portfolio summary**: Current NAV, vs SPY YTD performance, sector breakdown table (sector | weight%).
3. **Trades made**: Two sub-tables — "Bought" (ticker, weight%, rationale snippet) and "Sold / trimmed" (ticker, previous weight%). If `EXECUTE=0` (paper mode), prefix both tables with `_(paper mode — no ledger mutation)_`.
4. **Selector commentary**: The `commentary` field from `selection.json`, verbatim.
5. **Risk note**: Top 2–3 concentration risks (heaviest sector, highest single-name weight, any tickers with `p_outperform < 0.45`).
6. **Week ahead**: Known catalysts for the next 7 days that could move portfolio holdings — earnings dates, Fed events, macro releases. Note "no major catalysts identified" if none are found in `news.json` or `macro.json`.

Keep the report under 2 000 words. Use Markdown formatting.

## Stage 16 — Publish (commit + push only; Telegram is sent by GitHub Actions)

Telegram delivery is handled by `.github/workflows/telegram-notify.yml`, which fires on push to `reports/**.md`. CCR has no outbound network access to Telegram, so the publish step skips it via `--no-telegram`.

Bash: `python -m trader.helpers.publish_report --report data/runs/$RUN_DATE/report-rebalance.md --run-date $RUN_DATE --name $RUN_DATE-rebalance --no-telegram`

On non-zero exit: run the failure handler, exit non-zero.

## Failure handler

On any **non-zero exit** from Stages 2–16 (excluding Stage 1 gate):

1. Capture the failing stage name (e.g., "Stage 6 — Score 1 000 tickers") and the first 200 characters of its stderr.
2. Bash: `python -m trader.helpers.publish_alert --type failure --message "<stage name>: <stderr excerpt>"`
3. Exit non-zero.

If `gate.py` (Stage 1) exits non-zero, that is a **normal skip** — exit 0, no alert.

## Force-rerunning a stage

To force a specific stage to re-execute (e.g., after fixing a helper bug), delete the corresponding checkpoint file before re-firing the routine:

```bash
rm data/runs/$RUN_DATE/<stage-output>.json
```

Stage → checkpoint file mapping:
- Stage 3: `universe.json`
- Stage 4: `market_data_full.json`
- Stage 5: `news.json` and `macro.json` (delete both to force re-run)
- Stage 7.5: `news_full.done` (also delete `news_full.json` and `_discard_macro.json`)
- Stage 6: `scores.json`
- Stage 7: `shortlist.json`
- Stage 8: `debate_context.json`
- Stage 9: `debates.json`
- Stage 10: `estimates.json`
- Stage 11: `selection.json`
- Stage 14: (mark-to-market is gated by `ledger.as_of`; delete `market_data_full.json` to force a full redo)
- Stage 15: `report-rebalance.md`

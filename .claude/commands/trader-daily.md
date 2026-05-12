---
name: trader-daily
description: Daily portfolio scan + newswriter report (~5-10 LLM calls)
allowed-tools: Bash, Read, Write
---

# Daily scan pipeline

You are running the trader's daily-scan pipeline. Full design context: `docs/superpowers/specs/2026-04-28-routine-based-trader-design.md`. You will execute 7 stages sequentially. Every stage's output is checkpointed to `data/runs/<RUN_DATE>/`. If a checkpoint file already exists for a stage, **skip** that stage (idempotent re-run support).

## Setup

First, install Python deps (CCR sandbox starts bare; idempotent — fast on subsequent runs), then compute the run date and create the run directory:

1. Bash: `pip install -e .` — installs project deps from `pyproject.toml`.
2. Bash: `date -u +%Y-%m-%d` — capture the output as `RUN_DATE`.
3. Bash: `mkdir -p data/runs/$RUN_DATE`

## Stage 1 — Trading-day gate

Bash: `python -m trader.helpers.gate daily`

- If exit code is **0**: continue to Stage 2.
- If exit code is **non-zero**: today is not a trading day. Exit 0 silently. Do NOT send a failure alert — this is a normal skip, not an error.

## Stage 2 — Pull repo and read ledger

Bash: `git pull --rebase`

Then confirm the ledger loads:
Bash: `python -c "import json; d=json.load(open('data/ledger.json')); print('ledger ok, nav=', d.get('nav', d.get('cash', '?')))"`

If the ledger file does not exist, print a warning and continue — the mark-to-market step will be a no-op.

## Stage 2.5 — Wait for GH Actions prefetch

The prefetch workflow (`.github/workflows/daily-scan.yml`) writes today's `market_data.json`, `news.json`, and `macro.json` to `data/runs/$RUN_DATE/` and pushes to main ~60 min before this routine fires. GH Actions cron drifts unreliably; this stage polls origin/main until the prefetch commit appears (or 30 min elapses), then `git pull --rebase`s the new files into the worktree. Without this guard, CCR would fall through to yfinance/RSS/FRED and get 403s from the sandbox network policy.

Bash: `python -m trader.helpers.wait_for_prefetch --kind daily --run-date $RUN_DATE --timeout 1800`

On non-zero exit (prefetch never landed within 30 min): run the failure handler with the stderr excerpt, exit non-zero. Failing loudly is preferable to producing a degraded report from carried-forward prices.

## Stage 3 — Snapshot prices for current holdings

**Skip condition**: if `data/runs/$RUN_DATE/market_data.json` exists, skip this stage.

Otherwise:
Bash: `python -m trader.helpers.snapshot_market_data --mode holdings-only --out data/runs/$RUN_DATE/market_data.json`

On non-zero exit: capture stderr (first 200 chars), run the failure handler (see bottom of this document), then exit non-zero.

## Stage 4 — Snapshot news

**Skip condition**: if both `data/runs/$RUN_DATE/news.json` AND `data/runs/$RUN_DATE/macro.json` exist, skip this stage.

Otherwise:
Bash: `python -m trader.helpers.snapshot_news --mode holdings-only --out-news data/runs/$RUN_DATE/news.json --out-macro data/runs/$RUN_DATE/macro.json`

On non-zero exit: run the failure handler, exit non-zero.

## Stage 5 — Mark to market

**Skip condition**: read `data/ledger.json` and check whether its `as_of` field equals `$RUN_DATE`. If it does, skip this stage (already marked today).

Otherwise:
Bash: `python -m trader.helpers.mark_to_market --market data/runs/$RUN_DATE/market_data.json`

On non-zero exit: run the failure handler, exit non-zero.

## Stage 6 — Newswriter report (the one LLM turn this run)

**Skip condition**: if `data/runs/$RUN_DATE/report.md` exists, skip this stage.

Otherwise, read the following files into your context:

- Read: `data/runs/$RUN_DATE/market_data.json`
- Read: `data/runs/$RUN_DATE/news.json`
- Read: `data/runs/$RUN_DATE/macro.json`
- Read: `data/ledger.json`

Then write a structured daily report to `data/runs/$RUN_DATE/report.md`. The report must contain these sections in order:

1. **Header**: `# Daily Trader Report — {RUN_DATE}`
2. **NAV**: Render a table with these rows:
   - Current NAV (from `ledger.nav_history[-1].nav`)
   - Prior NAV (from `ledger.nav_history[-2].nav`, with its date)
   - Daily change ($) and (%)
   - SPY today / prior (from `nav_history[-1].spy` and `nav_history[-2].spy`)
   - SPY daily change (%)
   - Portfolio vs SPY (pp difference, daily)
   - **Since inception:** portfolio total return % `((nav/starting_nav) - 1)` and SPY total return % `((spy_now / spy_inception) - 1)` over the same window. `spy_inception` is the first non-null `spy` in `nav_history`; `starting_nav` comes from `ledger.starting_nav`. Show both numbers and the pp gap. If `spy_inception` is null (no SPY ever recorded), note "SPY since-inception unavailable".

   If `ledger.nav_history[-1].stale` is non-empty, add a one-line note **immediately under the table**: `> Note: N positions used carried-forward prices today (last marked YYYY-MM-DD): [list]. NAV reflects last-known closes for those names.` Do NOT exclude them from holdings — they still appear with their last-known price flagged in the Holdings table column.
3. **Holdings**: Markdown table with columns: Ticker | Weight% | Price | Daily P&L | Unrealized P&L. Derive from ledger positions and `market_data.json` closes. If a ticker is in `ledger.nav_history[-1].stale`, suffix its price with " (stale, MM-DD)" using its `last_close_date` from ledger.positions, and use `last_close` as the price. Sort by weight descending.
4. **Movers**: Top 3 gainers and top 3 losers by daily % change. Use closes from `market_data.json`.
5. **Headlines**: One-line summary of the single most important headline per current holding, drawn from `news.json`'s per-ticker entries.
6. **Macro callout**: 1–2 sentences on the macro environment most relevant to the current portfolio, using `macro.json`.
7. **Tomorrow's risk**: Any known earnings releases, Fed events, or major news catalysts in the next 24 hours that could move current holdings. Note if none are identified.

Keep the total report under 1 500 words. Use Markdown formatting throughout.

Write the finished report to `data/runs/$RUN_DATE/report.md` using the Write tool.

## Stage 7 — Publish (commit + push only; Telegram is sent by GitHub Actions)

Telegram delivery is handled by `.github/workflows/telegram-notify.yml`, which fires on push to `reports/**.md`. CCR has no outbound network access to Telegram, so the publish step skips it via `--no-telegram`.

Bash: `python -m trader.helpers.publish_report --report data/runs/$RUN_DATE/report.md --run-date $RUN_DATE --no-telegram`

On non-zero exit: run the failure handler, exit non-zero.

## Failure handler

On any **non-zero exit** from Stages 2–7:

1. Capture the failing stage name (e.g., "Stage 3 — Snapshot prices") and the first 200 characters of its stderr output.
2. Bash: `python -m trader.helpers.publish_alert --type failure --message "<stage name>: <stderr excerpt>"`
3. Exit non-zero.

If `gate.py` (Stage 1) exits non-zero, that is a **normal skip** — exit 0, no alert, no log.

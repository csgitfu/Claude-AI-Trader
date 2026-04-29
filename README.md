# Claude-AI-Trader

> **Educational simulation. Not investment advice. No real funds are traded by this repo.**

An autonomous, multi-agent Russell 1000 portfolio manager powered by Claude. Inspired by [@theaiportfolios](https://x.com/theaiportfolios).

## Architecture

The system runs as two cooperating layers connected through git:

```
┌──────────────────────────────┐    ┌────────────────────────────┐    ┌──────────────────────────────┐
│   GitHub Actions (data)      │    │  Claude Code Routines      │    │  GitHub Actions (notify)     │
│   .github/workflows/         │    │  (CCR, Anthropic cloud)    │    │   .github/workflows/         │
│                              │    │                            │    │                              │
│   daily-scan.yml             │    │   trader-daily             │    │   telegram-notify.yml        │
│   Mon–Fri 19:00 UTC          │    │   Mon–Fri 19:30 UTC        │    │   on push: reports/**.md     │
│                              │    │                            │    │                              │
│   weekly-rebalance.yml       │    │   trader-rebalance         │    │                              │
│   Fri 18:00 UTC              │    │   Fri 20:30 UTC            │    │                              │
│                              │    │                            │    │                              │
│   • snapshot_market_data     │    │   • git pull               │    │   • git diff detects new     │
│   • snapshot_news            │ →  │   • skip data stages       │ →  │     reports/YYYY-MM-DD.md    │
│   • snapshot_macro (FRED)    │    │   • scorer (Haiku ×40)     │    │   • POST to Telegram bot     │
│   • commit checkpoints to    │    │   • debater (Opus ×50)     │    │                              │
│     data/runs/<date>/        │    │   • prob-estimator (×50)   │    │                              │
│                              │    │   • selector + apply       │    │                              │
│                              │    │   • newswriter (report)    │    │                              │
│                              │    │   • commit report.md       │    │                              │
└──────────────────────────────┘    └────────────────────────────┘    └──────────────────────────────┘
        outbound: yes                       outbound: github only                outbound: yes
```

**Why split?** CCR runs in a sandboxed environment with no outbound network access except GitHub — perfect for LLM workflows but it can't reach Yahoo Finance, FRED, or Telegram. GitHub Actions has full network access but no Anthropic billing relationship. We split the work so each layer does what it can: GitHub Actions fetches data and sends Telegram, CCR does LLM stages and bills against your Claude Max subscription.

## What runs on what schedule

| Day (SGT)         | Layer      | Job                  | Time (UTC)  |
|---                |---         |---                   |---          |
| Tue–Sat 03:00     | Actions    | daily prefetch       | Mon–Fri 19:00 |
| Tue–Sat 03:30     | CCR        | `/trader-daily`      | Mon–Fri 19:30 |
| Sat 02:00         | Actions    | rebalance prefetch   | Fri 18:00     |
| Sat 04:30         | CCR        | `/trader-rebalance`  | Fri 20:30     |
| any time          | Actions    | telegram notify      | on report push |

## Setup (first-time only)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env    # fill in keys for local CLI use
python -m trader init   # seed ledger.json with STARTING_NAV (default $50K)
python -m trader ping-telegram   # verify Telegram wiring
```

**Secrets distribution:**

| Secret | GitHub Actions | CCR `.env` |
|---|---|---|
| `FRED_API_KEY` | ✓ | — |
| `TELEGRAM_BOT_TOKEN` | ✓ | — |
| `TELEGRAM_CHAT_ID` | ✓ | — |
| `GIT_REMOTE_URL` (PAT) | not needed (GITHUB_TOKEN) | ✓ |
| `EXECUTE` (0/1) | repo variable | ✓ |
| `FORCE_REBALANCE=1` | — | init routine only |

GitHub Actions secrets: `gh secret set NAME --repo csgitfu/claude-ai-trader`. CCR routine env is embedded in the routine prompt at https://claude.ai/code/routines.

## Local CLI

| Command | What it does |
|---|---|
| `python -m trader init` | Seed `ledger.json` with `STARTING_NAV` |
| `python -m trader performance` | TWRR / Sharpe / max-DD / vs SPY |
| `python -m trader ping-telegram` | Send a test Telegram message |
| `python -m trader backfill-universe` | Refresh IWB holdings cache |
| `/trader-daily` | Run daily scan locally (interactive Claude Code) |
| `/trader-rebalance` | Run full rebalance locally |
| `/test-subagent <name> <fixture>` | Layer-2 schema sanity test |

## Safety toggles

- `EXECUTE=0` (default) → paper mode. `apply_trades.py` writes `trades.json` but does not mutate `data/ledger.json`.
- `EXECUTE=1` → live ledger mutations. Flip after at least one full weekly rebalance reviewed in paper mode.
- `KILL_SWITCH=1` → all routines abort at gate stage, no LLM calls, no ledger writes.
- `FORCE_REBALANCE=1` → skips the Friday-only gate (used only by the one-time init routine).

## Operations

See `docs/runbook.md` for: killing a run, rotating secrets, force-rerunning a stage, debugging schedule no-shows, and switching paper → live.

## Disclaimer

This project is for research and education. Outputs are generated by an LLM and may be wrong. Nothing here constitutes financial, investment, legal, or tax advice. Do not use this code to trade real money without understanding it end-to-end.

# Routine-Based Trader — Design Spec

**Date:** 2026-04-28
**Status:** Draft, pending user review
**Origin:** brainstorming session 2026-04-27 → 2026-04-28

## TL;DR

Replace the current `anthropic` SDK + `ANTHROPIC_API_KEY` trader with a Claude Code routine (`/schedule`) that runs on Anthropic's infrastructure and bills against the user's Max plan subscription. LLM stages (scoring, debate, probability, selection, newswriter) move into Claude Code subagents and orchestrator turns. Deterministic Python becomes a library of small helper CLIs invoked by the orchestrator via `Bash`. Ledger persists by committing `data/ledger.json` back to the GitHub repo on each run.

Schedule:
- **Daily scan**: Tue–Sat 03:30 SGT (5 runs/week)
- **Weekly rebalance**: Sat 04:30 SGT (1 run/week)

## 1. Goals & non-goals

### Goals

- Run the trader autonomously on a cron schedule with **zero pay-per-token API usage**.
- Preserve current portfolio behavior: Russell 1000 universe, 5-stage decision pipeline, 15-position portfolio, sector/name caps.
- Keep deterministic Python helpers (data fetch, ledger math, simulation, risk validation) unchanged in logic.
- Maintain the same checkpoint/resume property: a failed run can be re-fired and pick up where it left off.
- Maintain Telegram report delivery.

### Non-goals (explicit)

- Notion integration at any layer (state, reports, config, dashboard). Decision 2026-04-28.
- Local open-weights model substitution.
- Live trading on day one (`EXECUTE=False` remains default; first month is paper mode).
- `claude -p`-based scheduling — would route through API key billing.
- `/loop`-based scheduling — requires Claude Code to be actively running on a machine.
- Local Windows Task Scheduler — would invoke `claude -p` and hit API billing.
- Manual approval workflow on trades — defeats autonomy.
- UI / dashboard.
- Multi-user / multi-portfolio.

## 2. Architecture

### 2.1 Runtime model

The trader runs as a **Claude Code routine** scheduled via `/schedule`. At each scheduled time, Anthropic infrastructure spawns an ephemeral sandbox that:

1. Clones the repo from GitHub (`csgitfu/claude-ai-trader`).
2. Installs Python dependencies.
3. Invokes the project slash command (`/trader-daily` or `/trader-rebalance`).
4. The orchestrator runs the pipeline: alternating Bash → Python helper calls and LLM turns (orchestrator + subagents).
5. Ledger updates and report markdown are committed and pushed back to the repo.
6. Telegram receives the final report.

LLM usage bills against the user's Max plan subscription. Routines have a 15-runs/day cap on Max; this design uses ~1/day average, leaving ample headroom.

### 2.2 Component map

**Files added:**

- `.claude/commands/trader-daily.md` — slash command body driving the daily scan
- `.claude/commands/trader-rebalance.md` — slash command body driving the weekly rebalance
- `.claude/commands/test-subagent.md` — local manual sanity command (Layer 2 testing)
- `.claude/agents/scorer.md` — Haiku subagent, scores 25-ticker batches
- `.claude/agents/debater.md` — Opus subagent, bull/bear case for one ticker
- `.claude/agents/prob-estimator.md` — Opus subagent, probability + sizing for one ticker
- `src/trader/helpers/` — Python helper CLIs:
  - `gate.py` — trading-day check (daily and rebalance variants)
  - `snapshot_universe.py`
  - `snapshot_market_data.py` — `--full` and `--holdings-only` modes
  - `snapshot_news.py` — `--full` and `--holdings-only` modes
  - `snapshot_debate_context.py`
  - `parse_subagent_output.py`
  - `merge_stage_output.py`
  - `build_shortlist.py`
  - `validate_proposal.py`
  - `apply_trades.py`
  - `mark_to_market.py`
  - `publish_report.py`
  - `publish_alert.py`
- `src/trader/helpers/schemas.py` — Pydantic models for subagent outputs

**Files kept (unchanged in logic):**

- `src/trader/data/{prices,fundamentals,news,macro}.py`
- `src/trader/portfolio/{ledger,simulate,performance,risk}.py`
- `src/trader/calendar_.py` — adds one helper, `last_trading_day_was_friday()`, used by the rebalance gate
- `src/trader/universe.py`
- `src/trader/publish/telegram.py`

**Files modified:**

- `src/trader/config.py` — drop `anthropic_api_key`, `agent_concurrency`, `model_*`, `daily_budget_usd`. Keep `starting_nav`, `kill_switch`, `execute`, telegram tokens, FRED key, sizing/sector caps. Add `git_remote_url` for the routine to push back to.
- `src/trader/cli.py` — strip `weekly_rebalance` / `daily_scan` entry points; keep helper CLI dispatch only.
- `pyproject.toml` — drop `anthropic` only; keep tenacity (used by `data/prices.py` for retry logic).

**Files deleted:**

- `src/trader/agents/client.py` (the `AsyncAnthropic` wrapper)
- `src/trader/agents/{scorer,debate,probability,selector,newswriter}.py`
- `src/trader/pipeline.py`
- `tests/test_pipeline_smoke.py`
- `tests/test_probability.py`

**Existing prompts to port:**

- `src/trader/prompts/*.md` — system prompts for each agent. Inline contents into the corresponding `.claude/agents/*.md` bodies. Adjust phrasing to drop `tool_use` references; replace with the fenced-JSON convention (Section 4).

### 2.3 Configuration & secrets

Routine secrets (set once via routine config UI):

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `FRED_API_KEY`
- `GIT_REMOTE_URL` — full HTTPS URL with embedded PAT, or routine config provides SSH key
- `KILL_SWITCH` — optional; `1` aborts the run at the gate stage
- `EXECUTE` — `0` (paper, default) or `1` (live)

**Removed:** `ANTHROPIC_API_KEY`. Routines do not require it.

## 3. Pipeline flows

Both flows are sequences of Bash → Python helper calls interleaved with LLM turns. Every stage checkpoint is written to `data/runs/<YYYY-MM-DD>/`. The slash command bodies use "skip if `<stage>.json` exists" logic so a failed run can be re-fired and pick up where it left off.

### 3.1 Daily scan — `/trader-daily`

**Schedule:** Tue, Wed, Thu, Fri, Sat at 03:30 SGT (= prev day 14:30–15:30 ET, depending on DST).

| # | Stage | Mechanism | Writes |
|---|---|---|---|
| 1 | Trading-day gate | Bash → `python -m trader.helpers.gate daily` | exits non-zero if non-trading day |
| 2 | Pull repo + read ledger | Bash → `git pull --rebase`, `cat data/ledger.json` | |
| 3 | Snapshot prices + macro for current holdings | Bash → `snapshot_market_data.py --holdings-only` | `market_data.json` |
| 4 | Snapshot news (market + per-holding) | Bash → `snapshot_news.py --holdings-only` | `news.json` |
| 5 | Mark-to-market | Bash → `mark_to_market.py` | updates `data/ledger.json` |
| 6 | **Newswriter — orchestrator turn (Opus)** | Read inputs, write report markdown | `report.md` |
| 7 | Publish | Bash → `publish_report.py` | Telegram + `reports/<date>.md` + git commit + push |

**LLM volume:** 1 orchestrator turn (Opus) + a few coordinating turns. ~5–10 messages per run.

### 3.2 Weekly rebalance — `/trader-rebalance`

**Schedule:** Sat at 04:30 SGT (= Fri 15:30–16:30 ET, just after Friday's NYSE close).

| # | Stage | Mechanism | Writes |
|---|---|---|---|
| 1 | "Friday-was-trading-day" gate | Bash → `python -m trader.helpers.gate rebalance` | exits non-zero otherwise |
| 2 | Pull repo + read ledger | Bash → `git pull --rebase`, `cat data/ledger.json` | |
| 3 | Snapshot universe (Russell 1000) | Bash → `snapshot_universe.py` | `universe.json` |
| 4 | Snapshot prices + fundamentals + momentum + vol | Bash → `snapshot_market_data.py --full` | `market_data.json` |
| 5 | Snapshot macro + headlines | Bash → `snapshot_news.py --full` | `news.json`, `macro.json` |
| 6 | **Score 1000 tickers — fan-out (Haiku subagents)** | 40 batches × 25 tickers; spawn in waves of 10 parallel `scorer` subagents | `scores.json` |
| 7 | Build shortlist top-50 | Bash → `build_shortlist.py` | `shortlist.json` |
| 8 | Snapshot debate context per shortlist ticker | Bash → `snapshot_debate_context.py` | `debate_context.json` |
| 9 | **Debate 50 tickers — fan-out (Opus subagents)** | 50 parallel `debater` subagents in waves of 10 | `debates.json` |
| 10 | **Probability 50 tickers — fan-out (Opus subagents)** | 50 parallel `prob-estimator` subagents in waves of 10 | `estimates.json` |
| 11 | **Selector synthesis — orchestrator turn (Opus)** | Reads estimates + current weights + sector caps | `selection.json` |
| 12 | Validate proposal against risk rules | Bash → `validate_proposal.py` | exits non-zero on cap violation |
| 13 | Apply trades to ledger | Bash → `apply_trades.py` | updates `data/ledger.json`, writes `trades.json` |
| 14 | Mark-to-market | Bash → `mark_to_market.py` | updates `data/ledger.json` |
| 15 | **Newswriter — orchestrator turn (Opus)** | Read everything, write report | `report.md` |
| 16 | Publish | Bash → `publish_report.py` | Telegram + `reports/<date>.md` + git commit + push |

**LLM volume:** 40 (scorer Haiku) + 50 (debater Opus) + 50 (prob-estimator Opus) + 2 orchestrator turns (selector + newswriter) ≈ **~142 LLM calls per weekly run**, fanned out 10-at-a-time.

## 4. Subagent contract

### 4.1 File structure

Each subagent is a markdown file in `.claude/agents/` with frontmatter (name, description, tools, model) and a body that's the persistent system prompt. Tool grants are empty — subagents only receive a prompt and produce text.

**`.claude/agents/scorer.md` (sketch — outer fence shown as `~~~` to avoid nested-fence collision):**

~~~markdown
---
name: scorer
description: Scores a batch of equity tickers 0-100 on quality, momentum, valuation
tools: []
model: haiku
---

You are a disciplined equity screener. The user message contains a JSON
array of ticker rows with fundamentals, momentum, and volatility data.

Score each ticker 0-100 using:
- 40% quality (margins, ROE, leverage, revenue growth)
- 30% momentum (3M / 6M / 12M trend, risk-adjusted)
- 20% valuation (P/E, P/FCF vs sector)
- 10% red flags (high beta, negative growth, leverage spikes)

Output ONLY a fenced JSON block (triple-backtick `json`), no preamble.
The block contains:

{"scores": [{"ticker": "AAPL", "score": 78, "one_liner": "...", "flags": []}, ...]}

Every ticker in the input must appear exactly once.
~~~

`debater.md` and `prob-estimator.md` follow the same pattern with their respective system prompts (ported from `src/trader/prompts/*.md`) and JSON output schemas.

### 4.2 Input / output convention

- **Input**: orchestrator invokes `Agent(subagent_type=..., prompt=...)`. The `prompt` parameter is a fenced JSON block containing the dynamic input only — the persistent system prompt is in the agent file.
- **Output**: subagent's final assistant message contains exactly one fenced ` ```json ` block with the schema-conformant payload.

### 4.3 Validation & retry

The orchestrator passes each subagent's reply through `Bash → python -m trader.helpers.parse_subagent_output --schema <name> --input <reply>`:

1. Extract the first ` ```json ` fenced block.
2. Parse + validate against the relevant Pydantic model.
3. On success: print validated JSON to stdout, exit 0.
4. On failure: print `{"error": "schema", "details": "..."}` to stderr, exit 1.

When the helper exits non-zero, the slash command instructs the orchestrator to **re-invoke the same subagent once** with an appended hint: "Your previous reply failed validation: {error}. Return only the JSON block." If the second attempt fails, log to `data/runs/<date>/errors.jsonl` and skip that batch/ticker.

### 4.4 Pydantic schemas — `src/trader/helpers/schemas.py`

```python
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
```

Field names and constraints match the existing `tool_use` schemas (`scorer.py:17-39`, etc.) so downstream Python is unchanged.

### 4.5 Aggregation

After all subagents in a stage return + parse, the orchestrator does **one** `Bash → python -m trader.helpers.merge_stage_output --stage <name> --inputs <files>` call that concatenates validated outputs into `data/runs/<date>/<stage>.json`.

## 5. Error handling & recovery

### 5.1 Failure profiles

| Stage type | Failure mode | Response |
|---|---|---|
| Bash → Python helper | Non-zero exit | Read `errors.jsonl`. Abort if data-prep fails; continue if non-fatal (Telegram unreachable, partial news fetch). |
| Subagent fan-out | Malformed JSON | One retry; on second failure, log + skip that ticker/batch. Stage continues with partial output. |
| Orchestrator turn | Self-output malformed | Self-correct in next turn. |

Hard fails that abort the run:

- Trading-day gate fails → exit 0 (no error).
- `validate_proposal.py` flags a cap violation → write `errors.jsonl`, send Telegram alert, exit non-zero. **No ledger mutation.**
- Fewer than 30 of 50 shortlist tickers produce both debate + probability outputs → abort before selector. Selector with too few candidates would produce a degenerate portfolio.
- Git push fails (remote diverged, auth expired) → write `errors.jsonl`, send Telegram alert, exit non-zero. Operator reconciles manually.

### 5.2 Idempotency & resume

The slash command's first action after the gate is `ls data/runs/<date>/`. Each subsequent stage is wrapped in "if `<stage>.json` exists, skip; else execute". This means:

- Run dies at stage 9 → re-fire the routine; stages 1–8 skip, stage 9 retries.
- Force-rerun a stage → delete the corresponding JSON. Documented in the slash command body.
- Two runs on the same date can never collide because everything is namespaced by `data/runs/<YYYY-MM-DD>/`.

### 5.3 Kill switch

`KILL_SWITCH=1` in routine secrets is checked in two places:

1. `gate.py` (stage 1) — exits non-zero, halts before any LLM work or data fetch.
2. `apply_trades.py` (weekly stage 13) — re-reads it just before mutating the ledger. Belt-and-suspenders.

Setting `KILL_SWITCH=1` halts the system without disabling the schedule itself.

### 5.4 Risk caps

`validate_proposal.py` (weekly stage 12) reads `selection.json` and checks against `config.py`'s `max_weight_per_name=0.10`, `max_weight_per_sector=0.25`, `min_sectors=8`. Last gate before any ledger mutation. Cap violation → abort + Telegram alert.

### 5.5 Telegram alerts

Three message types, separate from the daily/weekly report:

- **Run failed**: stage that failed + first 200 chars of `errors.jsonl`.
- **Risk-cap violation**: full proposal JSON + which cap it violated.
- **Run started** (heartbeat): optional, for the first two weeks of operation; can disable via config.

Implementation: new helper `publish_alert.py`, sibling to `publish_report.py`, both using the existing `telegram.py` module.

### 5.6 Quota awareness

`daily_budget_usd: float = 25.0` is removed (was an API-cost ceiling; subscription cost is fixed). Relevant Max plan limits:

- 5-hour rolling window quota (numerics not published; observed empirically).
- 15 routine runs/day account cap.

Cadence: 6 scheduled runs/week (5 daily + 1 weekly), ~1/day average. Substantial headroom.

If a run exhausts the rolling window mid-stage, subagents fail with quota errors. The orchestrator treats them as standard subagent failures (retry once, skip). Resume-from-checkpoint then handles the rest on the next manual or scheduled trigger.

### 5.7 Logging

- Routine run logs are visible in Anthropic's routine UI (per-run stdout, duration, exit status).
- Per-stage JSON checkpoints + `report.md` are committed to the repo on each successful run, becoming the durable audit trail.
- `errors.jsonl` (per run, per date) is committed alongside on failures.

## 6. Testing strategy

### Layer 1 — Python helpers (pytest, no LLM)

The new helpers in `src/trader/helpers/` are pure-Python and fully unit-testable.

Coverage targets:

- `parse_subagent_output.py` — golden tests: well-formed input, malformed JSON, schema violations, multiple fenced blocks, prose around the block.
- `validate_proposal.py` — risk-cap violation detection (per-name, per-sector, min-sectors).
- `gate.py` — daily Tue–Sat trading-day mapping; rebalance "Friday-was-trading-day" mapping. Use `freezegun` against known holidays.
- `apply_trades.py`, `mark_to_market.py` — port logic from existing `tests/test_simulate.py` and `tests/test_ledger.py`.
- Schema models — round-trip serialization tests.

**Existing tests:**

- Keep: `test_calendar.py`, `test_ledger.py`, `test_simulate.py`, `test_risk.py`, `test_universe.py`.
- Delete: `test_probability.py`.
- Replace: `test_pipeline_smoke.py` → `test_helpers_smoke.py`, runs each helper CLI end-to-end against fixture JSONs in `tests/fixtures/runs/2026-01-02/`.

### Layer 2 — Subagent prompt sanity (manual, low quota)

Before scheduling, manually invoke each subagent against fixture input from an interactive Claude Code session:

```
/test-subagent scorer tests/fixtures/scorer_input.json
/test-subagent debater tests/fixtures/debater_input.json
/test-subagent prob-estimator tests/fixtures/prob_input.json
```

`/test-subagent` is a tiny slash command in `.claude/commands/` that reads the fixture, calls the named subagent once, runs the parser, and prints `PASS` or the validation error. Sanity check, not a regression suite. Re-run after any agent file edit.

### Layer 3 — Full pipeline dry-run (manual one-off, ~one full run's quota)

Before flipping the routine schedules on:

1. Set `KILL_SWITCH=1`, `EXECUTE=0` in routine secrets.
2. Trigger one-off `/trader-rebalance` via routine "run now".
3. Inspect each `data/runs/<today>/*.json`; eyeball `report.md`.
4. Confirm Telegram receives the report (no alert).
5. Then unset `KILL_SWITCH`, leave `EXECUTE=0` for the first live week, audit reports daily before flipping `EXECUTE=1`.

### Layer 4 — Production observability

For the first month, watch:

- Per-run logs in Anthropic's routine UI for stage durations and exit codes.
- `data/runs/<date>/errors.jsonl` in the repo for skipped tickers.
- Telegram alerts (run-failed, risk-cap-violation).

If any stage routinely produces malformed output, that's a prompt problem — fix the agent file body and add a fixture to Layer 2.

### Out of CI scope (intentional)

- Subagent LLM output quality. Nondeterminism + quota cost. Manual sanity (Layer 2) + production observability (Layer 4) carry this load.
- Full orchestrator flow. Same reason. Helpers carry the regression load; orchestration is configuration.

## 7. Open risks & required verification

### 7.1 Pre-implementation blockers

**B1. Routine sandbox resource limits.** CPU, memory, wall-clock, and network egress caps for routine sandboxes are not clearly documented. The 1000-ticker yfinance bulk fetch + pandas momentum/vol calc + 142 LLM calls fanning out in waves may exceed limits.
- **Verification:** trigger a one-off `/trader-rebalance` routine in `EXECUTE=0`, `KILL_SWITCH=0` mode early in implementation; observe wall time, peak memory if surfaced, and any sandbox-limit errors.

**B2. Ledger commit race.** A manual rerun overlapping a scheduled routine could produce conflicting ledger commits.
- **Mitigation built in:** `git pull --rebase` at stage 2 of every flow; `apply_trades.py` aborts if the remote moved ahead during the run.
- **Verification:** unit test simulating the race condition (two helpers attempting `apply_trades` against the same starting ledger).

**B3. Secrets handling and rotation.** Lifecycle of routine secrets (rotation cadence, expiry behavior) is not documented in detail.
- **Mitigation:** rotation is a manual step on both ends. If the GitHub PAT in `GIT_REMOTE_URL` expires, git push fails → Telegram alert (per 5.1) surfaces it within 24h.

### 7.2 During-dry-run monitors

**M1. Parallel subagent ceiling.** "Waves of 10" is a heuristic; real ceiling per orchestrator turn is undocumented.
- **Verification:** Layer 3 dry-run captures actual wall time per stage. Tune up to 15–20 if no throttling, down to 5 if throttling observed.

**M2. Subagent JSON reliability per type.** Failure rates differ by output complexity. Haiku producing 25-row JSON may misbehave more than Opus producing a 2-field object.
- **Verification:** Layer 2 tests + Layer 4 production `errors.jsonl` rate. Threshold: >5% skip rate on any stage means re-tune that subagent's prompt.

**M3. Subscription quota math.** Max 5-hour rolling window quota numerics not published. ~142 messages per weekly run, ~5–10 daily — should be safe but worth measuring.
- **Verification:** First few runs surface real consumption.

**M4. Half-day market closures.** NYSE 1pm ET close (post-Thanksgiving, occasionally Christmas Eve) means our 3:30am SGT trigger captures pre-close data instead of "just before close" on those days.
- **Verdict:** acceptable tax, no code fix.

**M5. Existing prompt files port effort.** `src/trader/prompts/*.md` files are referenced by `client.py:142-144`. They need to be inlined into `.claude/agents/*.md` bodies and rewritten to drop `tool_use` phrasing in favor of fenced JSON convention.
- **Effort:** 1–2 hours per agent × 5 agents = 5–10 hours.

## 8. Migration / cutover plan

### Phase 1 — Build helpers + subagents (no schedule changes)

1. Create `src/trader/helpers/` with all new CLIs.
2. Create `.claude/agents/*.md` with ported system prompts.
3. Create `.claude/commands/{trader-daily,trader-rebalance,test-subagent}.md`.
4. Add Layer 1 unit tests; ensure existing pytest suite passes.
5. Run Layer 2 subagent sanity tests from interactive Claude Code.

Output: a working trader callable from interactive Claude Code, but no schedule yet. Existing `pipeline.py` still in tree.

### Phase 2 — Delete legacy + verify shape

6. Delete `src/trader/agents/{client,scorer,debate,probability,selector,newswriter}.py`, `pipeline.py`, `tests/test_pipeline_smoke.py`, `tests/test_probability.py`.
7. Trim `config.py` and `cli.py`. Drop `anthropic`, `tenacity` from `pyproject.toml`.
8. Verify `pip install -e .` clean install succeeds in a fresh venv.
9. Commit + push to GitHub.

### Phase 3 — Routine dry-run (Layer 3)

10. Configure routine secrets in Anthropic's routine UI.
11. Trigger one-off `/trader-rebalance` with `KILL_SWITCH=1`, `EXECUTE=0`.
12. Inspect outputs; capture wall time; look for sandbox limit warnings.
13. Address any B1–M5 issue before scheduling.

### Phase 4 — Schedule + paper run

14. Create `/schedule` entries:
    - `/trader-daily` — Tue–Sat 03:30 SGT
    - `/trader-rebalance` — Sat 04:30 SGT
15. Set `EXECUTE=0`, `KILL_SWITCH=0`. Daily Telegram audit for one week.

### Phase 5 — Live trading

16. Flip `EXECUTE=1`. Continue daily audit; watch ledger commits.
17. After 1 month, retire run-started Telegram heartbeat. Keep run-failed and risk-cap-violation alerts.

## 9. Sources

- [Routines — Usage and limits](https://code.claude.com/docs/en/routines)
- [Run prompts on a schedule](https://code.claude.com/docs/en/scheduled-tasks)
- [Using Claude Code with your Pro or Max plan](https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan)
- [Agent SDK should support Max plan billing, not just API keys (#559)](https://github.com/anthropics/claude-agent-sdk-python/issues/559)
- [`claude -p` suggested to Max subscriber — caused unintended API billing (#37686)](https://github.com/anthropics/claude-code/issues/37686)
- [Anthropic Bans Claude Subscription OAuth in Third-Party Apps](https://winbuzzer.com/2026/02/19/anthropic-bans-claude-subscription-oauth-in-third-party-apps-xcxwbn/)

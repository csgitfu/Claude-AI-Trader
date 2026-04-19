"""Orchestration: weekly_rebalance and daily_scan.

Every stage's artifact is persisted under `data/runs/<YYYY-MM-DD>/` so any step
can be re-run from the previous stage's output.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from trader import universe
from trader.agents import debate, newswriter, probability, scorer, selector
from trader.agents.client import AnthropicAgent
from trader.agents.probability import Estimate
from trader.calendar_ import is_trading_day
from trader.config import settings
from trader.data import fundamentals, macro, news, prices
from trader.portfolio import performance, simulate
from trader.portfolio.ledger import Ledger, Trade
from trader.portfolio.risk import Proposal, sector_breakdown
from trader.publish import telegram

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    report_markdown: str
    report_path: Path | None
    trades: list[Trade]
    cost_usd: float


def _run_dir(as_of_iso: str) -> Path:
    d = settings.data_dir / "runs" / as_of_iso
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str))


def _kill_check() -> None:
    if settings.kill_switch:
        raise SystemExit("KILL_SWITCH is on; aborting before any API call.")


async def weekly_rebalance(*, dry_run: bool = False) -> RunResult:
    """Full pipeline: score → debate → probability → select → trade → news → publish."""
    _kill_check()
    if not is_trading_day():
        logger.info("not a trading day; skipping weekly")
        return RunResult("", None, [], 0.0)

    as_of = datetime.now(timezone.utc).date()
    run_dir = _run_dir(as_of.isoformat())
    agent = AnthropicAgent()

    # 1) Universe + market data
    uni_df = universe.fetch_universe()
    tickers = universe.tickers(uni_df)[:1000]
    logger.info("universe: %d tickers", len(tickers))

    hist = prices.download_history(tickers + ["SPY"], period="1y")
    spy_price = None
    if "SPY" in hist.columns:
        spy_price = float(hist["SPY"].ffill().iloc[-1])
        hist = hist.drop(columns=["SPY"])
    mom = prices.momentum(hist)
    vol = prices.realized_vol(hist)
    closes = prices.latest_close(list(hist.columns))

    fund = fundamentals.fetch_many(tickers)
    sector_of = {t: (fund.get(t) or {}).get("sector") or "Unknown" for t in tickers}

    # 2) Score (Haiku)
    score_rows = scorer.build_input_rows(tickers, fund, mom, vol)
    scores = await scorer.score_universe(agent, score_rows)
    _dump(run_dir / "scores.json", [s.__dict__ for s in scores])

    scores.sort(key=lambda s: s.score, reverse=True)
    shortlist = [s.ticker for s in scores[: settings.shortlist_size]]
    logger.info("shortlist: %s", shortlist)

    # 3) Debate (bull/bear)
    macro_snapshot = macro.snapshot()
    debate_ctx = {}
    for t in shortlist:
        debate_ctx[t] = {
            "fundamentals": fund.get(t, {}),
            "momentum": mom.get(t, {}),
            "ann_vol": vol.get(t),
            "headlines": news.ticker_headlines(t, limit=8),
            "macro": macro_snapshot,
        }
    debates = await debate.debate(agent, debate_ctx)
    _dump(run_dir / "debates.json", debates)

    # 4) Probability
    prob_payloads = {}
    for t in shortlist:
        prob_payloads[t] = {
            "ticker": t,
            "bull_case": debates.get(t, {}).get("bull", ""),
            "bear_case": debates.get(t, {}).get("bear", ""),
            "ann_vol": vol.get(t),
            "momentum": mom.get(t, {}),
            "fundamentals_summary": {
                k: (fund.get(t) or {}).get(k)
                for k in ("marketCap", "trailingPE", "forwardPE", "revenueGrowth", "beta")
            },
            "macro": macro_snapshot,
        }
    estimates: list[Estimate] = await probability.estimate(agent, prob_payloads)
    _dump(run_dir / "estimates.json", [e.__dict__ for e in estimates])

    # 5) Select (15 picks)
    ledger = Ledger.load() if settings.ledger_path.exists() else _seed_if_missing()
    current_weights = ledger.current_weights(closes)
    selection = await selector.select(
        agent,
        estimates=estimates,
        current_weights=current_weights,
        macro=macro_snapshot,
        sector_of=sector_of,
    )
    _dump(
        run_dir / "selection.json",
        {
            "commentary": selection.commentary,
            "picks": [p.__dict__ for p in selection.proposals],
        },
    )

    # 6) Simulate trades (unless shadow/dry_run)
    trades: list[Trade] = []
    if settings.execute and not dry_run:
        pick_prices = {p.ticker: closes[p.ticker] for p in selection.proposals if p.ticker in closes}
        # tag positions with their sectors as we update
        trades = simulate.plan_trades(ledger, selection.proposals, pick_prices, selection.rationales)
        simulate.apply(ledger, trades)
        # stamp sectors on resulting positions
        for p in selection.proposals:
            if p.ticker in ledger.positions:
                ledger.positions[p.ticker].sector = p.sector

    # 7) Mark to market + nav history
    mtm_prices = {t: closes[t] for t in ledger.positions if t in closes}
    ledger.mark_to_market(mtm_prices, spy=spy_price, as_of=as_of.isoformat())

    # 8) News scan
    report_md = await newswriter.write(
        agent,
        as_of=as_of,
        holdings_with_sectors=[
            {"ticker": t, "sector": p.sector, "shares": round(p.shares, 4)}
            for t, p in ledger.positions.items()
        ],
        sector_pct=sector_breakdown(selection.proposals),
        market_headlines=news.market_headlines(limit=15),
        holding_headlines={
            t: news.ticker_headlines(t, limit=5) for t in list(ledger.positions)[:10]
        },
        macro=macro_snapshot,
        portfolio_commentary=selection.commentary,
    )

    # 9) Persist + publish
    report_path: Path | None = None
    if not dry_run:
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = settings.reports_dir / f"{as_of.isoformat()}.md"
        report_path.write_text(report_md)
        if settings.execute:
            ledger.save()
        telegram.send(report_md)
    else:
        print(report_md)

    logger.info("run cost: $%.2f (in=%d, out=%d)", agent.total_cost, agent.total_in, agent.total_out)
    return RunResult(
        report_markdown=report_md,
        report_path=report_path,
        trades=trades,
        cost_usd=agent.total_cost,
    )


async def daily_scan(*, dry_run: bool = False) -> RunResult:
    """Lightweight path: mark-to-market + news scan, no rebalance."""
    _kill_check()
    if not is_trading_day():
        logger.info("not a trading day; skipping daily")
        return RunResult("", None, [], 0.0)

    as_of = datetime.now(timezone.utc).date()
    agent = AnthropicAgent()

    ledger = Ledger.load() if settings.ledger_path.exists() else _seed_if_missing()
    holding_tickers = list(ledger.positions) + ["SPY"]
    closes = prices.latest_close(holding_tickers) if holding_tickers else {}
    spy_price = closes.pop("SPY", None)

    ledger.mark_to_market(closes, spy=spy_price, as_of=as_of.isoformat())

    macro_snapshot = macro.snapshot()
    sector_pct = {}
    equity = sum(p.shares * closes.get(t, 0.0) for t, p in ledger.positions.items())
    if equity > 0:
        for t, p in ledger.positions.items():
            sector_pct[p.sector] = sector_pct.get(p.sector, 0.0) + p.shares * closes.get(t, 0.0) / equity

    report_md = await newswriter.write(
        agent,
        as_of=as_of,
        holdings_with_sectors=[
            {"ticker": t, "sector": p.sector, "shares": round(p.shares, 4)}
            for t, p in ledger.positions.items()
        ],
        sector_pct=sector_pct,
        market_headlines=news.market_headlines(limit=15),
        holding_headlines={
            t: news.ticker_headlines(t, limit=5) for t in list(ledger.positions)[:10]
        },
        macro=macro_snapshot,
        portfolio_commentary="No rebalance today; weekly cadence only.",
    )

    report_path: Path | None = None
    if not dry_run:
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = settings.reports_dir / f"{as_of.isoformat()}.md"
        report_path.write_text(report_md)
        if settings.execute:
            ledger.save()
        telegram.send(report_md)
    else:
        print(report_md)

    return RunResult(
        report_markdown=report_md, report_path=report_path, trades=[], cost_usd=agent.total_cost
    )


def _seed_if_missing() -> Ledger:
    from trader.portfolio.ledger import seed
    logger.warning("no ledger found; auto-seeding with STARTING_NAV=%s", settings.starting_nav)
    return seed(settings.starting_nav)


def performance_report() -> str:
    ledger = Ledger.load()
    m = performance.compute(ledger)
    return performance.format_markdown(m)

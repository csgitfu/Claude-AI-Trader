"""End-to-end smoke test with all external I/O mocked.

Exercises the full daily_scan and weekly_rebalance code paths without hitting
Anthropic, yfinance, FRED, Telegram, or iShares.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from trader import pipeline, universe
from trader.agents import probability, scorer
from trader.config import settings
from trader.portfolio.ledger import Trade, seed


@pytest.fixture
def fake_universe_df():
    return pd.DataFrame(
        [
            {"ticker": "AAPL", "name": "Apple", "sector": "Tech", "asset_class": "Equity"},
            {"ticker": "MSFT", "name": "Microsoft", "sector": "Tech", "asset_class": "Equity"},
            {"ticker": "JPM", "name": "JPMorgan", "sector": "Financials", "asset_class": "Equity"},
            {"ticker": "XOM", "name": "Exxon", "sector": "Energy", "asset_class": "Equity"},
            {"ticker": "JNJ", "name": "J&J", "sector": "Healthcare", "asset_class": "Equity"},
            {"ticker": "WMT", "name": "Walmart", "sector": "Consumer Staples", "asset_class": "Equity"},
            {"ticker": "HD", "name": "Home Depot", "sector": "Consumer Discretionary", "asset_class": "Equity"},
            {"ticker": "UNP", "name": "Union Pacific", "sector": "Industrials", "asset_class": "Equity"},
            {"ticker": "NEE", "name": "NextEra", "sector": "Utilities", "asset_class": "Equity"},
            {"ticker": "AMT", "name": "Amer Tower", "sector": "Real Estate", "asset_class": "Equity"},
            {"ticker": "LIN", "name": "Linde", "sector": "Materials", "asset_class": "Equity"},
            {"ticker": "T", "name": "AT&T", "sector": "Communication", "asset_class": "Equity"},
            {"ticker": "GOOG", "name": "Alphabet", "sector": "Tech", "asset_class": "Equity"},
            {"ticker": "META", "name": "Meta", "sector": "Tech", "asset_class": "Equity"},
            {"ticker": "NVDA", "name": "Nvidia", "sector": "Tech", "asset_class": "Equity"},
        ]
    )


@pytest.fixture
def fake_prices_df(fake_universe_df):
    dates = pd.date_range("2025-04-19", "2026-04-19", freq="B")
    data = {}
    for i, t in enumerate(list(fake_universe_df["ticker"]) + ["SPY"]):
        data[t] = [100.0 + i + j * 0.1 for j in range(len(dates))]
    return pd.DataFrame(data, index=dates)


def _fake_complete_factory():
    """Returns an async fn that mimics AnthropicAgent.complete for every tool."""

    async def _complete(*args, **kwargs):
        tools = kwargs.get("tools") or []
        tool_name = tools[0]["name"] if tools else None
        if tool_name == "score_stock":
            # return all tickers in the batch with a score
            user = kwargs["messages"][0]["content"] if "messages" in kwargs else kwargs["user"]
            import json as _j
            scores = []
            for line in user.split("\n"):
                try:
                    row = _j.loads(line)
                    scores.append({"ticker": row["ticker"], "score": 80, "one_liner": "ok", "flags": []})
                except Exception:
                    continue
            return {"text": "", "tool_use": {"name": tool_name, "input": {"scores": scores}},
                    "usage": {"in": 100, "out": 100}, "cost": 0.01}
        if tool_name == "probability_estimate":
            return {"text": "", "tool_use": {"name": tool_name, "input": {
                "p_up_6m": 0.4, "p_flat_6m": 0.4, "p_down_6m": 0.2,
                "expected_return": 0.08, "implied_vol": 0.25, "conviction": 3,
                "summary": "ok"}}, "usage": {"in": 100, "out": 100}, "cost": 0.01}
        if tool_name == "build_portfolio":
            tickers = ["AAPL", "MSFT", "JPM", "XOM", "JNJ", "WMT", "HD", "UNP", "NEE",
                       "AMT", "LIN", "T", "GOOG", "META", "NVDA"]
            sectors = ["Tech", "Tech", "Financials", "Energy", "Healthcare", "Consumer Staples",
                       "Consumer Discretionary", "Industrials", "Utilities", "Real Estate",
                       "Materials", "Communication", "Tech", "Tech", "Tech"]
            picks = [{"ticker": t, "weight": 1 / 15, "sector": s, "rationale": "test"}
                     for t, s in zip(tickers, sectors)]
            return {"text": "", "tool_use": {"name": tool_name, "input": {
                "picks": picks, "commentary": "diversified test portfolio"}},
                    "usage": {"in": 100, "out": 100}, "cost": 0.02}
        # Plain text calls (debate + newswriter)
        system = kwargs.get("system", "")
        if isinstance(system, list):
            system = system[0].get("text", "")
        if "bull" in system.lower()[:100]:
            return {"text": "Bull case: compelling fundamentals.", "tool_use": None,
                    "usage": {"in": 100, "out": 100}, "cost": 0.01}
        if "bear" in system.lower()[:100]:
            return {"text": "Bear case: valuation stretched.", "tool_use": None,
                    "usage": {"in": 100, "out": 100}, "cost": 0.01}
        return {"text": "# Daily News Scan — 2026-04-19\n\nTest report.", "tool_use": None,
                "usage": {"in": 100, "out": 100}, "cost": 0.02}

    return _complete


def test_weekly_rebalance_smoke(tmp_data_dir, fake_universe_df, fake_prices_df, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "execute", True)
    monkeypatch.setattr(settings, "shortlist_size", 5)

    seed(100_000)

    with patch("trader.universe.fetch_universe", return_value=fake_universe_df), \
         patch("trader.data.prices.download_history", return_value=fake_prices_df), \
         patch("trader.data.fundamentals.fetch_many",
               return_value={t: {"sector": s} for t, s in
                             zip(fake_universe_df["ticker"], fake_universe_df["sector"])}), \
         patch("trader.data.news.ticker_headlines", return_value=[]), \
         patch("trader.data.news.market_headlines", return_value=[]), \
         patch("trader.data.macro.snapshot", return_value={}), \
         patch("trader.publish.telegram.send", return_value=True), \
         patch("trader.pipeline.is_trading_day", return_value=True), \
         patch("trader.agents.client.AnthropicAgent.complete",
               new=AsyncMock(side_effect=_fake_complete_factory())):

        result = asyncio.run(pipeline.weekly_rebalance(dry_run=False))

    assert result.report_markdown
    assert result.report_path is not None
    assert result.report_path.exists()
    # ledger got written with 15 positions
    from trader.portfolio.ledger import Ledger
    ledger = Ledger.load()
    assert len(ledger.positions) == 15


def test_daily_scan_smoke(tmp_data_dir, fake_prices_df, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "execute", True)

    ledger = seed(100_000)
    ledger.apply_trade(Trade(ts="t0", ticker="AAPL", side="buy", shares=100, price=150))
    ledger.positions["AAPL"].sector = "Tech"
    ledger.save()

    with patch("trader.data.prices.latest_close",
               return_value={"AAPL": 160.0, "SPY": 5200.0}), \
         patch("trader.data.news.ticker_headlines", return_value=[]), \
         patch("trader.data.news.market_headlines", return_value=[]), \
         patch("trader.data.macro.snapshot", return_value={}), \
         patch("trader.publish.telegram.send", return_value=True), \
         patch("trader.pipeline.is_trading_day", return_value=True), \
         patch("trader.agents.client.AnthropicAgent.complete",
               new=AsyncMock(side_effect=_fake_complete_factory())):

        result = asyncio.run(pipeline.daily_scan(dry_run=False))

    assert "Daily News Scan" in result.report_markdown
    from trader.portfolio.ledger import Ledger
    ledger2 = Ledger.load()
    assert ledger2.nav_history[-1].spy == 5200.0

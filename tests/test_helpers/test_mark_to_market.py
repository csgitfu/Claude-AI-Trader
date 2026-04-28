"""Tests for mark_to_market helper."""

import json
from pathlib import Path

import pytest

from trader.portfolio.ledger import Ledger, seed, Trade
from trader.helpers import mark_to_market


@pytest.fixture
def market_data():
    """Sample market data with closes."""
    return {
        "closes": {
            "AAPL": 150.0,
            "MSFT": 300.0,
        },
        "spy_close": 450.0,
    }


def test_mark_to_market_with_positions(tmp_data_dir, market_data):
    """Exercise mark_to_market with seeded ledger and positions."""
    # Setup: create ledger with initial positions
    ledger = seed(100_000)

    # Add some positions by applying trades
    trade_aapl = Trade(
        ts="2026-01-01T10:00:00Z",
        ticker="AAPL",
        side="buy",
        shares=100.0,
        price=100.0,
        rationale="test buy",
    )
    trade_msft = Trade(
        ts="2026-01-01T10:30:00Z",
        ticker="MSFT",
        side="buy",
        shares=50.0,
        price=200.0,
        rationale="test buy",
    )
    ledger.apply_trade(trade_aapl)
    ledger.apply_trade(trade_msft)
    ledger.save()

    # Create market data file
    market_file = tmp_data_dir / "market.json"
    market_file.write_text(json.dumps(market_data))

    # Call mark_to_market
    result = mark_to_market.main(["--market", str(market_file)])

    # Assert
    assert result == 0

    # Reload ledger and verify nav_history updated
    ledger_reloaded = Ledger.load()
    assert len(ledger_reloaded.nav_history) > 0

    # Check latest nav point
    latest_nav = ledger_reloaded.nav_history[-1]
    assert latest_nav.nav is not None
    # NAV = cash + equity where equity = AAPL (100 * 150) + MSFT (50 * 300)
    expected_equity = 100 * 150.0 + 50 * 300.0  # 15000 + 15000 = 30000
    expected_nav = (100_000 - 100 * 100.0 - 50 * 200.0) + expected_equity
    # cash = 100000 - 10000 - 10000 = 80000
    # nav = 80000 + 30000 = 110000 (but market prices are higher, so nav went up)
    assert abs(latest_nav.nav - expected_nav) < 0.01
    assert latest_nav.spy == 450.0


def test_mark_to_market_no_ledger(tmp_data_dir, market_data):
    """With no ledger, mark_to_market exits cleanly."""
    # Setup: no ledger created
    market_file = tmp_data_dir / "market.json"
    market_file.write_text(json.dumps(market_data))

    # Call mark_to_market
    result = mark_to_market.main(["--market", str(market_file)])

    # Assert
    assert result == 0

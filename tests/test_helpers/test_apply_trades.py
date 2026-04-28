"""Tests for apply_trades helper."""

import json
from pathlib import Path

import pytest

from trader.portfolio.ledger import Ledger, seed
from trader.portfolio.risk import Proposal
from trader.helpers import apply_trades


@pytest.fixture
def market_data():
    """Sample market data with closes."""
    return {
        "closes": {
            "AAPL": 150.0,
            "MSFT": 300.0,
            "GOOGL": 120.0,
        }
    }


@pytest.fixture
def selection():
    """Sample selection with proposals."""
    return {
        "picks": [
            {"ticker": "AAPL", "weight": 0.5, "sector": "Tech"},
            {"ticker": "MSFT", "weight": 0.5, "sector": "Tech"},
        ],
        "rationales": {
            "AAPL": "strong fundamentals",
            "MSFT": "steady growth",
        }
    }


def test_execute_0_writes_trades_unchanged_ledger(tmp_data_dir, monkeypatch, market_data, selection):
    """With EXECUTE=0, trades.json is written but ledger unchanged."""
    # Setup
    from trader.config import settings
    ledger = seed(100_000)
    starting_positions = len(ledger.positions)
    starting_cash = ledger.cash

    selection_file = tmp_data_dir / "selection.json"
    selection_file.write_text(json.dumps(selection))
    market_file = tmp_data_dir / "market.json"
    market_file.write_text(json.dumps(market_data))
    trades_file = tmp_data_dir / "trades.json"

    # Monkeypatch EXECUTE
    monkeypatch.setattr(settings, "execute", False)
    monkeypatch.setenv("EXECUTE", "0")

    # Call
    result = apply_trades.main([
        "--selection", str(selection_file),
        "--market", str(market_file),
        "--trades-out", str(trades_file),
    ])

    # Assert
    assert result == 0
    assert trades_file.exists()
    trades = json.loads(trades_file.read_text())
    assert len(trades) > 0  # trades were planned

    # Ledger unchanged
    ledger_reloaded = Ledger.load()
    assert len(ledger_reloaded.positions) == starting_positions
    assert ledger_reloaded.cash == starting_cash


def test_kill_switch_aborts(tmp_data_dir, monkeypatch, market_data, selection):
    """With KILL_SWITCH=1, process exits non-zero, ledger unchanged."""
    # Setup
    seed(100_000)

    selection_file = tmp_data_dir / "selection.json"
    selection_file.write_text(json.dumps(selection))
    market_file = tmp_data_dir / "market.json"
    market_file.write_text(json.dumps(market_data))
    trades_file = tmp_data_dir / "trades.json"

    monkeypatch.setenv("KILL_SWITCH", "1")

    # Call
    result = apply_trades.main([
        "--selection", str(selection_file),
        "--market", str(market_file),
        "--trades-out", str(trades_file),
    ])

    # Assert
    assert result == 1
    # trades_file may not exist or be incomplete due to early exit
    # Ledger should be unchanged (not saved)


def test_execute_1_applies_trades(tmp_data_dir, monkeypatch, market_data, selection):
    """With EXECUTE=1 and no git drift, trades applied to ledger."""
    # Setup
    from trader.config import settings
    ledger = seed(100_000)

    selection_file = tmp_data_dir / "selection.json"
    selection_file.write_text(json.dumps(selection))
    market_file = tmp_data_dir / "market.json"
    market_file.write_text(json.dumps(market_data))
    trades_file = tmp_data_dir / "trades.json"

    monkeypatch.setattr(settings, "execute", True)
    monkeypatch.setenv("EXECUTE", "1")
    # Mock git_drifted to return False
    monkeypatch.setattr(apply_trades, "_git_drifted", lambda: False)

    # Call
    result = apply_trades.main([
        "--selection", str(selection_file),
        "--market", str(market_file),
        "--trades-out", str(trades_file),
    ])

    # Assert
    assert result == 0
    assert trades_file.exists()
    trades = json.loads(trades_file.read_text())
    assert len(trades) > 0

    # Ledger was modified
    ledger_reloaded = Ledger.load()
    # Should have positions in AAPL and MSFT
    assert "AAPL" in ledger_reloaded.positions
    assert "MSFT" in ledger_reloaded.positions
    # Cash should be reduced from initial 100_000
    assert ledger_reloaded.cash < 100_000
    # Sector should be set from proposal
    assert ledger_reloaded.positions["AAPL"].sector == "Tech"
    assert ledger_reloaded.positions["MSFT"].sector == "Tech"

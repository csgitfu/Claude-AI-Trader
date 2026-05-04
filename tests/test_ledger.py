import pytest

from trader.portfolio.ledger import Ledger, Trade, seed


def test_seed_persists_starting_nav(tmp_data_dir):
    ledger = seed(1_000_000)
    assert ledger.cash == 1_000_000
    loaded = Ledger.load()
    assert loaded.starting_nav == 1_000_000
    assert loaded.cash == 1_000_000
    assert loaded.positions == {}


def test_buy_then_sell_round_trip(tmp_data_dir):
    ledger = seed(100_000)
    ledger.apply_trade(Trade(ts="t0", ticker="AAPL", side="buy", shares=100, price=150.0))
    assert ledger.cash == 100_000 - 15_000
    assert ledger.positions["AAPL"].shares == 100
    assert ledger.positions["AAPL"].avg_cost == 150.0

    ledger.apply_trade(Trade(ts="t1", ticker="AAPL", side="sell", shares=100, price=160.0))
    assert "AAPL" not in ledger.positions
    assert ledger.cash == pytest.approx(100_000 - 15_000 + 16_000)


def test_insufficient_cash_rejected(tmp_data_dir):
    ledger = seed(1000)
    with pytest.raises(ValueError):
        ledger.apply_trade(Trade(ts="t0", ticker="AAPL", side="buy", shares=100, price=150.0))


def test_insufficient_shares_rejected(tmp_data_dir):
    ledger = seed(100_000)
    ledger.apply_trade(Trade(ts="t0", ticker="AAPL", side="buy", shares=10, price=100))
    with pytest.raises(ValueError):
        ledger.apply_trade(Trade(ts="t1", ticker="AAPL", side="sell", shares=100, price=100))


def test_nav_invariant_after_trades(tmp_data_dir):
    ledger = seed(100_000)
    ledger.apply_trade(Trade(ts="t0", ticker="AAPL", side="buy", shares=100, price=150.0))
    ledger.apply_trade(Trade(ts="t0", ticker="MSFT", side="buy", shares=50, price=400.0))
    prices = {"AAPL": 150.0, "MSFT": 400.0}
    point = ledger.mark_to_market(prices, spy=5000.0, as_of="2026-04-19")
    # invariant: nav == cash + sum(shares * price)
    assert point.nav == pytest.approx(100_000)
    assert point.cash == pytest.approx(100_000 - 15_000 - 20_000)
    assert point.equity == pytest.approx(15_000 + 20_000)


def test_mark_to_market_is_idempotent_per_date(tmp_data_dir):
    ledger = seed(100_000)
    ledger.mark_to_market({}, spy=5000.0, as_of="2026-04-19")
    ledger.mark_to_market({}, spy=5010.0, as_of="2026-04-19")
    assert len(ledger.nav_history) == 1
    assert ledger.nav_history[0].spy == 5010.0


def test_save_load_round_trip(tmp_data_dir):
    ledger = seed(100_000)
    ledger.apply_trade(Trade(ts="t0", ticker="NVDA", side="buy", shares=10, price=900, rationale="high conviction"))
    ledger.save()
    loaded = Ledger.load()
    assert loaded.cash == pytest.approx(91_000)
    assert loaded.positions["NVDA"].shares == 10
    assert loaded.trades[0].rationale == "high conviction"


def test_mark_to_market_carries_forward_missing_prices(tmp_data_dir):
    """Regression: May 1 NAV reported -50% because positions without prices
    were silently dropped from equity. Carry-forward keeps NAV plausible and
    flags which positions used a stale mark."""
    ledger = seed(100_000)
    ledger.apply_trade(Trade(ts="t0", ticker="AAPL", side="buy", shares=100, price=150.0))
    ledger.apply_trade(Trade(ts="t0", ticker="ZION", side="buy", shares=10, price=50.0))

    # Day 1: full price coverage — last_close gets seeded.
    p1 = ledger.mark_to_market({"AAPL": 160.0, "ZION": 55.0}, spy=500.0, as_of="2026-04-29")
    assert p1.stale == []
    assert p1.equity == pytest.approx(100 * 160 + 10 * 55)
    assert ledger.positions["AAPL"].last_close == 160.0
    assert ledger.positions["ZION"].last_close_date == "2026-04-29"

    # Day 2: ZION price missing → carry forward 55.0, stale list flags ZION.
    p2 = ledger.mark_to_market({"AAPL": 165.0}, spy=510.0, as_of="2026-04-30")
    assert p2.stale == ["ZION"]
    assert p2.equity == pytest.approx(100 * 165 + 10 * 55)
    assert ledger.positions["AAPL"].last_close == 165.0
    # ZION's last_close untouched because no fresh price arrived
    assert ledger.positions["ZION"].last_close == 55.0
    assert ledger.positions["ZION"].last_close_date == "2026-04-29"


def test_mark_to_market_no_prior_close_reports_stale_no_equity(tmp_data_dir):
    """If a position has never been marked, refuse to fabricate equity for it."""
    ledger = seed(100_000)
    ledger.apply_trade(Trade(ts="t0", ticker="AAPL", side="buy", shares=100, price=150.0))
    point = ledger.mark_to_market({}, spy=500.0, as_of="2026-04-30")
    assert point.stale == ["AAPL"]
    assert point.equity == 0  # no fabricated equity
    assert point.nav == pytest.approx(ledger.cash)


def test_load_handles_legacy_ledger_without_last_close(tmp_data_dir, tmp_path):
    """Old ledger files lack last_close fields; load must default them to None."""
    import json
    legacy = {
        "starting_nav": 50_000,
        "cash": 1_000,
        "positions": {
            "AAPL": {"shares": 100, "avg_cost": 150.0, "sector": "Tech"},
        },
        "trades": [],
        "nav_history": [
            {"date": "2026-04-29", "nav": 50_000, "cash": 1_000, "equity": 49_000, "spy": 500.0},
        ],
    }
    from trader.config import settings
    settings.ledger_path.write_text(json.dumps(legacy))
    loaded = Ledger.load()
    assert loaded.positions["AAPL"].last_close is None
    assert loaded.nav_history[0].stale == []

import pytest

from trader.portfolio.ledger import Ledger, Trade, seed
from trader.portfolio.risk import Proposal
from trader.portfolio.simulate import apply, plan_trades


def test_plan_trades_from_empty_book(tmp_data_dir):
    ledger = seed(100_000)
    targets = [
        Proposal(ticker="AAPL", weight=0.5, sector="Tech"),
        Proposal(ticker="MSFT", weight=0.5, sector="Tech"),
    ]
    prices = {"AAPL": 100.0, "MSFT": 200.0}
    trades = plan_trades(ledger, targets, prices)
    assert len(trades) == 2
    apply(ledger, trades)
    # each target got 50k → 500 AAPL + 250 MSFT
    assert ledger.positions["AAPL"].shares == 500
    assert ledger.positions["MSFT"].shares == 250
    assert ledger.cash < 1e-6  # all cash deployed


def test_plan_trades_sells_removed_names(tmp_data_dir):
    ledger = seed(100_000)
    ledger.apply_trade(Trade(ts="t0", ticker="IBM", side="buy", shares=1000, price=50))
    targets = [Proposal(ticker="AAPL", weight=1.0, sector="Tech")]
    prices = {"IBM": 50.0, "AAPL": 100.0}
    trades = plan_trades(ledger, targets, prices)
    sides = {(t.ticker, t.side) for t in trades}
    assert ("IBM", "sell") in sides
    assert ("AAPL", "buy") in sides


def test_plan_trades_raises_when_held_position_missing_price(tmp_data_dir):
    """Regression: silent skip of held-position sells caused the May 1 bloat."""
    ledger = seed(100_000)
    ledger.apply_trade(Trade(ts="t0", ticker="IBM", side="buy", shares=1000, price=50))
    ledger.apply_trade(Trade(ts="t0", ticker="ZION", side="buy", shares=10, price=50))
    targets = [Proposal(ticker="AAPL", weight=1.0, sector="Tech")]
    prices = {"IBM": 50.0, "AAPL": 100.0}  # ZION price missing
    with pytest.raises(ValueError, match="ZION"):
        plan_trades(ledger, targets, prices)

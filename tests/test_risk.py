import pytest

from trader.portfolio.risk import Proposal, enforce, sector_breakdown


def _prop(ticker, weight, sector):
    return Proposal(ticker=ticker, weight=weight, sector=sector)


_SECTORS = [
    "Tech", "Financials", "Energy", "Healthcare", "Staples",
    "Discretionary", "Industrials", "Utilities", "RE",
    "Materials", "Comm", "Tech", "Financials", "Energy", "Healthcare",
]


def _feasible_15(base_weight: float = 1 / 15) -> list[Proposal]:
    return [_prop(f"T{i}", base_weight, _SECTORS[i]) for i in range(15)]


def test_weights_sum_to_one_when_feasible():
    out = enforce(_feasible_15(), max_weight_per_name=0.10, max_weight_per_sector=0.25, portfolio_size=15)
    assert pytest.approx(sum(p.weight for p in out), abs=1e-6) == 1.0
    for p in out:
        assert p.weight <= 0.10 + 1e-9


def test_per_name_cap_clamps_outsized_proposal():
    props = [_prop("AAPL", 0.50, _SECTORS[0])]
    props += [_prop(f"T{i}", 0.05, _SECTORS[i]) for i in range(1, 15)]
    out = enforce(props, max_weight_per_name=0.10, max_weight_per_sector=0.25, portfolio_size=15)
    for p in out:
        assert p.weight <= 0.10 + 1e-9


def test_sector_cap_never_exceeded():
    # 5 tech names proposed at 0.15 each (0.75 total) + 10 others
    props = [_prop(f"TECH{i}", 0.15, "Tech") for i in range(5)]
    props += [_prop(f"OTH{i}", 0.02, _SECTORS[(i % len(_SECTORS)) + 1]) for i in range(10)]
    out = enforce(props, max_weight_per_name=0.10, max_weight_per_sector=0.25, portfolio_size=15)
    breakdown = sector_breakdown(out)
    for sec, w in breakdown.items():
        assert w <= 0.25 + 1e-9, f"sector {sec} = {w}"


def test_infeasible_constraints_return_under_one():
    # 3 Tech, 2 Fin, 2 Energy — impossible to reach sum 1.0 under cap_s=0.25
    props = [_prop("AAPL", 0.20, "Tech"), _prop("MSFT", 0.20, "Tech"),
             _prop("NVDA", 0.20, "Tech"), _prop("JPM", 0.10, "Financials"),
             _prop("BAC", 0.10, "Financials"), _prop("XOM", 0.10, "Energy"),
             _prop("CVX", 0.10, "Energy")]
    out = enforce(props, max_weight_per_name=0.15, max_weight_per_sector=0.25, portfolio_size=7)
    breakdown = sector_breakdown(out)
    assert breakdown["Tech"] <= 0.25 + 1e-6
    total = sum(p.weight for p in out)
    assert total <= 1.0 + 1e-9
    # and cash > 0 (the remainder)
    assert total < 1.0


def test_drops_negative_weights():
    props = [_prop("A", 0.5, _SECTORS[0]), _prop("B", -0.1, _SECTORS[1]),
             _prop("C", 0.5, _SECTORS[2])]
    out = enforce(props, portfolio_size=3)
    assert all(p.weight > 0 for p in out)
    assert "B" not in {p.ticker for p in out}

import json
import subprocess
import sys
from pathlib import Path

CMD = [sys.executable, "-m", "trader.helpers.validate_proposal"]


def _write_selection(tmp_path: Path, picks: list[dict]) -> Path:
    p = tmp_path / "selection.json"
    p.write_text(json.dumps({"commentary": "x", "picks": picks}))
    return p


def _balanced_picks(weight: float = 0.075, n: int = 13, sectors: list[str] | None = None) -> list[dict]:
    sectors = sectors or [
        "Tech", "Health", "Energy", "Fin", "Indust", "Cons", "Util", "Mat",
        "Tech", "Health", "Energy", "Fin", "Indust",
    ]
    return [
        {"ticker": f"T{i:02d}", "weight": weight, "sector": sectors[i], "rationale": "x"}
        for i in range(n)
    ]


def _write_ledger(tmp_path: Path, positions: dict[str, dict]) -> Path:
    """Write a ledger.json with the given positions at unit price (1 share = $1 weight unit)."""
    ledger_path = tmp_path / "ledger.json"
    raw = {
        "starting_nav": 1000.0,
        "cash": 0.0,
        "positions": positions,
        "trades": [],
        "nav_history": [],
    }
    ledger_path.write_text(json.dumps(raw))
    return ledger_path


def _write_market(tmp_path: Path, prices: dict[str, float]) -> Path:
    market_path = tmp_path / "market_data.json"
    market_path.write_text(json.dumps({"closes": prices}))
    return market_path


def test_passes_balanced_proposal(tmp_path):
    picks = [
        {"ticker": f"T{i:02d}", "weight": 0.075, "sector": s, "rationale": "x"}
        for i, s in enumerate(
            ["Tech", "Health", "Energy", "Fin", "Indust", "Cons", "Util", "Mat",
             "Tech", "Health", "Energy", "Fin", "Indust"]
        )
    ]
    sel = _write_selection(tmp_path, picks)
    r = subprocess.run(CMD + ["--in", str(sel)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_rejects_per_name_cap_violation(tmp_path):
    picks = [{"ticker": "AAPL", "weight": 0.15, "sector": "Tech", "rationale": "x"}]
    sel = _write_selection(tmp_path, picks)
    r = subprocess.run(CMD + ["--in", str(sel)], capture_output=True, text=True)
    assert r.returncode != 0
    assert "per_name" in (r.stderr + r.stdout).lower()


def test_rejects_sector_concentration(tmp_path):
    picks = [
        {"ticker": f"T{i:02d}", "weight": 0.09, "sector": "Tech", "rationale": "x"}
        for i in range(10)
    ]
    sel = _write_selection(tmp_path, picks)
    r = subprocess.run(CMD + ["--in", str(sel)], capture_output=True, text=True)
    assert r.returncode != 0
    assert "sector" in (r.stderr + r.stdout).lower()


def test_rejects_too_few_sectors(tmp_path):
    picks = [
        {"ticker": f"T{i:02d}", "weight": 0.05, "sector": s, "rationale": "x"}
        for i, s in enumerate(["A", "B", "C", "A", "B", "C", "A", "B"])  # 3 sectors only
    ]
    sel = _write_selection(tmp_path, picks)
    r = subprocess.run(CMD + ["--in", str(sel)], capture_output=True, text=True)
    assert r.returncode != 0
    assert "min_sector" in (r.stderr + r.stdout).lower()


# ---------- turnover guardrail ----------


def test_turnover_skipped_for_first_run(tmp_path):
    """Empty ledger (no positions) is exempt from the turnover cap."""
    picks = _balanced_picks()
    sel = _write_selection(tmp_path, picks)
    ledger = _write_ledger(tmp_path, positions={})
    market = _write_market(tmp_path, prices={f"T{i:02d}": 100.0 for i in range(13)})
    r = subprocess.run(
        CMD + ["--in", str(sel), "--ledger", str(ledger), "--market", str(market)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def test_turnover_passes_when_holdings_overlap(tmp_path):
    """If most names carry over and weight changes are modest, turnover < cap."""
    picks = _balanced_picks(weight=0.075, n=13)
    sel = _write_selection(tmp_path, picks)
    # Old portfolio: same 13 tickers at slightly different weights — small drift.
    positions = {
        f"T{i:02d}": {"shares": 7.5, "avg_cost": 100.0, "sector": "Tech"}
        for i in range(13)
    }
    ledger = _write_ledger(tmp_path, positions=positions)
    market = _write_market(tmp_path, prices={f"T{i:02d}": 100.0 for i in range(13)})
    r = subprocess.run(
        CMD + ["--in", str(sel), "--ledger", str(ledger), "--market", str(market)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def test_turnover_rejects_full_rotation(tmp_path):
    """Replacing all 13 names with new tickers triggers the cap."""
    picks = [
        {"ticker": f"NEW{i:02d}", "weight": 0.075, "sector": s, "rationale": "x"}
        for i, s in enumerate(
            ["Tech", "Health", "Energy", "Fin", "Indust", "Cons", "Util", "Mat",
             "Tech", "Health", "Energy", "Fin", "Indust"]
        )
    ]
    sel = _write_selection(tmp_path, picks)
    # Old portfolio: 13 different tickers, all priced.
    positions = {
        f"OLD{i:02d}": {"shares": 7.5, "avg_cost": 100.0, "sector": "Tech"}
        for i in range(13)
    }
    ledger = _write_ledger(tmp_path, positions=positions)
    prices = {f"OLD{i:02d}": 100.0 for i in range(13)}
    prices.update({f"NEW{i:02d}": 100.0 for i in range(13)})
    market = _write_market(tmp_path, prices=prices)
    r = subprocess.run(
        CMD + ["--in", str(sel), "--ledger", str(ledger), "--market", str(market)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "turnover" in (r.stderr + r.stdout).lower()


def test_turnover_check_skipped_when_flags_omitted(tmp_path):
    """Without --ledger/--market, turnover check is silently disabled (back-compat)."""
    picks = _balanced_picks()
    sel = _write_selection(tmp_path, picks)
    r = subprocess.run(CMD + ["--in", str(sel)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

import json
import subprocess
import sys
from pathlib import Path

CMD = [sys.executable, "-m", "trader.helpers.validate_proposal"]


def _write_selection(tmp_path: Path, picks: list[dict]) -> Path:
    p = tmp_path / "selection.json"
    p.write_text(json.dumps({"commentary": "x", "picks": picks}))
    return p


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

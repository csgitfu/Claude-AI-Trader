import json
import subprocess
import sys
from pathlib import Path

CMD = [sys.executable, "-m", "trader.helpers.merge_stage_output"]


def test_merge_scorer_batches(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"scores": [
        {"ticker": "AAPL", "score": 80, "one_liner": "x", "flags": []}
    ]}))
    b.write_text(json.dumps({"scores": [
        {"ticker": "MSFT", "score": 70, "one_liner": "y", "flags": []}
    ]}))
    out = tmp_path / "scores.json"
    r = subprocess.run(CMD + ["--stage", "scorer", "--out", str(out), str(a), str(b)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    merged = json.loads(out.read_text())
    assert {row["ticker"] for row in merged["scores"]} == {"AAPL", "MSFT"}


def test_merge_debater_dict(tmp_path):
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"ticker": "AAPL", "bull": "...", "bear": "..."}))
    out = tmp_path / "debates.json"
    r = subprocess.run(CMD + ["--stage", "debater", "--out", str(out), str(a)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    merged = json.loads(out.read_text())
    assert "AAPL" in merged
    assert merged["AAPL"]["bull"] == "..."

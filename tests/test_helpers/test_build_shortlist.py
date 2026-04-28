import json
import subprocess
import sys
from pathlib import Path

CMD = [sys.executable, "-m", "trader.helpers.build_shortlist"]


def test_top_n_selection(tmp_path):
    scores = {
        "scores": [
            {"ticker": "AAPL", "score": 90, "one_liner": "x", "flags": []},
            {"ticker": "MSFT", "score": 80, "one_liner": "x", "flags": []},
            {"ticker": "GOOG", "score": 70, "one_liner": "x", "flags": []},
            {"ticker": "AMZN", "score": 60, "one_liner": "x", "flags": []},
        ]
    }
    in_path = tmp_path / "scores.json"
    out_path = tmp_path / "shortlist.json"
    in_path.write_text(json.dumps(scores))

    r = subprocess.run(
        CMD + ["--in", str(in_path), "--out", str(out_path), "--n", "2"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(out_path.read_text())
    assert out["tickers"] == ["AAPL", "MSFT"]

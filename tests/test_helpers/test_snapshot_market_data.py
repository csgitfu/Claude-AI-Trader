import json
import subprocess
import sys
from pathlib import Path

import pytest

CMD = [sys.executable, "-m", "trader.helpers.snapshot_market_data"]


def test_holdings_only_writes_expected_keys(tmp_path, monkeypatch):
    """Smoke: helper writes a JSON with expected top-level keys.

    We can't fully mock yfinance from a subprocess; this test relies on the
    helper running with --tickers explicit list to bypass ledger reading.
    """
    out = tmp_path / "market_data.json"
    r = subprocess.run(
        CMD + ["--mode", "holdings-only", "--out", str(out), "--tickers", "AAPL,MSFT,SPY"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(out.read_text())
    assert "closes" in data
    assert "momentum" in data
    assert "vol" in data
    assert "spy_close" in data

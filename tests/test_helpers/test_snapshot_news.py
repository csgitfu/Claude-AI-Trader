import json
import subprocess
import sys

CMD = [sys.executable, "-m", "trader.helpers.snapshot_news"]


def test_holdings_only_writes_expected_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "")  # exercise no-FRED path
    out_news = tmp_path / "news.json"
    out_macro = tmp_path / "macro.json"
    r = subprocess.run(
        CMD
        + [
            "--mode", "holdings-only",
            "--out-news", str(out_news),
            "--out-macro", str(out_macro),
            "--tickers", "AAPL,MSFT",
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr

    news = json.loads(out_news.read_text())
    assert "market" in news
    assert "tickers" in news
    assert set(news["tickers"]) <= {"AAPL", "MSFT"}

    macro = json.loads(out_macro.read_text())
    assert isinstance(macro, dict)

from trader import universe


SAMPLE_IWB = b"""iShares Russell 1000 ETF,
Fund Holdings as of 18-Apr-2026

Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Shares,CUSIP,ISIN
AAPL,APPLE INC,Information Technology,Equity,123456,3.45,1,100,037833100,US0378331005
MSFT,MICROSOFT CORP,Information Technology,Equity,100000,3.0,1,80,594918104,US5949181045
XXXX,CASH,Cash and/or Derivatives,Cash,1000,0.03,1,0,,
"""


def test_parse_iwb_csv_filters_non_equity():
    df = universe._parse_iwb_csv(SAMPLE_IWB)
    assert "AAPL" in df["ticker"].values
    assert "MSFT" in df["ticker"].values
    # cash row should be filtered out (asset_class != equity)
    assert "XXXX" not in df["ticker"].values


def test_tickers_helper():
    df = universe._parse_iwb_csv(SAMPLE_IWB)
    tickers = universe.tickers(df)
    assert tickers == ["AAPL", "MSFT"]


class _FakeResp:
    """Minimal stand-in for requests.Response."""

    def __init__(self, content: bytes, status: int = 200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# iShares intermittently serves an HTML page (product page / bot wall) with
# HTTP 200 and a misleading text/csv content-type instead of the holdings CSV.
IWB_HTML_200 = b"<!DOCTYPE html>\n<html><head><title>iShares</title></head><body>not csv</body></html>"


def test_fetch_universe_html_200_falls_back_without_poisoning_cache(monkeypatch):
    """A force-refresh that gets unparseable HTML (HTTP 200) must not cache the
    bad body, and must fall back to the last good snapshot rather than failing."""
    good = universe.settings.universe_dir / "iwb_2020-01-01.csv"
    good.write_bytes(SAMPLE_IWB)

    monkeypatch.setattr(
        universe.requests, "get", lambda *a, **k: _FakeResp(IWB_HTML_200, 200)
    )

    df = universe.fetch_universe(force=True)

    # fell back to the seeded good snapshot
    assert "AAPL" in df["ticker"].values
    assert "MSFT" in df["ticker"].values
    # the HTML body must NOT have been written to today's cache file
    assert not universe._cache_path().exists()

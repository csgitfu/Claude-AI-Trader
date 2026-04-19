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

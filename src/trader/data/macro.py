"""FRED macro snapshot: CPI, Fed funds, unemployment, 10Y yield, VIX."""

from __future__ import annotations

import logging

from fredapi import Fred

from trader.config import settings

logger = logging.getLogger(__name__)

SERIES = {
    "cpi_yoy": "CPIAUCSL",        # compute yoy in code
    "fed_funds": "DFF",
    "unemployment": "UNRATE",
    "ten_year": "DGS10",
    "vix": "VIXCLS",
}


def snapshot() -> dict[str, float]:
    if not settings.fred_api_key:
        logger.warning("FRED_API_KEY not set; returning empty macro snapshot")
        return {}
    fred = Fred(api_key=settings.fred_api_key)
    out: dict[str, float] = {}
    for key, series_id in SERIES.items():
        try:
            s = fred.get_series(series_id).dropna()
            if key == "cpi_yoy" and len(s) > 12:
                out[key] = float(s.iloc[-1] / s.iloc[-13] - 1.0)
            else:
                out[key] = float(s.iloc[-1])
        except Exception as exc:
            logger.warning("FRED %s failed: %s", series_id, exc)
    return out

"""Russell 1000 constituents via the iShares IWB ETF holdings CSV.

iShares publishes a daily holdings CSV per ETF. The URL has a stable shape but
requires a real UA header and occasionally returns HTML on error. We cache each
fetch to `data/universe/iwb_YYYY-MM-DD.csv`; on failure we fall back to the most
recent cached file.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from trader.config import settings

logger = logging.getLogger(__name__)

IWB_URL = (
    "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund"
)
UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _parse_iwb_csv(raw: bytes) -> pd.DataFrame:
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.lower().startswith("ticker,")),
        None,
    )
    if header_idx is None:
        raise ValueError("IWB CSV: no 'Ticker,' header row found")
    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    if "asset_class" in df.columns:
        df = df[df["asset_class"].astype(str).str.lower() == "equity"]
    df = df[df["ticker"].astype(str).str.match(r"^[A-Z.\-]{1,6}$", na=False)]
    return df.reset_index(drop=True)


def _cache_path(d: datetime | None = None) -> Path:
    d = d or datetime.now(timezone.utc)
    return settings.universe_dir / f"iwb_{d.strftime('%Y-%m-%d')}.csv"


def fetch_universe(force: bool = False) -> pd.DataFrame:
    today_path = _cache_path()
    settings.universe_dir.mkdir(parents=True, exist_ok=True)

    if today_path.exists() and not force:
        return _parse_iwb_csv(today_path.read_bytes())

    try:
        resp = requests.get(IWB_URL, headers=UA, timeout=30)
        resp.raise_for_status()
        # Parse BEFORE caching: iShares sometimes returns an HTML page with a 200
        # status, which raise_for_status() won't catch. Writing it first would
        # poison today's cache and defeat the fallback below.
        df = _parse_iwb_csv(resp.content)
        today_path.write_bytes(resp.content)
        return df
    except Exception as exc:  # network, parse, 404 — all recoverable
        logger.warning("IWB fetch failed (%s); falling back to most recent good cache", exc)
        snapshots = sorted(settings.universe_dir.glob("iwb_*.csv"))
        for snap in reversed(snapshots):  # newest first; skip any unparseable snapshot
            try:
                return _parse_iwb_csv(snap.read_bytes())
            except Exception:
                logger.warning("cached snapshot %s is unparseable; trying older", snap.name)
        raise RuntimeError("no parseable IWB cache available and live fetch failed") from exc


def tickers(df: pd.DataFrame | None = None) -> list[str]:
    df = fetch_universe() if df is None else df
    return df["ticker"].astype(str).str.upper().tolist()

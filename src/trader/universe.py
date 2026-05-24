"""Russell 1000 constituents via the iShares IWB ETF holdings JSON API.

iShares migrated www.ishares.com to an Astro front-end (~May 2026), which broke
the legacy ``.ajax?fileType=csv`` holdings download: it now returns the product
page HTML with HTTP 200 for every client, regardless of headers/TLS. The Astro
page instead loads holdings client-side from BlackRock's product-data API, which
still serves clean JSON to plain HTTP clients with no API key:

    .../api/v2/get-product-data?component=holdings.all&portfolioId=239707&...

The payload is columnar:
``componentsByNameMap.holdings.containersByNameMap.all.dataPointsByNameMap.<col>
.formattedValue`` is a parallel array (one entry per holding). We convert the
ticker/name/sector/assetClass columns into the same CSV byte shape iShares used
to publish, so the existing parse-before-cache logic, the ``iwb_YYYY-MM-DD.csv``
snapshot cache, and the resilient newest->oldest fallback all keep working
unchanged. Omitting ``asOfDate`` returns the latest available holdings.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from trader.config import settings

logger = logging.getLogger(__name__)

# IWB's portfolio id on ishares.com (the number in the product-page URL).
IWB_PORTFOLIO_ID = "239707"
# Public product-data endpoint the Astro product page calls to render holdings.
# No API key required; this is what the live site itself fetches.
IWB_HOLDINGS_URL = (
    "https://www.ishares.com/varnish-api/blk-one01-product-data/product-data"
    "/api/v2/get-product-data"
    "?appSubType=ISHARES&appType=PRODUCT_PAGE&component=holdings.all"
    f"&locale=en_US&portfolioId={IWB_PORTFOLIO_ID}&targetSite=us-ishares"
    "&userType=individual&excludeContent=false&includeConfig=false"
)
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

# API columnar field -> legacy iShares CSV header, so _parse_iwb_csv reads the
# serialised result unchanged.
_API_COLUMNS = {
    "ticker": "Ticker",
    "issueName": "Name",
    "sectorName": "Sector",
    "assetClass": "Asset Class",
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


def _fetch_ishares_holdings_csv() -> bytes:
    """Fetch IWB holdings from the iShares product-data API and serialise them to
    the legacy iShares CSV byte format.

    Returning CSV bytes lets ``fetch_universe`` parse-before-cache and keeps the
    on-disk snapshot compatible with the fallback path. Raises on anything
    unexpected (HTML body, missing keys, ragged/empty columns) so the caller
    falls back to the last good snapshot rather than caching garbage.
    """
    resp = requests.get(IWB_HOLDINGS_URL, headers=UA, timeout=30)
    resp.raise_for_status()
    # json.loads raises on the HTML product page (the broken legacy path), which
    # the caller treats as a fetch failure and falls back, exactly as before.
    data = json.loads(resp.content.decode("utf-8-sig", errors="replace"))
    points = (
        data["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"][
            "dataPointsByNameMap"
        ]
    )
    cols = {
        header: points[api_name]["formattedValue"]
        for api_name, header in _API_COLUMNS.items()
    }
    if not cols["Ticker"]:
        raise ValueError("iShares holdings API returned zero rows")
    # pd.DataFrame raises if the columnar arrays are ragged -> caught by caller.
    df = pd.DataFrame(cols)
    return df.to_csv(index=False).encode("utf-8")


def _cache_path(d: datetime | None = None) -> Path:
    d = d or datetime.now(timezone.utc)
    return settings.universe_dir / f"iwb_{d.strftime('%Y-%m-%d')}.csv"


def fetch_universe(force: bool = False) -> pd.DataFrame:
    today_path = _cache_path()
    settings.universe_dir.mkdir(parents=True, exist_ok=True)

    if today_path.exists() and not force:
        return _parse_iwb_csv(today_path.read_bytes())

    try:
        raw = _fetch_ishares_holdings_csv()
        # Parse BEFORE caching: a malformed/partial response (e.g. the HTML
        # product page) must not poison today's cache and defeat the fallback.
        df = _parse_iwb_csv(raw)
        today_path.write_bytes(raw)
        return df
    except Exception as exc:  # network, HTML body, missing keys, parse — recoverable
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

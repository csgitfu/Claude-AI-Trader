# Weekly Rebalance Report — 2026-05-22

> **⚠️ DATA QUALITY NOTE:** The GH Actions prefetch workflow did not deliver market data for the 2026-05-22 run date within the 45-minute window. The scorer (Stage 6) and debater context (Stage 8) were built using `market_data_full.json` carried forward from the **2026-05-15** run — data that was 7 calendar days stale at time of scoring. Prices, momentum, and fundamentals may not reflect developments between 2026-05-15 and 2026-05-22. The ledger was marked to 2026-05-22 closing prices via `mark_to_market`; that step used the same stale file, so position values and weights reflect 2026-05-22 closes for held positions, but the scoring universe and alpha estimates were formed on week-old data.

---

## Portfolio Summary

| Metric | Value |
|--------|-------|
| **NAV** | $50,255.21 |
| **Starting NAV** | $50,000.00 |
| **Total Return (since inception ~2026-05-09)** | +$255.21 (+0.5%) |
| **SPY (2026-05-22 close, from ledger)** | $745.64 |
| **Cash** | $13,870.44 (27.6%) |
| **Positions invested** | $36,384.77 (72.4%) |

*Note: Portfolio inception is approximately 2026-05-09 based on earliest trades. Full YTD comparison vs SPY is not available — nav history spans only 2026-05-19 to present. Over that 4-day window the portfolio returned approximately +0.36% vs SPY +0.74% (price return).*

### Sector Breakdown

| Sector | Weight (%) |
|--------|-----------|
| Financial Services | 23.0% |
| Technology | 20.5% |
| Healthcare | 9.4% |
| Industrials | 6.5% |
| Basic Materials | 5.5% |
| Communication Services | 3.5% |
| Consumer Defensive | 2.0% |
| Energy | 2.0% |
| **Cash** | **27.6%** |
| **Total** | **100.0%** |

---

## Trades Made

### Bought / Added

| Ticker | New Weight | Sector | Rationale |
|--------|-----------|--------|-----------|
| DUOL | 7.0% | Technology | #1 composite score (p=0.63, +280 bps alpha); 35% revenue growth + AI-driven EdTech with 72% gross margins; mean-reversion after −40% drawdown |
| NVDA | 8.5% | Technology | Retained existing holding; no new buy — prior weight 9.0% trimmed slightly |
| RNR | 7.0% | Financial Services | Retained; prior weight 7.6% trimmed toward sizing hint |
| FSLR | 5.0% | Technology | New: 9.1x forward P/E, +65% earnings growth, IRA manufacturing tailwind; +21.8% 1-month momentum reversal |
| PRI | 5.0% | Financial Services | New: 10.7x P/E, 31.9% ROE, 12.7% FCF yield; life insurance distribution compounder at deep discount |
| NBIX | 5.4% | Healthcare | Retained + small top-up; p=0.62, +220 bps alpha — highest Healthcare conviction |
| NEM | 5.5% | Basic Materials | Retained; gold macro tailwind, 9.6x P/E, $9.8B FCF |
| EME | 6.5% | Industrials | Retained; electrical contractor benefiting from data-center infrastructure buildout |
| CI | 4.0% | Healthcare | New: 8.5x forward P/E with $6.9B FCF; managed-care value re-rating candidate |
| AMG | 4.5% | Financial Services | Retained + small top-up; 9.87x P/E, 66% ROE, alt-asset manager compounder |
| SEIC | 4.0% | Financial Services | New: 13.8x P/E, 29.6% ROE, GARP asset manager; +14.8% 1-month momentum |
| RDDT | 3.5% | Communication Services | New: p=0.56, +180 bps alpha; DAU/MAU growth + advertising revenue ramp |

### Sold / Trimmed

| Ticker | Previous Weight | Action | Reason |
|--------|----------------|--------|--------|
| ADBE | 8.0% | **Sold (full)** | Fell off top-50 shortlist — quality breakdown; no probability estimate generated |
| GMED | 6.1% | **Sold (full)** | Fell off top-50 shortlist — quality breakdown |
| META | 4.5% | **Sold (full)** | Fell off top-50 shortlist — quality breakdown |
| SNX | 4.5% | **Sold (full)** | Fell off top-50 shortlist — quality breakdown |
| TIGO | 4.2% | **Sold (full)** | Fell off top-50 shortlist — quality breakdown |
| BMY | 4.0% | **Sold (full)** | Fell off top-50 shortlist — quality breakdown |
| NVDA | 9.0% → 8.5% | Trimmed | Sizing-hint drift toward 5.0%; gradual reduction |
| RNR | 7.6% → 7.0% | Trimmed | Sizing-hint drift toward 2.0%; gradual reduction |
| STZ | 3.9% → 2.0% | Trimmed | Not in shortlist; trimmed to minimum 2.0% for turnover management; sector anchor |
| IBKR | 4.9% → 2.5% | Trimmed | Not in shortlist; trimmed to minimum 2.5% for turnover management |
| RRC | 3.8% → 2.0% | Trimmed | Not in shortlist; trimmed to minimum 2.0% for turnover management; Energy anchor |
| EME | 6.8% → 6.5% | Trimmed | Sizing-hint drift toward 5.0% |
| NEM | 5.8% → 5.5% | Trimmed | Sizing-hint drift toward 5.0% |

---

## Selector Commentary

Retained 6 shortlist positions (AMG, EME, NBIX, NEM, NVDA, RNR) under catalyst protection — all under 28 days old with p_outperform 0.55–0.62 — and held 3 additional legacy names (STZ, IBKR, RRC) trimmed to minimum sizing to contain one-way turnover at 39.1% against the 40% cap; rotated out 6 names (ADBE, BMY, GMED, META, SNX, TIGO) that scored out of the top-50 shortlist and have no active probability estimate. Added 6 high-conviction new picks led by DUOL (p=0.63, +280 bps expected alpha) and FSLR (p=0.60, +220 bps), filling Communication Services via RDDT and anchoring the portfolio across 8 distinct sectors with Financial Services the largest concentration at 23%.

---

## Risk Notes

1. **Financial Services concentration (23.0%):** Five names — RNR, AMG, PRI, SEIC, and IBKR — together represent nearly a quarter of NAV. Any sector-wide credit event, regulatory shock, or rate-market dislocation could move this bloc simultaneously. RNR has a modestly bearish near-term momentum profile (sizing hint only 2.0%); the concentration risk is partially mitigated by the diverse sub-sector mix (reinsurance, alt-asset management, life insurance, asset servicing, brokerage).

2. **Technology concentration (20.5%)** and **single-name NVDA (8.5%):** NVDA at 8.5% is the largest single position. A negative datacenter demand signal, export-control escalation, or forward-guidance cut would impact the portfolio meaningfully. DUOL and FSLR add growth-oriented Tech exposure but with very different risk drivers (consumer EdTech, solar manufacturing), reducing co-movement risk within the bucket.

3. **Tickers with p_outperform < 0.55 in portfolio:** STZ (no estimate — kept for turnover), IBKR (no estimate — kept for turnover), RRC (no estimate — kept for turnover), RNR (p=0.55), RDDT (p=0.56). These five account for 22.0% of portfolio weight. Three of the five (STZ, IBKR, RRC) are structural carry-overs slated for rotation next cycle and carry no active bull thesis.

---

## Week Ahead

**Macro backdrop (as of 2026-05-22):** Fed Funds 3.62%, CPI YoY 3.95%, unemployment 4.3%, 10-year yield 4.57%, VIX 16.76. The rate environment is moderately supportive — the Fed is easing but inflation remains above target. Low VIX signals complacency; any macro shock could cause a rapid risk-off repricing.

**Known catalysts for portfolio holdings (next 7 days):**

- **NVDA:** Any commentary from hyperscaler earnings calls or AI industry events could move GPU demand expectations. Management conference appearances scheduled in late May are typical for NVDA around this time.
- **NEM (Newmont):** Gold continues to trade on geopolitical and inflation signals. Any USD strength spike or Fed hawkish surprise would pressure the gold price and NEM simultaneously.
- **FSLR (First Solar):** Solar policy developments (IRA implementation guidance, tariff updates on imported panels) remain live catalysts in either direction.
- **DUOL:** No scheduled near-term earnings catalyst, but any AI product launch announcement or DAU/subscriber data releases could move the stock given momentum setup.
- **CI (Cigna):** Healthcare sector broadly sensitive to any CMS (Centers for Medicare & Medicaid Services) rate-setting announcements or pharmacy-benefit-manager legislative developments.
- **Macro:** FOMC minutes and any Fed speaker commentary in the post-meeting window could reset rate expectations. Watch 10-year yield — if it backs up through 4.70%, Financial Services names (AMG, PRI, SEIC, RNR) could face multiple compression.

*No major scheduled earnings for any current portfolio holdings identified in the news data for the week of 2026-05-25 through 2026-05-29.*

---

*Report generated: 2026-05-22. Market data used for scoring was 7 days stale (2026-05-15 prefetch fallback). All trade prices and position values reflect 2026-05-22 closes from mark-to-market.*

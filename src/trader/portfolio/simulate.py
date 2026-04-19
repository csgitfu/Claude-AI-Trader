"""Diff current positions against target weights; emit simulated trades at close."""

from __future__ import annotations

from datetime import datetime, timezone

from trader.portfolio.ledger import Ledger, Trade
from trader.portfolio.risk import Proposal


def plan_trades(
    ledger: Ledger,
    targets: list[Proposal],
    prices: dict[str, float],
    rationale_by_ticker: dict[str, str] | None = None,
) -> list[Trade]:
    """Return the list of trades that would move the book to `targets`.

    Sells every position not in targets. Buys/sells deltas for kept positions.
    Assumes fractional shares (simulation only).
    """
    rationale_by_ticker = rationale_by_ticker or {}
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # current NAV at today's marks
    equity = sum(p.shares * prices[t] for t, p in ledger.positions.items() if t in prices)
    nav = ledger.cash + equity
    if nav <= 0:
        return []

    current_shares = {t: p.shares for t, p in ledger.positions.items()}
    target_shares: dict[str, float] = {}
    for tgt in targets:
        if tgt.ticker not in prices:
            continue
        target_value = nav * tgt.weight
        target_shares[tgt.ticker] = target_value / prices[tgt.ticker]

    trades: list[Trade] = []
    # sells first (frees up cash for buys)
    for t, shares in current_shares.items():
        tgt = target_shares.get(t, 0.0)
        delta = tgt - shares
        if delta < -1e-6 and t in prices:
            trades.append(
                Trade(
                    ts=ts,
                    ticker=t,
                    side="sell",
                    shares=round(-delta, 6),
                    price=prices[t],
                    rationale=rationale_by_ticker.get(t, "rebalance"),
                )
            )
    for t, tgt in target_shares.items():
        cur = current_shares.get(t, 0.0)
        delta = tgt - cur
        if delta > 1e-6:
            trades.append(
                Trade(
                    ts=ts,
                    ticker=t,
                    side="buy",
                    shares=round(delta, 6),
                    price=prices[t],
                    rationale=rationale_by_ticker.get(t, "rebalance"),
                )
            )
    return trades


def apply(ledger: Ledger, trades: list[Trade]) -> None:
    for t in trades:
        ledger.apply_trade(t)

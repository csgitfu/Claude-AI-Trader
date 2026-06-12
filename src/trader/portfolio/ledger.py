"""JSON-backed portfolio ledger.

Invariant: at any snapshot, `nav == cash + sum(shares * mark_price)`.
Reads and writes are full-file atomic via a temp file + rename.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from trader.config import settings

# Integer split ratios to check for (N:1 forward splits).
_SPLIT_RATIOS = [2, 3, 4, 5, 6, 7, 8, 10, 12, 20]
# Tolerance: ratio must be within this fraction of an integer to count.
_SPLIT_TOL = 0.025


def _detect_forward_split(prev_close: float, new_price: float) -> int | None:
    """Return N if prices imply an N:1 forward split occurred, else None.

    Only fires when the new price is less than 60% of the previous close —
    a genuine 40%+ single-day drop is extremely rare and warrants the split
    assumption for any ratio in _SPLIT_RATIOS.
    """
    if prev_close <= 0 or new_price <= 0:
        return None
    if new_price >= prev_close * 0.60:
        return None  # modest drop — not a split
    ratio = prev_close / new_price
    for n in _SPLIT_RATIOS:
        if abs(ratio - n) / n < _SPLIT_TOL:
            return n
    return None


@dataclass
class Position:
    shares: float
    avg_cost: float
    sector: str = "Unknown"
    last_close: float | None = None
    last_close_date: str | None = None


@dataclass
class Trade:
    ts: str
    ticker: str
    side: str  # "buy" | "sell"
    shares: float
    price: float
    rationale: str = ""


@dataclass
class NavPoint:
    date: str
    nav: float
    cash: float
    equity: float
    spy: float | None = None
    stale: list[str] = field(default_factory=list)


@dataclass
class Ledger:
    starting_nav: float
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    nav_history: list[NavPoint] = field(default_factory=list)

    # ---------- persistence ----------

    @classmethod
    def load(cls, path: Path | None = None) -> "Ledger":
        path = path or settings.ledger_path
        if not path.exists():
            raise FileNotFoundError(
                f"No ledger at {path}. Run `python -m trader init` to seed one."
            )
        raw = json.loads(path.read_text())
        pos_fields = {f.name for f in fields(Position)}
        nav_fields = {f.name for f in fields(NavPoint)}
        return cls(
            starting_nav=raw["starting_nav"],
            cash=raw["cash"],
            positions={
                t: Position(**{k: v for k, v in p.items() if k in pos_fields})
                for t, p in raw.get("positions", {}).items()
            },
            trades=[Trade(**t) for t in raw.get("trades", [])],
            nav_history=[
                NavPoint(**{k: v for k, v in n.items() if k in nav_fields})
                for n in raw.get("nav_history", [])
            ],
        )

    def save(self, path: Path | None = None) -> None:
        path = path or settings.ledger_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "starting_nav": self.starting_nav,
            "cash": round(self.cash, 4),
            "positions": {
                t: {
                    "shares": p.shares,
                    "avg_cost": p.avg_cost,
                    "sector": p.sector,
                    "last_close": p.last_close,
                    "last_close_date": p.last_close_date,
                }
                for t, p in self.positions.items()
            },
            "trades": [t.__dict__ for t in self.trades],
            "nav_history": [n.__dict__ for n in self.nav_history],
        }
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".ledger.", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise

    # ---------- mutation ----------

    def apply_trade(self, trade: Trade) -> None:
        if trade.side == "buy":
            cost = trade.shares * trade.price
            # 1 cent tolerance for floating-point drift across multi-trade plans
            if cost > self.cash + 0.01:
                raise ValueError(f"insufficient cash: need {cost:.4f}, have {self.cash:.4f}")
            if cost > self.cash:
                cost = self.cash  # clip to available, preserve non-negative cash
                trade.shares = cost / trade.price if trade.price > 0 else 0.0
            self.cash -= cost
            pos = self.positions.get(trade.ticker)
            if pos is None:
                self.positions[trade.ticker] = Position(
                    shares=trade.shares, avg_cost=trade.price, sector="Unknown"
                )
            else:
                total_cost = pos.shares * pos.avg_cost + cost
                new_shares = pos.shares + trade.shares
                pos.shares = new_shares
                pos.avg_cost = total_cost / new_shares if new_shares else 0.0
        elif trade.side == "sell":
            pos = self.positions.get(trade.ticker)
            if pos is None or pos.shares + 1e-9 < trade.shares:
                raise ValueError(f"insufficient shares of {trade.ticker} to sell")
            pos.shares -= trade.shares
            self.cash += trade.shares * trade.price
            if pos.shares <= 1e-9:
                del self.positions[trade.ticker]
        else:
            raise ValueError(f"unknown side {trade.side!r}")
        self.trades.append(trade)

    # ---------- reporting ----------

    def mark_to_market(
        self, prices: dict[str, float], spy: float | None = None, as_of: str | None = None
    ) -> NavPoint:
        """Compute NAV; carry forward last-known close for any position whose
        ticker is missing from `prices`. The carry-forward keeps NAV plausible
        when an upstream snapshot drops a ticker; the resulting NavPoint records
        which positions used a stale price so the report can flag them."""
        as_of = as_of or datetime.now(timezone.utc).date().isoformat()
        stale: list[str] = []
        equity = 0.0
        for t, p in self.positions.items():
            if t in prices:
                new_price = prices[t]
                if p.last_close is not None:
                    n = _detect_forward_split(p.last_close, new_price)
                    if n is not None:
                        print(
                            f"[split] {t}: {n}:1 forward split detected "
                            f"(prev={p.last_close:.4f} → new={new_price:.4f}); "
                            f"shares ×{n}, avg_cost ÷{n}",
                            file=sys.stderr,
                        )
                        p.shares *= n
                        p.avg_cost /= n
                p.last_close = new_price
                p.last_close_date = as_of
                equity += p.shares * new_price
            elif p.last_close is not None:
                stale.append(t)
                equity += p.shares * p.last_close
            else:
                # No fresh price and no prior mark — refuse to fabricate equity.
                stale.append(t)
        nav = self.cash + equity
        point = NavPoint(
            date=as_of, nav=nav, cash=self.cash, equity=equity, spy=spy, stale=stale
        )
        # replace-or-append: idempotent for a given date
        self.nav_history = [n for n in self.nav_history if n.date != as_of]
        self.nav_history.append(point)
        self.nav_history.sort(key=lambda n: n.date)
        return point

    def current_weights(self, prices: dict[str, float]) -> dict[str, float]:
        equity = sum(p.shares * prices[t] for t, p in self.positions.items() if t in prices)
        nav = self.cash + equity
        if nav <= 0:
            return {}
        return {t: p.shares * prices[t] / nav for t, p in self.positions.items() if t in prices}


def seed(starting_nav: float, path: Path | None = None) -> Ledger:
    ledger = Ledger(starting_nav=starting_nav, cash=starting_nav)
    ledger.save(path)
    return ledger

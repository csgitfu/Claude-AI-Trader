"""Performance metrics: TWRR, Sharpe, max-drawdown, vs SPY."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from trader.portfolio.ledger import Ledger


@dataclass
class Metrics:
    days: int
    total_return: float
    spy_return: float | None
    alpha: float | None
    ann_vol: float
    sharpe: float
    max_drawdown: float


def _returns(vals: list[float]) -> np.ndarray:
    arr = np.asarray(vals, dtype=float)
    if len(arr) < 2:
        return np.array([])
    return arr[1:] / arr[:-1] - 1.0


def compute(ledger: Ledger) -> Metrics:
    if len(ledger.nav_history) < 2:
        return Metrics(days=len(ledger.nav_history), total_return=0.0, spy_return=None,
                       alpha=None, ann_vol=0.0, sharpe=0.0, max_drawdown=0.0)

    navs = [n.nav for n in ledger.nav_history]
    rets = _returns(navs)
    total = navs[-1] / navs[0] - 1.0

    spys = [n.spy for n in ledger.nav_history if n.spy is not None]
    spy_ret: float | None = None
    alpha: float | None = None
    if len(spys) >= 2:
        spy_ret = spys[-1] / spys[0] - 1.0
        alpha = total - spy_ret

    ann_vol = float(rets.std() * np.sqrt(252)) if len(rets) else 0.0
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0

    peak = np.maximum.accumulate(navs)
    dd = (np.array(navs) - peak) / peak
    max_dd = float(dd.min()) if len(dd) else 0.0

    return Metrics(
        days=len(navs),
        total_return=total,
        spy_return=spy_ret,
        alpha=alpha,
        ann_vol=ann_vol,
        sharpe=sharpe,
        max_drawdown=max_dd,
    )


def format_markdown(m: Metrics) -> str:
    lines = [
        f"**Days tracked:** {m.days}",
        f"**Total return:** {m.total_return:.2%}",
    ]
    if m.spy_return is not None:
        lines.append(f"**SPY return:** {m.spy_return:.2%}")
    if m.alpha is not None:
        lines.append(f"**Alpha vs SPY:** {m.alpha:+.2%}")
    lines += [
        f"**Ann. volatility:** {m.ann_vol:.2%}",
        f"**Sharpe:** {m.sharpe:.2f}",
        f"**Max drawdown:** {m.max_drawdown:.2%}",
    ]
    return "\n".join(lines)

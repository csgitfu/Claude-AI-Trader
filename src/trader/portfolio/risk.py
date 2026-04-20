"""Risk constraints applied to LLM-proposed portfolios.

LLMs drift. We treat their output as a *proposal* and project it onto the
feasible set before any trade is simulated.

Projection algorithm:
  1. Drop non-positives; keep top-N by weight.
  2. Clamp per-name to `max_weight_per_name`.
  3. Clamp each sector's total to `max_weight_per_sector` (proportional scale-down).
  4. Water-fill upward toward sum=1.0, respecting both caps jointly per sector.

If the caps are infeasible for sum=1.0 (e.g. too few sectors given the sector
cap), the result is a best-effort allocation that respects every cap but sums
to less than 1.0 — cash holds the remainder.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from trader.config import settings


@dataclass
class Proposal:
    ticker: str
    weight: float
    sector: str
    rationale: str = ""


def enforce(
    proposals: list[Proposal],
    *,
    max_weight_per_name: float | None = None,
    max_weight_per_sector: float | None = None,
    portfolio_size: int | None = None,
) -> list[Proposal]:
    cap_n = max_weight_per_name if max_weight_per_name is not None else settings.max_weight_per_name
    cap_s = max_weight_per_sector if max_weight_per_sector is not None else settings.max_weight_per_sector
    n = portfolio_size if portfolio_size is not None else settings.portfolio_size

    cleaned = [p for p in proposals if p.weight > 0]
    cleaned.sort(key=lambda p: p.weight, reverse=True)
    cleaned = cleaned[:n]
    if not cleaned:
        return []

    # Step 1: per-name clamp
    for p in cleaned:
        p.weight = min(p.weight, cap_n)

    by_sector: dict[str, list[Proposal]] = defaultdict(list)
    for p in cleaned:
        by_sector[p.sector].append(p)

    # Step 2: per-sector clamp
    for group in by_sector.values():
        tot = sum(p.weight for p in group)
        if tot > cap_s and tot > 0:
            scale = cap_s / tot
            for p in group:
                p.weight *= scale

    # Step 3: water-fill up to sum=1.0 (within caps)
    for _ in range(20):
        total = sum(p.weight for p in cleaned)
        if total >= 1.0 - 1e-9:
            break
        need = 1.0 - total

        # For each sector, the achievable budget to add is min(sector slack,
        # sum of per-name slacks). Within the sector, distribute proportional
        # to per-name slack.
        deltas: dict[int, float] = {}
        for group in by_sector.values():
            sector_total = sum(p.weight for p in group)
            sector_slack = max(0.0, cap_s - sector_total)
            name_slack = {id(p): max(0.0, cap_n - p.weight) for p in group}
            total_name_slack = sum(name_slack.values())
            if sector_slack <= 1e-12 or total_name_slack <= 1e-12:
                continue
            sector_budget = min(sector_slack, total_name_slack)
            for p in group:
                deltas[id(p)] = sector_budget * (name_slack[id(p)] / total_name_slack)

        total_delta = sum(deltas.values())
        if total_delta <= 1e-12:
            break
        scale = min(1.0, need / total_delta)
        for p in cleaned:
            p.weight += deltas.get(id(p), 0.0) * scale
        if scale < 1.0:
            # we just reached sum=1.0 exactly
            break
    return cleaned


def sector_breakdown(proposals: list[Proposal]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for p in proposals:
        out[p.sector] += p.weight
    return dict(out)

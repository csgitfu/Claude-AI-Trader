import pytest
from freezegun import freeze_time

from trader.helpers import gate


# 03:30 SGT Tuesday = 19:30 UTC Monday. Monday was a trading day.
@freeze_time("2026-01-20 19:30:00")  # UTC; SGT = 2026-01-21 03:30 (Wed)
def test_daily_passes_on_trading_day_utc():
    # UTC date 2026-01-20 (Tue) is a trading day
    rc = gate.main(["daily"])
    assert rc == 0


@freeze_time("2026-01-26 19:30:00")  # UTC date 2026-01-26 = Mon US is trading
def test_daily_passes_on_monday():
    rc = gate.main(["daily"])
    assert rc == 0


# Sunday SGT 03:30 = Saturday UTC 19:30 — Sat is not a trading day
@freeze_time("2026-01-17 19:30:00")
def test_daily_fails_on_weekend():
    rc = gate.main(["daily"])
    assert rc != 0


# Sat 04:30 SGT = Fri 20:30 UTC. Fri 2026-01-23 was a trading day.
@freeze_time("2026-01-23 20:30:00")
def test_rebalance_passes_after_friday_close():
    rc = gate.main(["rebalance"])
    assert rc == 0


# Sat 04:30 SGT after a holiday Friday (e.g. Good Friday 2026-04-03)
@freeze_time("2026-04-03 20:30:00")
def test_rebalance_fails_on_market_holiday_friday():
    rc = gate.main(["rebalance"])
    assert rc != 0


def test_kill_switch_aborts(monkeypatch, capsys):
    monkeypatch.setenv("KILL_SWITCH", "1")
    with freeze_time("2026-01-20 19:30:00"):
        rc = gate.main(["daily"])
    assert rc != 0
    captured = capsys.readouterr()
    assert "KILL_SWITCH" in (captured.err + captured.out)

from datetime import date, datetime, timezone

import pandas as pd
import pandas_market_calendars as mcal

_XNYS = mcal.get_calendar("XNYS")


def is_trading_day(d: date | None = None) -> bool:
    d = d or datetime.now(timezone.utc).date()
    schedule = _XNYS.schedule(start_date=d, end_date=d)
    return not schedule.empty


def last_trading_day(d: date | None = None) -> date:
    d = d or datetime.now(timezone.utc).date()
    schedule = _XNYS.schedule(start_date=pd.Timestamp(d) - pd.Timedelta(days=10), end_date=d)
    return schedule.index[-1].date()


def is_monday_trading_day(d: date | None = None) -> bool:
    d = d or datetime.now(timezone.utc).date()
    return d.weekday() == 0 and is_trading_day(d)


def last_trading_day_was_friday(d: date | None = None) -> bool:
    """At time of call, was the most recent trading day a Friday?

    Used by the rebalance gate, which runs Sat 04:30 SGT (Fri ~20:30 UTC).
    Returns True only if the previous US trading day landed on a Friday
    (i.e., the UTC date today is a Friday and is a trading day).
    """
    d = d or datetime.now(timezone.utc).date()
    if d.weekday() != 4:  # 4 = Friday
        return False
    return is_trading_day(d)

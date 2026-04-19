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

from datetime import date

from trader import calendar_


def test_saturday_is_not_trading_day():
    # 2026-04-18 is a Saturday
    assert calendar_.is_trading_day(date(2026, 4, 18)) is False


def test_weekday_is_trading_day():
    # 2026-04-17 is Good Friday (market closed), so pick a regular Thursday
    assert calendar_.is_trading_day(date(2026, 4, 16)) is True


def test_good_friday_closed():
    assert calendar_.is_trading_day(date(2026, 4, 3)) is False


def test_last_trading_day_skips_weekend():
    # 2026-04-19 is a Sunday; last trading day on/before is Friday 04-17.
    assert calendar_.last_trading_day(date(2026, 4, 19)) == date(2026, 4, 17)

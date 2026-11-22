"""Whether the New York market is in its regular session, when it next opens, and how an answer says how current its price is (design doc v2/16
section 3.3). There is no holiday table: on a holiday the last trade is a day old during what would be trading hours, so it reads as a close."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from utils.text_utils import spoken_time

NEW_YORK = ZoneInfo("America/New_York")
OPENING_BELL = time(9, 30)
CLOSING_BELL = time(16, 0)
SATURDAY = 5


def market_in_session(now: datetime) -> bool:
    local = now.astimezone(NEW_YORK)
    return local.weekday() < SATURDAY and OPENING_BELL <= local.time() < CLOSING_BELL


def next_opening(now: datetime) -> datetime:
    """The next weekday 9:30 AM in New York after now; a holiday costs one extra fetch, not a wrong answer."""
    local = now.astimezone(NEW_YORK)
    day = local.date() if local.time() < OPENING_BELL else local.date() + timedelta(days=1)
    while day.weekday() >= SATURDAY:
        day += timedelta(days=1)
    return datetime.combine(day, OPENING_BELL, tzinfo=NEW_YORK)


def as_of_phrase(traded_at: datetime, now: datetime, fresh_trade_minutes: float) -> str:
    """ "as of 2:41 PM Eastern" while the market trades, else "as of Friday's close", named from the last trade's own day."""
    if market_in_session(now) and now - traded_at < timedelta(minutes=fresh_trade_minutes):
        return f"as of {spoken_time(traded_at, NEW_YORK)} Eastern"
    return f"as of {spoken_trading_day(traded_at, now)}'s close"


def spoken_trading_day(traded_at: datetime, now: datetime) -> str:
    trading_day, today = traded_at.astimezone(NEW_YORK).date(), now.astimezone(NEW_YORK).date()
    if trading_day == today:
        return "today"
    if trading_day == today - timedelta(days=1):
        return "yesterday"
    return f"{trading_day:%A}"

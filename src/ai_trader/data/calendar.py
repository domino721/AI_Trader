from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

import exchange_calendars as xcals


@lru_cache(maxsize=128)
def calendar_for(start: date, end: date):
    return xcals.get_calendar(
        "XNYS", start=start - timedelta(days=10), end=end + timedelta(days=10)
    )


def sessions(start: date, end: date) -> tuple[date, ...]:
    if end < start or (end - start).days > 366:
        raise ValueError("date range must be ordered and no longer than 366 days")
    return tuple(day.date() for day in calendar_for(start, end).sessions_in_range(start, end))


@lru_cache(maxsize=512)
def session_close(day: date) -> datetime:
    return calendar_for(day, day).session_close(str(day)).to_pydatetime()


def default_range(now: datetime | None = None) -> tuple[date, date]:
    now = now or datetime.now(UTC)
    start, end = now.date() - timedelta(days=60), now.date()
    completed = [day for day in sessions(start, end) if session_close(day) <= now]
    return completed[-20], completed[-1]

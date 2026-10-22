"""Equity exchange sessions independent of observed price responses."""

from datetime import date

import exchange_calendars


def exchange_sessions_for(calendar_name: str, start: date, end: date) -> tuple[date, ...]:
    """Return inclusive US or KRX trading sessions, including exchange holidays."""
    calendar = exchange_calendars.get_calendar(calendar_name, start=start, end=end)
    return tuple(stamp.date() for stamp in calendar.sessions)

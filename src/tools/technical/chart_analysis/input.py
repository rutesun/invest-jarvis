"""Deterministic two-year input using only sessions returned by the provider."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from importlib.metadata import version
from typing import Protocol

import pandas as pd

from src.providers.exchange_calendar import exchange_sessions_for
from src.providers.price_history_range import (
    OHLCV,
    HistoryFinality,
    InputHistoryError,
    RangeCoverage,
    RawHistory,
    normalize_history,
)


class SessionCalendar(Protocol):
    """Versioned verified sessions; verified non-trading days may be excluded.

    Price-response absence alone must never remove a session from this calendar.
    """

    version: str
    timezone: str

    def sessions(self, start: date, end: date) -> tuple[date, ...]: ...


@dataclass(frozen=True)
class ExchangeSessionCalendar:
    name: str
    timezone: str
    version: str = field(
        default_factory=lambda: f"exchange_calendars:{version('exchange-calendars')}"
    )

    def sessions(self, start: date, end: date) -> tuple[date, ...]:
        if start > end:
            return ()
        # exchange_calendars rejects a singleton/holiday-only construction span.
        padded = exchange_sessions_for(
            self.name, start - timedelta(days=7), end + timedelta(days=7)
        )
        return tuple(day for day in padded if start <= day <= end)


def resolve_session(as_of: date, *, calendar: SessionCalendar) -> date:
    sessions = calendar.sessions(as_of - timedelta(days=370), as_of)
    if not sessions:
        raise InputHistoryError("no exchange session at or before as_of")
    return sessions[-1]


def resolve_input_start(
    session: date, *, calendar: SessionCalendar, listing_first_session: date | None
) -> date:
    resolved = resolve_session(session, calendar=calendar)
    calendar_start = (pd.Timestamp(resolved) - pd.DateOffset(years=2)).date()
    sessions = calendar.sessions(calendar_start, resolved)
    if not sessions:
        raise InputHistoryError("no exchange session in input range")
    start = sessions[0]
    if listing_first_session is not None:
        if listing_first_session > resolved:
            raise InputHistoryError("listing first session follows as_of")
        if calendar.sessions(listing_first_session, listing_first_session) != (
            listing_first_session,
        ):
            raise InputHistoryError("verified listing date must be an exchange session")
        start = max(start, listing_first_session)
    return start


@dataclass(frozen=True)
class PreparedHistory:
    frame: pd.DataFrame
    requested_as_of: date
    session: date
    input_start: date
    expected_sessions: tuple[date, ...]
    finality: dict[date, HistoryFinality]
    coverage: RangeCoverage
    final_frame: pd.DataFrame
    preview_frame: pd.DataFrame
    provider: str
    adjustment_policy: str
    revision_if_known: str | None
    calendar_version: str
    timezone: str
    listing_first_session: date | None
    input_origin_policy: str = "CHART_INPUT_RESPONSE_V2"


def prepare_history(
    raw: RawHistory,
    *,
    as_of: date,
    calendar: SessionCalendar,
    listing_first_session: date | None = None,
) -> PreparedHistory:
    raw_start, raw_end = raw.coverage.requested_start, raw.coverage.requested_end
    if raw_start > raw_end:
        raise InputHistoryError("raw declared range start must not follow end")
    available = sorted(
        {
            pd.Timestamp(stamp).date()
            for stamp in raw.frame.index
            if raw_start <= pd.Timestamp(stamp).date() <= min(as_of, raw_end)
        }
    )
    if not available:
        raise InputHistoryError("no returned daily bar at or before as_of")
    session = available[-1]
    start = (pd.Timestamp(session) - pd.DateOffset(years=2)).date()
    if listing_first_session is not None:
        if listing_first_session > session:
            raise InputHistoryError("listing first session follows as_of")
        start = max(start, listing_first_session)
    supplied_start, supplied_end = max(start, raw_start), min(session, raw_end)
    supplied = (
        normalize_history(raw.frame, start=supplied_start, end=supplied_end)
        if supplied_start <= supplied_end
        else normalize_history(raw.frame.iloc[:0], start=start, end=session)
    )
    # An absent date in the response is not evidence of a missing trading bar.
    # Validate returned rows, never synthesize rows from an exchange calendar.
    frame = supplied
    expected = tuple(frame.index.date)
    missing_sessions = tuple(stamp.date() for stamp, row in frame.iterrows() if row.isna().all())
    missing_fields = {
        stamp.date(): tuple(column for column in OHLCV if pd.isna(row[column]))
        for stamp, row in frame.iterrows()
        if row.isna().any()
    }
    finality = {
        day: (
            HistoryFinality(raw.finality.get(day, HistoryFinality.UNKNOWN))
            if raw_start <= day <= raw_end
            else HistoryFinality.UNKNOWN
        )
        for day in expected
    }
    provisional = tuple(day for day in expected if finality[day] == HistoryFinality.PROVISIONAL)
    unknown = tuple(day for day in expected if finality[day] == HistoryFinality.UNKNOWN)
    reasons = []
    # A union request may be truncated strictly before this date's own origin.
    # Only the current [A(T), T] prefix determines this prepared input's status.
    reached_start = raw_start <= start <= raw_end and (
        raw.coverage.reached_start or (len(supplied) > 0 and supplied.index[0].date() == start)
    )
    if not reached_start or missing_fields or any(day != session for day in provisional):
        reasons.append("INCOMPLETE_PREFIX")
    if unknown:
        reasons.append("UNKNOWN_FINALITY")
    if provisional:
        reasons.append(
            "PROVISIONAL_PREVIEW" if provisional == (session,) else "INTERMEDIATE_PROVISIONAL"
        )
    coverage = RangeCoverage(
        requested_start=start,
        requested_end=session,
        reached_start=reached_start,
        observed_start=supplied.index[0].date() if len(supplied) else None,
        observed_end=supplied.index[-1].date() if len(supplied) else None,
        expected_sessions=expected,
        missing_sessions=missing_sessions,
        missing_fields=missing_fields,
        provisional_sessions=provisional,
        unknown_finality_sessions=unknown,
        reasons=tuple(reasons),
    )
    final_count = 0
    for day in expected:
        if finality[day] != HistoryFinality.FINAL or day in missing_fields:
            break
        final_count += 1
    final_frame = frame.iloc[:final_count].copy()
    # Preview must directly follow an intact FINAL prefix, never cross a gap.
    preview = (
        frame.iloc[final_count : final_count + 1].copy()
        if (
            final_count == len(expected) - 1
            and provisional == (session,)
            and session not in missing_fields
        )
        else frame.iloc[:0].copy()
    )
    return PreparedHistory(
        frame=frame,
        requested_as_of=as_of,
        session=session,
        input_start=start,
        expected_sessions=expected,
        finality=finality,
        coverage=coverage,
        final_frame=final_frame,
        preview_frame=preview,
        provider=raw.provider,
        adjustment_policy=raw.adjustment_policy,
        revision_if_known=raw.revision_if_known,
        calendar_version="API_RESPONSE_SESSIONS_V1",
        timezone=calendar.timezone,
        listing_first_session=listing_first_session,
    )

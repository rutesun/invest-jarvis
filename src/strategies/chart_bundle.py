"""Convert price frames into canonical chart inputs and replay prefixes."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd

from src.strategies.models import BarFinality, ChartBar, ChartBundle, ChartSeries, CoverageManifest
from src.tools.disclosure import is_korean_ticker


_CLOSE_BUFFER = timedelta(minutes=15)


def _exchange_close_at(ticker: str, session: date) -> datetime:
    korean = is_korean_ticker(ticker) or ticker in {"^KS11", "^KQ11"}
    zone = ZoneInfo("Asia/Seoul" if korean else "America/New_York")
    close = time(15, 30) if korean else time(16, 0)
    return datetime.combine(session, close, tzinfo=zone)


def _finality(
    ticker: str, session: date, observed_at: datetime, session_close_at: datetime | None
) -> BarFinality:
    close_at = session_close_at or _exchange_close_at(ticker, session)
    if close_at.tzinfo is None or observed_at.tzinfo is None:
        raise ValueError("session close and observation timestamps must be timezone aware")
    return BarFinality.PROVISIONAL if observed_at < close_at + _CLOSE_BUFFER else BarFinality.FINAL


def chart_series_from_dataframe(
    frame: pd.DataFrame,
    coverage: CoverageManifest,
    *,
    as_of: date | None = None,
    finality: BarFinality = BarFinality.FINAL,
) -> ChartSeries:
    columns = {str(column).lower(): column for column in frame.columns}
    required = ("open", "high", "low", "close", "volume")
    missing = set(required) - columns.keys()
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    bars = []
    for index, row in frame.sort_index().iterrows():
        session = pd.Timestamp(index).date()
        bars.append(
            ChartBar(
                session_date=session,
                finality=finality if session == as_of else BarFinality.FINAL,
                **{name: Decimal(str(row[columns[name]])) for name in required},
            )
        )
    if len({bar.session_date for bar in bars}) != len(bars):
        raise ValueError("Duplicate price sessions")
    return ChartSeries(bars=tuple(bars), coverage=coverage)


def chart_bundle_from_dataframes(
    *,
    profile_version: str,
    ticker: str,
    as_of: date,
    instrument: pd.DataFrame,
    instrument_coverage: CoverageManifest,
    exchange_sessions: tuple[date, ...],
    market: pd.DataFrame | None = None,
    market_coverage: CoverageManifest | None = None,
    market_ticker: str | None = None,
    industry: pd.DataFrame | None = None,
    industry_coverage: CoverageManifest | None = None,
    session_close_at: datetime | None = None,
    observed_at: datetime | None = None,
) -> ChartBundle:
    if (market is None) != (market_coverage is None):
        raise ValueError("Market frame and coverage must be supplied together")
    if (industry is None) != (industry_coverage is None):
        raise ValueError("Industry frame and coverage must be supplied together")
    observed = observed_at or datetime.now(UTC)
    return ChartBundle(
        profile_version=profile_version,
        ticker=ticker,
        as_of=as_of,
        instrument=chart_series_from_dataframe(
            instrument,
            instrument_coverage,
            as_of=as_of,
            finality=_finality(ticker, as_of, observed, session_close_at),
        ),
        market=(
            chart_series_from_dataframe(
                market,
                market_coverage,
                as_of=as_of,
                finality=_finality(market_ticker or ticker, as_of, observed, None),
            )
            if market is not None
            else None
        ),
        market_ticker=market_ticker,
        industry=(
            chart_series_from_dataframe(
                industry,
                industry_coverage,
                as_of=as_of,
                finality=_finality(ticker, as_of, observed, None),
            )
            if industry is not None
            else None
        ),
        exchange_sessions=exchange_sessions,
    )


def _prefix_series(
    series: ChartSeries, origin: date | None, as_of: date, exchange_sessions: tuple[date, ...]
) -> ChartSeries:
    bars = tuple(
        bar
        for bar in series.bars
        if (origin is None or bar.session_date >= origin) and bar.session_date <= as_of
    )
    coverage = series.coverage
    start = origin if origin is not None else coverage.requested_start
    return ChartSeries(
        bars=bars,
        coverage=CoverageManifest(
            requested_start=start,
            effective_start=(
                coverage.effective_start
                if coverage.effective_start is not None
                and any(
                    coverage.requested_start <= day < coverage.effective_start
                    for day in exchange_sessions
                )
                else None
            ),
            actual_start=bars[0].session_date if bars else coverage.actual_start,
            actual_end=bars[-1].session_date if bars else coverage.actual_start,
            expected_sessions=tuple(
                day for day in coverage.expected_sessions if start <= day <= as_of
            ),
            no_trade_sessions=tuple(
                day for day in coverage.no_trade_sessions if start <= day <= as_of
            ),
            complete=coverage.complete and start >= coverage.requested_start,
            truncation_reason=coverage.truncation_reason,
            listing_first_session=(
                coverage.listing_first_session
                if bars and bars[0].session_date == coverage.listing_first_session
                else None
            ),
        ),
    )


def slice_and_rehash_bundle(
    bundle: ChartBundle, *, origin: date | None, as_of: date
) -> ChartBundle:
    if as_of > bundle.as_of or (origin is not None and origin > as_of):
        raise ValueError("Prefix bounds must be within the source bundle")
    exchange_sessions = tuple(
        day
        for day in bundle.exchange_sessions
        if (origin is None or day >= origin) and day <= as_of
    )
    return ChartBundle(
        profile_version=bundle.profile_version,
        ticker=bundle.ticker,
        as_of=as_of,
        instrument=_prefix_series(bundle.instrument, origin, as_of, exchange_sessions),
        market=(
            _prefix_series(bundle.market, origin, as_of, exchange_sessions)
            if bundle.market
            else None
        ),
        market_ticker=bundle.market_ticker,
        industry=(
            _prefix_series(bundle.industry, origin, as_of, exchange_sessions)
            if bundle.industry
            else None
        ),
        exchange_sessions=exchange_sessions,
    )

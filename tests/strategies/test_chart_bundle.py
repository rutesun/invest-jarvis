from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.strategies.chart_bundle import chart_bundle_from_dataframes
from src.strategies.models import ChartBundle, ChartSeries, CoverageManifest


DATES = (date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2))


def make_frame():
    return pd.DataFrame(
        {
            "Open": [10, 11, 12],
            "High": [12, 13, 14],
            "Low": [9, 10, 11],
            "Close": [11, 12, 13],
            "Volume": [100, 200, 300],
        },
        index=pd.DatetimeIndex(DATES),
    )


def make_manifest(
    *, complete=True, actual_start=DATES[0], requested_start=DATES[0], expected_sessions=DATES
):
    return CoverageManifest(
        requested_start=requested_start,
        actual_start=actual_start,
        actual_end=DATES[-1],
        expected_sessions=expected_sessions,
        no_trade_sessions=(),
        complete=complete,
        truncation_reason=None if complete else "provider_limit",
    )


def make_bundle(*, manifest=None, frame=None):
    return chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=DATES[-1],
        instrument=make_frame() if frame is None else frame,
        instrument_coverage=make_manifest() if manifest is None else manifest,
        exchange_sessions=DATES,
    )


def test_chart_bundle_rejects_unproven_coverage():
    manifest = make_manifest(complete=False, actual_start=DATES[1], requested_start=DATES[0])
    bundle = make_bundle(manifest=manifest, frame=make_frame().loc[pd.Timestamp(DATES[1]) :])
    assert bundle.has_complete_coverage(DATES[0], DATES[-1]) is False
    assert make_bundle().has_complete_coverage(DATES[0], DATES[-1]) is True


@pytest.mark.parametrize("effective_start", [date(2026, 9, 29), DATES[2]])
def test_effective_start_must_be_between_nominal_request_and_actual_start(effective_start):
    with pytest.raises(ValueError, match="effective_start"):
        CoverageManifest(
            requested_start=DATES[0],
            actual_start=DATES[1],
            actual_end=DATES[-1],
            effective_start=effective_start,
            expected_sessions=DATES[1:],
            complete=True,
        )


def test_effective_start_cannot_skip_two_calendar_sessions():
    manifest = CoverageManifest(
        requested_start=DATES[0],
        actual_start=DATES[2],
        actual_end=DATES[-1],
        effective_start=DATES[2],
        expected_sessions=DATES[2:],
        complete=True,
    )
    with pytest.raises(ValueError):
        make_bundle(manifest=manifest, frame=make_frame().iloc[2:])


@pytest.mark.parametrize("origin", [date(2024, 11, 27), date(2024, 11, 28), date(2024, 11, 29)])
def test_holiday_origin_boundary_prefix_matches_direct_bundle_without_future_data(origin):
    from src.providers.exchange_calendar import exchange_sessions_for

    nominal = date(2024, 11, 27)
    effective = date(2024, 11, 29)
    end = date(2024, 12, 3)
    as_of = date(2024, 12, 2)
    sessions = exchange_sessions_for("XNYS", nominal, end)
    assert sessions == (nominal, effective, as_of, end)
    frame = pd.DataFrame(
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 100.0},
        index=pd.DatetimeIndex(sessions[1:]),
    )
    coverage = CoverageManifest(
        requested_start=nominal,
        effective_start=effective,
        actual_start=effective,
        actual_end=end,
        expected_sessions=sessions[1:],
        complete=True,
    )
    options = {
        "profile_version": "chart-v1",
        "ticker": "NVDA",
        "market_ticker": "SPY",
        "observed_at": datetime(2025, 1, 1, tzinfo=UTC),
    }
    source = chart_bundle_from_dataframes(
        **options,
        as_of=end,
        instrument=frame,
        market=frame,
        instrument_coverage=coverage,
        market_coverage=coverage,
        exchange_sessions=sessions,
    )
    prefix = source.prefix(as_of, origin=origin)
    prefix_sessions = tuple(day for day in sessions if origin <= day <= as_of)
    prefix_coverage = CoverageManifest(
        requested_start=origin,
        effective_start=effective if origin == nominal else None,
        actual_start=effective,
        actual_end=as_of,
        expected_sessions=(effective, as_of),
        complete=True,
    )
    direct = chart_bundle_from_dataframes(
        **options,
        as_of=as_of,
        instrument=frame.iloc[:2],
        market=frame.iloc[:2],
        instrument_coverage=prefix_coverage,
        market_coverage=prefix_coverage,
        exchange_sessions=prefix_sessions,
    )
    assert prefix.instrument.coverage.complete is True
    assert prefix.market.coverage.complete is True
    assert prefix.model_dump(mode="json") == direct.model_dump(mode="json")
    assert prefix.bundle_hash == direct.bundle_hash
    assert prefix.exchange_sessions == prefix_sessions
    assert prefix.instrument.bars[-1].session_date == as_of
    changed = frame.copy()
    changed.loc[pd.Timestamp(end), :] = 999.0
    changed_source = chart_bundle_from_dataframes(
        **options,
        as_of=end,
        instrument=changed,
        market=changed,
        instrument_coverage=coverage,
        market_coverage=coverage,
        exchange_sessions=sessions,
    )
    assert changed_source.prefix(as_of, origin=origin).model_dump(mode="json") == direct.model_dump(
        mode="json"
    )


def test_current_open_session_is_provisional():
    from src.strategies.models import BarFinality

    bundle = chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=DATES[-1],
        instrument=make_frame(),
        instrument_coverage=make_manifest(),
        exchange_sessions=DATES,
        session_close_at=datetime(2026, 10, 2, 20, tzinfo=UTC),
        observed_at=datetime(2026, 10, 2, 20, 10, tzinfo=UTC),
    )

    assert [bar.finality for bar in bundle.instrument.bars] == [
        BarFinality.FINAL,
        BarFinality.FINAL,
        BarFinality.PROVISIONAL,
    ]


def test_closed_session_becomes_final_after_close_buffer():
    from src.strategies.models import BarFinality

    bundle = chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=DATES[-1],
        instrument=make_frame(),
        instrument_coverage=make_manifest(),
        exchange_sessions=DATES,
        session_close_at=datetime(2026, 10, 2, 20, tzinfo=UTC),
        observed_at=datetime(2026, 10, 2, 20, 16, tzinfo=UTC),
    )

    assert all(bar.finality is BarFinality.FINAL for bar in bundle.instrument.bars)


@pytest.mark.parametrize(
    ("ticker", "timezone", "close_hour", "close_minute"),
    [
        ("AAPL", "America/New_York", 16, 0),
        ("005930", "Asia/Seoul", 15, 30),
        ("005930.KS", "Asia/Seoul", 15, 30),
        ("035720.KQ", "Asia/Seoul", 15, 30),
        ("0167A0", "Asia/Seoul", 15, 30),
        ("0167a0", "Asia/Seoul", 15, 30),
        ("^KS11", "Asia/Seoul", 15, 30),
        ("^KQ11", "Asia/Seoul", 15, 30),
    ],
)
def test_current_session_uses_ticker_exchange_close_without_provider_metadata(
    ticker, timezone, close_hour, close_minute
):
    from src.strategies.models import BarFinality

    session_close = datetime(2026, 10, 2, close_hour, close_minute, tzinfo=ZoneInfo(timezone))
    options = {
        "profile_version": "chart-v1",
        "ticker": ticker,
        "as_of": DATES[-1],
        "instrument": make_frame(),
        "instrument_coverage": make_manifest(),
        "exchange_sessions": DATES,
    }
    open_bundle = chart_bundle_from_dataframes(
        **options, observed_at=session_close + pd.Timedelta(minutes=14)
    )
    closed_bundle = chart_bundle_from_dataframes(
        **options, observed_at=session_close + pd.Timedelta(minutes=15)
    )

    assert open_bundle.instrument.bars[-1].finality is BarFinality.PROVISIONAL
    assert closed_bundle.instrument.bars[-1].finality is BarFinality.FINAL
    assert open_bundle.bundle_hash != closed_bundle.bundle_hash


@pytest.mark.parametrize("minute", [44, 45])
def test_us_session_remains_provisional_at_korean_close_buffer(minute):
    from src.strategies.models import BarFinality

    bundle = chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=DATES[-1],
        instrument=make_frame(),
        instrument_coverage=make_manifest(),
        exchange_sessions=DATES,
        observed_at=datetime(2026, 10, 2, 15, minute, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    assert bundle.instrument.bars[-1].finality is BarFinality.PROVISIONAL


def test_dataframe_column_order_does_not_change_bundle_identity():
    original = make_bundle()
    reordered = make_bundle(frame=make_frame()[["Volume", "Close", "Low", "High", "Open"]])
    assert original.bundle_hash == reordered.bundle_hash
    changed = make_frame()
    changed.loc[pd.Timestamp(DATES[-1]), "Close"] = 14
    assert make_bundle(frame=changed).bundle_hash != original.bundle_hash


def test_prefix_excludes_future_bars_and_rehashes():
    bundle = make_bundle()
    prefix = bundle.prefix(DATES[1])
    assert prefix.as_of == DATES[1]
    assert tuple(bar.session_date for bar in prefix.instrument.bars) == DATES[:2]
    assert prefix.exchange_sessions == DATES[:2]
    assert prefix.bundle_hash != bundle.bundle_hash
    assert prefix.has_complete_coverage(DATES[0], DATES[1]) is True


def test_market_identity_changes_hash_and_survives_prefix():
    frame = make_frame()
    spy = chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=DATES[-1],
        instrument=frame,
        instrument_coverage=make_manifest(),
        exchange_sessions=DATES,
        market=frame,
        market_coverage=make_manifest(),
        market_ticker="SPY",
    )
    qqq = spy.model_copy(update={"market_ticker": "QQQ", "bundle_hash": ""})
    qqq = ChartBundle.model_validate(qqq.model_dump())
    assert spy.bundle_hash != qqq.bundle_hash
    assert spy.prefix(DATES[1]).market_ticker == "SPY"


def test_verified_listing_session_is_preserved_by_prefix():
    manifest = make_manifest(requested_start=date(2023, 10, 2)).model_copy(
        update={"listing_first_session": DATES[0]}
    )
    bundle = make_bundle(manifest=manifest)
    assert bundle.instrument.coverage.listing_first_session == DATES[0]
    assert bundle.prefix(DATES[1]).instrument.coverage.listing_first_session == DATES[0]
    assert (
        bundle.prefix(DATES[-1], origin=DATES[1]).instrument.coverage.listing_first_session is None
    )


def test_verified_listing_excludes_prelisting_sessions_from_expected_coverage():
    prior = date(2026, 9, 29)
    manifest = CoverageManifest(
        requested_start=prior,
        actual_start=DATES[0],
        actual_end=DATES[-1],
        expected_sessions=DATES,
        complete=True,
        listing_first_session=DATES[0],
    )
    bundle = chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=DATES[-1],
        instrument=make_frame(),
        instrument_coverage=manifest,
        exchange_sessions=(prior, *DATES),
    )
    assert bundle.instrument.coverage.listing_first_session == DATES[0]


def test_listing_session_must_match_actual_start():
    with pytest.raises(ValueError, match="listing_first_session"):
        CoverageManifest(
            requested_start=DATES[0],
            actual_start=DATES[0],
            actual_end=DATES[-1],
            expected_sessions=DATES,
            complete=True,
            listing_first_session=DATES[1],
        )


def test_complete_manifest_requires_each_expected_session_to_be_accounted_for():
    missing_session = make_frame().drop(pd.Timestamp(DATES[1]))
    with pytest.raises(ValueError, match="Unaccounted expected sessions"):
        make_bundle(frame=missing_session)


def test_prefix_origin_cannot_claim_coverage_before_source_request():
    bundle = make_bundle()
    earlier_origin = date(2026, 9, 29)
    prefix = bundle.prefix(DATES[1], origin=earlier_origin)
    assert prefix.has_complete_coverage(earlier_origin, DATES[1]) is False


def test_complete_instrument_manifest_matches_exchange_calendar():
    manifest = make_manifest(expected_sessions=DATES[:2])
    with pytest.raises(ValueError, match="exchange calendar"):
        make_bundle(manifest=manifest)


def test_chart_bundle_rejects_future_benchmark_bars():
    market = make_frame()
    future = date(2026, 10, 5)
    market.loc[pd.Timestamp(future)] = [13, 15, 12, 14, 400]
    market_coverage = CoverageManifest(
        requested_start=DATES[0],
        actual_start=DATES[0],
        actual_end=future,
        expected_sessions=(*DATES, future),
        complete=False,
    )
    with pytest.raises(ValueError, match="future"):
        chart_bundle_from_dataframes(
            profile_version="chart-v1",
            ticker="AAPL",
            as_of=DATES[-1],
            instrument=make_frame(),
            instrument_coverage=make_manifest(),
            exchange_sessions=DATES,
            market=market,
            market_coverage=market_coverage,
            market_ticker="SPY",
        )


@pytest.mark.parametrize(
    "sessions",
    [
        (DATES[1], DATES[0], DATES[2]),
        (DATES[0], DATES[1], DATES[1]),
    ],
)
def test_direct_coverage_rejects_unordered_or_duplicate_expected_sessions(sessions):
    with pytest.raises(ValueError, match="expected_sessions.*ascending"):
        make_manifest(complete=False, expected_sessions=sessions)


@pytest.mark.parametrize(
    "sessions",
    [
        (DATES[1], DATES[0]),
        (DATES[1], DATES[1]),
    ],
)
def test_direct_coverage_rejects_unordered_or_duplicate_no_trade_sessions(sessions):
    with pytest.raises(ValueError, match="no_trade_sessions.*ascending"):
        CoverageManifest(
            requested_start=DATES[0],
            actual_start=DATES[0],
            actual_end=DATES[-1],
            expected_sessions=DATES,
            no_trade_sessions=sessions,
            complete=False,
        )


@pytest.mark.parametrize("bar_indexes", [(1, 0, 2), (0, 1, 1)])
def test_direct_chart_series_rejects_unordered_or_duplicate_bars(bar_indexes):
    bars = make_bundle().instrument.bars
    with pytest.raises(ValueError, match="bars.*ascending"):
        ChartSeries(
            bars=tuple(bars[index] for index in bar_indexes),
            coverage=make_manifest(complete=False),
        )


@pytest.mark.parametrize(
    "sessions",
    [
        (DATES[1], DATES[0], DATES[2]),
        (DATES[0], DATES[1], DATES[1]),
    ],
)
def test_direct_bundle_rejects_unordered_or_duplicate_exchange_sessions(sessions):
    bundle = make_bundle()
    with pytest.raises(ValueError, match="exchange_sessions.*ascending"):
        ChartBundle(
            profile_version=bundle.profile_version,
            ticker=bundle.ticker,
            as_of=bundle.as_of,
            instrument=bundle.instrument,
            exchange_sessions=sessions,
        )


def test_direct_chart_series_rejects_observed_no_trade_overlap():
    bars = make_bundle().instrument.bars
    coverage = CoverageManifest(
        requested_start=DATES[0],
        actual_start=DATES[0],
        actual_end=DATES[-1],
        expected_sessions=DATES,
        no_trade_sessions=(DATES[1],),
        complete=False,
    )
    with pytest.raises(ValueError, match="observed.*no_trade"):
        ChartSeries(bars=bars, coverage=coverage)


def test_direct_coverage_rejects_no_trade_outside_expected():
    with pytest.raises(ValueError, match="no_trade.*expected"):
        CoverageManifest(
            requested_start=DATES[0],
            actual_start=DATES[0],
            actual_end=DATES[-1],
            expected_sessions=DATES[:2],
            no_trade_sessions=(DATES[-1],),
            complete=False,
        )


def test_direct_chart_series_rejects_observed_bars_outside_actual_bounds():
    bars = make_bundle().instrument.bars
    coverage = CoverageManifest(
        requested_start=DATES[0],
        actual_start=DATES[1],
        actual_end=DATES[-1],
        expected_sessions=DATES,
        no_trade_sessions=(),
        complete=False,
    )
    with pytest.raises(ValueError, match="observed.*actual coverage"):
        ChartSeries(bars=bars, coverage=coverage)


def test_direct_coverage_rejects_no_trade_outside_actual_bounds():
    with pytest.raises(ValueError, match="no_trade.*actual coverage"):
        CoverageManifest(
            requested_start=DATES[0],
            actual_start=DATES[1],
            actual_end=DATES[-1],
            expected_sessions=DATES,
            no_trade_sessions=(DATES[0],),
            complete=False,
        )

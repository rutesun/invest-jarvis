"""응답 일봉 규약: 없는 날짜를 만들지 않고 반환된 결측·finality를 보존한다."""

from datetime import date

import pandas as pd
import pytest

from src.providers.price_history_range import (
    HistoryFinality,
    InputHistoryError,
    RangeCoverage,
    RawHistory,
)
from src.tools.technical.chart_analysis.input import (
    ExchangeSessionCalendar,
    prepare_history,
    resolve_input_start,
)


@pytest.fixture
def calendar():
    return ExchangeSessionCalendar("XNYS", "America/New_York")


def raw_history(frame, *, finality=None):
    return RawHistory(
        frame=frame,
        provider="fixture",
        adjustment_policy="synthetic-adjusted",
        revision_if_known=None,
        finality=finality or {day.date(): HistoryFinality.FINAL for day in frame.index},
        coverage=RangeCoverage(
            requested_start=date(2022, 1, 3), requested_end=date(2024, 1, 5), reached_start=True
        ),
    )


def bars(days):
    return pd.DataFrame(
        {"Open": 10.0, "High": 12.0, "Low": 9.0, "Close": 11.0, "Volume": 100.0},
        index=pd.to_datetime(days),
    )


def test_single_and_range_resolve_same_origin(calendar):
    sessions = (date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5))
    assert [
        resolve_input_start(t, calendar=calendar, listing_first_session=None) for t in sessions
    ] == [date(2022, 1, 3), date(2022, 1, 4), date(2022, 1, 5)]
    # A range union must still resolve each T separately, never reuse A(S).
    assert resolve_input_start(sessions[-1], calendar=calendar, listing_first_session=None) == date(
        2022, 1, 5
    )


def test_leap_day_and_weekend_resolution(calendar):
    assert resolve_input_start(
        date(2024, 2, 29), calendar=calendar, listing_first_session=None
    ) == date(2022, 2, 28)
    prepared = prepare_history(
        raw_history(bars(["2024-01-05"])), as_of=date(2024, 1, 7), calendar=calendar
    )
    assert prepared.requested_as_of == date(2024, 1, 7)
    assert prepared.session == date(2024, 1, 5)
    assert prepared.input_start == date(2022, 1, 5)


def test_verified_listing_limits_origin(calendar):
    assert resolve_input_start(
        date(2024, 1, 5), calendar=calendar, listing_first_session=date(2023, 8, 1)
    ) == date(2023, 8, 1)


def test_short_response_is_not_assumed_to_be_a_listing(calendar):
    prepared = prepare_history(
        raw_history(bars(["2024-01-05"])), as_of=date(2024, 1, 5), calendar=calendar
    )
    assert prepared.input_start == date(2022, 1, 5)
    assert prepared.expected_sessions == (date(2024, 1, 5),)
    assert prepared.frame.index[0] == pd.Timestamp("2024-01-05")
    assert prepared.listing_first_session is None
    assert prepared.coverage.missing_sessions == ()


def test_absent_response_date_is_not_synthesized(calendar):
    source = raw_history(bars(["2024-01-03", "2024-01-05"]))
    prepared = prepare_history(
        source, as_of=date(2024, 1, 5), calendar=calendar, listing_first_session=date(2024, 1, 3)
    )
    assert prepared.expected_sessions == (date(2024, 1, 3), date(2024, 1, 5))
    assert len(prepared.frame) == 2
    assert pd.Timestamp("2024-01-04") not in prepared.frame.index
    assert prepared.coverage.missing_sessions == ()
    assert len(source.frame) == 2
    assert source.coverage.missing_sessions == ()


def test_duplicate_conflict_is_error(calendar):
    frame = bars(["2024-01-05", "2024-01-05"])
    frame.iloc[1, frame.columns.get_loc("Close")] = 10
    with pytest.raises(InputHistoryError, match="conflicting duplicate"):
        prepare_history(raw_history(frame), as_of=date(2024, 1, 5), calendar=calendar)


@pytest.mark.parametrize(
    "column,value", [("Close", 0), ("High", 8), ("Open", float("inf")), ("Volume", -1)]
)
def test_invalid_ohlcv_is_explicit_error(calendar, column, value):
    frame = bars(["2024-01-05"])
    frame.loc[:, column] = value
    with pytest.raises(InputHistoryError):
        prepare_history(raw_history(frame), as_of=date(2024, 1, 5), calendar=calendar)


def test_nan_field_and_all_nan_row_remain_missing(calendar):
    frame = bars(["2024-01-03", "2024-01-04", "2024-01-05"])
    frame.loc["2024-01-03", "Close"] = float("nan")
    frame.loc["2024-01-04"] = float("nan")
    prepared = prepare_history(
        raw_history(frame),
        as_of=date(2024, 1, 5),
        calendar=calendar,
        listing_first_session=date(2024, 1, 3),
    )
    assert prepared.coverage.missing_fields[date(2024, 1, 3)] == ("Close",)
    assert date(2024, 1, 4) in prepared.coverage.missing_sessions
    assert len(prepared.frame) == 3
    assert not prepared.coverage.complete


def test_final_provisional_preview_and_unknown_are_preserved(calendar):
    source = raw_history(
        bars(["2024-01-03", "2024-01-04", "2024-01-05"]),
        finality={
            date(2024, 1, 3): HistoryFinality.FINAL,
            date(2024, 1, 4): HistoryFinality.FINAL,
            date(2024, 1, 5): HistoryFinality.PROVISIONAL,
        },
    )
    prepared = prepare_history(
        source, as_of=date(2024, 1, 5), calendar=calendar, listing_first_session=date(2024, 1, 3)
    )
    assert len(prepared.final_frame) == 2
    assert prepared.preview_frame.index.tolist() == [pd.Timestamp("2024-01-05")]
    source.finality[date(2024, 1, 5)] = HistoryFinality.UNKNOWN
    unknown = prepare_history(
        source, as_of=date(2024, 1, 5), calendar=calendar, listing_first_session=date(2024, 1, 3)
    )
    assert unknown.finality[date(2024, 1, 5)] == HistoryFinality.UNKNOWN
    assert "UNKNOWN_FINALITY" in unknown.coverage.reasons
    assert len(unknown.final_frame) == 2


def test_intermediate_provisional_is_incomplete_prefix(calendar):
    source = raw_history(
        bars(["2024-01-03", "2024-01-04", "2024-01-05"]),
        finality={
            date(2024, 1, 3): HistoryFinality.FINAL,
            date(2024, 1, 4): HistoryFinality.PROVISIONAL,
            date(2024, 1, 5): HistoryFinality.FINAL,
        },
    )
    prepared = prepare_history(
        source, as_of=date(2024, 1, 5), calendar=calendar, listing_first_session=date(2024, 1, 3)
    )
    assert "INCOMPLETE_PREFIX" in prepared.coverage.reasons
    assert len(prepared.final_frame) == 1
    assert prepared.preview_frame.empty


def test_future_rows_do_not_change_prefix(calendar):
    frame = bars(["2024-01-03", "2024-01-04", "2024-01-05"])
    frame.loc["2024-01-05", "Volume"] = -1
    prepared = prepare_history(
        raw_history(frame),
        as_of=date(2024, 1, 4),
        calendar=calendar,
        listing_first_session=date(2024, 1, 3),
    )
    assert len(prepared.frame) == 2
    assert prepared.coverage.complete


def test_calendar_can_exclude_only_verified_non_trading_sessions(calendar):
    class VerifiedNoTradeCalendar:
        version = "verified-no-trade-fixture-v1"
        timezone = "America/New_York"

        def sessions(self, start, end):
            return tuple(day for day in calendar.sessions(start, end) if day != date(2024, 1, 4))

    source = raw_history(bars(["2024-01-03", "2024-01-05"]))
    before = source.frame.copy(deep=True)
    prepared = prepare_history(
        source,
        as_of=date(2024, 1, 5),
        calendar=VerifiedNoTradeCalendar(),
        listing_first_session=date(2024, 1, 3),
    )
    assert prepared.expected_sessions == (date(2024, 1, 3), date(2024, 1, 5))
    assert prepared.coverage.complete
    assert prepared.calendar_version == "API_RESPONSE_SESSIONS_V1"
    pd.testing.assert_frame_equal(source.frame, before)


def test_unknown_finality_is_never_promoted_by_execution_date(calendar):
    source = raw_history(bars(["2024-01-03"]), finality={date(2024, 1, 3): HistoryFinality.UNKNOWN})
    prepared = prepare_history(
        source, as_of=date(2024, 1, 3), calendar=calendar, listing_first_session=date(2024, 1, 3)
    )
    assert prepared.final_frame.empty
    assert prepared.preview_frame.empty
    assert prepared.finality == {date(2024, 1, 3): HistoryFinality.UNKNOWN}
    assert not prepared.coverage.complete


def test_truncation_before_current_origin_does_not_poison_valid_prefix(calendar):
    source = raw_history(bars(["2024-01-03", "2024-01-04", "2024-01-05"]))
    source = RawHistory(
        frame=source.frame,
        provider=source.provider,
        adjustment_policy=source.adjustment_policy,
        revision_if_known=None,
        finality=source.finality,
        coverage=RangeCoverage(
            requested_start=date(2022, 1, 3),
            requested_end=date(2024, 1, 5),
            reached_start=False,
            reasons=("INCOMPLETE_PREFIX",),
        ),
    )
    prepared = prepare_history(
        source, as_of=date(2024, 1, 5), calendar=calendar, listing_first_session=date(2024, 1, 3)
    )
    assert prepared.coverage.complete
    assert len(prepared.final_frame) == 3


@pytest.mark.parametrize(
    "declared_start,declared_end,expected_dates,complete",
    [
        (date(2024, 1, 3), date(2024, 1, 4), (date(2024, 1, 3), date(2024, 1, 4)), True),
        (date(2024, 1, 4), date(2024, 1, 5), (date(2024, 1, 4), date(2024, 1, 5)), False),
        (date(2024, 1, 1), date(2024, 1, 2), (), False),
    ],
)
def test_outside_declared_range_cannot_be_consumed_as_final(
    calendar,
    declared_start,
    declared_end,
    expected_dates,
    complete,
):
    from dataclasses import replace

    source = raw_history(bars(["2024-01-03", "2024-01-04", "2024-01-05"]))
    source = replace(
        source,
        coverage=RangeCoverage(
            requested_start=declared_start,
            requested_end=declared_end,
            reached_start=True,
        ),
    )
    original = source.frame.copy(deep=True)
    if not expected_dates:
        with pytest.raises(InputHistoryError, match="no returned daily bar"):
            prepare_history(source, as_of=date(2024, 1, 5), calendar=calendar)
    else:
        prepared = prepare_history(
            source,
            as_of=date(2024, 1, 5),
            calendar=calendar,
            listing_first_session=date(2024, 1, 3),
        )
        assert prepared.coverage.complete is complete
        assert tuple(prepared.frame.index.date) == expected_dates
        assert prepared.session == expected_dates[-1]
        assert set(prepared.finality) == set(expected_dates)
    pd.testing.assert_frame_equal(source.frame, original)


def test_reversed_raw_declared_range_is_explicit_error(calendar):
    from dataclasses import replace

    source = raw_history(bars(["2024-01-03", "2024-01-04", "2024-01-05"]))
    source = replace(
        source,
        coverage=RangeCoverage(
            requested_start=date(2024, 1, 5),
            requested_end=date(2024, 1, 3),
            reached_start=True,
        ),
    )
    with pytest.raises(InputHistoryError, match="raw declared range"):
        prepare_history(
            source,
            as_of=date(2024, 1, 5),
            calendar=calendar,
            listing_first_session=date(2024, 1, 3),
        )

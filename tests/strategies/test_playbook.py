"""Chart-only Playbook strategy boundary."""

import inspect

import pandas as pd

from src.strategies.chart_bundle import chart_bundle_from_dataframes
from src.strategies.models import CoverageManifest, EntryIntent, ExitIntent
from src.strategies.playbook import PlaybookStrategy
from src.tools.technical.scorecard_models import DataStatus


def _bundle(
    count: int = 260,
    *,
    market: bool = True,
    stale_market: bool = False,
    common_sessions: int | None = None,
):
    index = pd.bdate_range("2025-01-01", periods=count)
    close = [100 + day * 0.5 for day in range(count)]
    frame = pd.DataFrame(
        {
            "Open": [value - 0.5 for value in close],
            "High": [value + 1 for value in close],
            "Low": [value - 1 for value in close],
            "Close": close,
            "Volume": [1_000_000 + day * 100 for day in range(count)],
        },
        index=index,
    )
    sessions = tuple(day.date() for day in index)
    coverage = CoverageManifest(
        requested_start=sessions[0],
        actual_start=sessions[0],
        actual_end=sessions[-1],
        expected_sessions=sessions,
        complete=True,
    )
    market_frame = frame.iloc[:-1].copy() if stale_market else frame.copy()
    if common_sessions is not None:
        earlier = pd.bdate_range("2023-01-02", periods=count - common_sessions)
        market_frame.index = earlier.append(index[-common_sessions:])
    market_sessions = tuple(day.date() for day in market_frame.index)
    market_coverage = CoverageManifest(
        requested_start=market_sessions[0],
        actual_start=market_sessions[0],
        actual_end=market_sessions[-1],
        expected_sessions=market_sessions,
        complete=True,
    )
    return chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=sessions[-1],
        instrument=frame,
        instrument_coverage=coverage,
        exchange_sessions=sessions,
        market=market_frame if market else None,
        market_coverage=market_coverage if market else None,
        market_ticker="^GSPC" if market else None,
    )


def test_playbook_strategy_has_no_position_inputs():
    assert tuple(inspect.signature(PlaybookStrategy.evaluate).parameters) == ("self", "bundle")


def test_playbook_evaluates_entry_and_exit_on_same_chart():
    verdict = PlaybookStrategy().evaluate(_bundle())
    assert verdict.strategy_id == "PLAYBOOK_V1"
    assert verdict.entry.data_status is DataStatus.COMPLETE
    assert verdict.exit.data_status is DataStatus.COMPLETE
    assert verdict.entry.intent in {EntryIntent.ALLOW, EntryIntent.BLOCK}
    assert verdict.exit.intent in {ExitIntent.HOLD, ExitIntent.REDUCE, ExitIntent.EXIT}
    assert verdict == PlaybookStrategy().evaluate(_bundle())


def test_missing_market_series_does_not_turn_gate_failure_into_block():
    verdict = PlaybookStrategy().evaluate(_bundle(market=False))
    assert verdict.entry.intent is EntryIntent.NOT_EVALUATED
    assert verdict.entry.data_status is DataStatus.INSUFFICIENT_DATA
    assert verdict.exit.data_status is DataStatus.PARTIAL


def test_unavailable_21_session_long_average_slope_is_insufficient_data():
    verdict = PlaybookStrategy().evaluate(_bundle(count=200))
    assert verdict.entry.intent is EntryIntent.NOT_EVALUATED
    assert verdict.exit.intent is ExitIntent.NOT_EVALUATED
    assert verdict.entry.data_status is DataStatus.INSUFFICIENT_DATA


def test_stale_market_chart_does_not_authorize_current_entry_gate():
    verdict = PlaybookStrategy().evaluate(_bundle(stale_market=True))
    assert verdict.entry.intent is EntryIntent.NOT_EVALUATED
    assert verdict.entry.data_status is DataStatus.INSUFFICIENT_DATA


def test_insufficient_common_sessions_make_rs_unavailable():
    verdict = PlaybookStrategy().evaluate(_bundle(common_sessions=20))
    assert verdict.entry.intent is EntryIntent.NOT_EVALUATED
    assert verdict.entry.data_status is DataStatus.INSUFFICIENT_DATA
    assert verdict.exit.data_status is DataStatus.PARTIAL
    assert any(reason.code == "insufficient_rs_chart" for reason in verdict.entry.reasons)


def test_complete_rs_slope_window_is_evaluable():
    verdict = PlaybookStrategy().evaluate(_bundle(common_sessions=21))
    assert verdict.entry.data_status is DataStatus.COMPLETE

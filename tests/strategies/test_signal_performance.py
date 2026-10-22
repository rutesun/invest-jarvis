"""Independent close-estimate and next-tradable-open performance contracts."""

from datetime import date
from decimal import Decimal

import pytest

from src.strategies.models import (
    BarFinality,
    ChartBar,
    ChartBundle,
    ChartSeries,
    CoverageManifest,
    ReferenceEntryBasis,
    SignalFinality,
    StrategySignal,
)
from src.strategies.signal_performance import evaluate_signal_performance
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance


@pytest.fixture
def signal():
    return StrategySignal(
        signal_id="signal-6",
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version="params-v2",
        parameter_fingerprint="fingerprint-6",
        code="TREND_BREAKOUT_ENTRY",
        occurred_on=date(2026, 10, 6),
        finality=SignalFinality.FINAL,
        direction=None,
        signal_price=Decimal("100"),
        evidence=[
            Evidence(
                code="entry",
                message="entry",
                observed_value=None,
                reference_value=None,
                importance=Importance.HIGH,
                source="SWING_W150_V2",
            )
        ],
        data_status=DataStatus.COMPLETE,
    )


def chart(rows, *, sessions=None, no_trade=(), complete=True, truncation_reason=None):
    bars = tuple(
        ChartBar(
            session_date=day,
            open=Decimal(open_),
            high=Decimal("200"),
            low=Decimal("50"),
            close=Decimal(close),
            volume=Decimal("1000"),
            finality=finality,
        )
        for day, open_, close, finality in rows
    )
    sessions = sessions or tuple(bar.session_date for bar in bars)
    return ChartBundle(
        profile_version="CHART_PROFILE_V1",
        ticker="AAPL",
        as_of=bars[-1].session_date,
        instrument=ChartSeries(
            bars=bars,
            coverage=CoverageManifest(
                requested_start=bars[0].session_date,
                actual_start=bars[0].session_date,
                actual_end=bars[-1].session_date,
                expected_sessions=sessions,
                no_trade_sessions=no_trade,
                complete=complete,
                truncation_reason=truncation_reason,
            ),
        ),
        exchange_sessions=sessions,
    )


def test_signal_day_has_estimate_but_no_executed_return(signal):
    result = evaluate_signal_performance(
        signal, chart([(date(2026, 10, 6), "99", "100", BarFinality.FINAL)])
    )
    assert result.estimated_return_from_signal_close == Decimal("0")
    assert result.executed_return_from_next_tradable_open is None
    assert result.estimated_data_status is DataStatus.COMPLETE
    assert result.executed_data_status is DataStatus.NOT_EVALUATED
    assert result.executed_status_reason == "NEXT_TRADABLE_BAR_UNAVAILABLE"
    assert result.estimated_price_basis is ReferenceEntryBasis.SIGNAL_CLOSE_ESTIMATE
    assert result.executed_price_basis is ReferenceEntryBasis.NEXT_OPEN_ACTUAL
    assert result.signal_price == Decimal("100")
    assert result.execution_reference_price is None
    assert result.signal_id == "signal-6"
    assert result.strategy_version == "SWING_W150_V2"
    assert result.parameter_set_version == "params-v2"
    assert result.parameter_fingerprint == "fingerprint-6"


def test_estimate_and_execution_remain_separate_ratios_after_next_open(signal):
    result = evaluate_signal_performance(
        signal,
        chart(
            [
                (date(2026, 10, 6), "99", "100", BarFinality.FINAL),
                (date(2026, 10, 7), "110", "121", BarFinality.FINAL),
            ]
        ),
    )
    # 121 / 100 - 1 = 0.21; 121 / 110 - 1 = 0.10 (ratios, not percent).
    assert result.estimated_return_from_signal_close == Decimal("0.21")
    assert result.executed_return_from_next_tradable_open == Decimal("0.1")
    assert result.evaluation_price == Decimal("121")
    assert result.execution_reference_price == Decimal("110")
    assert result.execution_as_of == date(2026, 10, 7)
    assert result.execution_delay_sessions == 0
    assert result.executed_data_status is DataStatus.COMPLETE


def test_two_suspended_exchange_sessions_delay_execution_by_two(signal):
    sessions = tuple(date(2026, 10, day) for day in (6, 7, 8, 9))
    result = evaluate_signal_performance(
        signal,
        chart(
            [
                (sessions[0], "99", "100", BarFinality.FINAL),
                (sessions[3], "110", "121", BarFinality.FINAL),
            ],
            sessions=sessions,
            no_trade=(sessions[1], sessions[2]),
        ),
    )
    assert result.execution_delay_sessions == 2
    assert result.execution_as_of == date(2026, 10, 9)
    assert result.execution_reference_price == Decimal("110")
    assert result.executed_return_from_next_tradable_open == Decimal("0.1")


@pytest.mark.parametrize("no_trade", [(), (date(2026, 10, 7),)])
def test_unaccounted_execution_sessions_preserve_estimate_but_reject_execution(signal, no_trade):
    sessions = tuple(date(2026, 10, day) for day in (6, 7, 8, 9))
    result = evaluate_signal_performance(
        signal,
        chart(
            [
                (sessions[0], "99", "100", BarFinality.FINAL),
                (sessions[3], "110", "121", BarFinality.FINAL),
            ],
            sessions=sessions,
            no_trade=no_trade,
            complete=False,
            truncation_reason="provider_session_gap",
        ),
    )
    assert result.evaluation_as_of == date(2026, 10, 9)
    assert result.evaluation_price == Decimal("121")
    assert result.estimated_return_from_signal_close == Decimal("0.21")
    assert result.estimated_data_status is DataStatus.COMPLETE
    assert result.executed_return_from_next_tradable_open is None
    assert result.executed_data_status is DataStatus.NOT_EVALUATED
    assert result.executed_status_reason == "UNACCOUNTED_EXECUTION_SESSIONS"
    assert result.execution_reference_price is None
    assert result.execution_as_of is None
    assert result.execution_delay_sessions is None


def test_non_trading_evaluation_uses_previous_final_session(signal):
    result = evaluate_signal_performance(
        signal,
        chart(
            [
                (date(2026, 10, 6), "99", "100", BarFinality.FINAL),
                (date(2026, 10, 9), "110", "121", BarFinality.FINAL),
            ]
        ),
        requested_as_of=date(2026, 10, 11),
    )
    assert result.requested_as_of == date(2026, 10, 11)
    assert result.evaluation_as_of == date(2026, 10, 9)
    assert result.evaluation_price == Decimal("121")


def test_historical_evaluation_never_uses_future_execution_bar(signal):
    result = evaluate_signal_performance(
        signal,
        chart(
            [
                (date(2026, 10, 6), "99", "100", BarFinality.FINAL),
                (date(2026, 10, 7), "110", "121", BarFinality.FINAL),
            ]
        ),
        requested_as_of=date(2026, 10, 6),
    )
    assert result.estimated_return_from_signal_close == Decimal("0")
    assert result.executed_return_from_next_tradable_open is None
    assert result.execution_reference_price is None


def test_provisional_latest_bar_supplies_partial_estimate_and_executed_returns(signal):
    result = evaluate_signal_performance(
        signal,
        chart(
            [
                (date(2026, 10, 6), "99", "100", BarFinality.FINAL),
                (date(2026, 10, 7), "110", "121", BarFinality.PROVISIONAL),
            ]
        ),
    )
    assert result.evaluation_as_of == date(2026, 10, 7)
    assert result.evaluation_price == Decimal("121")
    assert result.estimated_return_from_signal_close == Decimal("0.21")
    assert result.executed_return_from_next_tradable_open == Decimal("0.1")
    assert result.execution_reference_price == Decimal("110")
    assert result.estimated_data_status is DataStatus.PARTIAL
    assert result.executed_data_status is DataStatus.PARTIAL
    assert result.estimated_status_reason == "PROVISIONAL_EVALUATION_CLOSE"
    assert result.executed_status_reason == "PROVISIONAL_EVALUATION_CLOSE"


def test_provisional_signal_day_has_partial_zero_estimate_without_execution(signal):
    result = evaluate_signal_performance(
        signal.model_copy(update={"finality": SignalFinality.PROVISIONAL}),
        chart([(date(2026, 10, 6), "99", "100", BarFinality.PROVISIONAL)]),
    )
    assert result.evaluation_as_of == date(2026, 10, 6)
    assert result.estimated_return_from_signal_close == Decimal("0")
    assert result.estimated_data_status is DataStatus.PARTIAL
    assert result.estimated_status_reason == "PROVISIONAL_EVALUATION_CLOSE"
    assert result.estimated_price_basis is ReferenceEntryBasis.SIGNAL_CLOSE_ESTIMATE
    assert result.executed_return_from_next_tradable_open is None
    assert result.executed_data_status is DataStatus.NOT_EVALUATED
    assert result.executed_status_reason == "NEXT_TRADABLE_BAR_UNAVAILABLE"


@pytest.mark.parametrize(
    "update,reason",
    [
        ({"finality": SignalFinality.PROVISIONAL}, "SIGNAL_BAR_FINALITY_MISMATCH"),
        ({"code": "SMA150_EXIT"}, "NOT_ENTRY_SIGNAL"),
        ({"signal_price": Decimal("0")}, "INVALID_SIGNAL_PRICE"),
        ({"occurred_on": date(2026, 10, 5)}, "SIGNAL_BAR_UNAVAILABLE"),
    ],
)
def test_ineligible_signal_is_explicitly_not_evaluated(signal, update, reason):
    result = evaluate_signal_performance(
        signal.model_copy(update=update),
        chart([(date(2026, 10, 6), "99", "100", BarFinality.FINAL)]),
    )
    assert result.estimated_return_from_signal_close is None
    assert result.executed_return_from_next_tradable_open is None
    assert result.estimated_data_status is DataStatus.NOT_EVALUATED
    assert result.executed_data_status is DataStatus.NOT_EVALUATED
    assert result.estimated_status_reason == reason


def test_final_signal_with_provisional_source_bar_is_finality_mismatch(signal):
    result = evaluate_signal_performance(
        signal, chart([(date(2026, 10, 6), "99", "100", BarFinality.PROVISIONAL)])
    )
    assert result.estimated_return_from_signal_close is None
    assert result.executed_return_from_next_tradable_open is None
    assert result.estimated_data_status is DataStatus.NOT_EVALUATED
    assert result.executed_data_status is DataStatus.NOT_EVALUATED
    assert result.estimated_status_reason == "SIGNAL_BAR_FINALITY_MISMATCH"


def test_no_available_evaluation_session_is_explicit(signal):
    result = evaluate_signal_performance(
        signal,
        chart([(date(2026, 10, 6), "99", "100", BarFinality.FINAL)]),
        requested_as_of=date(2026, 10, 5),
    )
    assert result.evaluation_as_of is None
    assert result.estimated_data_status is DataStatus.NOT_EVALUATED
    assert result.estimated_status_reason == "EVALUATION_BAR_UNAVAILABLE"


def test_new_status_serializes_without_changing_existing_status_values():
    assert DataStatus.NOT_EVALUATED.value == "not_evaluated"
    assert [
        DataStatus(value).value for value in ("complete", "partial", "insufficient_data", "error")
    ] == ["complete", "partial", "insufficient_data", "error"]

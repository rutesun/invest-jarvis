"""Independent execution contracts for chart-only SWING_W150 V2 signals."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from src.strategies.models import SignalFinality, StrategySignal
from src.strategies.swing_w150.features import build_swing_features
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.strategies.swing_w150.signals import detect_swing
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance


@pytest.fixture
def api():
    # Keep V1 tests runnable even while the new adapter is absent during RED.
    from src.backtest.swing_w150 import (
        SwingExecutionPolicy,
        SwingRiskPolicy,
        simulate_swing_v2,
    )

    return SwingExecutionPolicy, SwingRiskPolicy, simulate_swing_v2


@pytest.fixture
def bars():
    index = pd.bdate_range("2024-01-01", periods=254)
    frame = pd.DataFrame(
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 100.0},
        index=index,
    )
    frame.loc[index[250:], ["Open", "High", "Low", "Close"]] = [110, 111, 109, 110]
    return frame


def signal(bars, bar, code="TREND_BREAKOUT_ENTRY", *, provisional=False, support=100):
    params = SwingW150Parameters()
    day = bars.index[bar].date()
    return StrategySignal(
        signal_id=f"TEST:{day}:{code}",
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version=params.parameter_set_version,
        parameter_fingerprint=params.parameter_fingerprint,
        code=code,
        occurred_on=day,
        finality=SignalFinality.PROVISIONAL if provisional else SignalFinality.FINAL,
        direction=None,
        signal_price=Decimal(str(bars.iloc[bar].Close)),
        evidence=[
            Evidence(
                code="SMA_50",
                message="support observed at signal close",
                observed_value=float(bars.iloc[bar].Close),
                reference_value=support,
                importance=Importance.HIGH,
                source="SWING_W150_V2",
            )
        ],
        data_status=DataStatus.COMPLETE,
    )


def run(api, bars, signals, *, risk_target=50, max_loss_pct=0.15, fee=0, slippage=0, **period):
    execution, risk, simulate = api
    return simulate(
        bars,
        SwingW150Parameters(),
        execution(fee_rate=fee, slippage_rate=slippage),
        risk_policy=risk(risk_target=risk_target, max_loss_pct=max_loss_pct),
        warmup_start=period.get("warmup_start", bars.index[0].date()),
        test_start=period.get("test_start", bars.index[249].date()),
        test_end=period.get("test_end", bars.index[-1].date()),
        ticker="TEST",
        expected_sessions=period.get(
            "expected_sessions", tuple(pd.bdate_range(bars.index[0], bars.index[-1]).date)
        ),
        no_trade_sessions=period.get("no_trade_sessions", ()),
        signal_history=signals,
    )


def test_warmup_signal_is_never_executed(api, bars):
    result = run(api, bars, [signal(bars, 248)])
    assert result.orders == ()
    assert result.open_lots == ()


def test_warmup_provisional_signal_is_rejected(api, bars):
    with pytest.raises(ValueError, match="FINAL"):
        run(api, bars, [signal(bars, 248, "OVERHEAT", provisional=True)])


@pytest.mark.parametrize(
    "identity_field",
    ["strategy_id", "strategy_version", "parameter_set_version", "parameter_fingerprint"],
)
def test_warmup_signal_identity_mismatch_is_rejected(api, bars, identity_field):
    changed = signal(bars, 248).model_copy(update={identity_field: "wrong"})
    with pytest.raises(ValueError, match="identity"):
        run(api, bars, [changed])


def test_warmup_signal_without_actual_instrument_bar_is_rejected(api, bars):
    missing = bars.drop(bars.index[248])
    with pytest.raises(ValueError, match="actual instrument bar"):
        run(
            api,
            missing,
            [signal(bars, 248)],
            test_start=bars.index[249].date(),
            no_trade_sessions=(bars.index[248].date(),),
        )


def test_test_end_signal_cannot_fill_on_future_bar(api, bars):
    result = run(api, bars, [signal(bars, 250)], test_end=bars.index[250].date())
    assert result.orders == ()
    assert result.identity.test_end == bars.index[250].date()


def test_future_bars_and_signals_do_not_affect_result(api, bars):
    end = bars.index[251].date()
    original = run(api, bars, [signal(bars, 249)], test_end=end)
    changed = bars.copy()
    changed.loc[changed.index[252:], :] = float("nan")
    future = signal(bars, 253, provisional=True)
    actual = run(api, changed, [signal(bars, 249), future], test_end=end)
    assert actual == original


def test_out_of_period_duplicate_bar_is_not_validated_or_executed(api, bars):
    end = bars.index[251].date()
    original = run(api, bars, [signal(bars, 249)], test_end=end)
    duplicated_future = pd.concat([bars, bars.iloc[[-1]]])
    assert run(api, duplicated_future, [signal(bars, 249)], test_end=end) == original


def test_provisional_signal_is_rejected_even_if_not_an_order(api, bars):
    with pytest.raises(ValueError, match="FINAL"):
        run(api, bars, [signal(bars, 249, "OVERHEAT", provisional=True)])


def test_next_actual_instrument_bar_open_skips_missing_sessions(api, bars):
    sparse = bars.drop(bars.index[250:253])
    sparse.loc[sparse.index[-1], ["Open", "High", "Low", "Close"]] = [120, 121, 119, 120]
    result = run(
        api,
        sparse,
        [signal(bars, 249)],
        test_start=bars.index[249].date(),
        no_trade_sessions=tuple(bars.index[250:253].date),
    )
    order = result.orders[0]
    assert (order.date, order.price, order.quantity) == (bars.index[253].date(), 120, 2)


@pytest.mark.parametrize("missing_bar", [248, 250, 251])
def test_unexplained_warmup_execution_or_holding_gap_is_rejected(api, bars, missing_bar):
    sparse = bars.drop(bars.index[missing_bar])
    with pytest.raises(ValueError, match="Unaccounted exchange sessions"):
        run(api, sparse, [signal(bars, 249)], test_start=bars.index[249].date())


def test_observed_bar_cannot_be_declared_no_trade(api, bars):
    with pytest.raises(ValueError, match="disjoint"):
        run(api, bars, [], no_trade_sessions=(bars.index[250].date(),))


def test_no_trade_declaration_must_belong_to_exchange_calendar(api, bars):
    with pytest.raises(ValueError, match="subset"):
        run(api, bars, [], no_trade_sessions=(date(2024, 1, 6),))


@pytest.mark.parametrize("missing_bar", [0, 253])
def test_expected_calendar_detects_leading_and_trailing_provider_gaps(api, bars, missing_bar):
    with pytest.raises(ValueError, match="Unaccounted exchange sessions"):
        run(
            api,
            bars.drop(bars.index[missing_bar]),
            [],
            expected_sessions=tuple(pd.bdate_range(bars.index[0], bars.index[-1]).date),
            warmup_start=bars.index[0].date(),
            test_end=bars.index[-1].date(),
            test_start=bars.index[249].date(),
        )


def test_future_calendar_and_no_trade_suffix_do_not_change_result_identity(api, bars):
    end = bars.index[251].date()
    prefix_sessions = tuple(pd.bdate_range(bars.index[0], bars.index[251]).date)
    original = run(api, bars, [signal(bars, 249)], test_end=end, expected_sessions=prefix_sessions)
    with_future = run(
        api,
        bars,
        [signal(bars, 249)],
        test_end=end,
        expected_sessions=prefix_sessions + (bars.index[253].date(), bars.index[252].date()),
        no_trade_sessions=(bars.index[253].date(), bars.index[253].date()),
    )
    assert with_future == original
    assert with_future.identity.expected_sessions == prefix_sessions
    assert with_future.identity.no_trade_sessions == ()


def test_coverage_declarations_are_bound_to_result_identity(api, bars):
    result = run(api, bars, [])
    assert (
        result.identity.identity_hash
        != replace(result.identity, no_trade_sessions=(date(2024, 1, 2),)).identity_hash
    )
    assert (
        result.identity.identity_hash
        != replace(
            result.identity, expected_sessions=result.identity.expected_sessions[1:]
        ).identity_hash
    )


@pytest.mark.parametrize("gap,price,reason", [(True, 90, "gap_stop"), (False, 100, "stop")])
def test_stop_precedes_same_day_close_exit_signal(api, bars, gap, price, reason):
    bars.loc[bars.index[251], ["Open", "High", "Low", "Close"]] = [90 if gap else 110, 111, 89, 105]
    result = run(api, bars, [signal(bars, 249), signal(bars, 251, "SMA150_EXIT")])
    assert [(o.reason, o.price) for o in result.orders] == [
        ("TREND_BREAKOUT_ENTRY", 110),
        (reason, price),
    ]
    assert result.open_lots == ()


def test_gap_stop_precedes_pending_correction_at_same_open(api, bars):
    bars.loc[bars.index[251], ["Open", "High", "Low", "Close"]] = [90, 91, 89, 90]
    result = run(api, bars, [signal(bars, 249), signal(bars, 250, "OVERHEAT_CORRECTION")])
    assert [(o.reason, o.quantity) for o in result.orders] == [
        ("TREND_BREAKOUT_ENTRY", 5),
        ("gap_stop", 5),
    ]


def test_entry_day_intraday_stop_is_executed(api, bars):
    bars.loc[bars.index[250], "Low"] = 95
    result = run(api, bars, [signal(bars, 249)])
    assert [(o.reason, o.price) for o in result.orders] == [
        ("TREND_BREAKOUT_ENTRY", 110),
        ("stop", 100),
    ]


def test_same_day_exit_suppresses_correction_and_entry(api, bars):
    result = run(
        api,
        bars,
        [
            signal(bars, 249),
            signal(bars, 250, "DEEP_RECOVERY_ENTRY"),
            signal(bars, 250, "OVERHEAT_CORRECTION"),
            signal(bars, 250, "SMA150_EXIT"),
        ],
    )
    assert [o.reason for o in result.orders] == ["TREND_BREAKOUT_ENTRY", "SMA150_EXIT"]
    assert len(result.signal_history) == 4


def test_same_day_entry_priority_uses_pullback_before_trend_and_deep(api, bars):
    result = run(
        api,
        bars,
        [
            signal(bars, 249, "DEEP_RECOVERY_ENTRY"),
            signal(bars, 249),
            signal(bars, 249, "PULLBACK_REVERSAL_ENTRY"),
        ],
    )
    assert [o.reason for o in result.orders] == ["PULLBACK_REVERSAL_ENTRY"]


def test_overheat_correction_sells_half_rounding_up(api, bars):
    result = run(api, bars, [signal(bars, 249), signal(bars, 250, "OVERHEAT_CORRECTION")])
    assert result.orders[-1].quantity == 3
    assert result.open_lots[0].quantity == 2


def test_partial_exit_keeps_lot_entry_basis_and_initial_risk(api, bars):
    bars.loc[bars.index[251:], ["Open", "High", "Low", "Close"]] = [120, 121, 119, 120]
    result = run(api, bars, [signal(bars, 249), signal(bars, 250, "OVERHEAT_CORRECTION")])
    lot = result.open_lots[0]
    assert (lot.entry_price, lot.stop, lot.initial_risk_per_share) == (110, 100, 10)
    assert (lot.initial_quantity, lot.quantity, lot.initial_risk_capital) == (2, 2, 20)
    assert lot.realized_pnl == 0
    assert result.closed_lots[0].initial_risk_capital == 30
    assert result.closed_lots[0].realized_pnl == 30


def test_partial_realized_r_excludes_unrealized_remaining_risk(api, bars):
    bars.loc[bars.index[251:], ["Open", "High", "Low", "Close"]] = [120, 121, 119, 120]
    result = run(api, bars, [signal(bars, 249), signal(bars, 250, "OVERHEAT_CORRECTION")])
    # Three realized shares earned 30 against 3*10 original risk; two remain open.
    assert result.aggregate_r == 1
    assert result.closed_lots[0].initial_quantity == 3
    assert result.open_lots[0].initial_quantity == 2


def test_recovery_adds_separate_lot_only_to_remaining_risk_target(api, bars):
    bars.loc[bars.index[251:], ["Open", "High", "Low", "Close"]] = [120, 121, 119, 120]
    result = run(
        api,
        bars,
        [
            signal(bars, 249),
            signal(bars, 250, "OVERHEAT_CORRECTION"),
            signal(bars, 251, "POST_OVERHEAT_RECOVERY_ENTRY"),
        ],
        max_loss_pct=0.1,
    )
    assert [
        (lot.entry_price, lot.quantity, lot.initial_risk_per_share) for lot in result.open_lots
    ] == [(110, 2, 10), (120, 2, 12)]
    assert [lot.initial_risk_capital for lot in result.open_lots] == [20, 24]


def test_aggregate_r_uses_realized_pnl_over_original_lot_risk_capital(api, bars):
    bars.loc[bars.index[251:253], ["Open", "High", "Low", "Close"]] = [120, 121, 119, 120]
    bars.loc[bars.index[253], ["Open", "High", "Low", "Close"]] = [130, 131, 129, 130]
    result = run(
        api,
        bars,
        [
            signal(bars, 249),
            signal(bars, 250, "OVERHEAT_CORRECTION"),
            signal(bars, 251, "POST_OVERHEAT_RECOVERY_ENTRY"),
            signal(bars, 252, "SMA150_EXIT"),
        ],
        max_loss_pct=0.1,
    )
    assert len(result.closed_lots) == 2
    assert [lot.realized_pnl for lot in result.closed_lots] == [70, 20]
    # 3*10 + 2*20 + 2*10 profit, original risks 5*10 + 2*12.
    assert result.aggregate_r == pytest.approx(1.2162162162162162)


@pytest.mark.parametrize(
    "code,stop,quantity",
    [
        ("TREND_BREAKOUT_ENTRY", 100, 12),
        ("DEEP_RECOVERY_ENTRY", 98, 10),
        ("PULLBACK_REVERSAL_ENTRY", 99, 10),
        ("POST_OVERHEAT_RECOVERY_ENTRY", 99, 10),
    ],
)
def test_four_initial_stop_formulas(api, bars, code, stop, quantity):
    result = run(api, bars, [signal(bars, 249, code)], risk_target=120)
    assert result.open_lots[0].stop == stop
    assert result.orders[0].quantity == quantity


def test_pullback_stop_uses_confirmed_highest_support(api, bars):
    entry = signal(bars, 249, "PULLBACK_REVERSAL_ENTRY", support=100)
    entry.evidence.append(
        entry.evidence[0].model_copy(
            update={
                "code": "SMA_150",
                "reference_value": 90,
            }
        )
    )
    result = run(api, bars, [entry], risk_target=120)
    # Detector requires reversal above the highest confirmed support: 100.
    assert result.open_lots[0].stop == 99


def test_explicit_v2_pullback_sizes_from_prior_breakout_support(api, bars):
    from scripts.research_trading_observations import explicit_research_parameters

    execution, risk, simulate = api
    params = explicit_research_parameters()
    entry = signal(bars, 249, "PULLBACK_REVERSAL_ENTRY", support=104).model_copy(
        update={
            "parameter_set_version": params.parameter_set_version,
            "parameter_fingerprint": params.parameter_fingerprint,
        }
    )
    entry.evidence[0] = entry.evidence[0].model_copy(update={"code": "PRIOR_BREAKOUT_LEVEL"})
    result = simulate(
        bars,
        params,
        execution(fee_rate=0, slippage_rate=0),
        risk_policy=risk(risk_target=120),
        ticker="TEST",
        warmup_start=bars.index[0].date(),
        expected_sessions=tuple(bars.index.date),
        test_start=bars.index[249].date(),
        test_end=bars.index[-1].date(),
        signal_history=[entry],
    )
    # ATR=2: support 104 - 0.5*2 = 103; floor(120 / (110-103)) = 17.
    assert (result.open_lots[0].stop, result.open_lots[0].initial_risk_per_share) == (103, 7)
    assert (result.orders[0].date, result.orders[0].price, result.orders[0].quantity) == (
        bars.index[250].date(),
        110,
        17,
    )


@pytest.mark.parametrize("support", [None, float("nan"), float("inf"), float("-inf")])
def test_pullback_rejects_missing_or_nonfinite_prior_breakout_support(api, bars, support):
    entry = signal(bars, 249, "PULLBACK_REVERSAL_ENTRY", support=support)
    entry.evidence[0] = entry.evidence[0].model_copy(update={"code": "PRIOR_BREAKOUT_LEVEL"})
    with pytest.raises(ValueError, match="Missing pullback support evidence"):
        run(api, bars, [entry])


def test_pullback_rejects_absent_support_evidence(api, bars):
    entry = signal(bars, 249, "PULLBACK_REVERSAL_ENTRY").model_copy(update={"evidence": []})
    with pytest.raises(ValueError, match="Missing pullback support evidence"):
        run(api, bars, [entry])


def test_coin_explicit_v2_detector_prior_breakout_signal_executes_next_open(api):
    from scripts.research_trading_observations import explicit_research_parameters

    execution, risk, simulate = api
    raw = pd.read_csv("tests/fixtures/swing_w150/COIN.csv", index_col=0, parse_dates=True).loc[
        :"2024-11-12"
    ]
    result = simulate(
        raw,
        explicit_research_parameters(),
        execution(fee_rate=0, slippage_rate=0),
        risk_policy=risk(risk_target=100),
        ticker="COIN",
        warmup_start=raw.index[0].date(),
        expected_sessions=tuple(raw.index.date),
        test_start=raw.index[249].date(),
        test_end=raw.index[-1].date(),
    )
    entry = next(
        item
        for item in result.signal_history
        if item.occurred_on == date(2024, 11, 11) and item.code == "PULLBACK_REVERSAL_ENTRY"
    )
    assert entry.finality is SignalFinality.FINAL
    assert entry.parameter_fingerprint == (
        "3902379a9ad687f105c316ebcd9b0921bc74f94044650ac3795648d7c8b211b1"
    )
    support = next(item for item in entry.evidence if item.code == "PRIOR_BREAKOUT_LEVEL")
    assert support.reference_value == 259.69000244140625
    fill = next(order for order in result.orders if order.signal_id == entry.signal_id)
    assert (fill.side, fill.date, fill.price, fill.quantity) == (
        "buy",
        date(2024, 11, 12),
        310.04998779296875,
        2,
    )
    lot = next(lot for lot in result.open_lots if lot.signal_id == entry.signal_id)
    # Source ATR=19.880330015537627 gives support stop 249.7498374336374;
    # the 15% loss floor at the next open raises it to 263.54248962402344.
    assert lot.stop == pytest.approx(263.54248962402344)
    assert lot.initial_risk_per_share == pytest.approx(46.50749816894531)
    assert lot.initial_risk_capital == pytest.approx(93.01499633789062)


@pytest.mark.parametrize("multiplier,stop,quantity", [(3, 95, 20), (2, 97, 30)])
def test_trend_stop_atr_branch_and_custom_multiplier(api, bars, multiplier, stop, quantity):
    execution, risk, simulate = api
    bars.loc[bars.index[250:], ["Open", "High", "Low", "Close"]] = [101, 102, 100, 101]
    result = simulate(
        bars,
        SwingW150Parameters(),
        execution(fee_rate=0, slippage_rate=0),
        risk_policy=risk(risk_target=120, trend_atr_multiplier=multiplier),
        ticker="TEST",
        warmup_start=bars.index[0].date(),
        expected_sessions=tuple(pd.bdate_range(bars.index[0], bars.index[-1]).date),
        test_start=bars.index[249].date(),
        test_end=bars.index[-1].date(),
        signal_history=[signal(bars, 249)],
    )
    assert result.open_lots[0].stop == stop
    assert result.orders[0].quantity == quantity


def test_correction_suppresses_same_day_recovery_and_other_entries(api, bars):
    result = run(
        api,
        bars,
        [
            signal(bars, 249),
            signal(bars, 250, "POST_OVERHEAT_RECOVERY_ENTRY"),
            signal(bars, 250, "PULLBACK_REVERSAL_ENTRY"),
            signal(bars, 250, "OVERHEAT_CORRECTION"),
        ],
    )
    assert [(o.reason, o.quantity) for o in result.orders] == [
        ("TREND_BREAKOUT_ENTRY", 5),
        ("OVERHEAT_CORRECTION", 3),
    ]


def test_too_small_risk_target_does_not_create_zero_quantity_lot(api, bars):
    result = run(api, bars, [signal(bars, 249)], risk_target=5)
    assert result.orders == ()
    assert result.open_lots == ()
    assert result.aggregate_r == 0


def test_gap_stop_fill_also_applies_fees_and_slippage(api, bars):
    bars.loc[bars.index[251], ["Open", "High", "Low", "Close"]] = [90, 91, 89, 90]
    result = run(api, bars, [signal(bars, 249)], risk_target=60, fee=0.01, slippage=0.01)
    assert result.orders[-1].reason == "gap_stop"
    assert result.orders[-1].price == 89.1
    assert result.orders[-1].fee == 4.455
    assert result.closed_lots[0].realized_pnl == pytest.approx(-120.01)


def test_partial_and_recovery_fills_apply_the_same_cost_policy(api, bars):
    bars.loc[bars.index[251:253], ["Open", "High", "Low", "Close"]] = [120, 121, 119, 120]
    bars.loc[bars.index[253], ["Open", "High", "Low", "Close"]] = [130, 131, 129, 130]
    result = run(
        api,
        bars,
        [
            signal(bars, 249),
            signal(bars, 250, "OVERHEAT_CORRECTION"),
            signal(bars, 251, "POST_OVERHEAT_RECOVERY_ENTRY"),
            signal(bars, 252, "SMA150_EXIT"),
        ],
        risk_target=60,
        max_loss_pct=0.1,
        fee=0.01,
        slippage=0.01,
    )
    assert [(o.price, o.quantity, o.fee) for o in result.orders] == [
        (111.1, 5, 5.555),
        (118.8, 3, 3.564),
        (121.2, 3, 3.636),
        (128.7, 2, 2.574),
        (128.7, 3, 3.861),
    ]
    assert [lot.realized_pnl for lot in result.closed_lots] == pytest.approx([46.607, 15.003])


def test_identity_hash_changes_with_execution_or_risk_policy(api, bars):
    first = run(api, bars, [])
    assert first.identity.identity_hash != run(api, bars, [], fee=0.01).identity.identity_hash
    assert first.identity.identity_hash != run(api, bars, [], risk_target=60).identity.identity_hash


def test_detector_path_excludes_future_raw_data_before_indicator_calculation(api):
    execution, risk, simulate = api
    raw = pd.read_csv("tests/fixtures/swing_w150/v2_signal_path.csv", index_col=0, parse_dates=True)
    kwargs = {
        "params": SwingW150Parameters(),
        "execution_policy": execution(fee_rate=0, slippage_rate=0),
        "risk_policy": risk(risk_target=50),
        "ticker": "TEST",
        "warmup_start": raw.index[0].date(),
        "expected_sessions": tuple(pd.bdate_range(raw.index[0], raw.index[-1]).date),
        "test_start": raw.index[249].date(),
        "test_end": raw.index[251].date(),
    }
    prefix = simulate(raw.iloc[:252], **kwargs)
    raw.loc[raw.index[252:], :] = float("nan")
    assert simulate(raw, **kwargs) == prefix


@pytest.mark.parametrize(
    "code", ["DEEP_RECOVERY_ENTRY", "PULLBACK_REVERSAL_ENTRY", "POST_OVERHEAT_RECOVERY_ENTRY"]
)
def test_max_loss_floor_for_non_trend_entries(api, bars, code):
    bars.loc[bars.index[250:], ["Open", "High", "Low", "Close"]] = [200, 201, 199, 200]
    result = run(api, bars, [signal(bars, 249, code)], risk_target=60)
    assert result.open_lots[0].stop == 170
    assert result.orders[0].quantity == 2


def test_every_fill_applies_slippage_and_fees(api, bars):
    bars.loc[bars.index[251:], ["Open", "High", "Low", "Close"]] = [120, 121, 119, 120]
    result = run(
        api,
        bars,
        [signal(bars, 249), signal(bars, 250, "SMA150_EXIT")],
        risk_target=60,
        fee=0.01,
        slippage=0.01,
    )
    assert [(o.price, o.fee, o.quantity) for o in result.orders] == [
        (111.1, pytest.approx(5.555), 5),
        (118.8, pytest.approx(5.94), 5),
    ]
    assert result.closed_lots[0].realized_pnl == pytest.approx(27.005)


def test_identity_binds_parameters_period_and_both_policies(api, bars):
    execution, risk, simulate = api
    params = replace(SwingW150Parameters(), parameter_set_version="CUSTOM", overheat_extension=0.35)
    result = simulate(
        bars,
        params,
        execution(fee_rate=0.001, slippage_rate=0.002),
        risk_policy=risk(risk_target=50),
        ticker="TEST",
        warmup_start=bars.index[0].date(),
        expected_sessions=tuple(pd.bdate_range(bars.index[0], bars.index[-1]).date),
        test_start=bars.index[249].date(),
        test_end=bars.index[251].date(),
        signal_history=[],
    )
    assert result.identity.parameter_fingerprint == params.parameter_fingerprint
    assert result.identity.warmup_start == date(2024, 1, 1)
    assert result.identity.execution_policy.fee_rate == 0.001
    assert result.identity.execution_policy.slippage_rate == 0.002
    assert result.identity.risk_policy.risk_target == 50


def test_signal_parameter_mismatch_is_rejected(api, bars):
    changed = signal(bars, 249).model_copy(update={"parameter_fingerprint": "wrong"})
    with pytest.raises(ValueError, match="identity"):
        run(api, bars, [changed])


def test_period_order_is_validated(api, bars):
    with pytest.raises(ValueError, match="period"):
        run(api, bars, [], test_end=bars.index[248].date())


@pytest.mark.parametrize("include_execution_tail", [False, True])
def test_one_pass_signal_history_matches_public_detector_prefixes(api, include_execution_tail):
    execution, risk, simulate = api
    raw = pd.read_csv(
        "tests/fixtures/swing_w150/v2_signal_path.csv", index_col=0, parse_dates=True
    ).astype(float)
    if include_execution_tail:
        from pathlib import Path

        expected = json.loads(
            Path("tests/fixtures/swing_w150/v2_backtest_expected.json").read_text()
        )
        raw = raw.iloc[:250].copy()
        for row in expected["raw_tail"]:
            raw.loc[pd.Timestamp(row["date"])] = row["ohlcv"]
    params = SwingW150Parameters()
    result = simulate(
        raw,
        params,
        execution(fee_rate=0, slippage_rate=0),
        risk_policy=risk(risk_target=50),
        ticker="TEST",
        warmup_start=raw.index[0].date(),
        expected_sessions=tuple(pd.bdate_range(raw.index[0], raw.index[-1]).date),
        test_start=raw.index[249].date(),
        test_end=raw.index[-1].date(),
    )
    prefix_history = []
    for bar in range(250, len(raw) + 1):
        detection = detect_swing("TEST", build_swing_features(raw.iloc[:bar], params), params)
        prefix_history.extend(detection.current_signals)
    assert result.signal_history == tuple(prefix_history)

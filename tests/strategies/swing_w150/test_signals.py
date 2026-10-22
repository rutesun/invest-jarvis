"""Chart-only SWING_W150 signal transitions and prefix replay."""

from dataclasses import replace
from decimal import Decimal

import pytest

from src.strategies.models import BarFinality, ObservationStatus, SignalFinality
from src.strategies.swing_w150.features import build_swing_features
from src.strategies.swing_w150.parameters import (
    SupportCycleParameters,
    SwingW150Parameters,
    SwingW150ParametersV2,
)
from src.strategies.swing_w150.signals import detect_swing, iter_swing_detection
from src.tools.technical.scorecard_models import DataStatus


@pytest.fixture
def params() -> SwingW150Parameters:
    return SwingW150Parameters()


def detect_test(features, params):
    return detect_swing("TEST", features, params)


def codes(result):
    return [signal.code for signal in result.signal_history]


def observation(result, code):
    return next(item for item in result.observation_history if item.code == code)


@pytest.fixture
def ladder_params():
    # Explicit test selection; these values are not an operating default.
    return SwingW150ParametersV2(
        support_cycle=SupportCycleParameters(
            normal_failure_closes=2,
            immediate_failure_volume_ratio=2,
            immediate_failure_close_location=0.25,
            support_break_buffer_atr=0,
            restart_mode="D",
        )
    )


def ladder_features(factory, changes):
    features = factory.make(changes)
    frame = features.frame
    frame["History_Bars"] = range(1, len(frame) + 1)
    frame["Previous_Close"] = frame["Close"].shift(1)
    frame["Volume_Ratio_Prev20"] = 0.5
    frame["Price_Breakout_Event"] = False
    frame.loc[frame.index[249], "Price_Breakout_Event"] = True
    frame["High_Break_5"] = False
    return features


def watches(result):
    return [item for item in result.observation_history if item.code == "PULLBACK_WATCH"]


@pytest.mark.parametrize("unfinished_high", [138, 134])
def test_initial_cycle_ignores_middle_provisional_pivot_price_and_row(
    signal_factory, ladder_params, unfinished_high
):
    highs = [131, 132, 133, 136, 133, 132, 131, 132, 133, unfinished_high, 133, 132, 131]
    f = signal_factory.make([{"High": high, "Volume": 50} for high in highs])
    f.frame["History_Bars"] = range(1, len(f.frame) + 1)
    f.frame["Price_Breakout_Event"] = False
    finalities = list(f.finalities)
    finalities[259] = BarFinality.PROVISIONAL
    f = replace(f, finalities=tuple(finalities))
    result = detect_test(f, ladder_params)
    assert result.signal_history == []
    assert result.up_cycle.status == "INACTIVE"
    removed = replace(
        f, frame=f.frame.drop(f.frame.index[259]), finalities=(BarFinality.FINAL,) * 262
    )
    assert detect_test(removed, ladder_params).up_cycle == result.up_cycle
    if unfinished_high == 138:
        all_final = replace(f, finalities=(BarFinality.FINAL,) * len(f.frame))
        active = detect_test(all_final, ladder_params).up_cycle
        assert active.status == "ACTIVE"
        assert active.started_on == f.frame.index[-1].date()
        assert active.confirmation_code == "HIGHER_HIGH"


def test_healthy_low_volume_sma50_pullback_needs_no_correction_mode(signal_factory, ladder_params):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 121, "Low": 120, "High": 123, "Volume": 50, "SMA_20": 110},
        ],
    )
    result = detect_test(features, ladder_params)
    assert result.up_cycle.status == "ACTIVE"
    assert [(item.anchor_type, item.status) for item in watches(result)] == [
        ("SMA50", ObservationStatus.ACTIVE)
    ]
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(result)


def test_sma150_watch_survives_supertrend_down_and_ma_weakness(signal_factory, ladder_params):
    features = ladder_features(
        signal_factory,
        [
            {
                "Close": 111,
                "Low": 110,
                "High": 113,
                "SMA_50": 100,
                "SMA_50_Slope_21": -1,
                "SuperTrend_Dir": -1,
            },
            {
                "Close": 111,
                "Low": 110,
                "High": 112,
                "SMA_50": 100,
                "SMA_50_Slope_21": -1,
                "SuperTrend_Dir": -1,
            },
        ],
    )
    result = detect_test(features, ladder_params)
    assert result.up_cycle.status == "ACTIVE"
    assert [(item.anchor_type, item.status) for item in watches(result)] == [
        ("SMA150", ObservationStatus.ACTIVE)
    ]
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(result)


def test_one_close_shakeout_and_reclaim(signal_factory, ladder_params):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 111, "Low": 110, "High": 114, "SMA_50": 100, "SuperTrend_Dir": -1},
            {"Close": 109, "Low": 108, "High": 114, "SMA_50": 100, "SuperTrend_Dir": -1},
            {"Close": 111, "Low": 110, "High": 114, "SMA_50": 100, "SuperTrend_Dir": -1},
        ],
    )
    result = detect_test(features, ladder_params)
    assert result.up_cycle.status == "ACTIVE"
    assert all(
        item.status != "FAILED"
        for item in result.support_tests
        if item.anchor.anchor_type == "SMA150"
    )
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(result)


def test_sma50_failure_moves_support_without_ending_cycle(signal_factory, ladder_params):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 121, "Low": 120, "High": 123, "SuperTrend_Dir": -1},
            {"Close": 119, "Low": 118, "High": 121, "SuperTrend_Dir": -1},
            {"Close": 111, "Low": 110, "High": 120, "SuperTrend_Dir": -1},
        ],
    )
    result = detect_test(features, ladder_params)
    assert result.up_cycle.status == "ACTIVE"
    assert [(item.anchor_type, item.status) for item in watches(result)] == [
        ("SMA50", ObservationStatus.INVALIDATED),
        ("SMA150", ObservationStatus.ACTIVE),
    ]
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(result)


def test_sma150_failure_overrides_lower_breakout(signal_factory, ladder_params):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 151, "Low": 150, "High": 152, "Volume": 200, "Trend_Breakout_High_Prev": 100},
            {"Close": 109, "Low": 108, "High": 111, "SuperTrend_Dir": -1},
            {"Close": 108, "Low": 107, "High": 110, "SuperTrend_Dir": -1},
        ],
    )
    result = detect_test(features, ladder_params)
    assert result.up_cycle.status == "TERMINATED"
    assert result.up_cycle.terminal_reason == "SMA150_SUPPORT_FAILED"
    assert any(item.anchor.anchor_type == "PRIOR_BREAKOUT_LEVEL" for item in result.support_tests)
    assert not any(item.status == ObservationStatus.ACTIVE for item in watches(result))


def test_cycle_failure_does_not_change_sma150_exit_detector(signal_factory, ladder_params, params):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 109, "Low": 108, "High": 111},
            {"Close": 108, "Low": 107, "High": 110},
            {"Close": 107, "Low": 106, "High": 109},
        ],
    )
    selected = replace(
        ladder_params, support_cycle=replace(ladder_params.support_cycle, normal_failure_closes=1)
    )
    old = detect_test(features, params)
    new = detect_test(features, selected)
    assert new.up_cycle.terminated_on == features.frame.index[-3].date()
    assert [
        (s.occurred_on, s.code, s.evidence) for s in new.signal_history if s.code == "SMA150_EXIT"
    ] == [
        (s.occurred_on, s.code, s.evidence) for s in old.signal_history if s.code == "SMA150_EXIT"
    ]


def test_provisional_failure_does_not_terminate_final_cycle(signal_factory, ladder_params):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 109, "Low": 108, "High": 111},
            {"Close": 108, "Low": 107, "High": 110},
        ],
    )
    features = replace(features, finalities=features.finalities[:-1] + (BarFinality.PROVISIONAL,))
    result = detect_test(features, ladder_params)
    assert result.up_cycle.status == "ACTIVE"
    assert result.up_cycle.status_as_of == features.frame.index[-2].date()
    assert not any(
        item.status == "FAILED"
        for item in result.support_tests
        if item.anchor.anchor_type == "SMA150"
    )


def test_new_ladder_anchor_cannot_reverse_on_its_first_watch_day(signal_factory, ladder_params):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 121, "Low": 120, "High": 122, "SuperTrend_Dir": -1},
            {"Close": 118, "Low": 110, "High": 119, "SuperTrend_Dir": -1},
            {"Close": 120, "Low": 110, "High": 121, "SuperTrend_Dir": -1},
        ],
    )
    result = detect_test(
        features,
        replace(
            ladder_params,
            support_cycle=replace(ladder_params.support_cycle, normal_failure_closes=1),
        ),
    )
    assert [(item.anchor_type, item.started_on) for item in watches(result)] == [
        ("SMA50", features.frame.index[-3].date()),
        ("SMA150", features.frame.index[-2].date()),
    ]
    assert [
        s.occurred_on for s in result.signal_history if s.code == "PULLBACK_REVERSAL_ENTRY"
    ] == [features.frame.index[-1].date()]


def test_prefix_and_full_replay_agree_after_skipped_runs(signal_factory, ladder_params):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 121, "Low": 120, "High": 123},
            {"Close": 119, "Low": 118, "High": 121},
            {"Close": 111, "Low": 110, "High": 120},
            {"Close": 122, "Low": 121, "High": 123},
        ],
    )
    snapshots = list(iter_swing_detection("TEST", features, ladder_params))
    for end in (250, 252, 254):
        prefix = replace(
            features, frame=features.frame.iloc[:end], finalities=features.finalities[:end]
        )
        assert detect_test(prefix, ladder_params) == snapshots[end - 1]


def test_provisional_watch_cannot_become_a_completed_watch_for_next_entry(
    signal_factory, ladder_params
):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 121, "Low": 120, "High": 122},
            {"Close": 124, "Low": 120, "High": 125},
        ],
    )
    features = replace(
        features,
        finalities=features.finalities[:-2]
        + (
            BarFinality.PROVISIONAL,
            BarFinality.FINAL,
        ),
    )
    result = detect_test(features, ladder_params)
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(result)
    assert [item.started_on for item in watches(result)] == [features.frame.index[-1].date()]


@pytest.mark.parametrize("last_finality", [BarFinality.FINAL, BarFinality.PROVISIONAL])
@pytest.mark.parametrize(
    "lookback,older_high,should_reverse",
    [
        (1, 121, True),
        (2, 121, True),
        (1, 126, True),
        (2, 126, False),
    ],
)
def test_v2_reversal_lookback_uses_only_completed_final_highs(
    signal_factory, ladder_params, last_finality, lookback, older_high, should_reverse
):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 120.5, "Low": 120, "High": older_high},
            {"Close": 121, "Low": 120, "High": 122},
            {"Close": 121, "Low": 120, "High": 130},
            {"Close": 124, "Low": 123, "High": 125},
        ],
    )
    features = replace(
        features,
        finalities=features.finalities[:-2]
        + (
            BarFinality.PROVISIONAL,
            last_finality,
        ),
    )
    params = replace(ladder_params, pullback_reversal_high_lookback=lookback)
    with_provisional = detect_test(features, params)
    keep = [index for index in range(len(features.frame)) if index != len(features.frame) - 2]
    completed_only = replace(
        features,
        frame=features.frame.iloc[keep],
        finalities=tuple(features.finalities[index] for index in keep),
    )
    without_provisional = detect_test(completed_only, params)
    expected = (
        [
            (
                features.frame.index[-1].date(),
                "PULLBACK_REVERSAL_ENTRY",
                SignalFinality(last_finality.value),
            )
        ]
        if should_reverse
        else []
    )
    for result in (with_provisional, without_provisional):
        assert [
            (item.occurred_on, item.code, item.finality)
            for item in result.signal_history
            if item.code == "PULLBACK_REVERSAL_ENTRY"
        ] == expected
    assert [item.status for item in watches(with_provisional)] == [
        item.status for item in watches(without_provisional)
    ]


def test_multiple_breakout_anchors_are_preserved(signal_factory, ladder_params):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 151, "Low": 150, "High": 152, "Volume": 200, "Trend_Breakout_High_Prev": 140},
            {"Close": 145, "Low": 144, "High": 150, "Trend_Breakout_High_Prev": 155},
            {"Close": 160, "Low": 159, "High": 161, "Volume": 200, "Trend_Breakout_High_Prev": 155},
        ],
    )
    result = detect_test(features, ladder_params)
    sources = [
        item
        for item in result.support_tests
        if item.anchor.anchor_type == "PRIOR_BREAKOUT_LEVEL" and item.anchor.source_signal_id
    ]
    assert [(item.anchor.origin_price, item.anchor.origin_on) for item in sources] == [
        (Decimal("140"), features.frame.index[-3].date()),
        (Decimal("155"), features.frame.index[-1].date()),
    ]


def test_incomplete_coverage_does_not_evaluate_cycle_or_support(signal_factory, ladder_params):
    features = ladder_features(signal_factory, [{"Close": 121, "Low": 120, "High": 123}])
    result = detect_test(replace(features, data_status=DataStatus.PARTIAL), ladder_params)
    assert result.up_cycle.status == "INACTIVE"
    assert result.support_tests == []
    assert result.pullback_policy_inactive_reason.startswith("NOT_EVALUATED")


def test_provisional_supertrend_down_cannot_reverse_using_previous_up_band(
    signal_factory, ladder_params
):
    features = ladder_features(
        signal_factory,
        [
            {"Close": 119.5, "Low": 119, "High": 120, "SMA_50": 100},
            {
                "Close": 122,
                "Low": 121,
                "High": 123,
                "SMA_50": 100,
                "SuperTrend_Dir": -1,
                "SuperTrend_Up": 119,
            },
        ],
    )
    features = replace(features, finalities=features.finalities[:-1] + (BarFinality.PROVISIONAL,))
    result = detect_test(features, ladder_params)
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(result)
    assert result.up_cycle.status == "ACTIVE"


def test_short_prefix_marks_cycle_as_not_evaluated(signal_factory, ladder_params):
    features = ladder_features(signal_factory, [])
    short = replace(features, frame=features.frame.iloc[:249], finalities=features.finalities[:249])
    result = detect_test(short, ladder_params)
    assert result.data_status == DataStatus.INSUFFICIENT_DATA
    assert result.up_cycle.status == "INACTIVE"
    assert result.support_tests == []
    assert result.pullback_policy_inactive_reason.startswith("NOT_EVALUATED")


def test_reversal_anchor_lineage_survives_sma50_breakout_sma150_rotation(
    signal_factory, ladder_params
):
    from src.strategies.entry_anchors import build_entry_source_anchors
    from tests.strategies.swing_w150.test_adapter import _bundle

    features = ladder_features(
        signal_factory,
        [
            {"Close": 121, "Low": 120, "High": 122},
            {"Close": 123, "Low": 122, "High": 124},
            {"Close": 119, "Low": 118, "High": 121},
            {"Close": 116, "Low": 115, "High": 117},
            {"Close": 118, "Low": 117, "High": 119},
            {"Close": 114, "Low": 113, "High": 116},
            {"Close": 111, "Low": 110, "High": 112},
            {"Close": 113, "Low": 112, "High": 114},
        ],
    )
    features.frame["SuperTrend_Dir"] = -1
    features.frame.loc[features.frame.index[249], "Trend_Breakout_High_Prev"] = 115
    params = replace(
        ladder_params,
        support_cycle=replace(
            ladder_params.support_cycle,
            normal_failure_closes=1,
        ),
    )
    result = detect_swing("COIN", features, params)
    bundle = _bundle(features.frame[["Open", "High", "Low", "Close", "Volume"]])
    signals = [item for item in result.signal_history if item.code == "PULLBACK_REVERSAL_ENTRY"]
    assert [item.occurred_on for item in signals] == [
        features.frame.index[i].date() for i in (251, 254, 257)
    ]
    anchors = [
        build_entry_source_anchors(item, bundle, features, result.observation_history)
        for item in signals
    ]
    assert [(item.origin_support, item.pullback_low) for item in anchors] == [
        (Decimal("120.0"), Decimal("120.0")),
        (Decimal("115.0"), Decimal("115.0")),
        (Decimal("110.0"), Decimal("110.0")),
    ]


def test_overheat_sequence_emits_each_transition_once(signal_factory, params):
    result = detect_test(signal_factory.overheat_correction_recovery(), params)
    assert codes(result) == [
        "OVERHEAT",
        "OVERHEAT_CORRECTION",
        "POST_OVERHEAT_RECOVERY_ENTRY",
    ]


def test_overheat_resolve_and_expiry_reset_without_recovery_entry(signal_factory, params):
    resolved = detect_test(signal_factory.overheat_then_reset_extension(), params)
    expired = detect_test(signal_factory.overheat_then_expiry(), params)
    assert codes(resolved)[-1] == "OVERHEAT_RESOLVED"
    assert codes(expired)[-1] == "OVERHEAT_EXPIRED"
    assert "POST_OVERHEAT_RECOVERY_ENTRY" not in codes(resolved) + codes(expired)


def test_corrected_phase_expires_after_twenty_bars(signal_factory, params):
    result = detect_test(signal_factory.correction_without_recovery(20), params)
    assert observation(result, "POST_OVERHEAT_RECOVERY_WATCH").status is ObservationStatus.EXPIRED


@pytest.mark.parametrize("support", ["SMA_50", "SMA_150", "SMA_200", "SuperTrend_Up"])
def test_pullback_support_to_signal_once(signal_factory, params, support):
    result = detect_test(signal_factory.pullback_reversal(support, atr_distance=0.5), params)
    episode = observation(result, "PULLBACK_WATCH")
    assert episode.status is ObservationStatus.RESOLVED_TO_SIGNAL
    assert codes(result).count("PULLBACK_REVERSAL_ENTRY") == 1


def test_pullback_invalidates_or_expires_and_does_not_late_fire(signal_factory, params):
    invalid = detect_test(signal_factory.pullback_invalidated(), params)
    expired = detect_test(signal_factory.pullback_expired_then_breakout(), params)
    assert observation(invalid, "PULLBACK_WATCH").status is ObservationStatus.INVALIDATED
    assert observation(expired, "PULLBACK_WATCH").status is ObservationStatus.EXPIRED
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(expired)


@pytest.mark.parametrize("missing_support", [None, float("nan")])
def test_pullback_invalidates_when_its_only_support_disappears(
    signal_factory, params, missing_support
):
    features = signal_factory.make(
        [
            {"Close": 119.5, "Low": 119, "High": 120},
            {
                "Close": 117,
                "Low": 116,
                "High": 118,
                "SuperTrend_Up": missing_support,
                "SuperTrend_Dir": -1,
            },
            {"Close": 130, "Low": 128, "High": 132},
            {"Close": 119.5, "Low": 119, "High": 120},
            {"Close": 122, "Low": 121, "High": 123},
        ]
    )
    snapshots = list(iter_swing_detection("TEST", features, params))
    started, disappeared, recovered, restarted, reversed_ = snapshots[-5:]
    watch = observation(started, "PULLBACK_WATCH")
    assert watch.status is ObservationStatus.ACTIVE
    assert {item.code for item in watch.evidence if item.reference_value == 119} == {
        "SuperTrend_Up"
    }

    invalidated = observation(disappeared, "PULLBACK_WATCH")
    assert invalidated.status is ObservationStatus.INVALIDATED
    assert invalidated.started_on == features.frame.index[-5].date()
    assert invalidated.ended_on == invalidated.status_as_of == features.frame.index[-4].date()
    evidence = {item.code: item for item in invalidated.evidence}
    assert evidence["SuperTrend_Up"].observed_value == 117
    assert evidence["SuperTrend_Up"].reference_value is None
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(recovered)
    assert observation(recovered, "PULLBACK_WATCH") == invalidated
    assert [episode.status for episode in restarted.observation_history] == [
        ObservationStatus.INVALIDATED,
        ObservationStatus.ACTIVE,
    ]
    assert [episode.status for episode in reversed_.observation_history] == [
        ObservationStatus.INVALIDATED,
        ObservationStatus.RESOLVED_TO_SIGNAL,
    ]
    assert [signal.code for signal in reversed_.signal_history] == ["PULLBACK_REVERSAL_ENTRY"]
    assert reversed_.signal_history[0].occurred_on == features.frame.index[-1].date()

    for bar in range(len(features.frame) - 4, len(features.frame) + 1):
        prefix = replace(
            features, frame=features.frame.iloc[:bar], finalities=features.finalities[:bar]
        )
        assert detect_test(prefix, params) == snapshots[bar - 1]


def test_pullback_still_reverses_when_another_captured_support_remains(signal_factory, params):
    features = signal_factory.make(
        [
            {"Close": 121, "Low": 120, "High": 122},
            {
                "Close": 123,
                "Low": 122,
                "High": 124,
                "SuperTrend_Up": float("nan"),
                "SuperTrend_Dir": -1,
            },
        ]
    )
    result = detect_test(features, params)
    assert observation(result, "PULLBACK_WATCH").status is ObservationStatus.RESOLVED_TO_SIGNAL
    assert codes(result) == ["PULLBACK_REVERSAL_ENTRY"]
    evidence = {item.code: item for item in result.signal_history[0].evidence}
    assert evidence["SMA_50"].reference_value == 120
    assert evidence["SuperTrend_Up"].reference_value is None


def test_sma150_exit_emits_on_second_below_close_only(signal_factory, params):
    result = detect_test(signal_factory.sma150_below_for_four_days(), params)
    assert codes(result).count("SMA150_EXIT") == 1


def test_all_same_day_events_are_kept_in_priority_order(signal_factory, params):
    result = detect_test(signal_factory.same_day_exit_and_entry(), params)
    today = [item.code for item in result.current_signals]
    assert today == ["SMA150_EXIT", "PULLBACK_REVERSAL_ENTRY"]
    assert observation(result, "PULLBACK_WATCH").status is ObservationStatus.INVALIDATED


def test_deep_recovery_is_suppressed_by_structural_breakdown(signal_factory, params):
    result = detect_test(signal_factory.deep_recovery_with_breakdown(), params)
    assert "DEEP_RECOVERY_ENTRY" not in codes(result)


def test_trend_breakout_emits_after_volume_confirmed_first_cross(signal_factory, params):
    features = signal_factory.make([{"Close": 150, "Low": 149, "High": 151, "Volume": 200}])
    assert codes(detect_test(features, params)) == ["TREND_BREAKOUT_ENTRY"]


def test_deep_recovery_emits_when_higher_low_is_confirmed(signal_factory, params):
    features = signal_factory.deep_recovery_with_breakdown()
    features.frame.loc[features.frame.index[-1], "Low_20_Prev"] = 80
    features.frame.loc[features.frame.index[-1], "Volume"] = 100
    assert "DEEP_RECOVERY_ENTRY" in codes(detect_test(features, params))


def test_raw_price_to_final_signal_golden(v2_raw_fixture, v2_expected_fixture, params):
    features = build_swing_features(v2_raw_fixture, params)
    result = detect_swing("TEST", features, params)
    assert (
        result.model_dump(
            mode="json", exclude={"up_cycle", "support_tests", "pullback_policy_inactive_reason"}
        )
        == v2_expected_fixture
    )


def test_prefix_replay_matches_one_pass_observations_signals_and_current(v2_raw_fixture, params):
    one_pass = list(
        iter_swing_detection("TEST", build_swing_features(v2_raw_fixture, params), params)
    )
    for bar in range(params.minimum_history_bars, len(v2_raw_fixture) + 1):
        prefix = v2_raw_fixture.iloc[:bar]
        recomputed = detect_swing("TEST", build_swing_features(prefix, params), params)
        assert recomputed.model_dump(mode="json") == one_pass[bar - 1].model_dump(mode="json")


def test_provisional_last_bar_only_marks_its_own_signal(v2_raw_fixture, params):
    finalities = [BarFinality.FINAL] * (len(v2_raw_fixture) - 1) + [BarFinality.PROVISIONAL]
    features = build_swing_features(v2_raw_fixture, params, finalities=finalities)
    result = detect_swing("TEST", features, params)
    assert [signal.finality for signal in result.signal_history] == [
        SignalFinality.FINAL,
        SignalFinality.FINAL,
        SignalFinality.PROVISIONAL,
    ]


def test_new_approach_restarts_same_support_watch(signal_factory, params):
    result = detect_test(signal_factory.new_support_approach(), params)
    watches = [
        episode for episode in result.observation_history if episode.code == "PULLBACK_WATCH"
    ]
    assert [episode.status for episode in watches] == [
        ObservationStatus.EXPIRED,
        ObservationStatus.ACTIVE,
    ]


def test_exit_keeps_same_day_overheat_correction_in_priority_order(signal_factory, params):
    result = detect_test(signal_factory.same_day_exit_and_overheat_correction(), params)
    assert [signal.code for signal in result.current_signals] == [
        "SMA150_EXIT",
        "OVERHEAT_CORRECTION",
    ]


def test_custom_sma_exit_count_waits_for_third_below_close(signal_factory, params):
    custom = replace(params, parameter_set_version="CUSTOM", sma_exit_consecutive_closes=3)
    features = signal_factory.sma150_below_for_four_days()
    result = detect_test(features, custom)
    exit_signal = next(signal for signal in result.signal_history if signal.code == "SMA150_EXIT")
    assert exit_signal.occurred_on == features.frame.index[252].date()


def test_sma150_exit_requires_prior_rising_structure(signal_factory, params):
    result = detect_test(signal_factory.below_sma150_without_rising_structure(), params)
    assert "SMA150_EXIT" not in codes(result)


def test_pullback_signal_keeps_all_support_and_momentum_evidence(signal_factory, params):
    features = signal_factory.pullback_reversal("SMA_50")
    features.frame.loc[features.frame.index[-2:], "cRSI"] = 10
    features.frame.loc[features.frame.index[-2:], "MACD"] = -5
    result = detect_test(features, params)
    signal = next(
        signal for signal in result.signal_history if signal.code == "PULLBACK_REVERSAL_ENTRY"
    )
    evidence = {item.code: item for item in signal.evidence}
    assert {"SMA_50", "SuperTrend_Up", "cRSI", "MACD"} <= evidence.keys()
    assert evidence["cRSI"].observed_value == 10
    assert evidence["MACD"].observed_value == -5


def test_pullback_reversal_uses_configured_prior_high_window(signal_factory, params):
    features = signal_factory.pullback_reversal("SMA_50")
    features = replace(
        features, frame=features.frame.iloc[:-1], finalities=features.finalities[:-1]
    )
    custom = replace(params, parameter_set_version="CUSTOM", pullback_reversal_high_lookback=2)
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(detect_test(features, custom))


def test_custom_trend_lookback_consumes_parameterized_feature(signal_factory, params):
    features = signal_factory.make(
        [{"Close": 150, "Low": 149, "High": 151, "Volume": 200, "High_50_Prev": 200}]
    )
    custom = replace(params, parameter_set_version="CUSTOM", trend_breakout_lookback=2)
    assert "TREND_BREAKOUT_ENTRY" in codes(detect_test(features, custom))


def test_custom_deep_lookback_consumes_parameterized_feature(signal_factory, params):
    features = signal_factory.deep_recovery_with_breakdown()
    features.frame.loc[features.frame.index[-1], "Low_20_Prev"] = 80
    features.frame.loc[features.frame.index[-1], "Volume"] = 100
    features.frame.loc[features.frame.index[-1], "High_20_Prev"] = 200
    custom = replace(params, parameter_set_version="CUSTOM", deep_recovery_breakout_lookback=2)
    assert "DEEP_RECOVERY_ENTRY" in codes(detect_test(features, custom))


def test_raw_custom_trend_lookback_reaches_signal(v2_raw_fixture, params):
    raw = v2_raw_fixture.iloc[:251].copy()
    raw.loc[raw.index[225], "High"] = 150
    raw.loc[raw.index[-1], ["Open", "High", "Low", "Close", "Volume"]] = [
        104,
        105,
        103,
        104,
        200,
    ]
    custom = replace(params, parameter_set_version="CUSTOM", trend_breakout_lookback=2)
    features = build_swing_features(raw, custom)
    assert features.frame["Trend_Breakout_High_Prev"].iloc[-1] == 101
    assert "TREND_BREAKOUT_ENTRY" in codes(detect_swing("TEST", features, custom))


def test_detector_rejects_registered_payload_mismatch_and_accepts_custom(signal_factory, params):
    changed = replace(params, overheat_extension=0.35)
    features = signal_factory.overheat_correction_recovery()
    with pytest.raises(ValueError, match="registered parameter payload mismatch"):
        detect_test(features, changed)

    custom = replace(changed, parameter_set_version="CUSTOM")
    result = detect_test(features, custom)
    assert "OVERHEAT" in codes(result)
    assert all(
        signal.parameter_fingerprint == custom.parameter_fingerprint
        for signal in result.signal_history
    )


def test_custom_breakdown_volume_threshold_changes_deep_suppression(signal_factory, params):
    features = signal_factory.deep_recovery_with_breakdown()
    assert "DEEP_RECOVERY_ENTRY" not in codes(detect_test(features, params))

    custom = replace(
        params,
        parameter_set_version="CUSTOM_VOLUME",
        structure_breakdown_volume_multiple=2.1,
    )
    result = detect_test(features, custom)
    assert "DEEP_RECOVERY_ENTRY" in codes(result)
    assert result.parameter_fingerprint == custom.parameter_fingerprint


def test_trend_signal_preserves_breakout_volume_and_slope_evidence(signal_factory, params):
    features = signal_factory.make([{"Close": 150, "Low": 149, "High": 151, "Volume": 200}])
    signal = detect_test(features, params).signal_history[-1]
    evidence = {item.code: item for item in signal.evidence}
    assert evidence["TREND_BREAKOUT_PRICE"].observed_value == 150
    assert evidence["TREND_BREAKOUT_PRICE"].reference_value == 140
    assert evidence["VOLUME_MULTIPLE"].observed_value == 2
    assert evidence["VOLUME_MULTIPLE"].reference_value == 1.4
    assert evidence["SMA_150_SLOPE_DIRECTION_RISING"].observed_value == 1
    assert evidence["SMA_150_SLOPE_DIRECTION_RISING"].reference_value == 0


def test_deep_signal_preserves_recovery_pivot_trend_and_basis_evidence(signal_factory, params):
    features = signal_factory.deep_recovery_with_breakdown()
    features.frame.loc[features.frame.index[-1], "Low_20_Prev"] = 80
    features.frame.loc[features.frame.index[-1], "Volume"] = 100
    signal = next(
        item
        for item in detect_test(features, params).signal_history
        if item.code == "DEEP_RECOVERY_ENTRY"
    )
    evidence = {item.code: item for item in signal.evidence}
    assert evidence["SMA_20_RECOVERY"].reference_value == 95
    assert evidence["SMA_50_RECOVERY"].reference_value == 90
    assert evidence["HIGHER_LOW"].observed_value == 1
    assert evidence["SUPERTREND_DIRECTION_RISING"].observed_value == 1
    assert evidence["DEEP_RECLAIM_SMA50"].observed_value == 100


def test_overheat_correction_and_recovery_preserve_transition_evidence(signal_factory, params):
    result = detect_test(signal_factory.overheat_correction_recovery(), params)
    overheat, correction, recovery = result.signal_history
    hot = {item.code: item for item in overheat.evidence}
    corrected = {item.code: item for item in correction.evidence}
    recovered = {item.code: item for item in recovery.evidence}
    assert hot["OVERHEAT_EXTENSION"].observed_value == pytest.approx(170 / 120 - 1)
    assert hot["OVERHEAT_EXTENSION"].reference_value == 0.4
    assert corrected["SMA20_CROSS_DOWN"].observed_value == 110
    assert corrected["SMA20_CROSS_DOWN"].reference_value == 125
    assert corrected["PRIOR_CLOSE_VS_SMA20"].observed_value == 170
    assert recovered["SMA20_RECOVERY"].observed_value == 130
    assert recovered["PRIOR_HIGH_BREAK"].reference_value == 112
    assert recovered["CORRECTED_AGE_BARS"].observed_value == 1


def test_overheat_expiry_preserves_age_evidence(signal_factory, params):
    result = detect_test(signal_factory.overheat_then_expiry(), params)
    expired = result.signal_history[-1]
    evidence = {item.code: item for item in expired.evidence}
    assert evidence["OVERHEAT_AGE_BARS"].observed_value == 20
    assert evidence["OVERHEAT_AGE_BARS"].reference_value == 20


def test_sma150_exit_preserves_line_and_consecutive_count(signal_factory, params):
    result = detect_test(signal_factory.sma150_below_for_four_days(), params)
    exit_signal = next(item for item in result.signal_history if item.code == "SMA150_EXIT")
    evidence = {item.code: item for item in exit_signal.evidence}
    assert evidence["CLOSE_VS_SMA150"].observed_value == 107
    assert evidence["CLOSE_VS_SMA150"].reference_value == 110
    assert evidence["CONSECUTIVE_BELOW_SMA150"].observed_value == 2


def test_pullback_evidence_preserves_slope_and_momentum_directions(signal_factory, params):
    features = signal_factory.pullback_reversal("SMA_50")
    watch, reversal = features.frame.index[-3:-1]
    features.frame.loc[watch, ["cRSI", "MACD"]] = [40, -1]
    features.frame.loc[reversal, ["cRSI", "MACD"]] = [50, -2]
    result = detect_test(features, params)
    signal = next(item for item in result.signal_history if item.code == "PULLBACK_REVERSAL_ENTRY")
    evidence = {item.code: item for item in signal.evidence}
    assert {"SMA_50", "SuperTrend_Up"} <= evidence.keys()
    assert evidence["SMA_50_SLOPE_DIRECTION_RISING"].observed_value == 1
    assert evidence["SMA_150_SLOPE_DIRECTION_RISING"].reference_value == 0
    assert evidence["SMA_200_SLOPE_DIRECTION_RISING"].observed_value == 1
    assert evidence["cRSI_DIRECTION_RISING"].observed_value == 10
    assert evidence["MACD_DIRECTION_FALLING"].observed_value == -1
    assert evidence["cRSI"].observed_value == 50
    assert evidence["MACD"].observed_value == -2

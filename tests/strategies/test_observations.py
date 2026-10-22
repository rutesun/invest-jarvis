from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

from src.strategies.models import BarFinality, ObservationCode, ObservationStatus
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.swing_w150.features import SwingFeatureFrame
from src.tools.technical.scorecard_models import DataStatus


def features(rows, provisional=False):
    frame = pd.DataFrame(rows, index=pd.bdate_range("2024-01-02", periods=len(rows)))
    return SwingFeatureFrame(
        frame,
        DataStatus.COMPLETE,
        (BarFinality.FINAL,) * (len(rows) - 1)
        + (BarFinality.PROVISIONAL if provisional else BarFinality.FINAL,),
    )


def test_source_free_volume_events_resolve_on_observed_date_and_exclude_missing():
    from src.strategies.observations.detectors import evaluate_observations

    f = features(
        [
            {"Close": 101, "Previous_Close": 100, "Volume_Ratio_Prev20": 1.5},
            {"Close": 102, "Previous_Close": 101, "Volume_Ratio_Prev20": None},
        ]
    )
    episodes = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=ObservationParameters(up_volume_ratio=1.5)
    )
    assert len(episodes) == 1
    event = episodes[0]
    assert event.code == ObservationCode.UP_VOLUME_EXPANSION
    assert event.started_on == event.ended_on == event.confirmed_on == date(2024, 1, 2)
    assert event.status == ObservationStatus.RESOLVED


def test_provisional_new_event_is_visible_without_committing_final_history():
    from src.strategies.observations.detectors import evaluate_observations

    f = features([{"Close": 101, "Previous_Close": 100, "Volume_Ratio_Prev20": 1.5}], True)
    history = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=ObservationParameters(up_volume_ratio=1.5)
    )
    assert len(history) == 1
    assert history[0].finality.value == "provisional"


def test_episode_counts_one_sample_and_reentry_has_new_origin():
    from src.strategies.observations.detectors import evaluate_observations

    f = features(
        [{"Contraction_Context": True, "Volume_Contraction_Ratio": v} for v in [0.6, 0.6, 0.9, 0.6]]
    )
    episodes = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=ObservationParameters(contraction_ratio=0.7)
    )
    assert len(episodes) == 2
    assert episodes[0].started_on == date(2024, 1, 2)
    assert episodes[0].ended_on == date(2024, 1, 4)
    assert episodes[1].status == ObservationStatus.ACTIVE


def test_provisional_recovery_cannot_close_final_episode():
    from src.strategies.observations.detectors import evaluate_observations

    f = features(
        [{"Contraction_Context": True, "Volume_Contraction_Ratio": v} for v in [0.6, 0.9]], True
    )
    episodes = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=ObservationParameters(contraction_ratio=0.7)
    )
    assert episodes[0].status == ObservationStatus.ACTIVE
    assert episodes[0].status_as_of == date(2024, 1, 2)


def test_source_free_deceleration_starts_on_turn_and_not_every_negative_day():
    from src.strategies.observations.detectors import evaluate_observations

    f = features(
        [
            {
                "Close": 95,
                "SMA_20": 100,
                "SMA_20_Slope_5": slope,
                "Previous_SMA20_Slope": prior,
                "Prior_Trend_Context": True,
            }
            for slope, prior in [(-1, 0), (-2, -1), (-3, -2), (1, -3), (-1, 1)]
        ]
    )
    episodes = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=ObservationParameters()
    )
    assert len(episodes) == 2
    assert episodes[0].ended_on == date(2024, 1, 5)
    assert episodes[1].started_on == date(2024, 1, 8)


def test_contraction_full_prefix_ids_and_final_status_match():
    from src.strategies.observations.detectors import evaluate_observations

    rows = [
        {"Contraction_Context": True, "Volume_Contraction_Ratio": v}
        for v in [0.6, 0.6, 0.9, 0.6, 0.9]
    ]
    params = ObservationParameters(contraction_ratio=0.7)
    full = evaluate_observations("TEST", features(rows), [], [], source_contexts=[], params=params)
    prefix = evaluate_observations(
        "TEST", features(rows[:2]), [], [], source_contexts=[], params=params
    )
    assert full[0].observation_id == prefix[0].observation_id
    assert prefix[0].status == ObservationStatus.ACTIVE
    assert full[0].status == ObservationStatus.RESOLVED
    assert prefix[0].ended_on is None


def test_structure_uses_confirmation_bar_and_has_no_source_dependency():
    from src.strategies.observations.detectors import evaluate_observations

    highs = [1, 2, 3, 6, 3, 2, 1, 2, 3, 8, 3, 2, 1]
    f = features([{"High": high, "Low": 0} for high in highs])
    episodes = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=ObservationParameters()
    )
    assert len(episodes) == 1
    event = episodes[0]
    assert event.code == ObservationCode.HIGHER_HIGH
    assert event.pivot_date == f.frame.index[9].date()
    assert event.confirmed_on == f.frame.index[12].date()
    unfinished = features([{"High": high, "Low": 0} for high in highs], True)
    preview = evaluate_observations(
        "TEST", unfinished, [], [], source_contexts=[], params=ObservationParameters()
    )
    assert len(preview) == 1 and preview[0].finality.value == "provisional"


@pytest.mark.parametrize(
    "complete,truncation_reason", [(False, None), (True, "instrument_history_incomplete")]
)
def test_supplied_incomplete_coverage_cannot_emit_structure_observations(
    complete, truncation_reason
):
    from src.strategies.models import CoverageManifest
    from src.strategies.observations.detectors import evaluate_observations

    highs = [1, 2, 3, 6, 3, 2, 1, 2, 3, 8, 3, 2, 1]
    f = features([{"High": high, "Low": 0} for high in highs])
    days = tuple(f.frame.index.date)
    coverage = CoverageManifest(
        requested_start=days[0],
        actual_start=days[0],
        actual_end=days[-1],
        expected_sessions=days,
        complete=complete,
        truncation_reason=truncation_reason,
    )
    history = evaluate_observations(
        "TEST",
        replace(f, coverage=coverage),
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(),
    )
    assert history == []


@pytest.mark.parametrize("unfinished_high", [138, 134])
def test_final_structure_ignores_middle_provisional_pivot_price_and_row(unfinished_high):
    from src.strategies.observations.detectors import evaluate_observations

    highs = [131, 132, 133, 136, 133, 132, 131, 132, 133, unfinished_high, 133, 132, 131]
    f = features([{"High": high, "Low": 128} for high in highs])
    finalities = list(f.finalities)
    finalities[9] = BarFinality.PROVISIONAL
    f = replace(f, finalities=tuple(finalities))
    history = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=ObservationParameters()
    )
    assert [(e.code, e.pivot_date, e.confirmed_on, e.finality.value) for e in history] == [
        (ObservationCode.LOWER_HIGH, date(2024, 1, 12), date(2024, 1, 18), "final")
    ]
    final_only = replace(
        f, frame=f.frame.drop(f.frame.index[9]), finalities=(BarFinality.FINAL,) * 12
    )
    assert history == evaluate_observations(
        "TEST", final_only, [], [], source_contexts=[], params=ObservationParameters()
    )
    preview = replace(f, finalities=(*f.finalities[:-1], BarFinality.PROVISIONAL))
    preview_history = evaluate_observations(
        "TEST", preview, [], [], source_contexts=[], params=ObservationParameters()
    )
    assert len(preview_history) == 1
    assert preview_history[0].finality.value == "provisional"
    assert preview_history[0].pivot_date == date(2024, 1, 12)


@pytest.mark.parametrize(
    "close, code, change",
    [(105, "UP_VOLUME_EXPANSION", 0.05), (95, "DOWN_VOLUME_EXPANSION", -0.05)],
)
def test_volume_event_preserves_price_volume_ratio_and_prior_reference(close, code, change):
    from src.strategies.observations.detectors import evaluate_observations

    f = features(
        [
            {
                "Close": close,
                "Previous_Close": 100,
                "Volume": 200,
                "Volume_Ratio_Prev20": 2,
                "Vol_SMA_20_Prev": 100,
            }
        ]
    )
    (event,) = evaluate_observations(
        "TEST",
        f,
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(up_volume_ratio=1.5, down_volume_ratio=1.5),
    )
    evidence = {item.code: item for item in event.evidence}
    assert event.code == code
    assert evidence[code].observed_value == 2
    assert evidence[code].reference_value == 1.5
    assert evidence["PRICE_CHANGE"].observed_value == pytest.approx(change)
    assert evidence["VOLUME"].observed_value == 200
    assert evidence["VOLUME_RATIO"].observed_value == 2
    assert evidence["REFERENCE_VOLUME"].observed_value == 100


def test_volume_event_does_not_estimate_missing_measured_volume():
    from src.strategies.observations.detectors import evaluate_observations

    f = features([{"Close": 105, "Previous_Close": 100, "Volume_Ratio_Prev20": 2}])
    (event,) = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=ObservationParameters(up_volume_ratio=1.5)
    )
    evidence = {item.code: item for item in event.evidence}
    assert evidence["VOLUME"].observed_value is None
    assert evidence["REFERENCE_VOLUME"].observed_value is None


def test_volume_evidence_uses_feature_reference_excluding_current_volume():
    from src.strategies.observations.detectors import evaluate_observations
    from src.strategies.swing_w150.features import build_swing_features
    from src.strategies.swing_w150.parameters import SwingW150Parameters

    raw = pd.DataFrame(
        {"Open": 100, "High": 106, "Low": 99, "Close": 100, "Volume": 100},
        index=pd.bdate_range("2024-01-02", periods=251),
    )
    raw.loc[raw.index[-1], ["Close", "Volume"]] = [105, 200]
    f = build_swing_features(raw, SwingW150Parameters())
    (event,) = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=ObservationParameters(up_volume_ratio=1.5)
    )
    evidence = {item.code: item.observed_value for item in event.evidence}
    assert evidence["VOLUME"] == 200
    assert evidence["VOLUME_RATIO"] == 2
    assert evidence["REFERENCE_VOLUME"] == 100


def test_distinct_sources_do_not_merge_same_day_breaches():
    from decimal import Decimal

    from src.strategies.models import (
        EntryOpportunityStatus,
        EntrySourceAnchors,
        ObservationSourceContext,
        SignalFinality,
        StrategySignal,
    )
    from src.strategies.observations.detectors import evaluate_observations
    from src.tools.technical.scorecard_models import Evidence, Importance

    contexts = []
    for identity in ["one", "two"]:
        signal = StrategySignal(
            signal_id=identity,
            strategy_id="TEST",
            strategy_version="TEST",
            parameter_set_version="TEST",
            parameter_fingerprint="TEST",
            code="TREND_BREAKOUT_ENTRY",
            occurred_on=date(2024, 1, 2),
            finality=SignalFinality.FINAL,
            direction=None,
            signal_price=Decimal(100),
            evidence=[
                Evidence(
                    code="test",
                    message="test",
                    observed_value=None,
                    reference_value=None,
                    importance=Importance.HIGH,
                    source="test",
                )
            ],
            data_status=DataStatus.COMPLETE,
        )
        anchors = EntrySourceAnchors(
            source_id=identity,
            source_date=signal.occurred_on,
            source_type=signal.code,
            signal_price=signal.signal_price,
            breakout_level=Decimal(100),
            anchor_finality=SignalFinality.FINAL,
            policy_version="test",
        )
        contexts.append(
            ObservationSourceContext(
                signal=signal,
                anchors=anchors,
                terminal_status=EntryOpportunityStatus.INVALIDATED,
                terminal_on=date(2024, 1, 3),
                terminal_reason="test",
            )
        )
    f = features([{"Close": close, "ATR": 2} for close in [99, 101, 99]])
    history = evaluate_observations(
        "TEST",
        f,
        [],
        [],
        source_contexts=contexts,
        params=ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0),
    )
    breaches = [item for item in history if item.code == ObservationCode.BREAKOUT_LEVEL_BREACH]
    reclaims = [item for item in history if item.code == ObservationCode.BREAKOUT_RECLAIM]
    assert len(breaches) == 4 and len(reclaims) == 2
    assert len({item.observation_id for item in history}) == 6
    assert all(item.source_terminal for item in reclaims)
    assert all(
        context.terminal_status == EntryOpportunityStatus.INVALIDATED for context in contexts
    )


def test_no_entry_source_still_emits_structure_and_volume():
    from src.strategies.observations.detectors import evaluate_observations

    highs = [1, 2, 3, 6, 3, 2, 1, 2, 3, 8, 3, 2, 1]
    rows = [{"High": high, "Low": 0} for high in highs]
    rows[-1].update(Close=101, Previous_Close=100, Volume_Ratio_Prev20=1.5)
    history = evaluate_observations(
        "TEST",
        features(rows),
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(up_volume_ratio=1.5),
    )
    assert {item.code.value for item in history} == {"HIGHER_HIGH", "UP_VOLUME_EXPANSION"}
    assert all(item.source_signal_id is None for item in history)


def test_continuous_episode_is_not_reemitted_daily_and_carries_origin_and_current_values():
    from src.strategies.observations.detectors import evaluate_observations

    history = evaluate_observations(
        "TEST",
        features(
            [
                {"Contraction_Context": True, "Volume_Contraction_Ratio": ratio}
                for ratio in [0.6, 0.5, 0.4]
            ]
        ),
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(contraction_ratio=0.7),
    )
    assert len(history) == 1
    assert history[0].started_on == date(2024, 1, 2)
    assert history[0].status_as_of == date(2024, 1, 4)
    values = {
        item.code: (item.observed_value, item.reference_value) for item in history[0].evidence
    }
    assert values["VOLUME_CONTRACTION"] == (0.6, 0.7)
    assert values["VOLUME_CONTRACTION_CURRENT"] == (0.4, 0.7)


def test_missing_features_are_not_normal_observations():
    from src.strategies.observations.detectors import evaluate_observations

    history = evaluate_observations(
        "TEST",
        features(
            [
                {"Contraction_Context": True, "Volume_Contraction_Ratio": 0.6},
                {"Contraction_Context": True, "Volume_Contraction_Ratio": None},
            ]
        ),
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(contraction_ratio=0.7),
    )
    assert len(history) == 1
    assert history[0].status == ObservationStatus.ACTIVE
    assert history[0].status_as_of == date(2024, 1, 2)


def test_provisional_breach_disappears_after_final_reclaim():
    from src.strategies.observations.detectors import evaluate_observations

    params = ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0)
    rows = [{"Close": close, "ATR": 2, "SMA_50": 100} for close in [101, 99]]
    preview = evaluate_observations(
        "TEST",
        features(rows, provisional=True),
        [],
        [],
        source_contexts=[],
        params=params,
    )
    assert len(preview) == 1 and preview[0].finality.value == "provisional"
    rows[-1]["Close"] = 101
    final = evaluate_observations(
        "TEST",
        features(rows),
        [],
        [],
        source_contexts=[],
        params=params,
    )
    assert final == []


def test_provisional_entry_source_is_preview_only():
    from decimal import Decimal

    from src.strategies.models import EntrySourceAnchors, ObservationSourceContext, SignalFinality
    from src.strategies.observations.detectors import evaluate_observations
    from tests.strategies.test_entry_anchors import _inputs

    source, _, _, _ = _inputs(finality=SignalFinality.PROVISIONAL)
    source = source.model_copy(update={"occurred_on": date(2024, 1, 3)})
    context = ObservationSourceContext(
        signal=source,
        anchors=EntrySourceAnchors(
            source_id=source.signal_id,
            source_date=source.occurred_on,
            source_type=source.code,
            signal_price=source.signal_price,
            breakout_level=Decimal(100),
            anchor_finality=source.finality,
            policy_version="test",
        ),
    )
    f = features([{"Close": close, "ATR": 2} for close in [101, 99]], provisional=True)
    history = evaluate_observations(
        "TEST",
        f,
        [source],
        [],
        source_contexts=[context],
        params=ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0),
    )
    assert len(history) == 1
    assert history[0].source_signal_id == source.signal_id
    assert history[0].finality == SignalFinality.PROVISIONAL
    assert source.finality == context.signal.finality == SignalFinality.PROVISIONAL
    prefix = SwingFeatureFrame(f.frame.iloc[:-1], f.data_status, (BarFinality.FINAL,))
    assert (
        evaluate_observations(
            "TEST",
            prefix,
            [source],
            [],
            source_contexts=[context],
            params=ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0),
        )
        == []
    )


def test_provisional_reclaim_keeps_final_breach_and_terminal_metadata_unmodified():
    from decimal import Decimal

    from src.strategies.models import (
        EntryOpportunityStatus,
        EntrySourceAnchors,
        ObservationSourceContext,
        SignalFinality,
    )
    from src.strategies.observations.detectors import evaluate_observations
    from tests.strategies.test_entry_anchors import _inputs

    source, _, _, _ = _inputs()
    source = source.model_copy(update={"occurred_on": date(2024, 1, 2)})
    context = ObservationSourceContext(
        signal=source,
        anchors=EntrySourceAnchors(
            source_id=source.signal_id,
            source_date=source.occurred_on,
            source_type=source.code,
            signal_price=source.signal_price,
            breakout_level=Decimal(100),
            anchor_finality=source.finality,
            policy_version="test",
        ),
        terminal_status=EntryOpportunityStatus.INVALIDATED,
        terminal_on=date(2024, 1, 3),
        terminal_reason="OVERHEAT_CORRECTION",
    )
    params = ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0)
    rows = [{"Close": close, "ATR": 2} for close in [99, 101]]
    confirmed = evaluate_observations(
        "TEST",
        features(rows[:1]),
        [source],
        [],
        source_contexts=[context],
        params=params,
    )
    preview = evaluate_observations(
        "TEST",
        features(rows, provisional=True),
        [source],
        [],
        source_contexts=[context],
        params=params,
    )
    assert preview[0] == confirmed[0]
    assert preview[0].status == ObservationStatus.ACTIVE
    assert preview[0].source_terminal is False
    assert preview[1].code == ObservationCode.BREAKOUT_RECLAIM
    assert preview[1].finality == SignalFinality.PROVISIONAL
    assert preview[1].source_terminal is True
    assert context.terminal_on == date(2024, 1, 3)


def test_missing_deceleration_features_preserve_last_confirmed_state():
    from src.strategies.observations.detectors import evaluate_observations

    history = evaluate_observations(
        "TEST",
        features(
            [
                {
                    "Close": 95,
                    "SMA_20": 100,
                    "SMA_20_Slope_5": -1,
                    "Previous_SMA20_Slope": 0,
                    "Prior_Trend_Context": True,
                },
                {
                    "Close": None,
                    "SMA_20": 100,
                    "SMA_20_Slope_5": None,
                    "Previous_SMA20_Slope": -1,
                    "Prior_Trend_Context": True,
                },
            ]
        ),
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(),
    )
    assert len(history) == 1
    assert history[0].status == ObservationStatus.ACTIVE
    assert history[0].status_as_of == date(2024, 1, 2)
    assert history[0].evidence[0].observed_value == 95
    assert history[0].evidence[0].reference_value == 100

"""현재 projection은 날짜·문맥·미평가를 보존하고 과거 신호를 승격하지 않는다."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date

import pytest

from src.strategies.models import SignalFinality
from tests.pipelines.test_observation_story import (
    BREACH,
    EXIT,
    TODAY,
    alab,
    analysis_for,
    observation,
    recovered_today,
)


def build(analysis):
    from src.pipelines.observation_current import build_current_observations

    return build_current_observations(analysis)


def test_linked_exit_has_priority_measurement_and_same_context_history():
    summary = build(alab())
    state = summary.states[0]
    assert state.title == "150일선 청산 조건 충족 후 미회복"
    assert state.measurement == "주가는 150일선보다 -20.97% 아래"
    assert state.next_check == "150일선 회복 여부"
    assert {row.day for row in state.history} >= {date(2026, 10, 28), BREACH, EXIT}
    assert any("2회 연속 종가 이탈" in row.text for row in state.history)
    assert any(
        "최근 확인된" in item.title and "고점 하락" in item.title and "저점 하락" in item.title
        for item in summary.states
    )


def test_old_active_retained_old_overheat_folded():
    origin = date(2026, 8, 20)
    analysis = analysis_for(
        [observation("SUPPORT_BREAK", origin)],
        signals=[
            ("SMA150_EXIT", date(2026, 8, 21), SignalFinality.FINAL),
            ("OVERHEAT", date(2026, 8, 19), SignalFinality.FINAL),
        ],
    )
    summary = build(analysis)
    assert "청산 조건 충족 후 미회복" in summary.states[0].title
    assert origin in [row.day for row in summary.states[0].history]
    assert not any("과열" in item.title for item in summary.states)
    assert not any("과열" in warning for warning in summary.warnings)


def test_exit_unknown_visible():
    summary = build(analysis_for(signals=[("SMA150_EXIT", EXIT, SignalFinality.FINAL)]))
    assert not any("청산 조건 충족 후 미회복" in item.title for item in summary.states)
    assert any("청산 상태 확인 불가" in text for text in summary.warnings)


def test_recovery_rebreach_contexts_remain_separate():
    analysis = recovered_today()
    other = observation("SUPPORT_BREAK", TODAY, source_signal_id="other-source")
    analysis.strategy_run.signal_bundles[0].observation_history.append(other)
    summary = build(analysis)
    recovery, breach = summary.states[:2]
    assert "당일 회복 확인" in recovery.title and "이탈 관찰" in breach.title
    assert recovery.context != breach.context
    assert not any("회복 확인" in row.text for row in breach.history)
    assert any("청산 상태 확인 불가" in text for text in summary.warnings)
    assert not any("이탈 관찰 종료" in row.text for row in recovery.history)


@pytest.mark.parametrize("mode", ["provisional", "mismatch", "partial", "stale"])
def test_provisional_and_mismatch_not_promoted(mode):
    from src.tools.technical.scorecard_models import DataStatus

    analysis = alab()
    bundle = analysis.strategy_run.signal_bundles[0]
    if mode == "provisional":
        bundle.entry_opportunity.finality = SignalFinality.PROVISIONAL
    elif mode == "mismatch":
        bundle.as_of = EXIT
    elif mode == "partial":
        bundle.data_status = DataStatus.PARTIAL
    else:
        bundle.observation_history[-3].status_as_of = EXIT
    summary = build(analysis)
    assert not any("청산 조건 충족 후 미회복" in item.title for item in summary.states)
    assert any("미평가" in warning for warning in summary.warnings)
    if mode == "provisional":
        assert summary.finality is SignalFinality.PROVISIONAL


def test_current_projection_preserves_input_and_default_text():
    from src.pipelines.quick_check import QuickCheckPipeline
    from tests.pipelines.test_check_html import result_for

    analysis = alab()
    result = result_for(analysis)
    before = deepcopy(asdict(analysis))
    text = QuickCheckPipeline(None).format_output(result)
    build(analysis)
    assert before == asdict(analysis)
    assert text == QuickCheckPipeline(None).format_output(result)
    mismatch = replace(analysis, scorecard=analysis.scorecard.model_copy(update={"as_of": EXIT}))
    assert "평가일 불일치" in " ".join(build(mismatch).warnings)


@pytest.mark.parametrize("field", ["anchor_id", "source_signal_id", "cycle_id"])
def test_same_day_recovery_does_not_clear_another_exit_context(field):
    summary = build(recovered_today(**{field: "different-context"}))
    assert any("당일 회복 확인" in state.title for state in summary.states)
    assert any("청산 상태 확인 불가" in text for text in summary.warnings)


def test_confirmed_today_signal_requires_owner_and_complete_evaluation():
    from src.tools.technical.scorecard_models import DataStatus

    analysis = analysis_for(signals=[("OVERHEAT", TODAY, SignalFinality.FINAL)])
    assert any(state.title == "과열 조건 도달 · 당일 신호" for state in build(analysis).states)
    bundle = analysis.strategy_run.signal_bundles[0]
    bundle.signal_history[0].data_status = DataStatus.PARTIAL
    assert not build(analysis).states
    assert any("당일 변화 잠정·데이터 미평가" in text for text in build(analysis).warnings)
    bundle.signal_history[0].data_status = DataStatus.COMPLETE
    bundle.signal_history[0].strategy_id = "DIFFERENT_OWNER"
    assert not build(analysis).states


def test_event_requires_resolved_status_before_becoming_today_change():
    from src.strategies.models import ObservationStatus
    from tests.pipelines.test_observation_story import event

    item = event("UP_VOLUME_EXPANSION", TODAY, anchor=None)
    analysis = analysis_for([item])
    assert any("당일 확인" in state.title for state in build(analysis).states)
    item.status = ObservationStatus.ACTIVE
    item.ended_on = None
    assert not any("당일 확인" in state.title for state in build(analysis).states)
    assert any("당일 변화 미평가" in text for text in build(analysis).warnings)


def test_provisional_today_does_not_relabel_confirmed_past_structure():
    analysis = alab()
    analysis.strategy_run.signal_bundles[0].entry_opportunity.finality = SignalFinality.PROVISIONAL
    summary = build(analysis)
    structure = next(state for state in summary.states if "최근 확인된" in state.title)
    assert summary.finality is SignalFinality.PROVISIONAL
    assert structure.finality is SignalFinality.FINAL
    assert not structure.warnings
    assert all(row.finality is SignalFinality.FINAL for row in structure.history)


@pytest.mark.parametrize("code", ["SUPPORT_RECLAIM", "BREAKOUT_RECLAIM"])
@pytest.mark.parametrize("reason", ["provisional", "missing_measurement"])
def test_unconfirmed_today_recovery_stays_visible_alongside_confirmed_structure(code, reason):
    from tests.pipelines.test_observation_render import _evidence
    from tests.pipelines.test_observation_story import event

    item = event(
        code,
        TODAY,
        finality=SignalFinality.PROVISIONAL if reason == "provisional" else SignalFinality.FINAL,
        evidence=[_evidence("UNRELATED", 233.62, 200)]
        if reason == "missing_measurement"
        else [_evidence(code, 233.62, 200)],
        source_signal_id="recovery-source",
        cycle_id="recovery-cycle",
    )
    summary = build(analysis_for([item, event("LOWER_HIGH", TODAY, anchor=None)]))
    assert any("최근 확인된 고점 하락" in state.title for state in summary.states)
    assert any("당일 회복 미평가" in warning for warning in summary.warnings)
    assert not any("당일 회복 확인" in state.title for state in summary.states)
    recovery = next(state for state in summary.states if "회복 미평가" in state.title)
    assert recovery.context[-2:] == ("recovery-source", "recovery-cycle")
    assert recovery.history and any(
        row.source_id == item.observation_id for row in recovery.history
    )
    assert summary.finality is (
        SignalFinality.PROVISIONAL if reason == "provisional" else SignalFinality.FINAL
    )


def detector_reacceleration_analysis():
    from src.strategies.observations.detectors import evaluate_observations
    from src.strategies.observations.parameters import PRODUCT_OBSERVATION_PARAMETERS
    from tests.strategies.test_observations import features

    history = evaluate_observations(
        "ALAB",
        features(
            [
                {
                    "Close": 101,
                    "SMA_20": 100,
                    "SMA_20_Slope_5": 1,
                    "Previous_SMA20_Slope": -1,
                    "Prior_Trend_Context": True,
                    "Prior_Below_SMA20": True,
                }
            ]
        ),
        [],
        [],
        source_contexts=[],
        params=PRODUCT_OBSERVATION_PARAMETERS,
    )
    return replace(analysis_for(history, today=history[0].status_as_of), current_close=101)


def test_real_detector_zero_slope_reference_remains_confirmed_current_change():
    from src.strategies.models import ObservationStatus

    analysis = detector_reacceleration_analysis()
    (item,) = analysis.strategy_run.signal_bundles[0].observation_history
    assert item.code == "MOMENTUM_REACCELERATION"
    assert item.finality is SignalFinality.FINAL and item.status is ObservationStatus.RESOLVED
    assert (item.evidence[0].observed_value, item.evidence[0].reference_value) == (1.0, 0.0)
    summary = build(analysis)
    assert any(state.title == "상승 모멘텀 재가속 · 당일 확인" for state in summary.states)
    assert not summary.warnings


def provisional_change_analysis(kind, scope="current"):
    from datetime import timedelta

    from tests.pipelines.test_observation_story import event

    changed_day = (
        TODAY - timedelta(days=1)
        if scope == "past"
        else TODAY + timedelta(days=1)
        if scope == "future"
        else TODAY
    )
    structure = event("LOWER_HIGH", EXIT, anchor=None)
    if kind == "event":
        change = event(
            "UP_VOLUME_EXPANSION",
            changed_day,
            finality=SignalFinality.PROVISIONAL,
            status_as_of=changed_day,
        )
        analysis = analysis_for([structure, change])
        if scope == "terminal":
            change.source_terminal = True
        elif scope == "stale":
            change.status_as_of = EXIT
    else:
        analysis = analysis_for(
            [structure], signals=[("OVERHEAT", changed_day, SignalFinality.PROVISIONAL)]
        )
        if scope == "other_owner":
            analysis.strategy_run.signal_bundles[0].signal_history[0].strategy_id = "OTHER_OWNER"
    if scope == "bundle_mismatch":
        analysis.strategy_run.signal_bundles[0].as_of = EXIT
    return analysis


@pytest.mark.parametrize("kind", ["event", "signal"])
def test_today_provisional_change_sets_summary_finality_without_relabeling_past_structure(kind):
    summary = build(provisional_change_analysis(kind))
    assert summary.finality is SignalFinality.PROVISIONAL
    assert any("잠정" in warning for warning in summary.warnings)
    structure = next(state for state in summary.states if "최근 확인된" in state.title)
    assert structure.finality is SignalFinality.FINAL and not structure.warnings


@pytest.mark.parametrize(
    "kind,scope",
    [
        ("event", "past"),
        ("event", "future"),
        ("event", "terminal"),
        ("event", "stale"),
        ("event", "bundle_mismatch"),
        ("signal", "past"),
        ("signal", "future"),
        ("signal", "other_owner"),
        ("signal", "bundle_mismatch"),
    ],
)
def test_excluded_provisional_change_does_not_change_current_finality(kind, scope):
    assert build(provisional_change_analysis(kind, scope)).finality is SignalFinality.FINAL

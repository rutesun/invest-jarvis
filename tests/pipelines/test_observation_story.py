"""현재 episode에 연결된 상태와 거래일 관찰 흐름의 표시 계약."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from src.pipelines.analysis_overview import render_analysis_overview
from src.pipelines.quick_check import QuickCheckPipeline
from src.pipelines.strategy_render import render_strategy_sections
from src.position.models import DirectiveKind, PositionDirective, PositionPlan, QuantityStatus
from src.strategies.models import ObservationCode, ObservationStatus, SignalFinality
from src.tools.technical.scorecard_models import DataStatus
from tests.pipelines.test_observation_render import _analysis, _evidence, _observation


TODAY = date(2026, 11, 3)
RECLAIM = date(2026, 10, 28)
BREACH = date(2026, 10, 29)
EXIT = date(2026, 10, 30)


def observation(code, origin, *, anchor="SMA150", **kwargs):
    return _observation(
        ObservationCode(code),
        day=origin,
        status_as_of=kwargs.pop("status_as_of", TODAY),
        anchor_type=kwargs.pop("anchor_type", anchor),
        anchor_id=anchor,
        evidence=kwargs.pop("evidence", [_evidence(code + "_CURRENT", 233.62, 295.60)]),
        **kwargs,
    )


def event(code, occurred, *, confirmed=None, **kwargs):
    return observation(
        code,
        occurred,
        confirmed_on=confirmed or occurred,
        ended_on=confirmed or occurred,
        status=ObservationStatus.RESOLVED,
        **kwargs,
    )


def analysis_for(items=(), *, signals=(), today=TODAY):
    base = _analysis(items)
    run = base.strategy_run
    sample = run.signal_bundles[0].signal_history[0]
    card = base.scorecard.model_copy(update={"as_of": today})
    run.as_of = today
    run.scorecard = card
    bundle = run.signal_bundles[0]
    bundle.as_of = today
    bundle.entry_opportunity.evaluation_as_of = today
    bundle.signal_history = [
        sample.model_copy(
            update={
                "code": code,
                "signal_id": f"{code}:{day}",
                "occurred_on": day,
                "finality": finality,
                "signal_price": Decimal("233.62"),
                "evidence": [
                    _evidence(code, 233.62, 295.60),
                    *(
                        [_evidence("CONSECUTIVE_BELOW_SMA150", 2, 2)]
                        if code == "SMA150_EXIT"
                        else []
                    ),
                ],
            }
        )
        for code, day, finality in signals
    ]
    bundle.current_signals = [s for s in bundle.signal_history if s.occurred_on == today]
    sessions = tuple(d.date() for d in pd.bdate_range(end=today, periods=40))
    return replace(base, scorecard=card, current_close=233.62, exchange_sessions=sessions)


def alab():
    return analysis_for(
        [
            observation(
                "SUPPORT_BREAK",
                date(2026, 10, 20),
                ended_on=RECLAIM,
                status=ObservationStatus.RESOLVED,
            ),
            event("SUPPORT_RECLAIM", RECLAIM),
            observation("SUPPORT_BREAK", BREACH),
            event("LOWER_LOW", BREACH, anchor=None, pivot_date=date(2026, 10, 26)),
            event("LOWER_HIGH", date(2026, 11, 2), anchor=None),
        ],
        signals=[("SMA150_EXIT", EXIT, SignalFinality.FINAL)],
    )


def story(analysis, **kwargs):
    from src.pipelines.observation_story import render_observation_story

    return render_observation_story(analysis, **kwargs)


def state(output):
    return output.split("### 현재 유효 상태")[1].split("### 관찰 흐름")[0]


def test_current_unrecovered_exit_is_linked_to_current_episode_and_structure_is_separate():
    output = story(alab())
    current = state(output)
    assert "150일선: 청산 조건 충족 후 미회복" in current
    assert "조건 충족 2026-10-30" in current and "현재 확인 2026-11-03" in current
    assert "$233.62" in current and "$295.60" in current
    assert "-20.97%" in current and "+26.53%" in current
    assert "가격 구조" in current and "저점 하락" in current and "고점 하락" in current
    flow = output.split("### 관찰 흐름")[1]
    assert flow.index(str(RECLAIM)) < flow.index(str(BREACH)) < flow.index(str(EXIT))
    assert "청산 조건 충족" in flow and "현재 확인" in flow
    assert "2회 연속 종가 이탈" in flow
    assert "발생일 2026-10-29" in flow and "저점일 2026-10-26" in flow
    assert "실제 매도 완료" not in output
    assert "Technical Score" not in output


def test_recovery_then_first_rebreach_does_not_inherit_old_exit():
    analysis = analysis_for(
        [event("SUPPORT_RECLAIM", date(2026, 11, 2)), observation("SUPPORT_BREAK", TODAY)],
        signals=[("SMA150_EXIT", EXIT, SignalFinality.FINAL)],
    )
    current = state(story(analysis))
    assert "청산 조건 충족 후 미회복" not in current
    assert "150일선: 이탈 관찰" in current
    assert "현재 이탈의 청산 조건 지속 여부 미평가" in current


def test_old_exit_without_explicit_current_episode_is_not_current_exit_state():
    analysis = analysis_for(signals=[("SMA150_EXIT", EXIT, SignalFinality.FINAL)])
    current = state(story(analysis))
    assert "청산 조건 충족 후 미회복" not in current
    assert "지속 여부 미평가" in current


@pytest.mark.parametrize(
    "updates",
    [
        {"status_as_of": TODAY - timedelta(days=1)},
        {"status_as_of": TODAY + timedelta(days=1)},
        {"started_on": TODAY + timedelta(days=1)},
        {"confirmed_on": TODAY + timedelta(days=1)},
        {"ended_on": TODAY + timedelta(days=1)},
    ],
)
def test_stale_or_future_episode_cannot_prove_persistent_exit(updates):
    item = observation("SUPPORT_BREAK", BREACH).model_copy(update=updates)
    analysis = analysis_for([item], signals=[("SMA150_EXIT", EXIT, SignalFinality.FINAL)])
    current = state(story(analysis))
    assert "청산 조건 충족 후 미회복" not in current
    assert "미평가" in current


def test_provisional_signal_and_observation_are_not_promoted_to_confirmed_exit():
    item = observation("SUPPORT_BREAK", BREACH, finality=SignalFinality.PROVISIONAL)
    analysis = analysis_for([item], signals=[("SMA150_EXIT", EXIT, SignalFinality.PROVISIONAL)])
    current = state(story(analysis))
    assert "잠정" in current
    assert "150일선: 청산 조건 충족 후 미회복" not in current
    assert "확정 상태 미평가" in current


def test_provisional_evaluation_does_not_publish_a_confirmed_current_measurement():
    analysis = alab()
    analysis.strategy_run.signal_bundles[0].entry_opportunity.finality = SignalFinality.PROVISIONAL
    output = story(analysis)
    current = state(output)
    assert "150일선: 청산 조건 충족 후 미회복" not in current
    assert "현재가격 $233.62" in current and "잠정" in current
    flow = output.split("### 관찰 흐름")[1]
    current_update = next(line for line in flow.splitlines() if "현재 확인" in line)
    assert "(잠정)" in current_update


def test_future_pivot_is_not_used_as_current_structure_evidence():
    future = TODAY + timedelta(days=1)
    analysis = analysis_for([event("LOWER_HIGH", TODAY, anchor=None, pivot_date=future)])
    output = story(analysis)
    assert str(future) not in output
    assert "고점 하락" not in state(output)


def test_current_valid_episode_without_current_measurement_does_not_prove_exit_persistence():
    item = observation("SUPPORT_BREAK", BREACH, evidence=[_evidence("SUPPORT_BREAK", 230, 290)])
    current = state(
        story(analysis_for([item], signals=[("SMA150_EXIT", EXIT, SignalFinality.FINAL)]))
    )
    assert "청산 조건 충족 후 미회복" not in current
    assert "실측" in current and "미평가" in current


@pytest.mark.parametrize("incomplete", ["signal", "bundle"])
def test_incomplete_evaluation_cannot_prove_current_exit_persistence(incomplete):
    analysis = alab()
    bundle = analysis.strategy_run.signal_bundles[0]
    if incomplete == "signal":
        bundle.signal_history[0].data_status = DataStatus.PARTIAL
    else:
        bundle.data_status = DataStatus.PARTIAL
    current = state(story(analysis))
    assert "150일선: 청산 조건 충족 후 미회복" not in current
    assert "미평가" in current


def test_future_or_mismatched_analysis_date_does_not_publish_current_state():
    analysis = alab()
    card = analysis.scorecard.model_copy(update={"as_of": TODAY - timedelta(days=1)})
    current = state(story(replace(analysis, scorecard=card)))
    assert "150일선: 청산 조건 충족 후 미회복" not in current
    assert "평가일 불일치" in current


def test_matching_recovery_collapses_only_same_anchor_and_date():
    ended = observation("SUPPORT_BREAK", BREACH, ended_on=TODAY, status=ObservationStatus.RESOLVED)
    other = observation(
        "SUPPORT_BREAK",
        BREACH,
        anchor="another",
        anchor_type="SMA150",
        ended_on=TODAY,
        status=ObservationStatus.RESOLVED,
    )
    output = story(analysis_for([ended, other, event("SUPPORT_RECLAIM", TODAY)]))
    flow = output.split("### 관찰 흐름")[1]
    assert flow.count("150일선 회복 확인") == 1
    assert flow.count("이탈 관찰 종료") == 1  # another anchor의 종료는 별도 보존


def test_different_date_recovery_does_not_erase_episode_end():
    ended = observation("SUPPORT_BREAK", BREACH, ended_on=EXIT, status=ObservationStatus.RESOLVED)
    output = story(analysis_for([ended, event("SUPPORT_RECLAIM", TODAY)]))
    assert "이탈 관찰 종료" in output.split("### 관찰 흐름")[1]
    assert "150일선 회복 확인" in output


def test_recent_returned_sessions_include_old_active_origin_and_linked_exit():
    origin, exit_day = date(2026, 8, 20), date(2026, 8, 21)
    recent = event("LOWER_HIGH", date(2026, 10, 8), anchor=None)
    old = event("LOWER_HIGH", date(2026, 9, 1), anchor=None)
    analysis = analysis_for(
        [observation("SUPPORT_BREAK", origin), old, recent],
        signals=[("SMA150_EXIT", exit_day, SignalFinality.FINAL)],
    )
    output = story(analysis)
    flow = output.split("### 관찰 흐름")[1]
    assert "최근 20개 반환 거래일" in flow
    assert "2026-08-20" in flow and "2026-08-21" in flow
    assert "기간 밖 현재 상태 근거" in flow
    assert "2026-10-08" in flow and "2026-09-01" not in flow


def test_future_events_and_signals_are_not_present_in_history():
    tomorrow = TODAY + timedelta(days=1)
    analysis = analysis_for(
        [event("LOWER_HIGH", TODAY, confirmed=tomorrow, anchor=None)],
        signals=[("SMA150_EXIT", tomorrow, SignalFinality.FINAL)],
    )
    output = story(analysis)
    assert str(tomorrow) not in output
    assert "150일선 청산 조건 충족" not in output
    assert "미평가" in output


def test_missing_or_disabled_observation_evaluation_is_explicit():
    analysis = analysis_for()
    bundle = analysis.strategy_run.signal_bundles[0]
    bundle.observations_enabled = False
    output = story(analysis)
    assert "비활성" in output and "미평가" in output
    assert "위험 없음" not in output


def test_latest_high_and_low_contexts_do_not_overwrite_each_other_or_overheat():
    analysis = analysis_for(
        [
            event("LOWER_LOW", BREACH, anchor=None),
            event("LOWER_HIGH", EXIT, anchor=None),
            observation("POST_OVERHEAT_RECOVERY_WATCH", date(2026, 11, 2), anchor=None),
        ],
        signals=[
            ("OVERHEAT", RECLAIM, SignalFinality.FINAL),
            ("OVERHEAT_CORRECTION", date(2026, 11, 2), SignalFinality.FINAL),
        ],
    )
    current = state(story(analysis))
    assert "가격 구조" in current and "저점 하락" in current and "고점 하락" in current
    assert "과열" in current and "회복 관찰" in current


def test_story_and_expanded_overview_preserve_all_input_payloads():
    analysis = alab()
    plan = PositionPlan(
        PositionDirective(DirectiveKind.KEEP_CURRENT), 42, 42, 0, 0, QuantityStatus.AVAILABLE
    )
    analysis = replace(analysis, position_plans={"SWING_W150": plan})
    before = deepcopy(asdict(analysis))
    story(analysis)
    output = render_analysis_overview(analysis.scorecard, analysis, expanded_observations=True)
    assert asdict(analysis) == before
    assert "오늘 신규 매매 지시 없음" in output
    assert "보유 수량 유지" in output
    assert "| 42 | 42 | 0 | 0 |" in output
    assert analysis.position_plans["SWING_W150"] is plan


def test_check_expansion_precedes_quality_and_deduplicates_only_observation_bullets():
    analysis = alab()
    output = render_analysis_overview(analysis.scorecard, analysis, expanded_observations=True)
    assert (
        output.index("### 현재 유효 상태")
        < output.index("### 관찰 흐름")
        < output.index("### 차트 상태 점수(Quality)")
    )
    five = output.split("### 최근 5거래일")[1].split("### 전략별 대응")[0]
    assert "주요 관찰 변화" in five and "SWING 청산" in five
    table = five.split("**핵심 변화**")[0]
    assert len([line for line in table.splitlines() if line.startswith("| 2026-")]) == 5
    assert "150일선 청산 조건 충족 (확정)" not in five
    assert "Technical Score" in five
    plain = render_analysis_overview(analysis.scorecard, analysis)
    assert "### 관찰 흐름" not in plain
    assert render_analysis_overview(
        analysis.scorecard, analysis, expanded_observations=True, detail=True
    ) == render_strategy_sections(analysis.scorecard, analysis, detail=True)


def test_check_uses_expanded_story_and_currency_without_changing_analysis_scope():
    analysis = alab()
    card = analysis.scorecard.model_copy(update={"ticker": "161890.KS"})
    analysis = replace(analysis, scorecard=card)
    result = {
        "success": True,
        "ticker": "161890.KS",
        "scorecard": card,
        "strategy_analysis": analysis,
    }
    output = QuickCheckPipeline(None).format_output(result)
    assert "### 현재 유효 상태" in output and "### 관찰 흐름" in output
    assert "₩233.62" in output and "₩295.60" in output
    assert "$233.62" not in output and "$295.60" not in output
    assert "+26.53%" in output and "상승 필요" in output


def recovered_today(*, code="SUPPORT_RECLAIM", anchor="SMA150", **updates):
    ended = observation(
        "SUPPORT_BREAK" if code == "SUPPORT_RECLAIM" else "BREAKOUT_LEVEL_BREACH",
        BREACH,
        anchor=anchor,
        ended_on=TODAY,
        status=ObservationStatus.RESOLVED,
    )
    recovery = event(code, TODAY, anchor=anchor, evidence=[_evidence(code, 300, 295.6)])
    recovery = recovery.model_copy(update=updates)
    analysis = analysis_for(
        [ended, recovery], signals=[("SMA150_EXIT", EXIT, SignalFinality.FINAL)]
    )
    return replace(analysis, current_close=300)


@pytest.mark.parametrize(
    ("code", "anchor", "label"),
    [
        ("SUPPORT_RECLAIM", "SMA150", "150일선"),
        ("BREAKOUT_RECLAIM", "PRIOR_BREAKOUT_LEVEL", "돌파 기준"),
    ],
)
def test_same_day_confirmed_recovery_is_current_state_not_unknown(code, anchor, label):
    analysis = recovered_today(code=code, anchor=anchor)
    output = story(analysis)
    current = state(output)
    assert f"{label}: 당일 회복 확인" in current
    assert "2026-11-03 · 확정" in current
    assert "$300.00" in current and "$295.60" in current
    if anchor == "SMA150":
        assert "현재 청산 조건 지속 여부 미평가" not in current
    flow = output.split("### 관찰 흐름")[1]
    assert flow.count(f"{label} 회복 확인") == 1
    assert "이탈 관찰 종료" not in flow


@pytest.mark.parametrize(
    "updates",
    [
        {"status_as_of": TODAY - timedelta(days=1)},
        {"status_as_of": TODAY + timedelta(days=1)},
        {"confirmed_on": TODAY + timedelta(days=1)},
        {"started_on": TODAY + timedelta(days=1)},
        {"finality": SignalFinality.PROVISIONAL},
    ],
)
def test_stale_future_or_provisional_recovery_does_not_clear_exit_uncertainty(updates):
    current = state(story(recovered_today(**updates)))
    assert "150일선: 당일 회복 확인" not in current
    assert "현재 청산 조건 지속 여부 미평가" in current


@pytest.mark.parametrize("field", ["anchor_id", "source_signal_id", "cycle_id"])
def test_recovery_different_context_cannot_clear_other_exit_uncertainty(field):
    analysis = recovered_today(**{field: "different-context"})
    current = state(story(analysis))
    assert "150일선: 당일 회복 확인" in current
    assert "현재 청산 조건 지속 여부 미평가" in current


def test_yesterdays_recovery_does_not_establish_current_recovered_state():
    yesterday = TODAY - timedelta(days=1)
    analysis = recovered_today(
        started_on=yesterday, confirmed_on=yesterday, ended_on=yesterday, status_as_of=yesterday
    )
    current = state(story(analysis))
    assert "당일 회복 확인" not in current
    assert "현재 청산 조건 지속 여부 미평가" in current


def test_same_day_recovery_keeps_other_current_breach_context_unassessed_and_payload_unchanged():
    analysis = recovered_today()
    bundle = analysis.strategy_run.signal_bundles[0]
    other = observation(
        "SUPPORT_BREAK",
        TODAY,
        source_signal_id="other-source",
        evidence=[_evidence("SUPPORT_BREAK_CURRENT", 300, 320)],
    )
    bundle.observation_history.append(other)
    plan = PositionPlan(
        PositionDirective(DirectiveKind.KEEP_CURRENT), 42, 42, 0, 0, QuantityStatus.AVAILABLE
    )
    analysis = replace(analysis, position_plans={"SWING_W150": plan})
    before = deepcopy(asdict(analysis))
    current = state(story(analysis))
    assert "150일선: 당일 회복 확인" in current
    assert "현재 이탈의 청산 조건 지속 여부 미평가" in current
    assert "청산 조건 충족 후 미회복" not in current
    output = render_analysis_overview(analysis.scorecard, analysis, expanded_observations=True)
    assert "| 42 | 42 | 0 | 0 |" in output
    assert asdict(analysis) == before

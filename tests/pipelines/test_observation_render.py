"""Observation display distinguishes setup, current episodes, events and uncertainty."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal

import pytest

from src.pipelines.strategy_analysis import AnalysisStrategyResult
from src.pipelines.strategy_render import render_strategy_sections
from src.strategies.models import (
    EntryOpportunityStatus,
    ObservationCode,
    ObservationStatus,
    SignalFinality,
)
from src.strategies.observations import make_observation
from src.strategies.observations.parameters import PRODUCT_OBSERVATION_PARAMETERS
from src.tools.technical.scorecard_models import Evidence, Importance
from tests.storage.test_entry_shadow import decision_inputs


def _evidence(code="SUPPORT_DISTANCE", value=102, reference=100, *, importance=Importance.HIGH):
    return Evidence(
        code=code,
        message=f"{code} measured",
        observed_value=value,
        reference_value=reference,
        importance=importance,
        source="OBSERVATION_V1",
    )


def _observation(code, day=date(2026, 9, 2), **context):
    return make_observation(
        ticker="AAPL",
        code=code,
        origin=day,
        params=context.pop("params", PRODUCT_OBSERVATION_PARAMETERS),
        evidence=context.pop("evidence", [_evidence()]),
        **context,
    )


def _analysis(observations=()):
    run, chart = decision_inputs()
    bundle = run.signal_bundles[0]
    bundle.observation_history = list(observations)
    bundle.observations_enabled = True
    bundle.observation_parameters = asdict(PRODUCT_OBSERVATION_PARAMETERS)
    bundle.pullback_policy_inactive_reason = "V2_FAILURE_RESTART_UNRESOLVED"
    scorecard = run.scorecard.model_copy(deep=True)
    scorecard.trend.metrics["supertrend_direction"] = -1
    run.scorecard = scorecard
    return AnalysisStrategyResult(
        scorecard,
        run,
        tuple(date(2026, 9, day) for day in (1, 2)),
        99,
    )


def test_custom_volume_event_renders_actual_price_volume_and_reference():
    from src.strategies.observations.detectors import evaluate_observations
    from src.strategies.observations.parameters import ObservationParameters
    from tests.strategies.test_observations import features

    f = features(
        [
            {
                "Close": 105,
                "Previous_Close": 100,
                "Volume": 200,
                "Volume_Ratio_Prev20": 2,
                "Vol_SMA_20_Prev": 100,
            }
        ]
    )
    (event,) = evaluate_observations(
        "AAPL", f, [], [], source_contexts=[], params=ObservationParameters(up_volume_ratio=1.5)
    )
    analysis = _analysis([event])
    output = render_strategy_sections(analysis.scorecard, analysis, detail=True)
    assert "UP_VOLUME_EXPANSION" in output
    for label, measured in [
        ("price change", "0.05"),
        ("volume", "200"),
        ("volume ratio", "2"),
        ("reference volume", "100"),
    ]:
        line = next(line for line in output.splitlines() if f": {label} (" in line)
        assert f"관측값={measured}" in line
    threshold = next(line for line in output.splitlines() if ": up volume expansion (" in line)
    assert "관측값=2" in threshold and "기준값=1.5" in threshold


def test_default_render_explains_sma150_watch_with_supertrend_warning():
    watch = _observation(
        ObservationCode.PULLBACK_WATCH,
        finality=SignalFinality.PROVISIONAL,
        anchor_id="sma150",
        anchor_type="SMA150",
        anchor_origin_on=date(2026, 8, 3),
        anchor_origin_price=Decimal("95"),
        source_signal_id="source",
        evidence=[_evidence(), _evidence("SUPPORT_DISTANCE_CURRENT", 99, 98)],
    )
    analysis = _analysis([watch])
    before = analysis.strategy_run.model_dump(mode="json")
    output = render_strategy_sections(analysis.scorecard, analysis)

    assert "눌림목 지지 관찰" in output
    assert "Supertrend DOWN" in output
    assert "Technical Evidence 경고" in output
    assert "[PROVISIONAL]" in output
    assert "anchor=SMA150" in output
    assert "origin=2026-08-03@95" in output
    assert "source=source" in output
    assert "관측값=102" in output and "기준값=100" in output
    assert "현재 실측" in output and "관측값=99" in output and "기준값=98" in output
    assert "V2_FAILURE_RESTART_UNRESOLVED" in output
    assert analysis.strategy_run.model_dump(mode="json") == before


def test_event_is_history_not_persistent_active():
    event = _observation(
        ObservationCode.HIGHER_HIGH,
        day=date(2026, 9, 1),
        status=ObservationStatus.RESOLVED,
        ended_on=date(2026, 9, 1),
        confirmed_on=date(2026, 9, 1),
        pivot_date=date(2026, 8, 27),
    )
    analysis = _analysis([event])
    output = render_strategy_sections(analysis.scorecard, analysis)
    current = output.split("### 현재 Observation\n")[1].split("### 최근 Observation history")[0]
    history = output.split("### 최근 Observation history")[1].split("### 최근 Signal history")[0]
    assert "HIGHER_HIGH" not in current.split("#### 평가 상태")[0]
    assert "당일 EVENT" in current
    assert "HIGHER_HIGH" in history
    assert "pivot=2026-08-27" in history and "확인일=2026-09-01" in history
    assert "EVENT" in history


def test_unresolved_detector_is_not_rendered_as_no_risk():
    analysis = _analysis()
    output = render_strategy_sections(analysis.scorecard, analysis)
    current = output.split("### 현재 Observation\n")[1].split("### 최근 Observation history")[0]
    assert "DOWN_VOLUME_EXPANSION" in current
    assert "UNRESOLVED" in current and "미평가" in current
    assert "detector" in current and "predictive usefulness=UNRESOLVED" in current
    assert "위험 없음" not in current
    assert "없음 또는 평가 불가" not in current


def test_custom_disabled_and_unknown_evaluation_are_distinct():
    analysis = _analysis()
    bundle = analysis.strategy_run.signal_bundles[0]
    bundle.observation_parameters["down_volume_ratio"] = 2.5
    custom = render_strategy_sections(analysis.scorecard, analysis)
    assert "down_volume_ratio=2.5" in custom
    assert "detector=UNRESOLVED" in custom  # registry validity remains independent
    bundle.observations_enabled = False
    disabled = render_strategy_sections(analysis.scorecard, analysis)
    assert "미평가 — Observation 비활성(OFF)" in disabled
    bundle.observations_enabled = None
    bundle.observation_parameters = None
    unknown = render_strategy_sections(analysis.scorecard, analysis)
    assert "미평가 — 평가 설정 확인 불가" in unknown


@pytest.mark.parametrize("break_buffer,reclaim_buffer", [(0.0, None), (None, 0.0)])
@pytest.mark.parametrize(
    "code",
    [
        "BREAKOUT_LEVEL_BREACH",
        "SUPPORT_BREAK",
        "PULLBACK_LOW_BREACH",
        "BREAKOUT_RECLAIM",
        "SUPPORT_RECLAIM",
    ],
)
def test_partial_break_reclaim_settings_are_unevaluated(code, break_buffer, reclaim_buffer):
    analysis = _analysis()
    params = analysis.strategy_run.signal_bundles[0].observation_parameters
    params["break_buffer_atr"] = break_buffer
    params["reclaim_buffer_atr"] = reclaim_buffer
    output = render_strategy_sections(analysis.scorecard, analysis)
    line = next(line for line in output.splitlines() if line.startswith(f"- {code}:"))
    assert "미평가 — 설정 미선정(UNRESOLVED)" in line
    assert f"break_buffer_atr={break_buffer}" in line
    assert f"reclaim_buffer_atr={reclaim_buffer}" in line


@pytest.mark.parametrize("mode", ["disabled", "failed", "unknown"])
@pytest.mark.parametrize("detail", [False, True])
def test_unevaluated_detail_retains_known_observation_settings(mode, detail):
    analysis = _analysis()
    bundle = analysis.strategy_run.signal_bundles[0]
    bundle.observation_parameters["up_volume_ratio"] = 2.5
    if mode == "disabled":
        bundle.observations_enabled = False
    elif mode == "failed":
        bundle.diagnostic_errors = ["observations: RuntimeError: failed"]
    else:
        bundle.observations_enabled = None
    output = render_strategy_sections(analysis.scorecard, analysis, detail=detail)
    assert ("Observation 설정=" in output) is detail
    assert ("'up_volume_ratio': 2.5" in output) is detail


def test_cycle_support_and_observation_groups_precede_decisions():
    from src.strategies.models import BarFinality, SupportAnchor, SupportTestState, UpCycleState

    analysis = _analysis(
        [
            _observation(ObservationCode.PULLBACK_WATCH, day=date(2026, 7, 1)),
            _observation(ObservationCode.MOMENTUM_DECELERATION),
            _observation(
                ObservationCode.HIGHER_LOW,
                status=ObservationStatus.RESOLVED,
                ended_on=date(2026, 9, 2),
                confirmed_on=date(2026, 9, 2),
            ),
        ]
    )
    bundle = analysis.strategy_run.signal_bundles[0]
    bundle.up_cycle = UpCycleState(
        cycle_id="cycle-1",
        started_on=date(2026, 7, 1),
        status="ACTIVE",
        status_as_of=bundle.as_of,
        confirmation_code="HIGHER_HIGH",
        confirmation_on=date(2026, 7, 1),
        finality=BarFinality.FINAL,
    )
    bundle.support_tests = [
        SupportTestState(
            anchor=SupportAnchor(
                anchor_id="anchor-1",
                anchor_type="SMA150",
                is_dynamic=True,
                origin_on=date(2026, 7, 1),
                origin_price=Decimal("95"),
                current_value=Decimal("98"),
                cycle_id="cycle-1",
            ),
            status="HELD",
            below_count=0,
            started_on=date(2026, 7, 1),
            status_as_of=bundle.as_of,
            ended_on=None,
            finality=BarFinality.FINAL,
        )
    ]
    output = render_strategy_sections(analysis.scorecard, analysis)
    ordered = [
        "Technical Scorecard",
        "최근 5거래일 Technical Score",
        "cycle / support",
        "SETUP",
        "Positive Observations",
        "Risk Observations",
        "최근 Signal history",
        "오늘 EntryOpportunity",
        "Risk: CAUTION",
    ]
    assert [output.index(text) for text in ordered] == sorted(
        output.index(text) for text in ordered
    )
    assert "anchor=SMA150" in output and "origin=2026-07-01@95" in output
    assert "current_value=98" in output and "HELD" in output
    assert (
        "PULLBACK_WATCH"
        in output.split("### 현재 Observation")[1].split("### 최근 Observation history")[0]
    )
    assert (
        "PULLBACK_WATCH"
        not in output.split("### 최근 Observation history")[1].split("### 최근 Signal history")[0]
    )


def test_source_free_structure_volume_are_once_per_observation_and_terminal_reclaim_is_context():
    from dataclasses import replace

    params = replace(PRODUCT_OBSERVATION_PARAMETERS, up_volume_ratio=2.0)
    analysis = _analysis(
        [
            _observation(
                ObservationCode.HIGHER_HIGH,
                status=ObservationStatus.RESOLVED,
                ended_on=date(2026, 9, 2),
                confirmed_on=date(2026, 9, 2),
                params=params,
            ),
            _observation(
                ObservationCode.UP_VOLUME_EXPANSION,
                status=ObservationStatus.RESOLVED,
                ended_on=date(2026, 9, 2),
                confirmed_on=date(2026, 9, 2),
                params=params,
                evidence=[_evidence("UP_VOLUME_EXPANSION", 2.5, 2.0)],
            ),
            _observation(
                ObservationCode.BREAKOUT_RECLAIM,
                status=ObservationStatus.RESOLVED,
                ended_on=date(2026, 9, 2),
                source_signal_id="old-source",
                source_terminal=True,
                params=params,
            ),
        ]
    )
    bundle = analysis.strategy_run.signal_bundles[0]
    bundle.observation_parameters = asdict(params)
    bundle.entry_opportunity = bundle.entry_opportunity.model_copy(
        update={
            "entry_signal": None,
            "anchors": None,
            "status": EntryOpportunityStatus.NO_RECENT_SIGNAL,
            "age_bars": None,
            "signal_price": None,
            "execution_reference_price": None,
            "extension_pct": None,
        }
    )
    bundle.entry_shadow = None
    bundle.signal_history = []
    bundle.current_signals = []
    output = render_strategy_sections(analysis.scorecard, analysis)
    current = output.split("### 현재 Observation\n")[1].split("### 최근 Observation history")[0]
    assert current.count("HIGHER_HIGH —") == 1
    assert current.count("UP_VOLUME_EXPANSION —") == 1
    assert "scopes=ENTRY,POSITION" in current
    assert "과거 EntryOpportunity를 부활시키지 않습니다" in current
    assert "필수 source 없음" in current


def test_detail_adds_full_evidence_ids_and_settings():
    observation = _observation(
        ObservationCode.SUPPORT_BREAK,
        evidence=[_evidence(), _evidence("EXTRA", None, None, importance=Importance.LOW)],
    )
    analysis = _analysis([observation])
    compact = render_strategy_sections(analysis.scorecard, analysis)
    detail = render_strategy_sections(analysis.scorecard, analysis, detail=True)
    assert "EXTRA measured" not in compact and "EXTRA measured" in detail
    assert observation.observation_id not in compact and observation.observation_id in detail
    assert "parameter_fingerprint=" in detail and "zone_distance_atr" in detail


def test_adapter_reports_actual_settings_without_changing_production_projection():
    from src.strategies.observations.parameters import ObservationParameters
    from src.strategies.swing_w150.adapter import SwingW150SignalStrategy
    from tests.strategies.swing_w150.conftest import load_prices
    from tests.strategies.swing_w150.test_adapter import _bundle

    chart = _bundle(load_prices("COIN").iloc[-300:])
    custom = ObservationParameters(up_volume_ratio=2.5, down_volume_ratio=3.0)
    baseline = SwingW150SignalStrategy().evaluate_signals(chart)
    selected = SwingW150SignalStrategy(observation_parameters=custom).evaluate_signals(chart)
    disabled = SwingW150SignalStrategy(observations_enabled=False).evaluate_signals(chart)
    assert baseline.observations_enabled is True
    assert baseline.observation_parameters == asdict(PRODUCT_OBSERVATION_PARAMETERS)
    assert selected.observation_parameters == asdict(custom)
    assert disabled.observations_enabled is False
    for item in (selected, disabled):
        assert item.signal_history == baseline.signal_history
        assert item.entry_opportunity == baseline.entry_opportunity
        assert item.entry_shadow == baseline.entry_shadow
        assert item.parameter_fingerprint == baseline.parameter_fingerprint


@pytest.mark.parametrize("mode", ["failed", "incomplete", "exit_only"])
def test_missing_evaluation_is_never_reported_as_absent_observation(mode):
    from src.tools.technical.scorecard_models import DataStatus

    analysis = _analysis()
    bundle = analysis.strategy_run.signal_bundles[0]
    expected = {
        "failed": "미평가 — observations: RuntimeError: failed",
        "incomplete": "미평가/불완전 — data_status=insufficient_data",
        "exit_only": "미평가 — 필수 source 없음",
    }[mode]
    if mode == "failed":
        bundle.diagnostic_errors = ["observations: RuntimeError: failed"]
    elif mode == "incomplete":
        bundle.data_status = DataStatus.INSUFFICIENT_DATA
    else:
        bundle.signal_history = [
            bundle.signal_history[0].model_copy(update={"code": "SMA150_EXIT"})
        ]
    current = render_strategy_sections(analysis.scorecard, analysis).split("#### 평가 상태")[1]
    assert expected in current


def test_old_active_event_is_not_a_persistent_episode():
    event = _observation(ObservationCode.HIGHER_HIGH, day=date(2026, 9, 1))
    analysis = _analysis([event])
    output = render_strategy_sections(analysis.scorecard, analysis)
    active = output.split("### 현재 Observation\n")[1].split("#### 평가 상태")[0]
    assert "HIGHER_HIGH —" not in active

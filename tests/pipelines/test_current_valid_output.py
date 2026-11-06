"""Default views show current validity; detail retains historical evidence."""

from dataclasses import replace
from datetime import timedelta

import pytest

from src.pipelines.chart_analysis_render import render_chart_analysis
from src.pipelines.strategy_render import render_strategy_sections
from src.strategies.models import ObservationCode, ObservationStatus
from src.tools.technical.chart_analysis.models import FactRef, FactSelection, plain
from src.tools.technical.scorecard_models import AnalysisTriggerEvent, TriggerStatus
from tests.pipelines.test_chart_analysis_render import result_for
from tests.pipelines.test_common_chart_analysis import anchor_analysis
from tests.pipelines.test_observation_render import _analysis, _observation
from tests.pipelines.test_strategy_analysis import signal_analysis  # noqa: F401


@pytest.mark.parametrize(
    ("kind", "state", "rule_id", "age", "visible"),
    [
        ("EPISODE", "ACTIVE", "OBSERVATION_V1", 100, True),
        ("EPISODE", "BREACHED", "chart.anchor.break_reclaim", 100, True),
        ("EPISODE", "RESOLVED", "OBSERVATION_V1", 1, False),
        ("EPISODE", "RECLAIMED", "chart.anchor.break_reclaim", 1, False),
        ("EVENT", "ACTIVE", "analysis.sma_20_cross_up", 100, True),
        ("EVENT", "INVALIDATED", "analysis.sma_20_cross_up", 0, False),
        ("EVENT", "EXPIRED", "analysis.sma_20_cross_up", 0, False),
        ("EVENT", "RESOLVED", "OBSERVATION_V1", 0, True),
        ("EVENT", "RESOLVED", "OBSERVATION_V1", 1, False),
        ("EVENT", "RECLAIMED", "chart.anchor.break_reclaim", 0, True),
        ("EVENT", "HH", "chart.pivot.span3", 0, True),
        ("EVENT", "HH", "chart.pivot.span3", 1, False),
        ("RISK", "DETECTED", "chart.rsi.wilder", 0, True),
        ("RISK", "CLEAR", "chart.rsi.wilder", 0, False),
        ("STATE", "OBSERVED", "chart.vcp.legacy", 0, True),
        ("STATE", "UNAVAILABLE", "chart.vcp.legacy", 0, True),
        ("STATE", "NOT_SELECTED", "OBSERVATION_V1", 0, True),
        ("EPISODE", "INCOMPLETE_PREFIX", "chart.anchor.break_reclaim", 0, True),
    ],
)
def test_default_common_fact_respects_temporal_semantics_even_when_selected(
    kind, state, rule_id, age, visible
):
    analysis = anchor_analysis()
    day = analysis.manifest.as_of
    item = replace(
        analysis.items[0],
        kind=kind,
        state=state,
        rule_id=rule_id,
        occurred_on=day - timedelta(days=age),
        confirmed_on=day - timedelta(days=age),
        status_as_of=day,
        evidence={"case_marker": "rendered-evidence"},
    )
    analysis = replace(analysis, items=(item,))
    ref = FactRef(analysis.analysis_id, item.id)
    selections = (FactSelection(ref, True, "CURRENT_CONSUMER_SOURCE"),)
    before = plain(analysis)
    compact = render_chart_analysis(
        result_for(analysis),
        analyses={analysis.analysis_id: analysis},
        selections=selections,
        detail=False,
    )
    detail = render_chart_analysis(
        result_for(analysis),
        analyses={analysis.analysis_id: analysis},
        selections=selections,
        detail=True,
    )
    assert ("case_marker=rendered-evidence" in compact) is visible
    assert "case_marker=rendered-evidence" in detail
    assert "CURRENT_CONSUMER_SOURCE" in detail
    assert plain(analysis) == before


def test_past_selected_scope_cannot_advertise_active_state_as_current():
    current = anchor_analysis()
    old = replace(
        current,
        analysis_id="old-scope",
        manifest=replace(current.manifest, as_of=current.manifest.as_of - timedelta(days=1)),
    )
    old_item = replace(
        old.items[0],
        state="BREACHED",
        status_as_of=old.manifest.as_of,
        evidence={"past_marker": "historical-active-state"},
    )
    old = replace(old, items=(old_item,))
    selected = (FactSelection(FactRef(old.analysis_id, old_item.id), True, "PAST_SOURCE"),)
    analyses = {a.analysis_id: a for a in (current, old)}
    compact = render_chart_analysis(
        result_for(current), analyses=analyses, selections=selected, detail=False
    )
    detail = render_chart_analysis(
        result_for(current), analyses=analyses, selections=selected, detail=True
    )
    assert "historical-active-state" not in compact
    assert "historical-active-state" in detail


def test_default_triggers_keep_old_active_and_hide_recent_terminal():
    analysis = _analysis()
    today = analysis.scorecard.as_of

    def trigger(code, status, age):
        return AnalysisTriggerEvent(
            code=code,
            trigger_version="test",
            occurred_on=today - timedelta(days=age),
            bars_ago=age,
            direction=None,
            source="test",
            observed_value=None,
            reference_value=None,
            status=status,
            status_as_of=today,
            status_changed_on=today,
            status_reason="test",
            expires_after_bars=None,
            invalidated_on=None,
            expired_on=None,
            evidence=[],
        )

    analysis.scorecard.triggers = [
        trigger("OLD_ACTIVE", TriggerStatus.ACTIVE, 100),
        trigger("RECENT_INVALIDATED", TriggerStatus.INVALIDATED, 1),
        trigger("RECENT_EXPIRED", TriggerStatus.EXPIRED, 1),
    ]
    compact = render_strategy_sections(analysis.scorecard, analysis)
    detail = render_strategy_sections(analysis.scorecard, analysis, detail=True)
    assert "OLD_ACTIVE" in compact
    assert "RECENT_INVALIDATED" not in compact and "RECENT_EXPIRED" not in compact
    assert "RECENT_INVALIDATED" in detail and "RECENT_EXPIRED" in detail


def test_default_observation_has_active_and_today_event_without_terminal_history():
    analysis = _analysis()
    today = analysis.strategy_run.signal_bundles[0].as_of
    active = _observation(
        ObservationCode.PULLBACK_WATCH, day=today - timedelta(days=100), status_as_of=today
    )
    yesterday = _observation(
        ObservationCode.HIGHER_HIGH,
        day=today - timedelta(days=1),
        status=ObservationStatus.RESOLVED,
        confirmed_on=today - timedelta(days=1),
        ended_on=today - timedelta(days=1),
    )
    event = _observation(
        ObservationCode.HIGHER_LOW,
        day=today,
        status=ObservationStatus.RESOLVED,
        confirmed_on=today,
        ended_on=today,
    )
    resolved = _observation(
        ObservationCode.MOMENTUM_DECELERATION,
        day=today - timedelta(days=3),
        status=ObservationStatus.RESOLVED,
        ended_on=today,
    )
    analysis.strategy_run.signal_bundles[0].observation_history = [
        active,
        yesterday,
        event,
        resolved,
    ]
    compact = render_strategy_sections(analysis.scorecard, analysis)
    detail = render_strategy_sections(analysis.scorecard, analysis, detail=True)
    assert "PULLBACK_WATCH —" in compact and "HIGHER_LOW —" in compact
    assert "HIGHER_HIGH —" not in compact and "MOMENTUM_DECELERATION —" not in compact
    assert "최근 Observation history" not in compact
    assert "HIGHER_HIGH —" in detail and "MOMENTUM_DECELERATION —" in detail
    assert "UNRESOLVED" in compact and "미평가" in compact


def test_default_signal_is_today_only_but_keeps_entry_source(signal_analysis):  # noqa: F811
    analysis = signal_analysis
    bundle = analysis.strategy_run.signal_bundles[0]
    source = bundle.entry_opportunity.entry_signal
    today = source.model_copy(
        update={"signal_id": "today", "code": "TODAY_SIGNAL", "occurred_on": bundle.as_of}
    )
    bundle.signal_history.append(today)
    before = plain(bundle.model_dump())
    compact = render_strategy_sections(analysis.scorecard, analysis)
    detail = render_strategy_sections(analysis.scorecard, analysis, detail=True)
    assert "TODAY_SIGNAL" in compact
    assert "OLD_ENTRY" not in compact and "BOUNDARY_ENTRY" not in compact
    assert f"source={source.code}" in compact
    assert f"발생일={source.occurred_on}" in compact
    assert f"- {source.occurred_on} SWING_W150 {source.code}" not in compact
    assert "OLD_ENTRY" in detail and "BOUNDARY_ENTRY" in detail
    assert plain(bundle.model_dump()) == before


def test_default_common_own_active_lifecycle_is_not_limited_to_recent_window():
    analysis = anchor_analysis()
    item = replace(
        analysis.items[0],
        kind="EVENT",
        state="ACTIVE",
        rule_id="analysis.sma_20_cross_up",
        occurred_on=analysis.manifest.as_of - timedelta(days=100),
        confirmed_on=analysis.manifest.as_of - timedelta(days=100),
        evidence={"old_active": "still-valid"},
    )
    analysis = replace(analysis, items=(item,))
    output = render_chart_analysis(result_for(analysis), analyses={}, detail=False)
    assert "old_active=still-valid" in output


def test_default_common_hides_future_confirmation_and_keeps_missing_ref_warning():
    analysis = anchor_analysis()
    item = replace(
        analysis.items[0],
        kind="EVENT",
        state="RESOLVED",
        rule_id="OBSERVATION_V1",
        confirmed_on=analysis.manifest.as_of + timedelta(days=1),
        evidence={"future_fact": "not-yet-available"},
    )
    analysis = replace(analysis, items=(item,))
    selections = (
        FactSelection(FactRef(analysis.analysis_id, item.id), True, "FUTURE_SOURCE"),
        FactSelection(FactRef("missing-analysis", "missing-item"), True, "MISSING"),
    )
    output = render_chart_analysis(
        result_for(analysis), analyses={}, selections=selections, detail=False
    )
    detail = render_chart_analysis(
        result_for(analysis), analyses={}, selections=selections, detail=True
    )
    assert "future_fact=not-yet-available" not in output
    assert "근거 참조 불가" in output
    assert "future_fact=not-yet-available" in detail


@pytest.mark.parametrize(
    "kind,state,rule_id",
    [
        ("STATE", "OBSERVED", "chart.vcp.legacy"),
        ("EPISODE", "ACTIVE", "OBSERVATION_V1"),
        ("EPISODE", "BREACHED", "chart.anchor.break_reclaim"),
        ("EVENT", "ACTIVE", "analysis.sma_20_cross_up"),
        ("RISK", "DETECTED", "chart.rsi.wilder"),
    ],
)
def test_default_common_does_not_promote_stale_status_within_current_scope(kind, state, rule_id):
    analysis = anchor_analysis()
    item = replace(
        analysis.items[0],
        kind=kind,
        state=state,
        rule_id=rule_id,
        status_as_of=analysis.manifest.as_of - timedelta(days=1),
        evidence={"stale_status": "old-evaluation"},
    )
    analysis = replace(analysis, items=(item,))
    selected = (FactSelection(FactRef(analysis.analysis_id, item.id), True, "STALE_SOURCE"),)
    compact = render_chart_analysis(
        result_for(analysis), analyses={}, selections=selected, detail=False
    )
    detail = render_chart_analysis(
        result_for(analysis), analyses={}, selections=selected, detail=True
    )
    assert "stale_status=old-evaluation" not in compact
    assert "stale_status=old-evaluation" in detail


def test_default_stale_active_observation_is_unassessed_with_detail_evidence():
    analysis = _analysis()
    bundle = analysis.strategy_run.signal_bundles[0]
    old_day = bundle.as_of - timedelta(days=1)
    episode = _observation(ObservationCode.PULLBACK_WATCH, day=old_day, status_as_of=old_day)
    bundle.observation_history = [episode]
    compact = render_strategy_sections(analysis.scorecard, analysis)
    detail = render_strategy_sections(analysis.scorecard, analysis, detail=True)
    assert "PULLBACK_WATCH —" not in compact
    assert "현재 미평가" in compact and str(old_day) in compact
    assert "PULLBACK_WATCH —" in detail
    assert "UNRESOLVED" in compact


def test_today_one_shot_confirmation_is_distinct_from_episode_status_date():
    analysis = anchor_analysis()
    item = replace(
        analysis.items[0],
        kind="EVENT",
        state="RESOLVED",
        rule_id="OBSERVATION_V1",
        status_as_of=analysis.manifest.as_of - timedelta(days=1),
        confirmed_on=analysis.manifest.as_of,
        evidence={"confirmed_today": True},
    )
    analysis = replace(analysis, items=(item,))
    output = render_chart_analysis(result_for(analysis), analyses={}, detail=False)
    assert "confirmed_today=True" in output


def test_stale_unavailable_fact_is_detail_only_and_current_unavailable_is_preserved():
    from types import SimpleNamespace

    from src.pipelines.chart_analysis_render import render_common_strategy_analysis

    analysis = anchor_analysis()
    item = replace(
        analysis.items[0],
        kind="STATE",
        state="UNAVAILABLE",
        status_as_of=analysis.manifest.as_of - timedelta(days=1),
        evidence={"old_warning": "historical-input-gap"},
    )
    analysis = replace(analysis, items=(item,))
    value = SimpleNamespace(
        strategy_run=SimpleNamespace(verdicts=[], signal_bundles=[]),
        scorecard=SimpleNamespace(as_of=analysis.manifest.as_of),
        common_analyses={analysis.analysis_id: analysis},
        technical_fact_selections=(
            FactSelection(FactRef(analysis.analysis_id, item.id), True, "OLD_WARNING"),
        ),
        chart_analysis=None,
        chart_analysis_unavailable="current INPUT_MISSING",
    )
    compact = render_common_strategy_analysis(value, detail=False)
    detail = render_common_strategy_analysis(value, detail=True)
    assert "historical-input-gap" not in compact
    assert "Quality: null — current INPUT_MISSING" in compact
    assert "historical-input-gap" in detail


@pytest.mark.parametrize("case", ["stale_status", "future_occurrence"])
def test_default_trigger_rejects_stale_or_future_active_status(case):
    analysis = _analysis()
    today = analysis.scorecard.as_of
    trigger = AnalysisTriggerEvent(
        code="NOT_CURRENT_ACTIVE",
        trigger_version="test",
        occurred_on=today + timedelta(days=1)
        if case == "future_occurrence"
        else today - timedelta(days=1),
        bars_ago=0,
        direction=None,
        source="test",
        observed_value=None,
        reference_value=None,
        status=TriggerStatus.ACTIVE,
        status_as_of=today - timedelta(days=1) if case == "stale_status" else today,
        status_changed_on=today,
        status_reason="test",
        expires_after_bars=None,
        invalidated_on=None,
        expired_on=None,
        evidence=[],
    )
    analysis.scorecard.triggers = [trigger]
    compact = render_strategy_sections(analysis.scorecard, analysis)
    detail = render_strategy_sections(analysis.scorecard, analysis, detail=True)
    assert "NOT_CURRENT_ACTIVE" not in compact
    assert "NOT_CURRENT_ACTIVE" in detail


@pytest.mark.parametrize(
    "case", ["event_future_status", "episode_future_start", "episode_future_confirmation"]
)
def test_default_observation_rejects_future_temporal_fields(case):
    analysis = _analysis()
    bundle = analysis.strategy_run.signal_bundles[0]
    today = bundle.as_of
    future = today + timedelta(days=1)
    if case == "event_future_status":
        item = _observation(
            ObservationCode.HIGHER_HIGH,
            day=today,
            confirmed_on=today,
            status_as_of=future,
            status=ObservationStatus.RESOLVED,
        )
    else:
        item = _observation(
            ObservationCode.PULLBACK_WATCH,
            day=future if case == "episode_future_start" else today,
            confirmed_on=future if case == "episode_future_confirmation" else None,
            status_as_of=today,
        )
    bundle.observation_history = [item]
    compact = render_strategy_sections(analysis.scorecard, analysis)
    detail = render_strategy_sections(analysis.scorecard, analysis, detail=True)
    assert f"{item.code} —" not in compact
    assert f"{item.code} —" in detail


def test_default_today_observation_event_keeps_confirmation_with_prior_status_date():
    analysis = _analysis()
    bundle = analysis.strategy_run.signal_bundles[0]
    event = _observation(
        ObservationCode.HIGHER_HIGH,
        day=bundle.as_of - timedelta(days=1),
        confirmed_on=bundle.as_of,
        status_as_of=bundle.as_of - timedelta(days=1),
        status=ObservationStatus.RESOLVED,
    )
    bundle.observation_history = [event]
    output = render_strategy_sections(analysis.scorecard, analysis)
    assert "HIGHER_HIGH —" in output


def test_default_common_rejects_future_origin_even_with_current_confirmation():
    analysis = anchor_analysis()
    item = replace(
        analysis.items[0],
        kind="EPISODE",
        state="BREACHED",
        occurred_on=analysis.manifest.as_of + timedelta(days=1),
        confirmed_on=analysis.manifest.as_of,
        status_as_of=analysis.manifest.as_of,
        evidence={"future_origin": "not-current"},
    )
    analysis = replace(analysis, items=(item,))
    compact = render_chart_analysis(result_for(analysis), analyses={}, detail=False)
    detail = render_chart_analysis(result_for(analysis), analyses={}, detail=True)
    assert "future_origin=not-current" not in compact
    assert "future_origin=not-current" in detail

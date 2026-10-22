"""Product surfaces expose diagnostics independently of entry authorization."""

import json
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.pipelines.strategy_analysis import AnalysisStrategyResult, AnalysisStrategyService
from src.pipelines.strategy_render import render_strategy_sections
from src.position.models import PositionSnapshot
from src.strategies.models import EntryOpportunityStatus
from src.tools.technical.models import IndicatorSnapshot, ScoreHistoryPoint, TechnicalResult
from src.tools.technical.scorecard_models import DataStatus
from tests.storage.test_entry_shadow import decision_inputs


def _service(run, chart, **options):
    class Loader:
        async def load(self, **kwargs):
            return chart

    class Runner:
        def run(self, bundle, **kwargs):
            return run

    return AnalysisStrategyService(Loader(), Runner(), **options)


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["check", "analyze", "brief"])
async def test_shared_service_records_pipeline_decision_and_keeps_planner_unchanged(
    tmp_path, pipeline
):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    run, chart = decision_inputs()
    path = tmp_path / "injected.jsonl"
    technical = SimpleNamespace()
    before = run.model_dump(mode="json")
    enabled = await _service(run, chart, shadow_recorder=EntryShadowJsonlRecorder(path)).evaluate(
        "AAPL", technical, as_of=chart.as_of, pipeline=pipeline, position=PositionSnapshot(7)
    )
    disabled = await _service(run, chart, shadow_recorder=None).evaluate(
        "AAPL", technical, as_of=chart.as_of, pipeline=pipeline, position=PositionSnapshot(7)
    )

    row = json.loads(path.read_text())
    assert row["pipeline"] == pipeline
    assert replace(enabled.position_plan, calculated_at=None) == replace(
        disabled.position_plan, calculated_at=None
    )
    assert enabled.position_plan.current_quantity == 7
    assert enabled.position_plan.sell_quantity == 0
    assert run.model_dump(mode="json") == before


@pytest.mark.asyncio
async def test_default_recorder_honors_env_path_and_explicit_none_disables(tmp_path, monkeypatch):
    run, chart = decision_inputs()
    path = tmp_path / "override" / "decisions.jsonl"
    monkeypatch.setenv("JARVIS_ENTRY_SHADOW_LOG_PATH", str(path))
    await _service(run, chart).evaluate("AAPL", SimpleNamespace(), as_of=chart.as_of)
    assert len(path.read_text().splitlines()) == 1
    await _service(run, chart, shadow_recorder=None).evaluate(
        "AAPL", SimpleNamespace(), as_of=chart.as_of
    )
    assert len(path.read_text().splitlines()) == 1


@pytest.mark.asyncio
async def test_default_recorder_uses_local_research_path(tmp_path, monkeypatch):
    run, chart = decision_inputs()
    monkeypatch.delenv("JARVIS_ENTRY_SHADOW_LOG_PATH")
    monkeypatch.chdir(tmp_path)
    await _service(run, chart).evaluate("AAPL", SimpleNamespace(), as_of=chart.as_of)
    path = tmp_path / "data" / "research" / "entry-shadow.jsonl"
    assert json.loads(path.read_text())["source_id"] == "source"
    assert sorted(item.name for item in tmp_path.iterdir()) == ["data"]


@pytest.mark.asyncio
async def test_recording_error_warns_without_changing_production_or_planner(tmp_path, caplog):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    run, chart = decision_inputs()
    before = run.model_dump(mode="json")
    broken = _service(run, chart, shadow_recorder=EntryShadowJsonlRecorder(tmp_path))
    result = await broken.evaluate(
        "AAPL", SimpleNamespace(), as_of=chart.as_of, position=PositionSnapshot(5)
    )
    baseline = await _service(run, chart, shadow_recorder=None).evaluate(
        "AAPL", SimpleNamespace(), as_of=chart.as_of, position=PositionSnapshot(5)
    )
    assert replace(result.position_plan, calculated_at=None) == replace(
        baseline.position_plan, calculated_at=None
    )
    assert result.strategy_run.data_status.value == "complete"
    assert run.model_dump(mode="json") == before
    assert "Shadow 기록 실패" in result.warning
    assert "Shadow 기록 실패" in caplog.text
    assert "Shadow 기록 실패" in render_strategy_sections(result.scorecard, result)


def _analysis(*, provisional=True):
    run, chart = decision_inputs(provisional=provisional)
    run.signal_bundles[0].entry_opportunity.status = EntryOpportunityStatus.WATCH
    history = tuple(
        ScoreHistoryPoint(
            date=f"2026-08-{day:02d}",
            close=100,
            component_raw_total=40,
            adjusted_score=day,
            verdict_action="watch",
            one_line_reason="점수 근거 보존",
        )
        for day in range(24, 29)
    )
    return AnalysisStrategyResult(
        run.scorecard, run, chart.exchange_sessions, 99, score_history=history
    )


def _all_surfaces(analysis):
    from src.cli.main import format_deep_dive_output
    from src.llm.models import TechnicalSummaryOutput
    from src.pipelines.brief import BriefPipeline
    from src.pipelines.quick_check import QuickCheckPipeline
    from src.tools.brief.models import BUCKET_HOLD_OK, BriefItem

    technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime(2026, 9, 2),
        snapshot=IndicatorSnapshot(price=99, change_pct=0),
        components={},
        scorecard=analysis.scorecard,
    )
    check = QuickCheckPipeline(None).format_output(
        {
            "ticker": "AAPL",
            "success": True,
            "scorecard": analysis.scorecard,
            "strategy_analysis": analysis,
            "price": 99,
            "change_pct": 0,
            "total_score": 50,
            "assessment": "hold",
            "confidence": 50,
            "signals": [],
            "warnings": [],
            "components": [],
            "indicators": {},
        }
    )
    analyze = format_deep_dive_output(
        {
            "ticker": "AAPL",
            "technical": technical,
            "scorecard": analysis.scorecard,
            "strategy_analysis": analysis,
            "technical_summary": TechnicalSummaryOutput(
                summary="hold",
                recommendation="hold",
                confidence=0.5,
                rationale="test",
                key_insights=[],
            ),
        }
    )
    item = BriefItem(
        ticker="AAPL",
        kind="watch",
        action="rejected",
        bucket=BUCKET_HOLD_OK,
        scorecard=analysis.scorecard,
        strategy_analysis=analysis,
    )
    brief = BriefPipeline.__new__(BriefPipeline).format_output(
        {
            "date": technical.timestamp,
            "macro": None,
            "items": [item],
        }
    )
    return check, analyze, brief


def test_default_renderer_shows_risk_without_today_entry_on_all_three_surfaces():
    analysis = _analysis()
    flag = analysis.strategy_run.signal_bundles[0].entry_shadow.risk_flags[0]
    assert analysis.strategy_run.signal_bundles[0].current_signals == []
    for rendered in _all_surfaces(analysis):
        section = rendered.split("### 오늘 EntryOpportunity", 1)[1]
        assert "EXECUTION_WATCH" in section
        assert "source=TREND_BREAKOUT_ENTRY" in section
        assert "발생일=2026-09-01" in section
        assert "1거래일 전" in section
        assert "Production policy=production" in section
        assert "Risk: CAUTION [PROVISIONAL]" in section
        assert "Shadow policy=WATCH_RECLAIM_SHADOW_V1" in section
        assert flag.message in section
        assert "관측값=99" in section
        assert "기준값=100" in section
        assert "진단은 Production·Position Plan을 변경하지 않습니다" in section
        assert "B1" not in section
        assert "B4" not in section
        assert "발생 원인: entry" in rendered
        assert rendered.count("점수 근거 보존") == 5


@pytest.mark.parametrize("mode", ["unsupported", "disabled", "failed"])
def test_renderer_never_invents_normal_for_missing_diagnostics(mode):
    analysis = _analysis()
    signals = analysis.strategy_run.signal_bundles[0]
    if mode == "unsupported":
        signals.entry_shadow = signals.entry_shadow.model_copy(
            update={
                "risk_level": None,
                "risk_flags": [],
                "data_status": DataStatus.NOT_EVALUATED,
                "reason": "UNSUPPORTED_SOURCE",
            }
        )
    else:
        signals.entry_shadow = None
        if mode == "failed":
            analysis.strategy_run.diagnostic_errors = [
                "SWING_W150: RuntimeError: broken diagnostic"
            ]
    rendered = render_strategy_sections(analysis.scorecard, analysis)
    section = rendered.split("### 오늘 EntryOpportunity", 1)[1]
    assert "NORMAL" not in section
    assert "미평가" in section
    if mode == "unsupported":
        assert "UNSUPPORTED_SOURCE" in section
    elif mode == "failed":
        assert "broken diagnostic" in rendered
    else:
        assert "비활성 또는 이용 불가" in section


def test_detail_renderer_exposes_research_state_without_hiding_evidence():
    analysis = _analysis()
    rendered = render_strategy_sections(analysis.scorecard, analysis, detail=True)
    assert "B1" in rendered
    assert "BREACHED" in rendered
    assert "production-fingerprint" in rendered

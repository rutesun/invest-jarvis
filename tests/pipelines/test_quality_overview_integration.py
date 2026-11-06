"""Quality·전략별 독립 수량을 새 사용자 화면에서 잃지 않는다."""

from dataclasses import replace
from datetime import datetime

from src.cli.main import format_deep_dive_output
from src.llm.models import TechnicalSummaryOutput
from src.pipelines.brief import BriefPipeline
from src.pipelines.quick_check import QuickCheckPipeline
from src.position.models import DirectiveKind, PositionDirective, PositionPlan, QuantityStatus
from src.tools.brief.models import BUCKET_HOLD_OK, BriefItem
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult
from tests.pipelines.test_chart_analysis_render import result_for
from tests.pipelines.test_observation_render import _analysis


def _case(*, quality=67.123456, reasons=()):
    analysis = _analysis()
    day = analysis.scorecard.as_of
    result = result_for(quality=quality, reasons=reasons)
    manifest = replace(result.analysis.manifest, as_of=day)
    common = replace(result.analysis, manifest=manifest)
    result = replace(
        result, analysis=common, quality=replace(result.quality, as_of=day, manifest=manifest)
    )
    analysis.strategy_run.chart_analysis = result
    plans = {
        "TECHNICAL_LEGACY": PositionPlan(
            PositionDirective(DirectiveKind.KEEP_CURRENT), 7, 7, 0, 0, QuantityStatus.AVAILABLE
        ),
        "PLAYBOOK_V1": PositionPlan(
            PositionDirective(DirectiveKind.REDUCE_CURRENT_BY_FRACTION, 0.5),
            7,
            3,
            0,
            4,
            QuantityStatus.AVAILABLE,
        ),
        "SWING_W150": PositionPlan(
            PositionDirective(DirectiveKind.KEEP_CURRENT), 7, 7, 0, 0, QuantityStatus.AVAILABLE
        ),
    }
    return replace(analysis, position_plans=plans, position_plan=plans["SWING_W150"])


def _surfaces(analysis, *, detail=False):
    technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime(2026, 9, 2),
        components={},
        snapshot=IndicatorSnapshot(price=99, change_pct=-1),
        scorecard=analysis.scorecard,
    )
    check = QuickCheckPipeline(None).format_output(
        {
            "ticker": "AAPL",
            "success": True,
            "scorecard": analysis.scorecard,
            "strategy_analysis": analysis,
            "price": 99,
            "change_pct": -1,
            "total_score": 50,
            "assessment": "hold",
            "confidence": 50,
            "signals": [],
            "warnings": [],
            "components": [],
            "indicators": {},
        },
        detailed_strategy=detail,
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
                rationale="fixed",
                key_insights=[],
            ),
        },
        detailed_strategy=detail,
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
        {"date": technical.timestamp, "macro": None, "items": [item]}, detailed_strategy=detail
    )
    return check, analyze, brief


def test_three_commands_keep_quality_and_independent_sizes_in_readable_default():
    analysis = _case()
    before = analysis.strategy_run.model_dump(mode="json")
    plans = analysis.position_plans.copy()
    for index, output in enumerate(_surfaces(analysis)):
        current = "### 현재 유효 상태" if index == 0 else "### 현재 상태"
        for heading in (current, "### 주요 가격대", "### 최근 5거래일", "### 전략별 대응"):
            assert heading in output
        assert ("### 관찰 흐름" in output) is (index == 0)
        assert output.count("### 차트 상태 점수(Quality)") == 1
        assert "Quality: 확정 67.12 / 100" in output
        assert "추세 61.23" in output and "구조 70.00" in output
        assert "모멘텀 80.00" in output and "거래량 방향(Participation) 100.00" in output
        assert "| TECHNICAL_LEGACY | 유지 | 7 | 7 | 0 | 0 |" in output
        assert "| PLAYBOOK_V1 | 일부 축소 | 7 | 3 | 0 | 4 |" in output
        assert "| SWING_W150 | 유지 | 7 | 7 | 0 | 0 |" in output
        assert "합산하지 않습니다" in output
        assert "Observation history" not in output
    assert analysis.strategy_run.model_dump(mode="json") == before
    assert analysis.position_plans == plans


def test_quality_null_diagnostics_are_visible_without_hiding_plans():
    analysis = _case(
        quality=None,
        reasons=("POLICY_HISTORY_SHORT", "LOW_DIRECTIONAL_SAMPLE", "CONCENTRATED_VOLUME"),
    )
    for output in _surfaces(analysis):
        assert "Quality: 미산출" in output and "null" not in output
        assert "252" in output and "5개 미만" in output and "집중" in output
        assert "preview" not in output and "67.12" not in output
        assert "| PLAYBOOK_V1 | 일부 축소 | 7 | 3 | 0 | 4 |" in output


def test_unavailable_plan_does_not_invent_zero_quantity():
    analysis = _case()
    missing = replace(
        analysis.position_plans["PLAYBOOK_V1"],
        target_quantity=None,
        buy_quantity=None,
        sell_quantity=None,
        quantity_status=QuantityStatus.UNAVAILABLE,
    )
    analysis = replace(analysis, position_plans={"PLAYBOOK_V1": missing})
    for output in _surfaces(analysis):
        assert "| PLAYBOOK_V1 | 일부 축소 | 7 | 미산정 | 미산정 | 미산정 |" in output
        assert "수량 미산정" in output


def test_plan_notes_do_not_break_rendered_quantity_table():
    from io import StringIO

    from rich.console import Console
    from rich.markdown import Markdown

    from src.strategies.models import SignalFinality

    analysis = _case()
    plans = dict(analysis.position_plans)
    plans["TECHNICAL_LEGACY"] = replace(
        plans["TECHNICAL_LEGACY"], signal_finality=SignalFinality.PROVISIONAL
    )
    analysis = replace(analysis, position_plans=plans)
    for output in _surfaces(analysis):
        stream = StringIO()
        Console(file=stream, width=180, color_system=None).print(Markdown(output))
        rendered = stream.getvalue()
        assert "PLAYBOOK_V1" in rendered and "SWING_W150" in rendered
        assert "| PLAYBOOK_V1 |" not in rendered
        assert "| SWING_W150 |" not in rendered

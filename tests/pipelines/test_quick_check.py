from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.core.models import ToolResult
from src.pipelines.quick_check import QuickCheckPipeline, _format_compact_history_point, _format_detailed_history_point
from src.tools.technical.models import (
    IndicatorSnapshot,
    ScoreHistoryPoint,
    StrategyResult,
    TechnicalResult,
    TechnicalVerdict,
)


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock()
    indicators = IndicatorSnapshot(
        price=178.50,
        change_pct=2.5,
        sma_20=175.0,
        sma_50=170.0,
        rsi=58.3,
    )
    strategy = StrategyResult(
        name="trend",
        status="강세",
        confidence=75.0,
        signals=["골든크로스"],
        evidence=["20일선 > 50일선"],
        metrics={"sma_20": 175.0},
    )
    tech_result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=indicators,
        indicators=indicators,
        components={},
        total_score=75,
        strategies=[strategy],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["골든크로스"],
        warnings=[],
    )
    tool.execute.return_value = ToolResult(success=True, data=tech_result)
    return tool


@pytest.mark.asyncio
async def test_quick_check_run(mock_technical_tool):
    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    result = await pipeline.run("AAPL")

    assert result["ticker"] == "AAPL"
    assert result["price"] == 178.50
    assert result["assessment"] == "매수"
    mock_technical_tool.execute.assert_called_once_with("AAPL")


@pytest.mark.asyncio
async def test_quick_check_format_output(mock_technical_tool):
    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    result = await pipeline.run("AAPL")
    output = pipeline.format_output(result)

    assert "AAPL" in output
    assert "178.50" in output
    assert "매수" in output
    assert "**SMA 100**: N/A · — 데이터 부족" in output
    assert "**SMA 200**: N/A · — 데이터 부족" in output


@pytest.mark.asyncio
async def test_quick_check_run_includes_verdict_and_score_history(mock_technical_tool):
    tech = mock_technical_tool.execute.return_value.data
    tech.adjusted_score = 62
    tech.technical_verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["상승 추세 유지"],
        cautions=["단기 과열"],
        invalidation_level=170.0,
        score_trend_summary="최근 5거래일 adjusted score는 70에서 62로 악화",
    )
    tech.score_history = [
        ScoreHistoryPoint(
            date="2026-07-10",
            close=178.5,
            component_raw_total=75,
            adjusted_score=62,
            verdict_action="hold",
            one_line_reason="단기 과열",
        )
    ]

    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    result = await pipeline.run("AAPL")

    assert result["adjusted_score"] == 62
    assert result["technical_verdict"]["action"] == "hold"
    assert result["score_history"][0]["adjusted_score"] == 62
    assert result["aggregation_trace"] == []


@pytest.mark.asyncio
async def test_quick_check_format_output_shows_verdict_reasons_and_history(
    mock_technical_tool,
):
    tech = mock_technical_tool.execute.return_value.data
    tech.adjusted_score = 62
    tech.technical_verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["상승 추세 유지"],
        cautions=["단기 과열"],
        invalidation_level=170.0,
        score_trend_summary="최근 5거래일 adjusted score는 70에서 62로 악화",
    )
    tech.score_history = [
        ScoreHistoryPoint(
            date="2026-07-10",
            close=178.5,
            component_raw_total=75,
            adjusted_score=62,
            verdict_action="hold",
            one_line_reason="단기 과열",
        )
    ]

    pipeline = QuickCheckPipeline(technical_tool=mock_technical_tool)
    output = pipeline.format_output(await pipeline.run("AAPL"))

    assert "Adjusted Score" in output
    assert "상승 추세 유지" in output
    assert "최근 5거래일" in output
    assert "2026-07-10" in output


def test_quick_check_format_output_shows_compact_score_history_context():
    pipeline = QuickCheckPipeline(technical_tool=None)
    output = pipeline.format_output(
        {
            "success": True,
            "ticker": "ALAB",
            "price": 350.62,
            "change_pct": -3.08,
            "total_score": -5,
            "adjusted_score": -25,
            "score_history": [
                {
                    "date": "2026-07-14",
                    "close": 361.78,
                    "component_raw_total": 25,
                    "adjusted_score": 25,
                    "verdict_action": "watch",
                    "one_line_reason": "가격이 주요 이동평균 위에서 상승 추세를 유지",
                    "new_entry_allowed": True,
                    "change_drivers": [],
                    "cautions": [],
                },
                {
                    "date": "2026-07-15",
                    "close": 350.62,
                    "component_raw_total": -5,
                    "adjusted_score": -25,
                    "verdict_action": "reduce",
                    "one_line_reason": "강세 (Stage 2 미충족)",
                    "new_entry_allowed": False,
                    "change_drivers": ["supertrend -40 신규 악화", "minervini -15 약화"],
                    "cautions": ["Supertrend가 매도 전환"],
                },
            ],
        }
    )

    assert "adjusted -25 (Δ -50)" in output
    assert "변화: supertrend -40 신규 악화, minervini -15 약화" in output
    assert "신규진입: yes→no" in output
    assert "주의:" not in output


def test_quick_check_format_output_shows_detailed_score_history_context():
    pipeline = QuickCheckPipeline(technical_tool=None)
    output = pipeline.format_output(
        {
            "success": True,
            "ticker": "ALAB",
            "price": 350.62,
            "change_pct": -3.08,
            "total_score": -5,
            "adjusted_score": -25,
            "score_history": [
                {
                    "date": "2026-07-15",
                    "close": 350.62,
                    "component_raw_total": -5,
                    "adjusted_score": -25,
                    "verdict_action": "reduce",
                    "one_line_reason": "강세 (Stage 2 미충족)",
                    "new_entry_allowed": False,
                    "change_drivers": ["supertrend -40 신규 악화", "minervini -15 약화"],
                    "cautions": ["Supertrend가 매도 전환"],
                }
            ],
        },
        detailed_history=True,
    )

    assert "  - reason: 강세 (Stage 2 미충족)" in output
    assert "  - 변화: supertrend -40 신규 악화, minervini -15 약화" in output
    assert "  - 신규진입: no" in output
    assert "  - 주의: Supertrend가 매도 전환" in output


def test_quick_check_format_output_shows_all_minervini_conditions():
    pipeline = QuickCheckPipeline(technical_tool=None)
    output = pipeline.format_output(
        {
            "success": True,
            "ticker": "ALAB",
            "price": 350.62,
            "change_pct": -3.08,
            "total_score": 25,
            "components": [
                {
                    "name": "minervini",
                    "score": 25,
                    "signals": ["강세 (Stage 2 미충족)"],
                    "evidence": [
                        "ma_stack: 충족",
                        "ma_50_stack: 충족",
                        "sma_150_rising: 충족",
                        "sma_200_rising: 충족",
                        "above_50: 충족",
                        "above_52w_low_30pct: 충족",
                        "within_52w_high_25pct: 미충족",
                    ],
                }
            ],
        }
    )

    assert "above_52w_low_30pct: 충족" in output
    assert "within_52w_high_25pct: 미충족" in output


def test_compact_history_shows_events_before_changes():
    point = {
        "date": "2026-07-31",
        "close": 311.23,
        "component_raw_total": -55,
        "adjusted_score": -55,
        "verdict_action": "avoid",
        "one_line_reason": "조정 점수가 -25점 미만으로 리스크 우위",
        "new_entry_allowed": False,
        "events": ["cRSI Hook Up (매수 시그널)"],
        "change_drivers": ["cRSI 32.7→38.1 상승"],
    }

    line = _format_compact_history_point(point, None)

    assert "이벤트: cRSI Hook Up (매수 시그널)" in line
    assert line.index("이벤트:") < line.index("변화:")


def test_compact_history_omits_events_segment_when_empty():
    point = {
        "date": "2026-08-03",
        "close": 321.05,
        "component_raw_total": -75,
        "adjusted_score": -75,
        "verdict_action": "avoid",
        "one_line_reason": "조정 점수가 -25점 미만으로 리스크 우위",
        "new_entry_allowed": False,
        "events": [],
        "change_drivers": ["cRSI 38.1→44.1 상승"],
    }

    line = _format_compact_history_point(point, None)

    assert "이벤트:" not in line


def test_compact_history_renders_multiline_layout():
    point = {
        "date": "2026-08-05",
        "close": 318.43,
        "component_raw_total": -20,
        "adjusted_score": -55,
        "verdict_action": "avoid",
        "one_line_reason": "거래량이 동반된 이탈로 신규 진입 금지",
        "new_entry_allowed": False,
        "events": ["약세/보합", "Egg (추가 하락 경고)", "중고위험"],
        "change_drivers": ["minervini -45 악화", "volume -30 악화"],
    }

    lines = _format_compact_history_point(point, None).split("\n")

    assert lines[0] == "- 2026-08-05: close 318.43, raw -20, adjusted -55 | 신규진입: no"
    assert lines[1] == "  - avoid — 거래량이 동반된 이탈로 신규 진입 금지"
    assert lines[2] == "  - 이벤트: 약세/보합, Egg (추가 하락 경고), 중고위험"
    assert lines[3] == "  - 변화: minervini -45 악화, volume -30 악화"


def test_compact_history_header_omits_entry_when_unknown():
    point = {
        "date": "2026-08-05",
        "close": 318.43,
        "component_raw_total": -20,
        "adjusted_score": -55,
        "verdict_action": "avoid",
        "one_line_reason": "리스크 우위",
        "new_entry_allowed": None,
        "events": [],
        "change_drivers": [],
    }

    lines = _format_compact_history_point(point, None).split("\n")

    assert lines[0] == "- 2026-08-05: close 318.43, raw -20, adjusted -55"
    assert lines[1] == "  - avoid — 리스크 우위"
    assert len(lines) == 2


def test_detailed_history_shows_events_before_changes():
    point = {
        "date": "2026-07-31",
        "close": 311.23,
        "component_raw_total": -55,
        "adjusted_score": -55,
        "verdict_action": "avoid",
        "one_line_reason": "조정 점수가 -25점 미만으로 리스크 우위",
        "new_entry_allowed": False,
        "events": ["cRSI Hook Up (매수 시그널)"],
        "change_drivers": ["cRSI 32.7→38.1 상승"],
    }

    lines = _format_detailed_history_point(point, None)
    joined = "\n".join(lines)

    event_line = next(line for line in lines if "이벤트:" in line)
    assert event_line == "  - 이벤트: cRSI Hook Up (매수 시그널)"
    assert joined.index("이벤트:") < joined.index("변화:")


def test_detailed_history_omits_events_line_when_empty():
    point = {
        "date": "2026-08-03",
        "close": 321.05,
        "component_raw_total": -75,
        "adjusted_score": -75,
        "verdict_action": "avoid",
        "one_line_reason": "조정 점수가 -25점 미만으로 리스크 우위",
        "new_entry_allowed": False,
        "events": [],
        "change_drivers": ["cRSI 38.1→44.1 상승"],
    }

    lines = _format_detailed_history_point(point, None)

    assert not any("이벤트:" in line for line in lines)

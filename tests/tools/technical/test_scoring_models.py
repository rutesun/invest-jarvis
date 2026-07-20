from datetime import UTC, datetime

import pytest

from src.tools.technical.models import (
    AggregationTraceEntry,
    ComponentResult,
    ComponentSignal,
    IndicatorSnapshot,
    ScoreHistoryPoint,
    TechnicalResult,
    TechnicalVerdict,
)


def test_component_result_accepts_signal_metadata():
    result = ComponentResult(
        signals=["cRSI Hook Up"],
        evidence=["cRSI 하단밴드 상향 돌파"],
        metrics={"crsi": 21.5},
        score=20,
        signal_metadata=[
            ComponentSignal(
                signal_type="pullback",
                bias="bullish",
                intent="entry",
                severity="medium",
                entry_eligible=True,
                source="crsi",
                reason="상승 추세에서 pullback entry 후보",
            )
        ],
    )

    assert result.signal_metadata[0].signal_type == "pullback"
    assert result.signal_metadata[0].entry_eligible is True


def test_component_result_rejects_float_score():
    with pytest.raises(ValueError):
        ComponentResult(
            signals=[],
            evidence=[],
            metrics={},
            score=20.0,
        )


def test_component_result_rejects_bool_score():
    with pytest.raises(ValueError):
        ComponentResult(
            signals=[],
            evidence=[],
            metrics={},
            score=True,
        )


def test_component_result_accepts_integer_score():
    result = ComponentResult(
        signals=[],
        evidence=[],
        metrics={},
        score=20,
    )

    assert result.score == 20


def test_technical_result_defaults_keep_total_score_contract():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(UTC),
        snapshot=snapshot,
        components={},
        total_score=65,
    )

    assert result.total_score == 65
    assert result.component_raw_total == 65
    assert result.adjusted_score == 65
    assert result.technical_verdict is None
    assert result.score_history == []


def test_technical_result_backfills_component_raw_total_from_component_scores():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(UTC),
        snapshot=snapshot,
        components={
            "trend": {"score": 20},
            "momentum": {"score": -5},
        },
        total_score=15,
    )

    assert result.total_score == 15
    assert result.component_raw_total == 15
    assert result.adjusted_score == 15


def test_technical_result_rejects_float_component_scores():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    with pytest.raises(ValueError, match="integer"):
        TechnicalResult(
            ticker="AAPL",
            timestamp=datetime.now(UTC),
            snapshot=snapshot,
            components={
                "trend": {"score": 1.5},
                "momentum": {"score": 0.5},
            },
            total_score=2,
        )


def test_technical_result_rejects_bool_component_scores():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    with pytest.raises(ValueError, match="integer"):
        TechnicalResult(
            ticker="AAPL",
            timestamp=datetime.now(UTC),
            snapshot=snapshot,
            components={
                "trend": {"score": True},
                "momentum": {"score": 1},
            },
            total_score=2,
        )


def test_technical_result_backfills_integer_component_raw_total():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(UTC),
        snapshot=snapshot,
        components={
            "trend": {"score": 2},
            "momentum": {"score": 3},
        },
        total_score=5,
    )

    assert result.component_raw_total == 5
    assert type(result.component_raw_total) is int


def test_technical_result_rejects_total_score_mismatch():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    with pytest.raises(ValueError, match="total_score"):
        TechnicalResult(
            ticker="AAPL",
            timestamp=datetime.now(UTC),
            snapshot=snapshot,
            components={
                "trend": {"score": 20},
                "momentum": {"score": -5},
            },
            total_score=99,
        )


def test_technical_result_rejects_component_raw_total_mismatch():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    with pytest.raises(ValueError):
        TechnicalResult(
            ticker="AAPL",
            timestamp=datetime.now(UTC),
            snapshot=snapshot,
            components={
                "trend": {"score": 20},
                "momentum": {"score": -5},
            },
            total_score=15,
            component_raw_total=20,
        )


def test_technical_result_rejects_explicit_raw_total_for_empty_components():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    with pytest.raises(ValueError, match="component_raw_total"):
        TechnicalResult(
            ticker="AAPL",
            timestamp=datetime.now(UTC),
            snapshot=snapshot,
            components={},
            total_score=80,
            component_raw_total=20,
        )


def test_technical_result_rejects_explicit_raw_total_for_incomplete_components():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)

    with pytest.raises(ValueError, match="component_raw_total"):
        TechnicalResult(
            ticker="AAPL",
            timestamp=datetime.now(UTC),
            snapshot=snapshot,
            components={"trend": {}},
            total_score=80,
            component_raw_total=20,
        )


def test_technical_result_accepts_adjusted_contract_fields():
    snapshot = IndicatorSnapshot(price=100.0, change_pct=1.0)
    verdict = TechnicalVerdict(
        action="hold",
        entry_mode="extended_hold",
        confidence="medium",
        new_entry_allowed=False,
        reasons=["추세는 유지"],
        cautions=["단기 과열"],
        invalidation_level=92.5,
        score_trend_summary="최근 5거래일 adjusted score가 70에서 62로 둔화",
    )

    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(UTC),
        snapshot=snapshot,
        components={},
        total_score=80,
        component_raw_total=80,
        adjusted_score=62,
        technical_verdict=verdict,
        score_history=[
            ScoreHistoryPoint(
                date="2026-07-16",
                close=100.0,
                component_raw_total=80,
                adjusted_score=62,
                verdict_action="hold",
                one_line_reason="과열로 신규 진입 제한",
            )
        ],
        aggregation_trace=[
            AggregationTraceEntry(
                rule="overextended_penalty",
                before=80,
                after=62,
                reason="RSI 과열",
            )
        ],
    )

    assert result.adjusted_score == 62
    assert result.technical_verdict.action == "hold"
    assert result.score_history[0].verdict_action == "hold"
    assert result.aggregation_trace[0].rule == "overextended_penalty"

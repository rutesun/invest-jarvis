import pytest
from datetime import datetime
from src.tools.technical.models import (
    IndicatorSnapshot,
    StrategyResult,
    TechnicalResult,
)


def test_indicator_snapshot():
    snapshot = IndicatorSnapshot(
        price=178.50,
        change_pct=2.5,
        sma_20=175.0,
        rsi=58.3,
    )
    assert snapshot.price == 178.50
    assert snapshot.sma_20 == 175.0
    assert snapshot.sma_50 is None


def test_strategy_result():
    result = StrategyResult(
        name="trend",
        status="강세",
        confidence=75.0,
        signals=["골든크로스"],
        evidence=["20일선 > 50일선"],
        metrics={"sma_20": 175.0, "sma_50": 170.0},
    )
    assert result.name == "trend"
    assert result.confidence == 75.0
    assert "골든크로스" in result.signals


def test_technical_result():
    indicators = IndicatorSnapshot(price=178.50, change_pct=2.5)
    strategy = StrategyResult(
        name="trend",
        status="강세",
        confidence=75.0,
        signals=[],
        evidence=[],
        metrics={},
    )
    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        indicators=indicators,
        strategies=[strategy],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["상승 추세"],
        warnings=[],
    )
    assert result.ticker == "AAPL"
    assert result.overall_assessment == "매수"
    assert len(result.strategies) == 1

import pytest
from datetime import datetime
from src.tools.technical.models import (
    IndicatorSnapshot,
    StrategyResult,
    TechnicalResult,
    ComponentResult,
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
        snapshot=indicators,
        components={},
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


def test_component_result():
    result = ComponentResult(
        signals=["Stage 2"],
        evidence=["Price > SMA_150 > SMA_200"],
        metrics={"sma_150": 175.0},
        score=40,
    )
    assert result.score == 40
    assert len(result.signals) == 1


def test_indicator_snapshot_extended_fields():
    snapshot = IndicatorSnapshot(
        price=178.50,
        change_pct=2.5,
        sma_150=172.0,
        crsi=65.0,
        crsi_high_band=80.0,
        crsi_low_band=20.0,
        vol_sma_20=1500000.0,
        swing_high=180.0,
        swing_low=170.0,
        is_gap_up=False,
        is_gap_down=False,
        macd_fast=1.5,
    )
    assert snapshot.sma_150 == 172.0
    assert snapshot.crsi == 65.0
    assert snapshot.vol_sma_20 == 1500000.0


def test_technical_result_total_score():
    snapshot = IndicatorSnapshot(price=178.50, change_pct=2.5)
    result = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=snapshot,
        components={},
        indicators=snapshot,
        strategies=[],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=[],
        warnings=[],
        total_score=65,
    )
    assert result.total_score == 65

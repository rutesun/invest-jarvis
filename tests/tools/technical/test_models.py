from datetime import datetime

from src.tools.technical.models import (
    ChartPatternResult,
    ComponentResult,
    IndicatorSnapshot,
    PriceLevel,
    PriceLevels,
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


def test_chart_pattern_result_creation():
    """Test ChartPatternResult model with all fields"""
    result = ChartPatternResult(
        pattern_name="Cup & Handle",
        detected=True,
        confidence=0.85,
        completed_date="2026-04-15",
        days_ago=8,
        current_price=200.0,
        breakout_level=205.0,
        support_level=175.0,
        description="컵 깊이 28%, 핸들 조정 12%, 8일 전 완성",
        key_levels={"cup_bottom": 140.0, "right_peak": 200.0},
    )

    assert result.detected is True
    assert result.confidence == 0.85
    assert result.pattern_name == "Cup & Handle"


def test_price_level_model():
    """Test PriceLevel with distance calculation"""
    level = PriceLevel(price=187.50, type="pivot_s1", distance_pct=-6.25, description="피봇 지지1")

    assert level.price == 187.50
    assert level.type == "pivot_s1"
    assert level.distance_pct == -6.25


def test_price_levels_container():
    """Test PriceLevels with sorted supports/resistances"""
    levels = PriceLevels(
        current_price=200.0,
        support_levels=[
            PriceLevel(price=187.0, type="pivot_s1", distance_pct=-6.5, description="피봇 S1"),
            PriceLevel(price=175.0, type="sma_50", distance_pct=-12.5, description="50일선"),
        ],
        resistance_levels=[
            PriceLevel(price=210.0, type="pivot_r1", distance_pct=+5.0, description="피봇 R1"),
        ],
        targets={"cup_handle": 250.0, "fib_1.618": 235.0},
    )

    assert levels.current_price == 200.0
    assert len(levels.support_levels) == 2
    assert levels.support_levels[0].price == 187.0  # Closer support first
    assert levels.targets["cup_handle"] == 250.0

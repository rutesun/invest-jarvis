"""Tests for chart rendering."""

import os
from datetime import datetime, timedelta

import pandas as pd

from src.tools.technical.charting import ChartResult, render_technical_chart
from src.tools.technical.models import ChartPatternResult, IndicatorSnapshot, PriceLevel


def test_chart_result_creation():
    """Test ChartResult dataclass creation."""
    result = ChartResult(ticker="AAPL", path="/tmp/chart.png", success=True)
    assert result.ticker == "AAPL"
    assert result.path == "/tmp/chart.png"
    assert result.success is True
    assert result.error == ""


def test_chart_result_with_error():
    """Test ChartResult with error."""
    result = ChartResult(ticker="AAPL", path="", success=False, error="Test error")
    assert result.success is False
    assert result.error == "Test error"


def test_render_technical_chart_basic():
    """Test basic chart rendering without patterns."""
    dates = pd.date_range(end=datetime.now(), periods=100, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100.0] * 100,
            "High": [105.0] * 100,
            "Low": [95.0] * 100,
            "Close": [102.0] * 100,
            "Volume": [1000000] * 100,
            "sma_20": [100.5] * 100,
            "sma_50": [99.5] * 100,
            "sma_200": [98.0] * 100,
        },
        index=dates,
    )

    snapshot = IndicatorSnapshot(price=102.0, change_pct=2.0)

    result = render_technical_chart(
        ticker="TEST",
        df=df,
        indicators=snapshot.model_dump(),
        out_dir="/tmp/test_charts",
        window_days=63,
    )

    assert result.ticker == "TEST"
    assert result.success is True
    assert result.path.endswith(".png")
    assert os.path.exists(result.path)

    # Cleanup
    if os.path.exists(result.path):
        os.remove(result.path)


def test_render_technical_chart_with_patterns():
    """Test chart rendering with pattern markers."""
    dates = pd.date_range(end=datetime.now(), periods=100, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100.0] * 100,
            "High": [105.0] * 100,
            "Low": [95.0] * 100,
            "Close": [102.0] * 100,
            "Volume": [1000000] * 100,
            "sma_20": [100.5] * 100,
        },
        index=dates,
    )

    snapshot = IndicatorSnapshot(price=102.0, change_pct=2.0)

    pattern = ChartPatternResult(
        pattern_name="Cup & Handle",
        detected=True,
        confidence=0.85,
        completed_date=(datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
        days_ago=10,
        current_price=102.0,
        breakout_level=105.0,
        description="Test pattern",
    )

    result = render_technical_chart(
        ticker="TEST_PATTERN",
        df=df,
        indicators=snapshot.model_dump(),
        patterns={"cup_and_handle": pattern},
        out_dir="/tmp/test_charts",
        window_days=63,
    )

    assert result.success is True
    assert os.path.exists(result.path)

    # Cleanup
    if os.path.exists(result.path):
        os.remove(result.path)


def test_render_technical_chart_with_levels():
    """Test chart rendering with support/resistance levels."""
    dates = pd.date_range(end=datetime.now(), periods=100, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100.0] * 100,
            "High": [105.0] * 100,
            "Low": [95.0] * 100,
            "Close": [102.0] * 100,
            "Volume": [1000000] * 100,
        },
        index=dates,
    )

    snapshot = IndicatorSnapshot(price=102.0, change_pct=2.0)

    support = [PriceLevel(price=95.0, type="swing_low", distance_pct=-6.9, description="Swing Low")]
    resistance = [
        PriceLevel(price=105.0, type="swing_high", distance_pct=2.9, description="Swing High")
    ]

    result = render_technical_chart(
        ticker="TEST_LEVELS",
        df=df,
        indicators=snapshot.model_dump(),
        price_levels={"support_levels": support, "resistance_levels": resistance},
        out_dir="/tmp/test_charts",
        window_days=63,
    )

    assert result.success is True
    assert os.path.exists(result.path)

    # Cleanup
    if os.path.exists(result.path):
        os.remove(result.path)


def test_render_technical_chart_empty_df():
    """Test chart rendering with empty dataframe."""
    df = pd.DataFrame()
    snapshot = IndicatorSnapshot(price=100.0, change_pct=0.0)

    result = render_technical_chart(
        ticker="EMPTY",
        df=df,
        indicators=snapshot.model_dump(),
        out_dir="/tmp/test_charts",
    )

    assert result.success is False
    assert "Empty dataframe" in result.error or "empty" in result.error.lower()

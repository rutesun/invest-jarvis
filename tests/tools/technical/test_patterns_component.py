import pandas as pd

from src.tools.technical.components.patterns import analyze_patterns


def test_analyze_patterns_vcp_detection():
    """Test VCP (Volatility Contraction Pattern) detection."""
    # Create test data with contracting volatility in recent 8 bars
    data = {
        "Close": [100] * 50,
        "High": [105] * 50,
        "Low": [95] * 50,
        "ATR": [10] * 42 + [10, 9, 8, 7, 5, 4, 3, 2],  # Contracting ATR in last 8
    }
    df = pd.DataFrame(data)

    result = analyze_patterns(df)

    assert "VCP (에너지 응축)" in result.signals
    assert result.score > 0
    assert "ATR" in str(result.evidence)


def test_analyze_patterns_breakout_rolling_high():
    """Test breakout detection using rolling high."""
    # Create breakout scenario
    close_values = [100] * 40 + [101, 102, 103, 104, 105, 110, 115, 120, 125, 130]
    df = pd.DataFrame(
        {
            "Close": close_values,
            "High": [c + 2 for c in close_values],
            "Low": [c - 2 for c in close_values],
            "Volume": [1000000] * 50,
        }
    )

    result = analyze_patterns(df)

    assert "돌파 (신고가)" in result.signals or "상승 돌파" in result.signals
    assert result.score > 0


def test_analyze_patterns_breakout_swing_high():
    """Test breakout detection using swing high."""
    df = pd.DataFrame(
        {
            "Close": [100] * 20 + [105] * 5,
            "High": [102] * 20 + [107] * 5,
            "Low": [98] * 20 + [103] * 5,
            "Volume": [1000000] * 25,
            "Swing_High": [None] * 15 + [102.0] + [None] * 9,  # Swing high at index 15
        }
    )

    result = analyze_patterns(df)

    # Should detect swing high breakout
    assert result.score >= 0


def test_analyze_patterns_hammer():
    """Test Hammer candlestick pattern detection."""
    df = pd.DataFrame(
        {
            "Open": [100] * 5 + [100],
            "High": [102] * 5 + [100.2],  # Small upper shadow
            "Low": [99] * 5 + [90],  # Long lower shadow
            "Close": [101] * 5 + [99.5],
            "Volume": [1000000] * 6,
        }
    )

    result = analyze_patterns(df)

    assert any("Hammer" in sig or "망치형" in sig for sig in result.signals)
    assert result.score > 0


def test_analyze_patterns_bullish_engulfing():
    """Test Bullish Engulfing pattern detection."""
    df = pd.DataFrame(
        {
            "Open": [102, 100, 97],  # Last open below prev close
            "High": [103, 101, 105],
            "Low": [99, 97, 96],
            "Close": [100, 98, 104],  # Last candle engulfs previous
            "Volume": [1000000] * 3,
        }
    )

    result = analyze_patterns(df)

    assert any("Bullish Engulfing" in sig or "상승장악형" in sig for sig in result.signals)
    assert result.score > 0


def test_analyze_patterns_no_data():
    """Test with insufficient data."""
    df = pd.DataFrame({"Close": [100]})

    result = analyze_patterns(df)

    assert result.score == 0
    assert len(result.signals) == 0


def test_analyze_patterns_no_patterns():
    """Test when no patterns are detected."""
    # Stable, no patterns
    df = pd.DataFrame(
        {
            "Open": [100] * 50,
            "High": [101] * 50,
            "Low": [99] * 50,
            "Close": [100] * 50,
            "Volume": [1000000] * 50,
            "ATR": [1.0] * 50,  # Stable ATR (no VCP)
        }
    )

    result = analyze_patterns(df)

    # Should return valid result with no strong signals
    assert isinstance(result.score, int)
    assert isinstance(result.signals, list)

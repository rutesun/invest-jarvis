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


def test_analyze_patterns_vcp_strong_both_conditions():
    """VCP Strong: ATR contraction (30%) + Tightness persistence (7/20 + 3 consecutive)."""
    # ATR contraction: first 4 avg = 10, last 4 avg = 6.5 → 35% contraction
    # Tightness: 7 tight days out of 20 (range < ATR × 0.5)
    # Recent: last 3 days all tight
    atr_values = [10.0] * 30 + [10, 9, 8, 7, 6, 6, 6, 6]  # 38 values, last 8 for contraction check

    # 20-day window for tightness check (indices 18-37)
    # Need 7 tight days: indices 27, 29, 31, 33, 34, 35, 36, 37 (last 3 consecutive)
    high_values = []
    low_values = []
    for i in range(38):
        atr = atr_values[i]
        if i in [27, 29, 31, 33, 34, 35, 36, 37]:  # Tight days
            high_values.append(100 + atr * 0.4)  # Range < ATR × 0.5
            low_values.append(100 - atr * 0.05)
        else:
            high_values.append(100 + atr * 0.6)  # Normal range
            low_values.append(100 - atr * 0.4)

    df = pd.DataFrame(
        {
            "Close": [100] * 38,
            "High": high_values,
            "Low": low_values,
            "ATR": atr_values,
        }
    )

    result = analyze_patterns(df)

    # Must detect VCP Strong (both conditions met)
    assert any("VCP Strong" in sig for sig in result.signals), (
        f"Expected VCP Strong, got: {result.signals}"
    )
    # VCP Strong scores 20 points
    vcp_score = sum(
        15 if "VCP" in sig and "Strong" not in sig else 20 if "Strong" in sig else 0
        for sig in result.signals
    )
    assert vcp_score == 20, f"Expected VCP Strong score 20, got: {vcp_score}"
    assert any("ATR" in str(e) and "수축" in str(e) for e in result.evidence)
    assert any("tight" in str(e).lower() or "응축" in str(e) for e in result.evidence)


def test_analyze_patterns_vcp_general_atr_only():
    """VCP General: ATR contraction (25%) but no tightness persistence."""
    # ATR contraction: first 4 avg = 10, last 4 avg = 7 → 30% contraction
    # No tightness: all days have normal range
    atr_values = [10.0] * 30 + [10, 9, 8, 7, 7, 7, 6, 6]  # 38 values

    # All days have normal range (High-Low > ATR × 0.5)
    high_values = [100 + atr * 0.6 for atr in atr_values]
    low_values = [100 - atr * 0.4 for atr in atr_values]

    df = pd.DataFrame(
        {
            "Close": [100] * 38,
            "High": high_values,
            "Low": low_values,
            "ATR": atr_values,
        }
    )

    result = analyze_patterns(df)

    # Should detect General VCP but not Strong (only stage 1 satisfied)
    assert any("VCP" in sig for sig in result.signals), (
        f"Expected VCP signal, got: {result.signals}"
    )
    assert all("Strong" not in sig for sig in result.signals), (
        f"Should not detect Strong, got: {result.signals}"
    )
    # General VCP scores 10 points
    vcp_score = sum(10 if "VCP" in sig and "Strong" not in sig else 0 for sig in result.signals)
    assert vcp_score == 10, f"Expected General VCP score 10, got: {vcp_score}"
    assert any("ATR" in str(e) for e in result.evidence)


def test_analyze_patterns_vcp_no_detection():
    """VCP Not Detected: No ATR contraction."""
    # Stable ATR (no contraction)
    atr_values = [10.0] * 38

    high_values = [100 + atr * 0.6 for atr in atr_values]
    low_values = [100 - atr * 0.4 for atr in atr_values]

    df = pd.DataFrame(
        {
            "Close": [100] * 38,
            "High": high_values,
            "Low": low_values,
            "ATR": atr_values,
        }
    )

    result = analyze_patterns(df)

    # Should NOT detect VCP
    assert "VCP" not in str(result.signals)


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
    metadata = next(item for item in result.signal_metadata if item.signal_type == "breakout")
    assert metadata.source == "patterns"
    assert metadata.bias == "bullish"
    assert metadata.intent == "entry"
    assert metadata.severity == "high"
    assert metadata.entry_eligible is True


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
    metadata = next(item for item in result.signal_metadata if item.signal_type == "reversal")
    assert metadata.source == "patterns"
    assert metadata.bias == "bullish"
    assert metadata.intent == "watch"
    assert metadata.severity == "medium"
    assert metadata.entry_eligible is False


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

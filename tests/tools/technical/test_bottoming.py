import pandas as pd

from src.tools.technical.bottoming import (
    BottomingStructure,
    BottomingThresholds,
    detect_bottoming_structure,
)
from src.tools.technical.models import ComponentSignal


def _divergence_components(bias: str) -> dict:
    return {
        "divergence": {
            "score": 15 if bias == "bullish" else -15,
            "signals": [],
            "evidence": [],
            "metrics": {},
            "signal_metadata": [
                ComponentSignal(
                    signal_type="reversal",
                    bias=bias,
                    intent="watch" if bias == "bullish" else "risk",
                    severity="medium",
                    source="divergence",
                    reason="divergence",
                )
            ],
        }
    }


def _velocity_components(slope_change: float) -> dict:
    return {
        "velocity": {
            "score": 0,
            "signals": [],
            "evidence": [],
            "metrics": {"norm_slope": -0.1, "slope_change": slope_change},
            "signal_metadata": [],
        }
    }


def _df(lows: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    """Build a minimal OHLCV frame from a list of daily lows.

    Close/Open/High track the low (flat body) unless overridden; only Low and
    Volume matter for the structure detectors under test.
    """
    n = len(lows)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    close = [low + 1 for low in lows]
    if volumes is None:
        volumes = [1_000_000.0] * n
    return pd.DataFrame(
        {
            "Open": close,
            "High": [c + 1 for c in close],
            "Low": lows,
            "Close": close,
            "Volume": volumes,
        },
        index=idx,
    )


def _empty_components() -> dict:
    return {}


def test_higher_low_detected_when_recent_lows_step_up():
    # Prior 30-day trough ~90, recent 10-day trough ~100 → higher low.
    lows = [90.0] * 30 + [100.0] * 10
    df = _df(lows)

    result = detect_bottoming_structure(df, _empty_components(), context=None)

    assert result.higher_low is True


def test_higher_low_absent_when_recent_lows_break_down():
    # Recent trough undercuts the prior trough → no higher low.
    lows = [100.0] * 30 + [88.0] * 10
    df = _df(lows)

    result = detect_bottoming_structure(df, _empty_components(), context=None)

    assert result.higher_low is False


def test_volume_dry_detected_when_recent_volume_contracts():
    # Prior 20-day avg ~2.0M, recent 5-day avg ~1.0M → dry (0.5 < 0.85 ratio).
    lows = [100.0] * 30
    volumes = [2_000_000.0] * 25 + [1_000_000.0] * 5
    df = _df(lows, volumes)

    result = detect_bottoming_structure(df, _empty_components(), context=None)

    assert result.volume_dry is True


def test_volume_dry_absent_when_recent_volume_expands():
    lows = [100.0] * 30
    volumes = [1_000_000.0] * 25 + [2_000_000.0] * 5
    df = _df(lows, volumes)

    result = detect_bottoming_structure(df, _empty_components(), context=None)

    assert result.volume_dry is False


def test_bullish_divergence_read_from_components():
    df = _df([100.0] * 30)

    result = detect_bottoming_structure(df, _divergence_components("bullish"), context=None)

    assert result.bullish_divergence is True


def test_bearish_divergence_does_not_count_as_bullish():
    df = _df([100.0] * 30)

    result = detect_bottoming_structure(df, _divergence_components("bearish"), context=None)

    assert result.bullish_divergence is False


def test_momentum_improving_when_slope_change_positive():
    df = _df([100.0] * 30)

    result = detect_bottoming_structure(df, _velocity_components(0.05), context=None)

    assert result.momentum_improving is True


def test_momentum_not_improving_when_slope_change_negative():
    df = _df([100.0] * 30)

    result = detect_bottoming_structure(df, _velocity_components(-0.05), context=None)

    assert result.momentum_improving is False


def test_signal_count_and_qualifies():
    # higher-low + volume-dry + momentum → 3 signals → qualifies (MIN_SIGNALS=3).
    lows = [90.0] * 30 + [100.0] * 10
    volumes = [2_000_000.0] * 35 + [1_000_000.0] * 5
    df = _df(lows, volumes)

    result = detect_bottoming_structure(df, _velocity_components(0.05), context=None)

    assert result.higher_low is True
    assert result.volume_dry is True
    assert result.momentum_improving is True
    assert result.signal_count == 3
    assert result.qualifies is True


def test_single_signal_does_not_qualify():
    # Only higher-low fires (volume flat) → 1 signal → not a candidate.
    lows = [90.0] * 30 + [100.0] * 10
    df = _df(lows)

    result = detect_bottoming_structure(df, _empty_components(), context=None)

    assert result.signal_count == 1
    assert result.qualifies is False


def test_two_signals_does_not_qualify():
    # higher-low + volume-dry → only 2 signals → below MIN_SIGNALS(3).
    lows = [90.0] * 30 + [100.0] * 10
    volumes = [2_000_000.0] * 35 + [1_000_000.0] * 5
    df = _df(lows, volumes)

    result = detect_bottoming_structure(df, _empty_components(), context=None)

    assert result.signal_count == 2
    assert result.qualifies is False


def test_bonus_zero_when_not_qualifying():
    lows = [90.0] * 30 + [100.0] * 10
    df = _df(lows)

    result = detect_bottoming_structure(df, _empty_components(), context=None)

    assert result.qualifies is False
    assert result.bonus == 0


def test_bonus_capped_at_max_when_all_signals_fire():
    structure = BottomingStructure(
        higher_low=True,
        bullish_divergence=True,
        volume_dry=True,
        momentum_improving=True,
    )

    assert structure.qualifies is True
    assert structure.bonus == BottomingThresholds.BONUS_MAX


def test_bonus_sums_weights_below_cap():
    structure = BottomingStructure(
        higher_low=True, volume_dry=True, bullish_divergence=True
    )

    expected = min(
        BottomingThresholds.W_HIGHER_LOW
        + BottomingThresholds.W_VOLUME_DRY
        + BottomingThresholds.W_BULLISH_DIV,
        BottomingThresholds.BONUS_MAX,
    )
    assert structure.qualifies is True
    assert structure.bonus == expected

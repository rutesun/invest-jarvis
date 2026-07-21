import math

import pytest

from src.tools.technical.presentation import format_long_sma


def test_format_long_sma_directions_and_missing_data():
    assert format_long_sma(123.45, 0.82) == "$123.45 · ↗ 상승 (+0.82%/21일)"
    assert format_long_sma(110.20, 0.12) == "$110.20 · → 보합 (+0.12%/21일)"
    assert format_long_sma(98.0, -0.75) == "$98.00 · ↘ 하락 (-0.75%/21일)"
    assert format_long_sma(None, None) == "N/A · — 데이터 부족"


@pytest.mark.parametrize(
    ("slope", "label"),
    [
        (0.5, "→ 보합"),
        (math.nextafter(0.5, math.inf), "↗ 상승"),
        (-0.5, "→ 보합"),
        (math.nextafter(-0.5, -math.inf), "↘ 하락"),
    ],
)
def test_format_long_sma_uses_exclusive_thresholds(slope, label):
    assert label in format_long_sma(100.0, slope)

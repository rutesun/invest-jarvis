from __future__ import annotations

import numpy as np
import pandas as pd

from src.strategies.swing_w150 import rules


def _breakout_bars(volume_today: float) -> pd.DataFrame:
    # 전날은 직전 고가 아래, 오늘은 위에서 마감하는 상승 150일선 위의 두 봉.
    return pd.DataFrame(
        {
            "Close": [99.0, 101.0],
            "Volume": [1000.0, volume_today],
            "SMA_150": [90.0, 90.0],
            "SMA_150_Slope_21": [1.0, 1.0],
            "High_50_Prev": [100.0, 100.0],
            "Vol_SMA_20": [1000.0, 1000.0],
        }
    )


def test_s_trigger_needs_volume_strictly_above_multiple():
    at_multiple = rules.s_trigger(_breakout_bars(rules.S_VOLUME_MULT * 1000.0))
    above_multiple = rules.s_trigger(_breakout_bars(rules.S_VOLUME_MULT * 1000.0 + 1.0))

    assert at_multiple.tolist() == [False, False]
    assert above_multiple.tolist() == [False, True]


def test_s_trigger_only_on_first_close_above_prior_high():
    bars = _breakout_bars(2000.0)
    bars.loc[0, "Close"] = 100.5

    assert not np.any(rules.s_trigger(bars))

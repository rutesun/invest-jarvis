"""Fixed-origin bulk values must equal independently evaluated raw prefixes."""

from dataclasses import replace
from importlib import import_module

import numpy as np
import pandas as pd

from src.tools.technical.chart_analysis.models import CalculationScope, SeriesInput
from tests.tools.technical.chart_analysis.test_features import bars, scope_for


def test_bulk_equals_same_origin_prefix():
    module = import_module("src.tools.technical.chart_analysis.features")
    frame = bars(100 + np.arange(225, dtype=float) / 4 + np.sin(np.arange(225)))
    frame.loc[frame.index[210], "Volume"] = np.nan
    frame.loc[frame.index[220], "Close"] = np.nan
    finality = {day.date(): "FINAL" for day in frame.index}
    finality[frame.index[222].date()] = "PROVISIONAL"
    scope = scope_for(frame, finality=finality, coverage={"complete": False})
    bulk = module.calculate_features(scope)
    for end in range(1, len(frame) + 1):
        raw = frame.iloc[:end]
        primary = SeriesInput(
            replace(scope.primary.manifest, as_of=raw.index[-1].date(), input_hash=""), raw
        )
        prefix = module.calculate_features(CalculationScope(primary, {}))
        assert prefix[raw.index[-1].date()] == bulk[raw.index[-1].date()]


def test_legacy_extrema_recomputed_on_prefix():
    from src.tools.technical.indicators import IndicatorCalculator

    module = import_module("src.tools.technical.chart_analysis.legacy_features")
    frame = bars([100, 101, 102, 103, 104, 105, 110, 109, 108, 107, 106, 115, 114, 113, 112, 111])
    prefix = frame.iloc[:11]
    shadow = module.calculate_legacy_features(prefix)
    pd.testing.assert_frame_equal(shadow, IndicatorCalculator().calculate(prefix), check_exact=True)
    assert shadow["Swing_High"].iloc[6] == 111
    assert pd.isna(module.calculate_legacy_features(frame)["Swing_High"].iloc[6])

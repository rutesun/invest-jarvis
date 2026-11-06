"""Participation uses the same raw 20-day window; concentration is diagnostic."""

import numpy as np
import pytest

from tests.tools.technical.chart_analysis.test_features import bars
from tests.tools.technical.chart_analysis.test_quality import analysis_for, score


def directional_frame(changes, volumes):
    # 232 rows including the previous close + the fixed 20-day evaluated window.
    close = np.r_[100 + np.arange(232) * 0.01, 102.31 + np.cumsum(changes)]
    frame = bars(close)
    frame.iloc[-20:, frame.columns.get_loc("Volume")] = volumes
    return frame


@pytest.mark.parametrize("count,want", [(4, None), (5, 100)])
def test_participation_policy_four_directional_samples_null_five_valid(count, want):
    changes = [1] * count + [0] * (20 - count)
    result = score(analysis_for(directional_frame(changes, [10] * 20)))
    assert result.axes["participation"] == want
    assert (result.quality is not None) is (count >= 5)
    assert ("LOW_DIRECTIONAL_SAMPLE" in result.reasons) is (count < 5)
    assert result.diagnostics["participation"]["flat_volume"] == 10 * (20 - count)
    assert result.diagnostics["participation"]["directional_sample"] == count


@pytest.mark.parametrize("change,want", [(1, 100), (-1, 0)])
def test_participation_policy_one_sided_keeps_100_or_0(change, want):
    result = score(analysis_for(directional_frame([change] * 20, [10] * 20)))
    assert result.axes["participation"] == want
    assert "ONE_SIDED_SAMPLE" in result.reasons


@pytest.mark.parametrize("changes,volumes", [([0] * 20, [10] * 20), ([1, -1] * 10, [0] * 20)])
def test_participation_policy_flat_or_zero_volume_is_null(changes, volumes):
    result = score(analysis_for(directional_frame(changes, volumes)))
    assert result.axes["participation"] is None
    assert result.quality is None
    assert "ZERO_DIRECTIONAL_VOLUME" in result.reasons
    assert result.diagnostics["participation"]["directional_sample"] == 0


@pytest.mark.parametrize("maximum,other,warn", [(49, 3, False), (50, 2, True)])
def test_participation_policy_concentration_049_050_is_inclusive(maximum, other, warn):
    volumes = [maximum] + [3] * 16 + [other, 0, 0]
    # 49+48+3=100 or 50+48+2=100; all positive-directional rows count.
    result = score(analysis_for(directional_frame([1, -1] * 10, volumes)))
    assert result.diagnostics["participation"]["max_share"] == maximum / 100
    assert ("CONCENTRATED_VOLUME" in result.reasons) is warn
    assert result.axes["participation"] == 100 * (maximum + 24) / 100


@pytest.mark.parametrize("factor", [1, 10, 100])
def test_concentration_sensitivity_fixed_window_changes_formula_and_max_share(factor):
    frame = directional_frame([1, -1] * 10, [10] * 20)
    frame.iloc[-20, frame.columns.get_loc("Volume")] *= factor
    result = score(analysis_for(frame))
    assert result.axes["participation"] == pytest.approx(
        100 * (90 + 10 * factor) / (190 + 10 * factor), abs=1e-10
    )
    assert result.diagnostics["participation"]["max_share"] == pytest.approx(
        10 * factor / (190 + 10 * factor), abs=1e-10
    )
    assert ("CONCENTRATED_VOLUME" in result.reasons) is (factor == 100)


@pytest.mark.parametrize("count,want", [(20, None), (21, 100)])
def test_participation_keeps_the_preceding_close_for_exactly_twenty_directions(count, want):
    result = score(analysis_for(bars(list(range(100, 100 + count)))))
    assert result.axes["participation"] == want


@pytest.mark.parametrize("column", ["Close", "Volume"])
def test_missing_price_or_volume_in_fixed_window_keeps_participation_null(column):
    frame = directional_frame([1, -1] * 10, [10] * 20)
    frame.loc[frame.index[-5], column] = np.nan
    result = score(analysis_for(frame))
    assert result.axes["participation"] is None
    assert result.quality is None
    assert "INPUT_MISSING" in result.reasons

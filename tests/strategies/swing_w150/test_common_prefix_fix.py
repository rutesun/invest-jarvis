"""Public replay references must describe only the snapshot's input prefix."""

from dataclasses import replace

import pytest

from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.strategies.swing_w150.signals import (
    _iter_swing_detection,
    detect_swing,
    iter_swing_detection,
)
from tests.strategies.swing_w150.conftest import SignalFactory


def test_each_public_snapshot_binds_real_prefix_analysis_and_refs():
    features = SignalFactory().same_day_exit_and_entry()
    params = SwingW150Parameters()
    snapshots = list(iter_swing_detection("TEST", features, params))
    for mode in ("latest", "none"):
        internal = list(_iter_swing_detection("TEST", features, params, metadata_mode=mode))
        assert [s.model_dump() for s in internal] == [s.model_dump() for s in snapshots]
        assert all(not s.common_analyses and not s.fact_selections for s in internal[:-1])
        assert internal[-1].common_analyses == (
            snapshots[-1].common_analyses if mode == "latest" else ()
        )
    for size in (1, 219, 251, 252):
        prefix = replace(
            features, frame=features.frame.iloc[:size], finalities=features.finalities[:size]
        )
        expected = detect_swing("TEST", prefix, params)
        actual = snapshots[size - 1]
        assert actual.model_dump() == expected.model_dump()
        assert actual.common_analyses[0].manifest.as_of == actual.as_of
        assert actual.common_analyses == expected.common_analyses
        assert actual.fact_selections == expected.fact_selections
        for item in actual.common_analyses[0].items:
            assert item.status_as_of <= actual.as_of


@pytest.mark.parametrize("size", [1, 220])
def test_future_suffix_cannot_change_past_public_evidence(size):
    from itertools import islice

    features = SignalFactory().same_day_exit_and_entry()
    altered = features.frame.copy(deep=True)
    for column in ("Open", "High", "Low", "Close", "Volume"):
        altered.iloc[size:, altered.columns.get_loc(column)] *= 3
    changed = replace(features, frame=altered)
    params = SwingW150Parameters()
    original = next(islice(iter_swing_detection("TEST", features, params), size - 1, size))
    future = next(islice(iter_swing_detection("TEST", changed, params), size - 1, size))
    assert original.model_dump() == future.model_dump()
    assert original.common_analyses == future.common_analyses
    assert original.fact_selections == future.fact_selections

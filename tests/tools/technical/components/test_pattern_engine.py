from __future__ import annotations

import pandas as pd

from src.tools.technical.components.pattern_engine import PatternEngine


def _build_test_df() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    prices = [100 + (i % 10) for i in range(60)]
    return pd.DataFrame(
        {
            "Open": prices,
            "High": [price + 2 for price in prices],
            "Low": [price - 2 for price in prices],
            "Close": prices,
            "Volume": [1_000_000 + i * 1000 for i in range(60)],
        },
        index=dates,
    )


def test_pattern_engine_passes_precomputed_swings(monkeypatch):
    captured = {}

    def _fake_detect_chart_patterns(df, snapshot=None, swings=None):
        captured["df_len"] = len(df)
        captured["swings"] = swings
        return {}

    monkeypatch.setattr(
        "src.tools.technical.components.pattern_engine.detect_chart_patterns",
        _fake_detect_chart_patterns,
    )

    result = PatternEngine(swing_window=5).detect(_build_test_df())

    assert result == {}
    assert captured["df_len"] == 60
    assert captured["swings"] is not None
    assert isinstance(captured["swings"].demand_candidates, list)
    assert isinstance(captured["swings"].supply_candidates, list)

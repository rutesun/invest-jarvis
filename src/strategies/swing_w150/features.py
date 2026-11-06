"""Typed SWING_W150 input computed from raw OHLCV at one boundary."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from src.strategies.models import BarFinality, CoverageManifest
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.tools.technical.chart_analysis.models import ChartAnalysis
from src.tools.technical.scorecard_models import DataStatus


_OHLCV = ("Open", "High", "Low", "Close", "Volume")


def observation_feature_columns(frame: pd.DataFrame) -> pd.DataFrame:
    from src.tools.technical.chart_analysis._legacy_structure import (
        observation_feature_columns as common_columns,
    )

    return common_columns(frame)


@dataclass(frozen=True)
class SwingFeatureFrame:
    frame: pd.DataFrame
    data_status: DataStatus
    finalities: tuple[BarFinality, ...]
    coverage: CoverageManifest | None = None
    common_analyses: tuple[ChartAnalysis, ...] = ()


def build_swing_features(
    raw_ohlcv: pd.DataFrame,
    params: SwingW150Parameters,
    *,
    finalities: Sequence[BarFinality] | None = None,
    coverage: CoverageManifest | None = None,
    common_analysis: ChartAnalysis | None = None,
) -> SwingFeatureFrame:
    """Calculate the signal inputs from the observed price bars."""
    resolved_finalities = (
        (BarFinality.FINAL,) * len(raw_ohlcv) if finalities is None else tuple(finalities)
    )
    if len(resolved_finalities) != len(raw_ohlcv):
        raise ValueError("finalities length must match raw OHLCV bars")
    frame = raw_ohlcv.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    missing = set(_OHLCV) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")
    frame = frame.loc[:, _OHLCV].copy()
    if common_analysis is not None:
        from src.strategies.swing_w150.common import frame_scope, raw_rules, validate_analysis
        from src.tools.technical.chart_analysis.features import LEGACY_VERSION

        scope = frame_scope(
            common_analysis.manifest.ticker,
            frame,
            finalities=resolved_finalities,
            coverage=coverage,
            feature_version=LEGACY_VERSION,
            source_manifest=common_analysis.manifest,
        )
        validate_analysis(common_analysis, scope, raw_rules(params))
    if len(frame) < params.minimum_history_bars:
        return SwingFeatureFrame(
            frame=frame,
            data_status=DataStatus.INSUFFICIENT_DATA,
            finalities=resolved_finalities,
            coverage=coverage,
        )

    if coverage is not None and (not coverage.complete or coverage.truncation_reason):
        return SwingFeatureFrame(
            frame=frame,
            data_status=DataStatus.PARTIAL,
            finalities=resolved_finalities,
            coverage=coverage,
        )

    from src.strategies.swing_w150.common import (
        frame_scope,
        raw_rules,
        raw_swing_analysis,
        row_frame,
        validate_analysis,
    )
    from src.tools.technical.chart_analysis.features import LEGACY_VERSION

    if common_analysis is None:
        common_analysis = raw_swing_analysis(
            frame, params, finalities=resolved_finalities, coverage=coverage
        )
    scope = frame_scope(
        common_analysis.manifest.ticker,
        frame,
        finalities=resolved_finalities,
        coverage=coverage,
        feature_version=LEGACY_VERSION,
        source_manifest=common_analysis.manifest,
    )
    validate_analysis(common_analysis, scope, raw_rules(params))
    material = row_frame(common_analysis, raw_rules(params)[0])
    material.index = frame.index.copy()
    return SwingFeatureFrame(
        material, DataStatus.COMPLETE, resolved_finalities, coverage, (common_analysis,)
    )

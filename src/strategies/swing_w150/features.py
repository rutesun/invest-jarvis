"""Typed SWING_W150 input computed from raw OHLCV at one boundary."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from src.strategies.models import BarFinality, CoverageManifest
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.pivots import confirmed_pivots
from src.tools.technical.scorecard_models import DataStatus


_OHLCV = ("Open", "High", "Low", "Close", "Volume")


def observation_feature_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Causal Observation inputs; all reference windows exclude overlapping bars."""
    frame = frame.copy()
    frame["History_Bars"] = range(1, len(frame) + 1)
    frame["Previous_Close"] = frame["Close"].shift(1)
    frame["Volume_Ratio_Prev20"] = frame["Volume"] / frame["Volume"].rolling(20).mean().shift(
        1
    ).replace(0, float("nan"))
    frame["Volume_Contraction_Ratio"] = frame["Volume"].rolling(5).mean() / frame["Volume"].rolling(
        20
    ).mean().shift(5).replace(0, float("nan"))
    prior_high = frame["High"].rolling(20).max().shift(1)
    trend = (frame["Close"] > frame["SMA_150"]) & (frame["SMA_150_Slope_21"] >= 0)
    frame["Contraction_Context"] = trend & (frame["Close"] <= prior_high)
    frame["Prior_Trend_Context"] = trend.shift(1).rolling(20).max().fillna(0).astype(bool)
    frame["Prior_Below_SMA20"] = (
        (frame["Close"] < frame["SMA_20"]).shift(1).rolling(10).max().fillna(0).astype(bool)
    )
    frame["Previous_SMA20_Slope"] = frame["SMA_20_Slope_5"].shift(1)
    frame["Return_5"] = frame["Close"] / frame["Close"].shift(5) - 1
    frame["High_Break_5"] = frame["Close"] > frame["High"].rolling(5).max().shift(1)
    breakout = frame["High"].rolling(50).max().shift(1)
    frame["Price_Breakout_Event"] = (frame["Close"] > breakout) & (
        frame["Close"].shift(1) <= breakout.shift(1)
    )
    return frame


@dataclass(frozen=True)
class SwingFeatureFrame:
    frame: pd.DataFrame
    data_status: DataStatus
    finalities: tuple[BarFinality, ...]
    coverage: CoverageManifest | None = None


def build_swing_features(
    raw_ohlcv: pd.DataFrame,
    params: SwingW150Parameters,
    *,
    finalities: Sequence[BarFinality] | None = None,
    coverage: CoverageManifest | None = None,
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

    frame = IndicatorCalculator().calculate(frame)
    lookback = params.direction_lookback_bars
    for period in (50, 150, 200):
        column = f"SMA_{period}"
        frame[f"{column}_Slope_{lookback}"] = frame[column] - frame[column].shift(lookback)
    frame["Trend_Breakout_High_Prev"] = (
        frame["High"].rolling(params.trend_breakout_lookback).max().shift(1)
    )
    frame["Deep_Recovery_High_Prev"] = (
        frame["High"].rolling(params.deep_recovery_breakout_lookback).max().shift(1)
    )
    higher_low, lower_low_lower_high = confirmed_pivots(
        frame["High"].to_numpy(dtype=float), frame["Low"].to_numpy(dtype=float)
    )
    frame["Higher_Low"] = higher_low
    frame["Lower_Low_Lower_High"] = lower_low_lower_high
    frame = observation_feature_columns(frame)
    return SwingFeatureFrame(
        frame=frame,
        data_status=DataStatus.COMPLETE,
        finalities=resolved_finalities,
        coverage=coverage,
    )

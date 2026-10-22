"""Source-time chart anchors shared with independent entry diagnostics."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pandas as pd

from src.strategies.entry_opportunity import SIGNAL_POLICY_VERSION
from src.strategies.models import (
    ChartBundle,
    EntrySourceAnchors,
    ObservationStatus,
    StrategyObservationEpisode,
    StrategySignal,
)
from src.strategies.swing_w150.features import SwingFeatureFrame


_SUPPORT_CODES = {"SMA_20", "SMA_50", "SMA_150", "SMA_200", "SuperTrend_Up"}
_BREAKOUT_COLUMNS = {
    "TREND_BREAKOUT_ENTRY": "Trend_Breakout_High_Prev",
    "DEEP_RECOVERY_ENTRY": "Deep_Recovery_High_Prev",
}


def _feature_value(frame: pd.DataFrame, day: date, column: str) -> Decimal | None:
    stamp = pd.Timestamp(day)
    if stamp not in frame.index or column not in frame.columns:
        return None
    value = frame.loc[stamp, column]
    if pd.isna(value):
        return None
    number = Decimal(str(value))
    return number if number.is_finite() and number > 0 else None


def build_entry_source_anchors(
    source: StrategySignal,
    bundle: ChartBundle,
    features: SwingFeatureFrame,
    observation_history: Sequence[StrategyObservationEpisode],
) -> EntrySourceAnchors:
    """Freeze only observed source-prefix values without changing signal evidence."""
    frame = features.frame.loc[: pd.Timestamp(source.occurred_on)]
    breakout_column = _BREAKOUT_COLUMNS.get(source.code)
    origin_support = pullback_low = None
    if source.code == "PULLBACK_REVERSAL_ENTRY":
        episode = next(
            (
                item
                for item in observation_history
                if item.code == "PULLBACK_WATCH"
                and item.status is ObservationStatus.RESOLVED_TO_SIGNAL
                and item.ended_on == source.occurred_on
                and item.status_as_of <= source.occurred_on
                and item.started_on <= source.occurred_on
                and (item.source_signal_id is None or item.source_signal_id == source.signal_id)
            ),
            None,
        )
        if episode is not None:
            if episode.anchor_id is not None:
                origin_support = episode.anchor_origin_price
            else:
                support = next(
                    (item.code for item in episode.evidence if item.code in _SUPPORT_CODES), None
                )
                # Episode evidence refreshes daily, but its support codes/order stay fixed.
                # Restore that support's initial level, never the reversal-day moving level.
                if support is not None:
                    origin_support = _feature_value(frame, episode.started_on, support)
            bars = [
                bar
                for bar in bundle.instrument.bars
                if episode.started_on <= bar.session_date <= source.occurred_on
            ]
            if (
                bars
                and bars[0].session_date == episode.started_on
                and bars[-1].session_date == source.occurred_on
            ):
                pullback_low = min(bar.low for bar in bars)
    return EntrySourceAnchors(
        source_id=source.signal_id,
        source_date=source.occurred_on,
        source_type=source.code,
        signal_price=source.signal_price,
        atr_at_signal=_feature_value(frame, source.occurred_on, "ATR"),
        breakout_level=(
            _feature_value(frame, source.occurred_on, breakout_column)
            if breakout_column is not None
            else None
        ),
        origin_support=origin_support,
        pullback_low=pullback_low,
        anchor_finality=source.finality,
        policy_version=SIGNAL_POLICY_VERSION,
    )

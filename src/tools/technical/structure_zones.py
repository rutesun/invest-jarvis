from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.tools.technical.models import (
    IndicatorSnapshot,
    StructureZone,
    StructureZoneConfig,
    StructureZoneSet,
)


def calculate_zone_half_width(
    price: float, atr: float | None, config: StructureZoneConfig
) -> float:
    atr_width = (atr or 0.0) * config.atr_width_multiplier
    min_width = price * config.min_zone_width_pct
    max_width = price * config.max_zone_width_pct
    return min(max(atr_width, min_width), max_width)


def cluster_price_candidates(prices: list[float], half_width: float) -> list[list[float]]:
    if not prices:
        return []

    sorted_prices = sorted(prices)
    clusters: list[list[float]] = [[sorted_prices[0]]]
    for price in sorted_prices[1:]:
        if abs(price - clusters[-1][-1]) <= half_width:
            clusters[-1].append(price)
        else:
            clusters.append([price])
    return clusters


@dataclass
class _SwingCandidate:
    price: float
    timestamp: pd.Timestamp
    volume: float


class StructureZoneDetector:
    def __init__(self, config: StructureZoneConfig | None = None):
        self.config = config or StructureZoneConfig()

    def detect(self, df: pd.DataFrame, snapshot: IndicatorSnapshot) -> StructureZoneSet:
        candidates = self._build_candidates(df, snapshot)
        demand_zones = sorted(
            [zone for zone in candidates if zone.zone_type == "demand"],
            key=lambda zone: zone.total_score,
            reverse=True,
        )[: self.config.top_n_per_side]
        supply_zones = sorted(
            [zone for zone in candidates if zone.zone_type == "supply"],
            key=lambda zone: zone.total_score,
            reverse=True,
        )[: self.config.top_n_per_side]

        invalidation_candidates = list(demand_zones[:1])
        invalidation_zone = invalidation_candidates[0] if invalidation_candidates else None

        return StructureZoneSet(
            demand_zones=demand_zones,
            supply_zones=supply_zones,
            invalidation_candidates=invalidation_candidates,
            invalidation_zone=invalidation_zone,
            all_candidates=candidates,
        )

    def _build_candidates(
        self, df: pd.DataFrame, snapshot: IndicatorSnapshot
    ) -> list[StructureZone]:
        recent = df.tail(self.config.lookback_days).copy()
        low_candidates = self._extract_swing_candidates(recent, side="demand")
        high_candidates = self._extract_swing_candidates(recent, side="supply")

        return [
            *self._build_side_zones(low_candidates, "demand", snapshot),
            *self._build_side_zones(high_candidates, "supply", snapshot),
        ]

    def _extract_swing_candidates(self, df: pd.DataFrame, side: str) -> list[_SwingCandidate]:
        value_col = "Low" if side == "demand" else "High"
        rolling = (
            df[value_col].rolling(window=5, center=True, min_periods=5).min()
            if side == "demand"
            else df[value_col].rolling(window=5, center=True, min_periods=5).max()
        )
        swing_rows = df[df[value_col] == rolling].tail(12)
        return [
            _SwingCandidate(
                price=float(row[value_col]),
                timestamp=pd.Timestamp(index),
                volume=float(row.get("Volume", 0.0)),
            )
            for index, row in swing_rows.iterrows()
        ]

    def _build_side_zones(
        self,
        swings: list[_SwingCandidate],
        zone_type: str,
        snapshot: IndicatorSnapshot,
    ) -> list[StructureZone]:
        if not swings:
            return []

        average_price = sum(candidate.price for candidate in swings) / len(swings)
        half_width = calculate_zone_half_width(average_price, snapshot.atr, self.config)
        clusters = cluster_price_candidates([candidate.price for candidate in swings], half_width)

        zones: list[StructureZone] = []
        for cluster in clusters:
            cluster_candidates = [candidate for candidate in swings if candidate.price in cluster]
            touch_count = len(cluster_candidates)
            latest_touch = max(candidate.timestamp for candidate in cluster_candidates)
            recency_score = self._score_recency(latest_touch, snapshot_date=swings[-1].timestamp)
            touch_score = float(touch_count)
            volume_reaction_score = min(
                5.0,
                sum(candidate.volume for candidate in cluster_candidates)
                / max(1.0, sum(candidate.volume for candidate in swings) / len(swings))
                / 2,
            )
            confluence_score = (
                1.0
                if snapshot.sma_150 and min(cluster) <= snapshot.sma_150 <= max(cluster)
                else 0.0
            )
            total_score = (
                touch_score * self.config.score_weights["touch"]
                + recency_score * self.config.score_weights["recency"]
                + volume_reaction_score * self.config.score_weights["volume"]
                + confluence_score * self.config.score_weights["confluence"]
            )
            lower_bound = min(cluster) - half_width / 2
            upper_bound = max(cluster) + half_width / 2
            zones.append(
                StructureZone(
                    zone_type=zone_type,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                    mid_price=(lower_bound + upper_bound) / 2,
                    touch_count=touch_count,
                    last_touch_date=latest_touch.date().isoformat(),
                    touch_score=touch_score,
                    recency_score=recency_score,
                    volume_reaction_score=volume_reaction_score,
                    confluence_score=confluence_score,
                    total_score=total_score,
                    strength="core" if total_score >= 2.0 else "secondary",
                    reasons=[f"{touch_count}회 터치"],
                )
            )

        return zones

    def _score_recency(self, latest_touch: pd.Timestamp, snapshot_date: pd.Timestamp) -> float:
        days = max(0, (snapshot_date - latest_touch).days)
        if days <= self.config.recent_window_days:
            return 5.0
        if days <= self.config.mid_window_days:
            return 3.0
        return 1.0

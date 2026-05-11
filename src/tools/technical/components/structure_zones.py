from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from src.tools.technical.components.swing_extractor import SwingCandidate, SwingExtractor
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


def cluster_price_candidates(
    prices: list[float],
    half_width: float | Callable[[float], float],
    span_cap_multiplier: float = 2.5,
) -> list[list[float]]:
    if not prices:
        return []

    width_fn = half_width if callable(half_width) else lambda _price: half_width

    sorted_prices = sorted(prices)
    clusters: list[list[float]] = [[sorted_prices[0]]]
    for price in sorted_prices[1:]:
        current_cluster = clusters[-1]
        center_price = sum(current_cluster) / len(current_cluster)
        center_width = width_fn(center_price)
        incoming_width = width_fn(price)
        merge_width = min(center_width, incoming_width)
        span_cap = center_width * span_cap_multiplier
        proposed_min = min(current_cluster[0], price)
        proposed_max = max(current_cluster[-1], price)

        if abs(price - center_price) <= merge_width and (proposed_max - proposed_min) <= span_cap:
            current_cluster.append(price)
        else:
            clusters.append([price])
    return clusters


class StructureZoneDetector:
    def __init__(self, config: StructureZoneConfig | None = None):
        self.config = config or StructureZoneConfig()
        self.swing_extractor = SwingExtractor(window=self.config.swing_window)

    def detect(self, df: pd.DataFrame, snapshot: IndicatorSnapshot) -> StructureZoneSet:
        candidates = self._build_candidates(df, snapshot)
        touch_episodes = self._collect_touch_episodes(candidates)
        (
            sorted_demand_zones,
            sorted_supply_zones,
        ) = self._build_sorted_side_candidates(
            candidates=candidates,
            current_price=snapshot.price,
        )
        demand_zones, supply_zones, dropped_side_candidates = self._select_side_zones(
            sorted_demand_zones=sorted_demand_zones,
            sorted_supply_zones=sorted_supply_zones,
            current_price=snapshot.price,
        )
        demand_zones, supply_zones, balance_zones = self._merge_overlapping_opposite_zones(
            demand_zones=demand_zones,
            supply_zones=supply_zones,
            atr=snapshot.atr,
            current_price=snapshot.price,
        )

        invalidation_seed = [
            zone for zone in demand_zones if zone.lower_bound <= snapshot.price
        ] or [zone for zone in balance_zones if zone.upper_bound <= snapshot.price]

        invalidation_candidates, invalidation_zone = self.choose_invalidation_zone(
            demand_zones=invalidation_seed,
            snapshot=snapshot,
        )
        no_clear_structure, no_clear_reasons = self._derive_no_clear_structure(
            demand_zones=demand_zones,
            supply_zones=supply_zones,
            balance_zones=balance_zones,
        )
        selected_label, selected_zone, candidate_priority_trace = self._pick_primary_selected_zone(
            demand_zones=demand_zones,
            supply_zones=supply_zones,
            balance_zones=balance_zones,
            current_price=snapshot.price,
        )
        if no_clear_structure:
            selected_label = "no_clear_structure"
            selected_zone = None
        selection_trace = self._build_selection_trace(
            selected_label=selected_label,
            selected_zone=selected_zone,
            dropped_candidates=dropped_side_candidates,
            candidate_priority_trace=candidate_priority_trace,
            no_clear_structure=no_clear_structure,
        )

        return StructureZoneSet(
            support_zones=demand_zones,
            resistance_zones=supply_zones,
            former_levels=balance_zones,
            invalidation_candidates=invalidation_candidates,
            invalidation_zone=invalidation_zone,
            all_candidates=candidates,
            selection_trace=selection_trace,
            touch_episodes=touch_episodes,
            no_clear_structure=no_clear_structure,
            no_clear_structure_reason_codes=no_clear_reasons,
        )

    def _build_sorted_side_candidates(
        self,
        *,
        candidates: list[StructureZone],
        current_price: float,
    ) -> tuple[list[StructureZone], list[StructureZone]]:
        demand_candidates = [zone for zone in candidates if zone.zone_type == "demand"]
        broken_demand_as_supply = [
            self._promote_broken_demand_to_supply(zone)
            for zone in demand_candidates
            if zone.lower_bound > current_price
        ]
        sorted_demand_zones = self._sort_zones(demand_candidates, current_price)
        sorted_supply_zones = self._sort_zones(
            [
                *[zone for zone in candidates if zone.zone_type == "supply"],
                *broken_demand_as_supply,
            ],
            current_price,
        )
        return sorted_demand_zones, sorted_supply_zones

    def _select_side_zones(
        self,
        *,
        sorted_demand_zones: list[StructureZone],
        sorted_supply_zones: list[StructureZone],
        current_price: float,
    ) -> tuple[list[StructureZone], list[StructureZone], list[dict[str, object]]]:
        demand_zones, dropped_demand = self._select_with_guard_with_trace(
            sorted_demand_zones,
            current_price,
            zone_type="demand",
            max_count=self.config.top_n_per_side,
        )
        supply_zones, dropped_supply = self._select_with_guard_with_trace(
            sorted_supply_zones,
            current_price,
            zone_type="supply",
            max_count=self.config.top_n_per_side,
        )
        return demand_zones, supply_zones, [*dropped_demand, *dropped_supply]

    def _build_candidates(
        self, df: pd.DataFrame, snapshot: IndicatorSnapshot
    ) -> list[StructureZone]:
        recent = df.tail(self.config.lookback_days).copy()
        swings = self.swing_extractor.extract(recent)

        return [
            *self._build_side_zones(recent, swings.demand_candidates, "demand", snapshot),
            *self._build_side_zones(recent, swings.supply_candidates, "supply", snapshot),
        ]

    def _derive_no_clear_structure(
        self,
        *,
        demand_zones: list[StructureZone],
        supply_zones: list[StructureZone],
        balance_zones: list[StructureZone],
    ) -> tuple[bool, list[str]]:
        selected = [*demand_zones, *supply_zones, *balance_zones]
        reason_codes: list[str] = []
        if not selected:
            reason_codes.append("no_zone_selected")
            return True, reason_codes

        top_zone = max(selected, key=lambda zone: zone.total_score)
        if top_zone.total_score < self.config.core_zone_threshold:
            reason_codes.append("top_score_weak")

        if all(zone.recency_score < self.config.selection_min_recency_score for zone in selected):
            reason_codes.append("stale_signal")

        return bool(reason_codes), reason_codes

    def _pick_primary_selected_zone(
        self,
        *,
        demand_zones: list[StructureZone],
        supply_zones: list[StructureZone],
        balance_zones: list[StructureZone],
        current_price: float,
    ) -> tuple[str, StructureZone | None, list[dict[str, object]]]:
        candidates: list[tuple[float, str, StructureZone]] = []
        priority_trace: list[dict[str, object]] = []

        if balance_zones:
            top_balance = self._select_best_zone(
                balance_zones,
                current_price=current_price,
                label_hint="active_box",
            )
            in_box = top_balance.lower_bound <= current_price <= top_balance.upper_bound
            label = "active_box" if in_box else "former_supply_box"
            boost = 0.5 if in_box else 0.0
            priority_score = (
                self._selection_priority_score(
                    top_balance,
                    current_price=current_price,
                    label_hint=label,
                )
                + boost
            )
            candidates.append((priority_score, label, top_balance))
            priority_trace.append(
                self._build_candidate_priority_entry(
                    label=label,
                    zone=top_balance,
                    current_price=current_price,
                    priority_score=priority_score,
                )
            )

        if demand_zones:
            top_demand = self._select_best_zone(
                demand_zones,
                current_price=current_price,
                label_hint="support_zone",
            )
            priority_score = self._selection_priority_score(
                top_demand,
                current_price=current_price,
                label_hint="support_zone",
            )
            candidates.append((priority_score, "support_zone", top_demand))
            priority_trace.append(
                self._build_candidate_priority_entry(
                    label="support_zone",
                    zone=top_demand,
                    current_price=current_price,
                    priority_score=priority_score,
                )
            )

        active_supply = [zone for zone in supply_zones if zone.upper_bound >= current_price]
        former_supply = [zone for zone in supply_zones if zone.upper_bound < current_price]
        if active_supply:
            top_supply = self._select_best_zone(
                active_supply,
                current_price=current_price,
                label_hint="resistance_zone",
            )
            priority_score = self._selection_priority_score(
                top_supply,
                current_price=current_price,
                label_hint="resistance_zone",
            )
            candidates.append((priority_score, "resistance_zone", top_supply))
            priority_trace.append(
                self._build_candidate_priority_entry(
                    label="resistance_zone",
                    zone=top_supply,
                    current_price=current_price,
                    priority_score=priority_score,
                )
            )
        elif former_supply:
            top_former = self._select_best_zone(
                former_supply,
                current_price=current_price,
                label_hint="former_supply_box",
            )
            priority_score = self._selection_priority_score(
                top_former,
                current_price=current_price,
                label_hint="former_supply_box",
            )
            candidates.append((priority_score, "former_supply_box", top_former))
            priority_trace.append(
                self._build_candidate_priority_entry(
                    label="former_supply_box",
                    zone=top_former,
                    current_price=current_price,
                    priority_score=priority_score,
                )
            )

        if candidates:
            candidates.sort(
                key=lambda item: (
                    item[0],
                    pd.Timestamp(item[2].last_touch_date).value if item[2].last_touch_date else 0,
                    item[2].touch_count,
                ),
                reverse=True,
            )
            _score, selected_label, selected_zone = candidates[0]
            return selected_label, selected_zone, priority_trace
        return "no_clear_structure", None, priority_trace

    def _select_best_zone(
        self,
        zones: list[StructureZone],
        *,
        current_price: float,
        label_hint: str,
    ) -> StructureZone:
        return max(
            zones,
            key=lambda zone: (
                self._selection_priority_score(
                    zone,
                    current_price=current_price,
                    label_hint=label_hint,
                ),
                pd.Timestamp(zone.last_touch_date).value if zone.last_touch_date else 0,
                zone.touch_count,
            ),
        )

    def _selection_priority_score(
        self,
        zone: StructureZone,
        *,
        current_price: float,
        label_hint: str,
    ) -> float:
        distance_pct = abs(zone.mid_price - current_price) / max(current_price, 1.0)
        episode_recent_score = zone.reason_context.get("episode_recent_score", zone.recency_score)
        if not isinstance(episode_recent_score, (int, float)):
            episode_recent_score = zone.recency_score

        proximity_penalty = min(distance_pct * 0.6, 0.6)
        recency_bonus = float(episode_recent_score) * 0.1
        label_bonus = 0.2 if label_hint == "active_box" else 0.0
        return zone.total_score + recency_bonus + label_bonus - proximity_penalty

    def _build_candidate_priority_entry(
        self,
        *,
        label: str,
        zone: StructureZone,
        current_price: float,
        priority_score: float,
    ) -> dict[str, object]:
        distance_pct = abs(zone.mid_price - current_price) / max(current_price, 1.0)
        return {
            "label": label,
            "zone_type": zone.zone_type,
            "lower_bound": zone.lower_bound,
            "upper_bound": zone.upper_bound,
            "total_score": zone.total_score,
            "priority_score": round(priority_score, 4),
            "distance_pct": round(distance_pct, 4),
            "episode_recent_score": zone.reason_context.get(
                "episode_recent_score", zone.recency_score
            ),
        }

    def _build_selection_trace(
        self,
        *,
        selected_label: str,
        selected_zone: StructureZone | None,
        dropped_candidates: list[dict[str, object]],
        candidate_priority_trace: list[dict[str, object]],
        no_clear_structure: bool,
    ) -> list[dict[str, object]]:
        trace: list[dict[str, object]] = []
        trace.append(
            {
                "selected_label": selected_label,
                "no_clear_structure": no_clear_structure,
            }
        )
        if selected_zone is not None:
            trace.append(
                {
                    "selected_label": selected_label,
                    "zone_type": selected_zone.zone_type,
                    "lower_bound": selected_zone.lower_bound,
                    "upper_bound": selected_zone.upper_bound,
                    "total_score": selected_zone.total_score,
                    "reason_codes": selected_zone.reason_codes,
                    "reason_context": selected_zone.reason_context,
                }
            )
        if dropped_candidates:
            trace.append(
                {
                    "dropped_candidates": dropped_candidates,
                }
            )
        if candidate_priority_trace:
            trace.append(
                {
                    "selection_priority_trace": candidate_priority_trace,
                }
            )
        return trace

    def choose_invalidation_zone(
        self,
        demand_zones: list[StructureZone],
        snapshot: IndicatorSnapshot,
    ) -> tuple[list[StructureZone], StructureZone | None]:
        candidates: list[StructureZone] = []
        core_demand_zones = [zone for zone in demand_zones if zone.strength == "core"]
        primary_zone = (
            self._sort_zones(core_demand_zones, snapshot.price)[0] if core_demand_zones else None
        )

        ma_candidates = self._build_ma_invalidation_candidates(snapshot)
        swing_low_candidate = self._build_swing_low_candidate(snapshot)

        selected = None
        if primary_zone:
            related_ma_reasons: list[str] = []
            for ma_candidate in ma_candidates:
                distance_pct = abs(ma_candidate.lower_bound - primary_zone.lower_bound) / max(
                    primary_zone.lower_bound,
                    1.0,
                )
                candidates.append(ma_candidate)
                if distance_pct <= self.config.invalidation_ma_distance_pct:
                    related_ma_reasons.extend(ma_candidate.reasons)

            selected = StructureZone(
                zone_type="invalidation",
                lower_bound=primary_zone.lower_bound,
                upper_bound=primary_zone.upper_bound,
                mid_price=primary_zone.mid_price,
                touch_count=primary_zone.touch_count,
                last_touch_date=primary_zone.last_touch_date,
                touch_score=primary_zone.touch_score,
                recency_score=primary_zone.recency_score,
                volume_reaction_score=primary_zone.volume_reaction_score,
                confluence_score=primary_zone.confluence_score,
                total_score=primary_zone.total_score,
                strength=primary_zone.strength,
                reasons=[*primary_zone.reasons, *related_ma_reasons],
                reason_codes=[*primary_zone.reason_codes, "invalidation_from_primary_zone"],
                reason_context={
                    "primary_zone_type": primary_zone.zone_type,
                    "related_ma_reason_count": len(related_ma_reasons),
                },
            )
            candidates.insert(0, selected)
        elif ma_candidates:
            selected = sorted(
                ma_candidates,
                key=lambda zone: abs(zone.lower_bound - snapshot.price),
            )[0]
            candidates.extend(ma_candidates)
        elif swing_low_candidate:
            selected = swing_low_candidate
            candidates.append(swing_low_candidate)

        if selected is None and swing_low_candidate:
            candidates.append(swing_low_candidate)
        return candidates, selected

    def _build_side_zones(
        self,
        df: pd.DataFrame,
        swings: list[SwingCandidate],
        zone_type: str,
        snapshot: IndicatorSnapshot,
    ) -> list[StructureZone]:
        if not swings:
            return []

        clusters = cluster_price_candidates(
            [candidate.price for candidate in swings],
            half_width=lambda price: calculate_zone_half_width(price, snapshot.atr, self.config),
            span_cap_multiplier=self.config.cluster_span_multiplier,
        )

        zones: list[StructureZone] = []
        for cluster in clusters:
            cluster_candidates = [candidate for candidate in swings if candidate.price in cluster]
            touch_count = len(cluster_candidates)
            latest_touch = max(candidate.timestamp for candidate in cluster_candidates)
            volume_reaction_score = self._score_volume_reaction(
                df=df,
                cluster_candidates=cluster_candidates,
                side=zone_type,
            )
            touch_episodes = self._build_touch_episodes(
                cluster_candidates,
                snapshot_date=swings[-1].timestamp,
            )
            touch_metrics = self._score_touch_from_episodes(
                touch_episodes,
                fallback_touch_count=touch_count,
            )
            touch_score = touch_metrics["touch_score"]
            recency_score = touch_metrics["guard_recency"]
            confluence = self._calculate_confluence(cluster, snapshot, df)
            confluence_score = float(confluence["score"])
            total_score = (
                touch_score * self.config.score_weights["touch"]
                + recency_score * self.config.score_weights["recency"]
                + volume_reaction_score * self.config.score_weights["volume"]
                + confluence_score * self.config.score_weights["confluence"]
            )
            cluster_center = sum(cluster) / len(cluster)
            cluster_half_width = calculate_zone_half_width(
                cluster_center,
                snapshot.atr,
                self.config,
            )
            lower_bound = min(cluster) - cluster_half_width / 2
            upper_bound = max(cluster) + cluster_half_width / 2
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
                    strength=(
                        "core" if total_score >= self.config.core_zone_threshold else "secondary"
                    ),
                    reasons=[
                        f"에피소드 {len(touch_episodes)}개 / 총 {touch_count}회 터치",
                        f"최근성 점수 {recency_score:.2f}",
                        f"거래량 반응 {volume_reaction_score:.2f}",
                        self._format_confluence_reason(confluence.get("sources", [])),
                    ],
                    reason_codes=[
                        f"{zone_type}_episode_strength",
                        f"{zone_type}_volume_reaction",
                        f"{zone_type}_confluence",
                    ],
                    reason_context={
                        "touch_count": touch_count,
                        "touch_episode_count": len(touch_episodes),
                        "touch_episodes": touch_episodes,
                        "episode_touch_score": round(touch_score, 4),
                        "episode_recent_score": round(touch_metrics["episode_recent_score"], 4),
                        "episode_independent_count": int(
                            touch_metrics["episode_independent_count"]
                        ),
                        "episode_guard_recency": round(touch_metrics["guard_recency"], 4),
                        "volume_reaction_score": round(volume_reaction_score, 4),
                        "recency_score": round(recency_score, 4),
                        "confluence_sources": confluence.get("sources", []),
                        "confluence_components": confluence.get("components", {}),
                    },
                )
            )

        return zones

    def _sort_zones(self, zones: list[StructureZone], current_price: float) -> list[StructureZone]:
        return sorted(
            zones,
            key=lambda zone: (
                -zone.total_score,
                -(pd.Timestamp(zone.last_touch_date).value if zone.last_touch_date else 0),
                -zone.touch_count,
                abs(zone.mid_price - current_price),
            ),
        )

    def _select_with_guard(
        self,
        sorted_zones: list[StructureZone],
        current_price: float,
        zone_type: str,
        max_count: int,
    ) -> list[StructureZone]:
        selected, _dropped = self._select_with_guard_with_trace(
            sorted_zones=sorted_zones,
            current_price=current_price,
            zone_type=zone_type,
            max_count=max_count,
        )
        return selected

    def _select_with_guard_with_trace(
        self,
        sorted_zones: list[StructureZone],
        current_price: float,
        zone_type: str,
        max_count: int,
    ) -> tuple[list[StructureZone], list[dict[str, object]]]:
        if not sorted_zones:
            return [], []

        preferred = [
            zone
            for zone in sorted_zones
            if self._is_preferred_side_zone(zone, current_price, zone_type)
        ]
        non_preferred = [zone for zone in sorted_zones if zone not in preferred]

        filtered_preferred: list[StructureZone] = []
        filtered_non_preferred: list[StructureZone] = []
        dropped: list[dict[str, object]] = []

        for zone in preferred:
            if self._passes_selection_guard(zone, current_price):
                filtered_preferred.append(zone)
                continue
            dropped.append(
                self._build_dropped_candidate_entry(
                    zone=zone,
                    reason_code="selection_guard_failed_preferred",
                )
            )
        for zone in non_preferred:
            if self._passes_selection_guard(zone, current_price):
                filtered_non_preferred.append(zone)
                continue
            dropped.append(
                self._build_dropped_candidate_entry(
                    zone=zone,
                    reason_code="selection_guard_failed_non_preferred",
                )
            )

        selected: list[StructureZone] = []
        for zone in [*filtered_preferred, *filtered_non_preferred]:
            if zone in selected:
                continue
            selected.append(zone)
            if len(selected) >= max_count:
                return selected, dropped

        for zone in [*preferred, *non_preferred]:
            if zone in selected:
                continue
            selected.append(zone)
            if len(selected) >= max_count:
                break
        return selected, dropped

    def _build_dropped_candidate_entry(
        self,
        *,
        zone: StructureZone,
        reason_code: str,
    ) -> dict[str, object]:
        return {
            "zone_type": zone.zone_type,
            "lower_bound": zone.lower_bound,
            "upper_bound": zone.upper_bound,
            "total_score": zone.total_score,
            "reason_code": reason_code,
        }

    def _is_preferred_side_zone(
        self,
        zone: StructureZone,
        current_price: float,
        zone_type: str,
    ) -> bool:
        if zone_type == "demand":
            return zone.lower_bound <= current_price
        if zone_type == "supply":
            return zone.upper_bound >= current_price
        return True

    def _passes_selection_guard(self, zone: StructureZone, current_price: float) -> bool:
        distance_pct = abs(zone.mid_price - current_price) / max(current_price, 1.0)
        guard_recency = zone.recency_score
        episode_guard_recency = zone.reason_context.get("episode_guard_recency")
        if isinstance(episode_guard_recency, (int, float)):
            guard_recency = float(episode_guard_recency)
        return (
            guard_recency >= self.config.selection_min_recency_score
            and distance_pct <= self.config.selection_max_distance_pct
        )

    def _score_recency(self, latest_touch: pd.Timestamp, snapshot_date: pd.Timestamp) -> float:
        days = max(0, (snapshot_date - latest_touch).days)
        if days <= self.config.recent_window_days:
            return 5.0
        if days <= self.config.mid_window_days:
            return 3.0
        return 1.0

    def _score_volume_reaction(
        self,
        df: pd.DataFrame,
        cluster_candidates: list[SwingCandidate],
        side: str,
    ) -> float:
        event_scores = [
            self._score_touch_event(df, candidate, side) for candidate in cluster_candidates
        ]
        return min(5.0, sum(event_scores))

    def _score_touch_event(
        self,
        df: pd.DataFrame,
        candidate: SwingCandidate,
        side: str,
    ) -> float:
        if "Volume" not in df.columns:
            return 0.0

        index_position = df.index.get_loc(candidate.timestamp)
        if isinstance(index_position, slice):
            index_position = index_position.stop - 1

        baseline_start = max(0, index_position - self.config.volume_baseline_window)
        baseline_series = df["Volume"].iloc[baseline_start:index_position]
        baseline_volume = (
            float(baseline_series.mean()) if not baseline_series.empty else candidate.volume
        )
        volume_multiple = candidate.volume / max(baseline_volume, 1.0)

        lookahead = df["Close"].iloc[
            index_position + 1 : index_position + 1 + self.config.reaction_lookahead_days
        ]
        if lookahead.empty:
            reaction_strength = 0.0
        elif side == "demand":
            reaction_strength = max(
                0.0, (float(lookahead.max()) - candidate.price) / candidate.price
            )
        else:
            reaction_strength = max(
                0.0, (candidate.price - float(lookahead.min())) / candidate.price
            )

        recency_factor = max(0.2, self._score_recency(candidate.timestamp, df.index[-1]) / 5.0)
        return min(5.0, volume_multiple * (1 + reaction_strength * 5) * recency_factor)

    def _score_confluence(
        self,
        cluster: list[float],
        snapshot: IndicatorSnapshot,
        df: pd.DataFrame,
    ) -> float:
        return float(self._calculate_confluence(cluster, snapshot, df)["score"])

    def _calculate_confluence(
        self,
        cluster: list[float],
        snapshot: IndicatorSnapshot,
        df: pd.DataFrame,
    ) -> dict[str, object]:
        lower_bound = min(cluster)
        upper_bound = max(cluster)
        score = 0.0
        ma_overlaps: dict[str, dict[str, float | bool | None]] = {}
        for moving_average in ("sma_150", "sma_200"):
            value = getattr(snapshot, moving_average, None)
            overlaps = bool(value and lower_bound <= value <= upper_bound)
            ma_overlaps[moving_average] = {
                "value": float(value) if value is not None else None,
                "overlap": overlaps,
            }
            if overlaps:
                score += 0.5

        poc_range, hvn_ranges = self._build_volume_profile_ranges(df)
        zone_range = (lower_bound, upper_bound)
        poc_overlap = bool(poc_range and self._range_overlaps(zone_range, poc_range))
        hvn_overlap_ranges = [
            hvn_range for hvn_range in hvn_ranges if self._range_overlaps(zone_range, hvn_range)
        ]

        if poc_overlap:
            score += 0.5
        if hvn_overlap_ranges:
            score += 0.5

        sources: list[str] = []
        if ma_overlaps["sma_150"]["overlap"]:
            sources.append("MA150")
        if ma_overlaps["sma_200"]["overlap"]:
            sources.append("MA200")
        if poc_overlap:
            sources.append("POC")
        if hvn_overlap_ranges:
            sources.append(f"HVNx{len(hvn_overlap_ranges)}")

        return {
            "score": min(score, 2.0),
            "sources": sources,
            "components": {
                "ma_overlaps": ma_overlaps,
                "poc_overlap": poc_overlap,
                "poc_range": self._range_to_dict(poc_range),
                "hvn_overlap_count": len(hvn_overlap_ranges),
                "hvn_overlap_ranges": [self._range_to_dict(item) for item in hvn_overlap_ranges],
            },
        }

    def _format_confluence_reason(self, sources: object) -> str:
        if not isinstance(sources, list) or not sources:
            return "정합 근거 없음"
        return f"정합 근거 {', '.join(str(item) for item in sources)}"

    def _build_volume_profile_ranges(
        self,
        df: pd.DataFrame,
    ) -> tuple[tuple[float, float] | None, list[tuple[float, float]]]:
        required_cols = {"High", "Low", "Close", "Volume"}
        if df.empty or not required_cols.issubset(df.columns):
            return None, []

        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
        min_price = float(typical_price.min())
        max_price = float(typical_price.max())
        if max_price <= min_price:
            return None, []

        bin_count = max(10, self.config.volume_profile_bin_count)
        bins = pd.interval_range(start=min_price, end=max_price, periods=bin_count)
        bucketed = pd.cut(typical_price, bins=bins, include_lowest=True)
        volume_profile = (
            df.groupby(bucketed, observed=False)["Volume"].sum().sort_values(ascending=False)
        )
        if volume_profile.empty:
            return None, []

        top_nodes = volume_profile.head(self.config.volume_profile_top_k)
        ranges = [
            (float(interval.left), float(interval.right))
            for interval in top_nodes.index
            if isinstance(interval, pd.Interval)
        ]
        poc_range = ranges[0] if ranges else None
        return poc_range, ranges

    def _range_overlaps(
        self,
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> bool:
        return min(left[1], right[1]) >= max(left[0], right[0])

    def _range_to_dict(
        self,
        value: tuple[float, float] | None,
    ) -> dict[str, float] | None:
        if value is None:
            return None
        return {"lower": float(value[0]), "upper": float(value[1])}

    def _build_touch_episodes(
        self,
        cluster_candidates: list[SwingCandidate],
        *,
        snapshot_date: pd.Timestamp,
    ) -> list[dict[str, object]]:
        if not cluster_candidates:
            return []

        ordered = sorted(cluster_candidates, key=lambda candidate: candidate.timestamp)
        grouped: list[list[SwingCandidate]] = [[ordered[0]]]

        for candidate in ordered[1:]:
            previous = grouped[-1][-1]
            gap_days = (candidate.timestamp - previous.timestamp).days
            if gap_days <= self.config.episode_max_gap_days:
                grouped[-1].append(candidate)
            else:
                grouped.append([candidate])

        episodes: list[dict[str, object]] = []
        for episode_candidates in grouped:
            start = episode_candidates[0].timestamp
            end = episode_candidates[-1].timestamp
            recency_score = self._score_recency(end, snapshot_date)
            touch_count = len(episode_candidates)
            episode_score = touch_count * 0.7 + recency_score * 0.3
            episodes.append(
                {
                    "start_date": start.date().isoformat(),
                    "end_date": end.date().isoformat(),
                    "touch_count": touch_count,
                    "recency_score": recency_score,
                    "episode_score": round(episode_score, 4),
                    "touch_dates": [
                        item.timestamp.date().isoformat() for item in episode_candidates
                    ],
                }
            )

        return episodes

    def _score_touch_from_episodes(
        self,
        episodes: list[dict[str, object]],
        *,
        fallback_touch_count: int,
    ) -> dict[str, float]:
        if not episodes:
            return {
                "touch_score": float(fallback_touch_count),
                "episode_recent_score": 0.0,
                "episode_independent_count": 0.0,
                "guard_recency": 1.0,
            }

        episode_scores = [
            float(item.get("episode_score", 0.0))
            for item in episodes
            if isinstance(item.get("episode_score"), (int, float))
        ]
        recency_scores = [
            float(item.get("recency_score", 1.0))
            for item in episodes
            if isinstance(item.get("recency_score"), (int, float))
        ]
        if not episode_scores:
            episode_scores = [float(fallback_touch_count)]
        if not recency_scores:
            recency_scores = [1.0]

        strongest_episode_score = max(episode_scores)
        episode_recent_score = max(
            score * (recency / 5.0)
            for score, recency in zip(episode_scores, recency_scores, strict=True)
        )
        episode_independent_count = len(episodes)
        guard_recency = max(recency_scores)

        touch_score = min(
            12.0,
            strongest_episode_score * 0.6
            + episode_recent_score * 0.8
            + max(0, episode_independent_count - 1) * 1.2,
        )
        return {
            "touch_score": float(touch_score),
            "episode_recent_score": float(episode_recent_score),
            "episode_independent_count": float(episode_independent_count),
            "guard_recency": float(guard_recency),
        }

    def _collect_touch_episodes(
        self,
        candidates: list[StructureZone],
    ) -> list[dict[str, object]]:
        collected: list[dict[str, object]] = []
        for zone in candidates:
            episodes = zone.reason_context.get("touch_episodes")
            if not isinstance(episodes, list) or not episodes:
                continue
            collected.append(
                {
                    "zone_type": zone.zone_type,
                    "lower_bound": zone.lower_bound,
                    "upper_bound": zone.upper_bound,
                    "total_score": zone.total_score,
                    "touch_episode_count": len(episodes),
                    "episodes": episodes,
                }
            )
        return collected

    def _build_ma_invalidation_candidates(
        self,
        snapshot: IndicatorSnapshot,
    ) -> list[StructureZone]:
        candidates: list[StructureZone] = []
        for label, value in (("150일선", snapshot.sma_150), ("200일선", snapshot.sma_200)):
            if value is None:
                continue
            candidates.append(
                StructureZone(
                    zone_type="invalidation",
                    lower_bound=value,
                    upper_bound=value,
                    mid_price=value,
                    touch_count=0,
                    last_touch_date=None,
                    touch_score=0.0,
                    recency_score=0.0,
                    volume_reaction_score=0.0,
                    confluence_score=1.0,
                    total_score=1.0,
                    strength="secondary",
                    reasons=[f"{label} fallback"],
                    reason_codes=["invalidation_ma_fallback"],
                    reason_context={"moving_average_label": label},
                )
            )
        return candidates

    def _build_swing_low_candidate(
        self,
        snapshot: IndicatorSnapshot,
    ) -> StructureZone | None:
        if snapshot.swing_low is None:
            return None
        return StructureZone(
            zone_type="invalidation",
            lower_bound=snapshot.swing_low,
            upper_bound=snapshot.swing_low,
            mid_price=snapshot.swing_low,
            touch_count=0,
            last_touch_date=None,
            touch_score=0.0,
            recency_score=0.0,
            volume_reaction_score=0.0,
            confluence_score=0.0,
            total_score=0.5,
            strength="secondary",
            reasons=["swing low fallback"],
            reason_codes=["invalidation_swing_low_fallback"],
            reason_context={"swing_low": snapshot.swing_low},
        )

    def _promote_broken_demand_to_supply(self, zone: StructureZone) -> StructureZone:
        reasons = ["붕괴 수요 → 전환 저항"] + zone.reasons
        return StructureZone(
            zone_type="supply",
            lower_bound=zone.lower_bound,
            upper_bound=zone.upper_bound,
            mid_price=zone.mid_price,
            touch_count=zone.touch_count,
            last_touch_date=zone.last_touch_date,
            touch_score=zone.touch_score,
            recency_score=zone.recency_score,
            volume_reaction_score=zone.volume_reaction_score,
            confluence_score=zone.confluence_score,
            total_score=zone.total_score,
            strength=zone.strength,
            reasons=reasons,
            reason_codes=["former_support_as_resistance", *zone.reason_codes],
            reason_context={"origin_zone_type": zone.zone_type},
        )

    def _is_promoted_supply_zone(self, zone: StructureZone) -> bool:
        if zone.zone_type != "supply" or not zone.reasons:
            return False
        return zone.reasons[0].startswith("붕괴 수요")

    def _merge_overlapping_opposite_zones(
        self,
        demand_zones: list[StructureZone],
        supply_zones: list[StructureZone],
        atr: float | None,
        current_price: float,
    ) -> tuple[list[StructureZone], list[StructureZone], list[StructureZone]]:
        if not demand_zones or not supply_zones:
            return demand_zones, supply_zones, []

        used_supply_indices: set[int] = set()
        kept_demand_zones: list[StructureZone] = []
        balance_zones: list[StructureZone] = []

        for demand in demand_zones:
            match_index = self._find_overlap_supply_index(
                demand=demand,
                supply_zones=supply_zones,
                used_supply_indices=used_supply_indices,
                atr=atr,
            )
            if match_index is None:
                kept_demand_zones.append(demand)
                continue

            matched_supply = supply_zones[match_index]
            used_supply_indices.add(match_index)
            balance_zones.append(
                self._build_balance_zone(
                    demand_zone=demand,
                    supply_zone=matched_supply,
                )
            )

        kept_supply_zones = [
            zone for index, zone in enumerate(supply_zones) if index not in used_supply_indices
        ]

        merged_balance = self._merge_balance_zones(balance_zones, atr)
        sorted_balance = self._sort_zones(merged_balance, current_price)[
            : self.config.top_n_per_side
        ]
        return kept_demand_zones, kept_supply_zones, sorted_balance

    def _find_overlap_supply_index(
        self,
        demand: StructureZone,
        supply_zones: list[StructureZone],
        used_supply_indices: set[int],
        atr: float | None,
    ) -> int | None:
        best_index: int | None = None
        best_score = float("-inf")

        for supply_index, supply in enumerate(supply_zones):
            if supply_index in used_supply_indices:
                continue
            if self._is_promoted_supply_zone(supply):
                continue

            last_touch_gap = self._last_touch_gap_days(demand, supply)
            if last_touch_gap > self.config.overlap_max_last_touch_gap_days:
                continue

            overlap_ratio = self._zone_overlap_ratio(demand, supply)
            center_distance = abs(demand.mid_price - supply.mid_price)
            distance_limit = self._merge_center_distance_limit(demand, supply, atr)

            if overlap_ratio < self.config.overlap_min_ratio and center_distance > distance_limit:
                continue

            normalized_distance = center_distance / max(distance_limit, 1e-6)
            normalized_gap = last_touch_gap / max(self.config.overlap_max_last_touch_gap_days, 1)
            candidate_score = overlap_ratio - (normalized_distance * 0.5) - (normalized_gap * 0.2)
            if candidate_score > best_score:
                best_score = candidate_score
                best_index = supply_index

        return best_index

    def _build_balance_zone(
        self,
        demand_zone: StructureZone,
        supply_zone: StructureZone,
    ) -> StructureZone:
        lower_bound = min(demand_zone.lower_bound, supply_zone.lower_bound)
        upper_bound = max(demand_zone.upper_bound, supply_zone.upper_bound)
        overlap_ratio = self._zone_overlap_ratio(demand_zone, supply_zone)
        gap_days = self._last_touch_gap_days(demand_zone, supply_zone)
        latest_touch = self._latest_touch_date(
            demand_zone.last_touch_date,
            supply_zone.last_touch_date,
        )
        reasons = [
            "수요/공급 중첩 구간 통합",
            f"중첩률 {overlap_ratio:.2f}, 날짜 간격 {gap_days}일",
        ]

        if demand_zone.reasons:
            reasons.append(f"수요 근거: {demand_zone.reasons[0]}")
        if supply_zone.reasons:
            reasons.append(f"공급 근거: {supply_zone.reasons[0]}")

        return StructureZone(
            zone_type="balance",
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            mid_price=(lower_bound + upper_bound) / 2,
            touch_count=demand_zone.touch_count + supply_zone.touch_count,
            last_touch_date=latest_touch,
            touch_score=max(demand_zone.touch_score, supply_zone.touch_score),
            recency_score=max(demand_zone.recency_score, supply_zone.recency_score),
            volume_reaction_score=max(
                demand_zone.volume_reaction_score,
                supply_zone.volume_reaction_score,
            ),
            confluence_score=max(demand_zone.confluence_score, supply_zone.confluence_score),
            total_score=max(demand_zone.total_score, supply_zone.total_score) + overlap_ratio,
            strength=(
                "core"
                if demand_zone.strength == "core" or supply_zone.strength == "core"
                else "secondary"
            ),
            reasons=reasons,
            reason_codes=[
                "balance_overlap_merge",
                *demand_zone.reason_codes[:1],
                *supply_zone.reason_codes[:1],
            ],
            reason_context={
                "overlap_ratio": round(overlap_ratio, 4),
                "last_touch_gap_days": gap_days,
            },
        )

    def _merge_balance_zones(
        self,
        balance_zones: list[StructureZone],
        atr: float | None,
    ) -> list[StructureZone]:
        if len(balance_zones) <= 1:
            return balance_zones

        remaining = sorted(balance_zones, key=lambda zone: zone.mid_price)
        merged: list[StructureZone] = []

        while remaining:
            seed = remaining.pop(0)
            group = [seed]
            pending: list[StructureZone] = []

            for candidate in remaining:
                if any(self._should_merge_balance_pair(base, candidate, atr) for base in group):
                    group.append(candidate)
                else:
                    pending.append(candidate)

            remaining = pending
            merged.append(self._collapse_balance_group(group))

        return merged

    def _should_merge_balance_pair(
        self,
        left: StructureZone,
        right: StructureZone,
        atr: float | None,
    ) -> bool:
        last_touch_gap = self._last_touch_gap_days(left, right)
        if last_touch_gap > self.config.balance_max_last_touch_gap_days:
            return False

        overlap_ratio = self._zone_overlap_ratio(left, right)
        center_distance = abs(left.mid_price - right.mid_price)
        distance_limit = self._balance_center_distance_limit(left, right, atr)
        return (
            overlap_ratio >= self.config.balance_overlap_min_ratio
            or center_distance <= distance_limit
        )

    def _collapse_balance_group(self, group: list[StructureZone]) -> StructureZone:
        if len(group) == 1:
            return group[0]

        lower_bound = min(zone.lower_bound for zone in group)
        upper_bound = max(zone.upper_bound for zone in group)
        touch_count = sum(zone.touch_count for zone in group)
        last_touch_date = self._latest_touch_date_from_many(
            [zone.last_touch_date for zone in group]
        )

        reasons = ["밸런스 존 중첩 병합"]
        for zone in group:
            if zone.reasons:
                reasons.append(zone.reasons[0])

        return StructureZone(
            zone_type="balance",
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            mid_price=(lower_bound + upper_bound) / 2,
            touch_count=touch_count,
            last_touch_date=last_touch_date,
            touch_score=max(zone.touch_score for zone in group),
            recency_score=max(zone.recency_score for zone in group),
            volume_reaction_score=max(zone.volume_reaction_score for zone in group),
            confluence_score=max(zone.confluence_score for zone in group),
            total_score=max(zone.total_score for zone in group) + (len(group) - 1) * 0.25,
            strength="core" if any(zone.strength == "core" for zone in group) else "secondary",
            reasons=reasons,
            reason_codes=["balance_group_merge"],
            reason_context={"merged_count": len(group)},
        )

    def _zone_overlap_ratio(self, first: StructureZone, second: StructureZone) -> float:
        overlap = max(
            0.0,
            min(first.upper_bound, second.upper_bound) - max(first.lower_bound, second.lower_bound),
        )
        first_width = max(first.upper_bound - first.lower_bound, 1e-6)
        second_width = max(second.upper_bound - second.lower_bound, 1e-6)
        return overlap / min(first_width, second_width)

    def _merge_center_distance_limit(
        self,
        demand_zone: StructureZone,
        supply_zone: StructureZone,
        atr: float | None,
    ) -> float:
        zone_width_floor = (
            min(
                demand_zone.upper_bound - demand_zone.lower_bound,
                supply_zone.upper_bound - supply_zone.lower_bound,
            )
            * 0.25
        )
        atr_limit = (
            atr * self.config.overlap_center_distance_atr_multiplier if atr and atr > 0 else 0.0
        )
        return max(zone_width_floor, atr_limit, 1e-6)

    def _balance_center_distance_limit(
        self,
        left_zone: StructureZone,
        right_zone: StructureZone,
        atr: float | None,
    ) -> float:
        zone_width_floor = (
            min(
                left_zone.upper_bound - left_zone.lower_bound,
                right_zone.upper_bound - right_zone.lower_bound,
            )
            * 0.75
        )
        atr_limit = (
            atr * self.config.balance_center_distance_atr_multiplier if atr and atr > 0 else 0.0
        )
        return max(zone_width_floor, atr_limit, 1e-6)

    def _last_touch_gap_days(self, first: StructureZone, second: StructureZone) -> int:
        if not first.last_touch_date or not second.last_touch_date:
            return 0
        return abs(
            (pd.Timestamp(first.last_touch_date) - pd.Timestamp(second.last_touch_date)).days
        )

    def _latest_touch_date(self, first_date: str | None, second_date: str | None) -> str | None:
        if first_date and second_date:
            return max(pd.Timestamp(first_date), pd.Timestamp(second_date)).date().isoformat()
        return first_date or second_date

    def _latest_touch_date_from_many(self, dates: list[str | None]) -> str | None:
        valid_dates = [pd.Timestamp(date) for date in dates if date]
        if not valid_dates:
            return None
        return max(valid_dates).date().isoformat()

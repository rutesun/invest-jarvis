from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from src.tools.technical.models import (
    IndicatorSnapshot,
    LevelPayload,
    StructurePresentationPayload,
    StructureZone,
    StructureZoneConfig,
    StructureZoneSet,
    ZoneTestArtifact,
)


def build_indicator_snapshot_from_ohlcv(df: pd.DataFrame) -> IndicatorSnapshot:
    """Fixture CSV만 있을 때 inspect용 최소 snapshot을 만든다."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    current_close = float(close.iloc[-1])
    previous_close = float(close.iloc[-2]) if len(close) > 1 else current_close
    change_pct = (
        ((current_close - previous_close) / previous_close) * 100 if previous_close else 0.0
    )

    atr = float((high - low).rolling(window=14, min_periods=1).mean().iloc[-1])
    sma_50 = float(close.rolling(window=50, min_periods=1).mean().iloc[-1])
    sma_150 = float(close.rolling(window=150, min_periods=1).mean().iloc[-1])
    sma_200 = float(close.rolling(window=200, min_periods=1).mean().iloc[-1])
    high_52w = float(high.tail(252).max())
    low_52w = float(low.tail(252).min())
    swing_low = float(low.tail(20).min())
    swing_high = float(high.tail(20).max())

    pivot = None
    support_s1 = None
    resistance_r1 = None
    if len(df) > 1:
        previous_high = float(high.iloc[-2])
        previous_low = float(low.iloc[-2])
        previous_close_value = float(close.iloc[-2])
        pivot = (previous_high + previous_low + previous_close_value) / 3
        support_s1 = (2 * pivot) - previous_high
        resistance_r1 = (2 * pivot) - previous_low

    return IndicatorSnapshot(
        price=current_close,
        change_pct=float(change_pct),
        atr=atr,
        sma_50=sma_50,
        sma_150=sma_150,
        sma_200=sma_200,
        high_52w=high_52w,
        low_52w=low_52w,
        swing_low=swing_low,
        swing_high=swing_high,
        pivot=pivot,
        support_s1=support_s1,
        resistance_r1=resistance_r1,
    )


def build_structure_zone_test_artifact(
    *,
    symbol: str,
    zone_set: StructureZoneSet,
    level_payload: LevelPayload,
    presented_structure: StructurePresentationPayload | None = None,
    config: StructureZoneConfig | None = None,
    csv_path: str = "",
) -> ZoneTestArtifact:
    params = config.model_dump() if config is not None else {}
    candidates = [_serialize_zone(zone) for zone in zone_set.all_candidates]
    score_breakdown = [
        {
            "zone_type": zone.zone_type,
            "lower_bound": zone.lower_bound,
            "upper_bound": zone.upper_bound,
            "strength": zone.strength,
            "touch_score": zone.touch_score,
            "recency_score": zone.recency_score,
            "volume_reaction_score": zone.volume_reaction_score,
            "confluence_score": zone.confluence_score,
            "total_score": zone.total_score,
        }
        for zone in zone_set.all_candidates
    ]

    return ZoneTestArtifact(
        schema_version="v1",
        symbol=symbol,
        csv_path=csv_path,
        params=params,
        candidates=candidates,
        selected_zones=[
            {
                "structure_levels": level_payload.structure_levels.model_dump(),
                "execution_levels": [item.model_dump() for item in level_payload.execution_levels],
                "presented_structure": (
                    presented_structure.model_dump() if presented_structure else None
                ),
            }
        ],
        score_breakdown=score_breakdown,
    )


def build_structure_zone_inspect_payload(
    *,
    symbol: str,
    snapshot: IndicatorSnapshot,
    zone_set: StructureZoneSet,
    level_payload: LevelPayload,
    presented_structure: StructurePresentationPayload | None = None,
    config: StructureZoneConfig | None = None,
    csv_path: str = "",
    source: str = "live",
) -> dict:
    artifact = build_structure_zone_test_artifact(
        symbol=symbol,
        zone_set=zone_set,
        level_payload=level_payload,
        presented_structure=presented_structure,
        config=config,
        csv_path=csv_path,
    )
    return {
        "symbol": symbol,
        "source": source,
        "csv_path": csv_path,
        "snapshot": _snapshot_view(snapshot),
        "structure_summary": level_payload.structure_summary,
        "execution_summary": level_payload.execution_summary,
        "structure_levels": level_payload.structure_levels.model_dump(),
        "execution_levels": [level.model_dump() for level in level_payload.execution_levels],
        "presented_structure": presented_structure.model_dump() if presented_structure else None,
        "selection_trace": zone_set.selection_trace,
        "no_clear_structure": zone_set.no_clear_structure,
        "no_clear_structure_reason_codes": zone_set.no_clear_structure_reason_codes,
        "artifact": artifact.model_dump(),
    }


def format_structure_zone_inspection(payload: Mapping[str, object], max_candidates: int = 5) -> str:
    symbol = str(payload["symbol"])
    source = str(payload["source"])
    csv_path = str(payload.get("csv_path") or "")
    snapshot = _as_dict(payload["snapshot"])
    structure_levels = _as_dict(payload["structure_levels"])
    presented_raw = payload.get("presented_structure")
    presented_structure = _as_dict(presented_raw) if presented_raw else None
    execution_levels = [_as_dict(level) for level in payload.get("execution_levels", [])]
    artifact = _as_dict(payload["artifact"])
    candidates = sorted(
        [_as_dict(candidate) for candidate in artifact.get("candidates", [])],
        key=lambda item: item.get("total_score", 0.0),
        reverse=True,
    )

    lines = [f"# Structure Zone Inspect: {symbol}", ""]
    lines.extend(
        [
            "## 입력 요약",
            "",
            f"- **소스**: {source}",
            f"- **현재가**: ${snapshot['price']:.2f} ({snapshot['change_pct']:+.2f}%)",
            f"- **ATR**: ${snapshot['atr']:.2f}"
            if snapshot.get("atr") is not None
            else "- **ATR**: N/A",
            _format_ma_summary(snapshot),
            f"- **구조 요약**: {payload['structure_summary']}",
            f"- **실행 요약**: {payload['execution_summary']}",
        ]
    )
    if csv_path:
        lines.append(f"- **CSV**: {csv_path}")
    lines.append("")

    lines.extend(["## 선택된 구조 레벨", ""])
    if presented_structure and presented_structure.get("cli_blocks"):
        lines.extend(presented_structure["cli_blocks"])
    else:
        lines.extend(
            _format_zone_group(
                "지지 존",
                structure_levels.get("support_zones", structure_levels.get("demand_zones", [])),
                current_price=float(snapshot["price"]),
                zone_type="support",
            )
        )
        lines.extend(
            _format_zone_group(
                "저항 존",
                structure_levels.get(
                    "resistance_zones",
                    structure_levels.get("supply_zones", []),
                ),
                current_price=float(snapshot["price"]),
                zone_type="resistance",
            )
        )
        former_levels = structure_levels.get(
            "former_levels", structure_levels.get("balance_zones", [])
        )
        lines.extend(
            _format_zone_group(
                "전환 레벨",
                former_levels,
                current_price=float(snapshot["price"]),
                zone_type="former",
            )
        )
    invalidation = structure_levels.get("invalidation")
    lines.append("### 구조 무효화")
    lines.append("")
    if invalidation:
        invalidation_dict = _as_dict(invalidation)
        lines.append(f"- **{invalidation_dict['label']}**")
        if invalidation_dict.get("reasons"):
            lines.append(f"  이유: {', '.join(invalidation_dict['reasons'])}")
    else:
        lines.append("- 없음")
    lines.append("")

    lines.extend(["## 실행 레벨", ""])
    if execution_levels:
        for level in execution_levels:
            lines.append(
                f"- **{level['description']}**: ${level['price']:.2f} ({level['distance_pct']:+.1f}%) [{level['type']}]"
            )
    else:
        lines.append("- 없음")
    lines.append("")

    lines.extend(["## 후보 점수", ""])
    for candidate in candidates[:max_candidates]:
        lines.append(
            "- "
            f"[{candidate['zone_type']}] {candidate['lower_bound']:.2f}~{candidate['upper_bound']:.2f} "
            f"| strength={candidate['strength']} "
            f"| total={candidate['total_score']:.2f} "
            f"| touch={candidate['touch_score']:.2f} "
            f"| recency={candidate['recency_score']:.2f} "
            f"| volume={candidate['volume_reaction_score']:.2f} "
            f"| confluence={candidate['confluence_score']:.2f}"
        )
    if not candidates:
        lines.append("- 없음")
    lines.append("")

    lines.extend(["## 선택 추적", ""])
    selection_trace = payload.get("selection_trace") or []
    if selection_trace:
        for item in selection_trace:
            lines.append(f"- {item}")
    else:
        lines.append("- 없음")
    lines.append("")

    return "\n".join(lines)


def compare_structure_zone_inspect_payloads(
    baseline_payload: Mapping[str, object],
    current_payload: Mapping[str, object],
) -> dict:
    baseline_artifact = _as_dict(baseline_payload["artifact"])
    current_artifact = _as_dict(current_payload["artifact"])

    baseline_scores = {
        _candidate_key(item): item
        for item in [
            _as_dict(candidate) for candidate in baseline_artifact.get("score_breakdown", [])
        ]
    }
    current_scores = {
        _candidate_key(item): item
        for item in [
            _as_dict(candidate) for candidate in current_artifact.get("score_breakdown", [])
        ]
    }

    score_changes = []
    for key in sorted(set(baseline_scores) | set(current_scores)):
        baseline = baseline_scores.get(key)
        current = current_scores.get(key)
        if baseline and current:
            score_changes.append(
                {
                    "candidate_key": key,
                    "zone_type": current["zone_type"],
                    "bounds": _bounds_label(current),
                    "touch_delta": round(current["touch_score"] - baseline["touch_score"], 4),
                    "recency_delta": round(current["recency_score"] - baseline["recency_score"], 4),
                    "volume_delta": round(
                        current["volume_reaction_score"] - baseline["volume_reaction_score"], 4
                    ),
                    "confluence_delta": round(
                        current["confluence_score"] - baseline["confluence_score"], 4
                    ),
                    "total_delta": round(current["total_score"] - baseline["total_score"], 4),
                    "status": "matched",
                }
            )
        elif current:
            score_changes.append(
                {
                    "candidate_key": key,
                    "zone_type": current["zone_type"],
                    "bounds": _bounds_label(current),
                    "touch_delta": None,
                    "recency_delta": None,
                    "volume_delta": None,
                    "confluence_delta": None,
                    "total_delta": None,
                    "status": "added",
                }
            )
        else:
            score_changes.append(
                {
                    "candidate_key": key,
                    "zone_type": baseline["zone_type"],
                    "bounds": _bounds_label(baseline),
                    "touch_delta": None,
                    "recency_delta": None,
                    "volume_delta": None,
                    "confluence_delta": None,
                    "total_delta": None,
                    "status": "removed",
                }
            )

    score_changes.sort(
        key=lambda item: (
            0 if item["status"] == "matched" else 1,
            -(abs(item["total_delta"]) if item["total_delta"] is not None else -1),
        )
    )

    baseline_levels = _as_dict(baseline_payload["structure_levels"])
    current_levels = _as_dict(current_payload["structure_levels"])
    return {
        "symbol": str(current_payload["symbol"]),
        "baseline_source": str(baseline_payload.get("source") or ""),
        "current_source": str(current_payload.get("source") or ""),
        "selection_changes": {
            "support_zones": _compare_selected_lists(
                baseline_levels.get("support_zones", baseline_levels.get("demand_zones", [])),
                current_levels.get("support_zones", current_levels.get("demand_zones", [])),
            ),
            "resistance_zones": _compare_selected_lists(
                baseline_levels.get(
                    "resistance_zones",
                    baseline_levels.get("supply_zones", []),
                ),
                current_levels.get(
                    "resistance_zones",
                    current_levels.get("supply_zones", []),
                ),
            ),
            "former_levels": _compare_selected_lists(
                baseline_levels.get("former_levels", baseline_levels.get("balance_zones", [])),
                current_levels.get("former_levels", current_levels.get("balance_zones", [])),
            ),
            "invalidation": _compare_single_level(
                baseline_levels.get("invalidation"),
                current_levels.get("invalidation"),
            ),
        },
        "score_changes": score_changes,
    }


def format_structure_zone_inspect_comparison(
    diff_payload: Mapping[str, object],
    max_score_changes: int = 10,
) -> str:
    lines = [f"# Structure Zone Compare: {diff_payload['symbol']}", ""]
    lines.extend(
        [
            "## 비교 요약",
            "",
            f"- **baseline**: {diff_payload.get('baseline_source') or 'unknown'}",
            f"- **current**: {diff_payload.get('current_source') or 'unknown'}",
            "",
            "## 선택 레벨 변경",
            "",
        ]
    )

    for title, key in (
        ("지지 존", "support_zones"),
        ("저항 존", "resistance_zones"),
        ("전환 레벨", "former_levels"),
    ):
        lines.append(f"### {title}")
        lines.append("")
        for item in diff_payload["selection_changes"][key]:
            marker = "changed" if item["changed"] else "same"
            lines.append(
                f"- slot {item['slot']}: {marker} | baseline={item['baseline']} | current={item['current']}"
            )
        lines.append("")

    invalidation = diff_payload["selection_changes"]["invalidation"]
    lines.extend(
        [
            "### 구조 무효화",
            "",
            f"- {'changed' if invalidation['changed'] else 'same'} | baseline={invalidation['baseline']} | current={invalidation['current']}",
            "",
            "## 점수 변화",
            "",
        ]
    )

    visible_changes = [
        item
        for item in diff_payload["score_changes"]
        if item["status"] != "matched"
        or any(
            abs(item[field]) > 0
            for field in (
                "total_delta",
                "touch_delta",
                "recency_delta",
                "volume_delta",
                "confluence_delta",
            )
            if item[field] is not None
        )
    ]

    for item in visible_changes[:max_score_changes]:
        if item["status"] == "matched":
            lines.append(
                "- "
                f"[{item['zone_type']}] {item['bounds']} "
                f"| total Δ {item['total_delta']:+.2f} "
                f"| touch Δ {item['touch_delta']:+.2f} "
                f"| recency Δ {item['recency_delta']:+.2f} "
                f"| volume Δ {item['volume_delta']:+.2f} "
                f"| confluence Δ {item['confluence_delta']:+.2f}"
            )
        else:
            lines.append(f"- [{item['zone_type']}] {item['bounds']} | {item['status']}")
    if not visible_changes:
        lines.append("- 변화 없음")
    lines.append("")

    return "\n".join(lines)


def _serialize_zone(zone: StructureZone) -> dict:
    return {
        "zone_type": zone.zone_type,
        "lower_bound": zone.lower_bound,
        "upper_bound": zone.upper_bound,
        "mid_price": zone.mid_price,
        "strength": zone.strength,
        "touch_count": zone.touch_count,
        "last_touch_date": zone.last_touch_date,
        "reasons": zone.reasons,
        "reason_codes": zone.reason_codes,
        "reason_context": zone.reason_context,
        "touch_score": zone.touch_score,
        "recency_score": zone.recency_score,
        "volume_reaction_score": zone.volume_reaction_score,
        "confluence_score": zone.confluence_score,
        "total_score": zone.total_score,
    }


def _snapshot_view(snapshot: IndicatorSnapshot) -> dict:
    return {
        "price": snapshot.price,
        "change_pct": snapshot.change_pct,
        "atr": snapshot.atr,
        "sma_50": snapshot.sma_50,
        "sma_150": snapshot.sma_150,
        "sma_200": snapshot.sma_200,
        "pivot": snapshot.pivot,
        "support_s1": snapshot.support_s1,
        "resistance_r1": snapshot.resistance_r1,
        "high_52w": snapshot.high_52w,
        "low_52w": snapshot.low_52w,
        "swing_low": snapshot.swing_low,
        "swing_high": snapshot.swing_high,
    }


def _format_zone_group(
    title: str,
    zones: list[object],
    current_price: float,
    zone_type: str,
) -> list[str]:
    lines = [f"### {title}", ""]
    if not zones:
        lines.append("- 없음")
        lines.append("")
        return lines

    for zone in zones:
        zone_dict = _as_dict(zone)
        suffix = ""
        if zone_type == "supply" and zone_dict["upper_bound"] <= current_price:
            suffix = " | absorbed_supply"
        lines.append(
            f"- **{zone_dict['lower_bound']:.2f}~{zone_dict['upper_bound']:.2f}** "
            f"| {zone_dict['strength']} | score {zone_dict['total_score']:.2f} "
            f"| touch {zone_dict['touch_count']} | 최근 {zone_dict['last_touch_date'] or 'N/A'}{suffix}"
        )
        if zone_dict.get("reasons"):
            lines.append(f"  이유: {', '.join(zone_dict['reasons'])}")
    lines.append("")
    return lines


def _format_ma_summary(snapshot: Mapping[str, object]) -> str:
    sma_50 = snapshot.get("sma_50")
    sma_150 = snapshot.get("sma_150")
    sma_200 = snapshot.get("sma_200")
    parts = []
    if sma_50 is not None:
        parts.append(f"50일선 ${float(sma_50):.2f}")
    if sma_150 is not None:
        parts.append(f"150일선 ${float(sma_150):.2f}")
    if sma_200 is not None:
        parts.append(f"200일선 ${float(sma_200):.2f}")
    if not parts:
        return "- **이동평균선**: N/A"
    return f"- **이동평균선**: {' / '.join(parts)}"


def _as_dict(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    raise TypeError(f"Unsupported payload type: {type(value)!r}")


def _candidate_key(item: Mapping[str, object]) -> str:
    return f"{item['zone_type']}:{float(item['lower_bound']):.4f}:{float(item['upper_bound']):.4f}"


def _bounds_label(item: Mapping[str, object]) -> str:
    return f"{float(item['lower_bound']):.2f}~{float(item['upper_bound']):.2f}"


def _compare_selected_lists(
    baseline_levels: list[object],
    current_levels: list[object],
) -> list[dict]:
    max_len = max(len(baseline_levels), len(current_levels))
    result: list[dict] = []
    for index in range(max_len):
        baseline = _as_dict(baseline_levels[index]) if index < len(baseline_levels) else None
        current = _as_dict(current_levels[index]) if index < len(current_levels) else None
        baseline_label = _bounds_label(baseline) if baseline else "없음"
        current_label = _bounds_label(current) if current else "없음"
        result.append(
            {
                "slot": index + 1,
                "baseline": baseline_label,
                "current": current_label,
                "changed": baseline_label != current_label,
            }
        )
    return result


def _compare_single_level(baseline_level: object, current_level: object) -> dict:
    baseline = _as_dict(baseline_level) if baseline_level else None
    current = _as_dict(current_level) if current_level else None
    baseline_label = baseline.get("label", "없음") if baseline else "없음"
    current_label = current.get("label", "없음") if current else "없음"
    return {
        "baseline": baseline_label,
        "current": current_label,
        "changed": baseline_label != current_label,
    }

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.tools.technical.components.pattern_engine import PatternEngine
from src.tools.technical.level_composer import compose_level_payload
from src.tools.technical.price_levels import get_fibonacci_base_points, identify_key_levels
from src.tools.technical.structure_presentation import build_structure_presentation
from src.tools.technical.structure_zone_inspector import (
    build_indicator_snapshot_from_ohlcv,
    build_structure_zone_inspect_payload,
    compare_structure_zone_inspect_payloads,
)
from src.tools.technical.structure_zones import StructureZoneConfig, StructureZoneDetector


@dataclass(frozen=True)
class VariantSpec:
    name: str
    overrides: dict[str, Any]


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer.")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fixture-based structure-zone parameter sweep and generate compare report."
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=Path("tests/fixtures/technical/structure_zones"),
        help="Fixture CSV directory (default: tests/fixtures/technical/structure_zones).",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        help="Target symbols. Omit to use all CSV stems in fixtures dir.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        default=[],
        help=(
            "Variant spec: name:key=value,key2=value. "
            "Example: tight:cluster_span_multiplier=1.8,selection_max_distance_pct=0.35"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/structure_zone_sweeps"),
        help="Output root directory for sweep artifacts.",
    )
    parser.add_argument(
        "--run-id",
        help="Optional run id (default: YYYYmmdd-HHMMSS).",
    )
    parser.add_argument(
        "--max-candidates",
        type=_positive_int,
        default=3,
        help="Number of top candidates to include in summary.",
    )
    return parser.parse_args()


def parse_variant_spec(spec: str) -> VariantSpec:
    if ":" not in spec:
        raise ValueError(f"Invalid variant spec '{spec}' (missing ':').")
    name, raw_pairs = spec.split(":", 1)
    name = name.strip()
    if not name:
        raise ValueError(f"Invalid variant spec '{spec}' (empty variant name).")
    if not raw_pairs.strip():
        raise ValueError(f"Invalid variant spec '{spec}' (empty overrides).")

    overrides: dict[str, Any] = {}
    for raw_pair in _split_override_pairs(raw_pairs):
        if "=" not in raw_pair:
            raise ValueError(f"Invalid override '{raw_pair}' in '{spec}'.")
        key, value = raw_pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Invalid override '{raw_pair}' in '{spec}'.")
        overrides[key] = value

    return VariantSpec(name=name, overrides=overrides)


_VARIANT_FILENAME_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def to_variant_file_stem(name: str) -> str:
    stem = _VARIANT_FILENAME_SAFE_CHARS.sub("-", name.strip()).strip("-.")
    if not stem:
        raise ValueError(f"Variant name '{name}' cannot be used as output filename.")
    return stem


def _split_override_pairs(raw_pairs: str) -> list[str]:
    pairs: list[str] = []
    buffer: list[str] = []
    depth = 0
    quote_char: str | None = None
    escaped = False

    for char in raw_pairs:
        if quote_char is not None:
            buffer.append(char)
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == quote_char:
                quote_char = None
            continue

        if char in {'"', "'"}:
            quote_char = char
            buffer.append(char)
            continue
        if char in "{[(":
            depth += 1
            buffer.append(char)
            continue
        if char in "}])":
            depth = max(0, depth - 1)
            buffer.append(char)
            continue
        if char == "," and depth == 0:
            pair = "".join(buffer).strip()
            if pair:
                pairs.append(pair)
            buffer = []
            continue
        buffer.append(char)

    tail = "".join(buffer).strip()
    if tail:
        pairs.append(tail)
    return pairs


def resolve_symbols(fixtures_dir: Path, explicit_symbols: list[str] | None) -> list[str]:
    if explicit_symbols:
        return explicit_symbols
    return sorted(path.stem for path in fixtures_dir.glob("*.csv"))


def _coerce_value(current_value: Any, override_value: Any) -> Any:
    if isinstance(current_value, bool):
        lowered = str(override_value).lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
        raise ValueError(f"Invalid bool value '{override_value}'.")
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        text = str(override_value).strip()
        try:
            return int(text)
        except ValueError as exc:
            try:
                parsed_float = float(text)
            except ValueError:
                raise ValueError(f"Invalid int value '{override_value}'.") from exc
            if not parsed_float.is_integer():
                raise ValueError(f"Invalid int value '{override_value}'.") from exc
            return int(parsed_float)
    if isinstance(current_value, float):
        return float(override_value)
    if isinstance(current_value, dict):
        loaded = json.loads(override_value)
        if not isinstance(loaded, dict):
            raise ValueError("dict field override must be JSON object.")
        # Allow partial object override (e.g. score_weights only touch key).
        return {**current_value, **loaded}
    return override_value


def build_config_with_overrides(overrides: dict[str, Any]) -> StructureZoneConfig:
    base = StructureZoneConfig().model_dump()
    for key, value in overrides.items():
        if key not in base:
            raise ValueError(f"Unknown StructureZoneConfig field: '{key}'")
        base[key] = _coerce_value(base[key], value)
    return StructureZoneConfig(**base)


def load_fixture_dataframe(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, index_col="Date")
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def build_fixture_payload(symbol: str, csv_path: Path, config: StructureZoneConfig) -> dict:
    df = load_fixture_dataframe(csv_path)
    snapshot = build_indicator_snapshot_from_ohlcv(df)

    detector = StructureZoneDetector(config)
    zone_set = detector.detect(df, snapshot)
    chart_patterns = PatternEngine(swing_window=config.swing_window).detect(df, snapshot)
    lookback_high, lookback_low = get_fibonacci_base_points(df, snapshot)
    price_levels = identify_key_levels(
        snapshot=snapshot,
        pattern_results=chart_patterns,
        lookback_high=lookback_high,
        lookback_low=lookback_low,
    )
    level_payload = compose_level_payload(
        zone_set,
        price_levels,
        atr=snapshot.atr,
    )
    presented_structure = build_structure_presentation(
        level_payload.structure_levels,
        level_payload.execution_levels,
    )
    return build_structure_zone_inspect_payload(
        symbol=symbol,
        snapshot=snapshot,
        zone_set=zone_set,
        level_payload=level_payload,
        presented_structure=presented_structure,
        config=config,
        csv_path=str(csv_path),
        source="fixture",
    )


def _first_zone_label(items: list[dict[str, Any]]) -> str:
    if not items:
        return "-"
    first = items[0]
    lower = _try_float(first.get("lower_bound"))
    upper = _try_float(first.get("upper_bound"))
    if lower is None or upper is None:
        return "-"
    return f"{lower:.2f}~{upper:.2f}"


def _try_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _top_candidates(payload: dict, max_candidates: int) -> list[dict[str, Any]]:
    artifact = payload.get("artifact", {})
    candidates = artifact.get("candidates", [])
    if not isinstance(candidates, list):
        return []
    sorted_candidates = sorted(
        [item for item in candidates if isinstance(item, dict)],
        key=lambda item: _try_float(item.get("total_score")) or 0.0,
        reverse=True,
    )
    top_limit = max(0, max_candidates)
    return [
        {
            "zone_type": item.get("zone_type"),
            "bounds": (
                f"{(_try_float(item.get('lower_bound')) or 0.0):.2f}"
                f"~{(_try_float(item.get('upper_bound')) or 0.0):.2f}"
            ),
            "total_score": round(_try_float(item.get("total_score")) or 0.0, 4),
            "confluence_sources": (
                item.get("reason_context", {}).get("confluence_sources")
                if isinstance(item.get("reason_context"), dict)
                else []
            ),
        }
        for item in sorted_candidates[:top_limit]
    ]


def summarize_payload(payload: dict, max_candidates: int) -> dict[str, Any]:
    structure_levels = payload.get("structure_levels", {})
    invalidation = structure_levels.get("invalidation")
    snapshot = payload.get("snapshot", {})
    return {
        "summary_label": structure_levels.get("summary_label"),
        "headline": structure_levels.get("headline"),
        "support_zone_1": _first_zone_label(structure_levels.get("support_zones", [])),
        "resistance_zone_1": _first_zone_label(structure_levels.get("resistance_zones", [])),
        "former_level_1": _first_zone_label(structure_levels.get("former_levels", [])),
        "invalidation": invalidation.get("label") if isinstance(invalidation, dict) else "-",
        "current_price": _try_float(snapshot.get("price")) or 0.0,
        "top_candidates": _top_candidates(payload, max_candidates=max_candidates),
    }


def summarize_diff(diff_payload: dict[str, Any]) -> dict[str, Any]:
    selection_changes = diff_payload.get("selection_changes", {})
    score_changes = diff_payload.get("score_changes", [])
    changed_slots = 0
    for key in ("support_zones", "resistance_zones", "former_levels"):
        entries = selection_changes.get(key, [])
        changed_slots += sum(1 for item in entries if item.get("changed"))
    invalidation_changed = bool(selection_changes.get("invalidation", {}).get("changed"))
    if invalidation_changed:
        changed_slots += 1

    churn_count = sum(
        1
        for item in score_changes
        if isinstance(item, dict) and item.get("status") in {"added", "removed"}
    )
    max_total_delta = max(
        (
            abs(parsed_delta)
            for item in score_changes
            if (parsed_delta := _try_float(item.get("total_delta"))) is not None
        ),
        default=0.0,
    )
    return {
        "changed_slots": changed_slots,
        "invalidation_changed": invalidation_changed,
        "churn_count": churn_count,
        "max_total_delta": round(max_total_delta, 4),
    }


def _parse_bounds_label(label: str) -> tuple[float, float] | None:
    if "~" not in label:
        return None
    left, right = label.split("~", 1)
    try:
        return float(left), float(right)
    except ValueError:
        return None


def _zone_width_ratio_score(summary: dict[str, Any]) -> float:
    current_price = float(summary.get("current_price") or 0.0)
    if current_price <= 0:
        return 0.0

    width_ratios: list[float] = []
    for key in ("support_zone_1", "resistance_zone_1"):
        bounds = _parse_bounds_label(str(summary.get(key) or "-"))
        if bounds is None:
            continue
        lower, upper = bounds
        width_ratios.append(max(0.0, (upper - lower) / current_price))

    if not width_ratios:
        return 0.0

    avg_ratio = sum(width_ratios) / len(width_ratios)
    # 2% 이내면 만점(15), 12% 이상이면 0점.
    score = 15.0 * max(0.0, 1.0 - max(0.0, avg_ratio - 0.02) / 0.10)
    return round(score, 2)


def evaluate_scorecard(
    summary: dict[str, Any],
    diff_summary: dict[str, Any],
    *,
    is_baseline: bool = False,
    baseline_total_score_100: float | None = None,
) -> dict[str, Any]:
    summary_label = str(summary.get("summary_label") or "")
    invalidation_label = str(summary.get("invalidation") or "-")
    top_candidates = summary.get("top_candidates", [])
    confluence_coverage = 0.0
    if isinstance(top_candidates, list) and top_candidates:
        coverage_hits = 0
        for item in top_candidates:
            if not isinstance(item, dict):
                continue
            sources = item.get("confluence_sources")
            if isinstance(sources, list) and sources:
                coverage_hits += 1
        confluence_coverage = coverage_hits / max(len(top_candidates), 1)

    structure_clarity_score = (
        20.0 if summary_label and summary_label != "no_clear_structure" else 5.0
    )
    invalidation_score = 10.0 if invalidation_label != "-" else 0.0
    confluence_score = round(15.0 * confluence_coverage, 2)
    width_ratio_score = _zone_width_ratio_score(summary)
    structure_quality_score = round(
        structure_clarity_score + invalidation_score + confluence_score + width_ratio_score,
        2,
    )

    changed_slots = int(diff_summary.get("changed_slots", 0))
    churn_count = int(diff_summary.get("churn_count", 0))
    max_total_delta = float(diff_summary.get("max_total_delta", 0.0))
    invalidation_changed = bool(diff_summary.get("invalidation_changed", False))
    effective_changed_slots = changed_slots + churn_count
    if effective_changed_slots <= 2:
        slot_stability_score = 20.0
    elif effective_changed_slots <= 4:
        slot_stability_score = 14.0
    elif effective_changed_slots <= 6:
        slot_stability_score = 8.0
    else:
        slot_stability_score = 3.0

    invalidation_stability_score = 10.0 if not invalidation_changed else 3.0
    if max_total_delta <= 1.0:
        delta_sanity_score = 10.0
    elif max_total_delta <= 2.0:
        delta_sanity_score = 8.0
    elif max_total_delta <= 3.0:
        delta_sanity_score = 5.0
    elif max_total_delta <= 5.0:
        delta_sanity_score = 2.0
    else:
        delta_sanity_score = 0.0
    stability_proxy_score = round(
        slot_stability_score + invalidation_stability_score + delta_sanity_score,
        2,
    )

    total_score = round(structure_quality_score + stability_proxy_score, 2)
    baseline_delta_score = (
        round(total_score - float(baseline_total_score_100), 2)
        if baseline_total_score_100 is not None
        else None
    )
    if is_baseline:
        verdict = "baseline"
    elif baseline_delta_score is not None:
        if total_score >= 70 and baseline_delta_score >= 3.0:
            verdict = "개선"
        elif total_score < 60 or baseline_delta_score <= -3.0:
            verdict = "악화"
        else:
            verdict = "보류"
    elif total_score >= 75:
        verdict = "개선"
    elif total_score >= 65:
        verdict = "보류"
    else:
        verdict = "악화"

    return {
        "structure_quality_score_60": structure_quality_score,
        "stability_proxy_score_40": stability_proxy_score,
        "total_score_100": total_score,
        "baseline_total_score_100": baseline_total_score_100,
        "baseline_delta_score": baseline_delta_score,
        "verdict": verdict,
        "breakdown": {
            "structure_clarity_score_20": structure_clarity_score,
            "invalidation_score_10": invalidation_score,
            "confluence_score_15": confluence_score,
            "width_ratio_score_15": width_ratio_score,
            "slot_stability_score_20": slot_stability_score,
            "invalidation_stability_score_10": invalidation_stability_score,
            "delta_sanity_score_10": delta_sanity_score,
            "effective_changed_slots": effective_changed_slots,
            "changed_slots": changed_slots,
            "churn_count": churn_count,
        },
    }


def _escape_markdown_cell(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def build_markdown_report(
    rows: list[dict[str, Any]],
    run_id: str,
) -> str:
    lines = [
        f"# Structure Zone Sweep Report ({run_id})",
        "",
        "## 자동 판정 기준",
        "- 구조 품질(60): 구조 명확성, 무효화 존재, confluence 근거, 존 폭 적절성",
        "- 안정성 프록시(40): 슬롯 변화량(+ added/removed churn), 무효화 변경 여부, 총점 변동폭",
        "- 판정(variant): baseline 대비 +3점 이상 & total 70점 이상=개선, -3점 이하 또는 total 60 미만=악화, 그 외 보류",
        "",
        "| symbol | variant | verdict | total(100) | delta_vs_baseline | structure(60) | stability(40) | summary | support1 | resistance1 | changed_slots | churn_count | max_total_delta |",
        "|---|---|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        scorecard = row["scorecard"]
        baseline_delta_score = scorecard.get("baseline_delta_score")
        baseline_delta_label = (
            "-" if baseline_delta_score is None else f"{float(baseline_delta_score):+.1f}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown_cell(row["symbol"]),
                    _escape_markdown_cell(row["variant"]),
                    _escape_markdown_cell(scorecard["verdict"]),
                    f"{float(scorecard['total_score_100']):.1f}",
                    baseline_delta_label,
                    f"{float(scorecard['structure_quality_score_60']):.1f}",
                    f"{float(scorecard['stability_proxy_score_40']):.1f}",
                    _escape_markdown_cell(row["summary"]["summary_label"] or "-"),
                    _escape_markdown_cell(row["summary"]["support_zone_1"]),
                    _escape_markdown_cell(row["summary"]["resistance_zone_1"]),
                    str(row["diff"]["changed_slots"]),
                    str(row["diff"].get("churn_count", 0)),
                    f"{float(row['diff']['max_total_delta']):.2f}",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    fixtures_dir: Path = args.fixtures_dir
    if not fixtures_dir.exists():
        raise SystemExit(f"Fixture directory not found: {fixtures_dir}")

    symbols = resolve_symbols(fixtures_dir, args.symbols)
    if not symbols:
        raise SystemExit("No fixture symbols found.")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    variants = [VariantSpec(name="baseline", overrides={})]
    seen_names = {"baseline"}
    for raw_spec in args.variant:
        try:
            parsed = parse_variant_spec(raw_spec)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if parsed.name in seen_names:
            raise SystemExit(f"Duplicate variant name: {parsed.name}")
        variants.append(parsed)
        seen_names.add(parsed.name)

    rows: list[dict[str, Any]] = []
    report_payload: dict[str, Any] = {
        "run_id": run_id,
        "fixtures_dir": str(fixtures_dir),
        "symbols": symbols,
        "variants": [
            {"name": variant.name, "overrides": variant.overrides} for variant in variants
        ],
        "results": {},
    }

    for symbol in symbols:
        csv_path = fixtures_dir / f"{symbol}.csv"
        if not csv_path.exists():
            raise SystemExit(f"Fixture CSV not found for {symbol}: {csv_path}")

        baseline_payload = build_fixture_payload(
            symbol=symbol,
            csv_path=csv_path,
            config=StructureZoneConfig(),
        )
        baseline_summary = summarize_payload(baseline_payload, max_candidates=args.max_candidates)

        symbol_dir = output_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        baseline_json_path = symbol_dir / "baseline.json"
        baseline_json_path.write_text(
            json.dumps(baseline_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        baseline_diff_summary = {
            "changed_slots": 0,
            "invalidation_changed": False,
            "churn_count": 0,
            "max_total_delta": 0.0,
        }
        baseline_scorecard = evaluate_scorecard(
            baseline_summary,
            baseline_diff_summary,
            is_baseline=True,
        )

        report_payload["results"][symbol] = {
            "baseline": {
                "summary": baseline_summary,
                "scorecard": baseline_scorecard,
                "payload_path": str(baseline_json_path),
            },
            "variants": {},
        }

        rows.append(
            {
                "symbol": symbol,
                "variant": "baseline",
                "summary": baseline_summary,
                "diff": baseline_diff_summary,
                "scorecard": baseline_scorecard,
            }
        )

        used_variant_stems: set[str] = set()
        for variant in variants[1:]:
            try:
                config = build_config_with_overrides(variant.overrides)
            except ValueError as exc:
                raise SystemExit(f"Invalid overrides for variant '{variant.name}': {exc}") from exc
            payload = build_fixture_payload(symbol=symbol, csv_path=csv_path, config=config)
            variant_summary = summarize_payload(payload, max_candidates=args.max_candidates)
            diff = compare_structure_zone_inspect_payloads(baseline_payload, payload)
            diff_summary = summarize_diff(diff)
            scorecard = evaluate_scorecard(
                variant_summary,
                diff_summary,
                baseline_total_score_100=baseline_scorecard["total_score_100"],
            )

            variant_stem = to_variant_file_stem(variant.name)
            original_stem = variant_stem
            suffix = 2
            while variant_stem in used_variant_stems:
                variant_stem = f"{original_stem}-{suffix}"
                suffix += 1
            used_variant_stems.add(variant_stem)

            variant_json_path = symbol_dir / f"{variant_stem}.json"
            diff_json_path = symbol_dir / f"{variant_stem}.diff.json"
            variant_json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            diff_json_path.write_text(
                json.dumps(diff, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            report_payload["results"][symbol]["variants"][variant.name] = {
                "overrides": variant.overrides,
                "summary": variant_summary,
                "diff_summary": diff_summary,
                "scorecard": scorecard,
                "payload_path": str(variant_json_path),
                "diff_path": str(diff_json_path),
            }
            rows.append(
                {
                    "symbol": symbol,
                    "variant": variant.name,
                    "summary": variant_summary,
                    "diff": diff_summary,
                    "scorecard": scorecard,
                }
            )

    report_json_path = output_dir / "report.json"
    report_md_path = output_dir / "report.md"
    report_json_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_md_path.write_text(
        build_markdown_report(rows, run_id),
        encoding="utf-8",
    )

    print(f"[sweep] run_id={run_id}")
    print(f"[sweep] report_json={report_json_path}")
    print(f"[sweep] report_md={report_md_path}")


if __name__ == "__main__":
    main()

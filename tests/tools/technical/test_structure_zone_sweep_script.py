from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module():
    script_path = Path("scripts/sweep_structure_zone_params.py")
    spec = importlib.util.spec_from_file_location("structure_zone_sweep_script", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load sweep_structure_zone_params.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_variant_spec_parses_name_and_overrides():
    module = _load_module()

    parsed = module.parse_variant_spec(
        "tight:cluster_span_multiplier=1.8,selection_max_distance_pct=0.35"
    )

    assert parsed.name == "tight"
    assert parsed.overrides == {
        "cluster_span_multiplier": "1.8",
        "selection_max_distance_pct": "0.35",
    }


def test_parse_variant_spec_keeps_json_object_override_as_single_value():
    module = _load_module()

    parsed = module.parse_variant_spec(
        'weights:score_weights={"touch":0.4,"recency":0.2},selection_max_distance_pct=0.35'
    )

    assert parsed.name == "weights"
    assert parsed.overrides["score_weights"] == '{"touch":0.4,"recency":0.2}'
    assert parsed.overrides["selection_max_distance_pct"] == "0.35"


def test_build_config_with_overrides_coerces_value_types():
    module = _load_module()

    config = module.build_config_with_overrides(
        {
            "top_n_per_side": "3",
            "cluster_span_multiplier": "1.8",
            "selection_max_distance_pct": "0.35",
        }
    )

    assert config.top_n_per_side == 3
    assert config.cluster_span_multiplier == 1.8
    assert config.selection_max_distance_pct == 0.35


def test_build_config_with_overrides_accepts_integral_float_for_int():
    module = _load_module()

    config = module.build_config_with_overrides(
        {
            "top_n_per_side": "3.0",
        }
    )

    assert config.top_n_per_side == 3


def test_build_config_with_overrides_rejects_non_integral_float_for_int():
    module = _load_module()

    with pytest.raises(ValueError, match="Invalid int value"):
        module.build_config_with_overrides(
            {
                "top_n_per_side": "3.5",
            }
        )


def test_build_config_with_overrides_merges_partial_score_weights():
    module = _load_module()

    config = module.build_config_with_overrides(
        {
            "score_weights": '{"touch":0.4}',
        }
    )

    assert config.score_weights["touch"] == 0.4
    assert config.score_weights["recency"] == 0.2
    assert config.score_weights["volume"] == 0.3
    assert config.score_weights["confluence"] == 0.15


def test_summarize_diff_aggregates_selection_and_score_changes():
    module = _load_module()

    summary = module.summarize_diff(
        {
            "selection_changes": {
                "support_zones": [{"changed": True}, {"changed": False}],
                "resistance_zones": [{"changed": False}],
                "former_levels": [{"changed": True}],
                "invalidation": {"changed": True},
            },
            "score_changes": [
                {"status": "matched", "total_delta": 0.6},
                {"status": "matched", "total_delta": -1.1},
                {"status": "added", "total_delta": None},
            ],
        }
    )

    assert summary["changed_slots"] == 3
    assert summary["invalidation_changed"] is True
    assert summary["churn_count"] == 1
    assert summary["max_total_delta"] == 1.1


def test_positive_int_rejects_non_positive():
    module = _load_module()

    with pytest.raises(argparse.ArgumentTypeError):
        module._positive_int("0")
    with pytest.raises(argparse.ArgumentTypeError):
        module._positive_int("-1")


def test_to_variant_file_stem_sanitizes_unsafe_name():
    module = _load_module()

    stem = module.to_variant_file_stem("foo/bar:alpha|beta")
    assert stem == "foo-bar-alpha-beta"


def test_zone_width_ratio_score_returns_zero_on_missing_data():
    module = _load_module()

    score = module._zone_width_ratio_score(
        {
            "current_price": 0.0,
            "support_zone_1": "-",
            "resistance_zone_1": "-",
        }
    )
    assert score == 0.0


def test_evaluate_scorecard_marks_improved_for_strong_structure_and_stability():
    module = _load_module()

    scorecard = module.evaluate_scorecard(
        summary={
            "summary_label": "support_zone",
            "invalidation": "100.00~105.00 하향 이탈",
            "support_zone_1": "100.00~103.00",
            "resistance_zone_1": "110.00~113.00",
            "current_price": 110.0,
            "top_candidates": [
                {"confluence_sources": ["MA150", "POC"]},
                {"confluence_sources": ["HVNx1"]},
            ],
        },
        diff_summary={
            "changed_slots": 1,
            "invalidation_changed": False,
            "max_total_delta": 0.8,
        },
    )

    assert scorecard["total_score_100"] >= 75
    assert scorecard["verdict"] == "개선"


def test_evaluate_scorecard_uses_baseline_delta_not_absolute_only():
    module = _load_module()

    scorecard = module.evaluate_scorecard(
        summary={
            "summary_label": "support_zone",
            "invalidation": "100.00~105.00 하향 이탈",
            "support_zone_1": "100.00~103.00",
            "resistance_zone_1": "110.00~113.00",
            "current_price": 110.0,
            "top_candidates": [
                {"confluence_sources": ["MA150", "POC"]},
                {"confluence_sources": ["HVNx1"]},
            ],
        },
        diff_summary={
            "changed_slots": 1,
            "invalidation_changed": False,
            "churn_count": 0,
            "max_total_delta": 0.8,
        },
        baseline_total_score_100=101.0,
    )

    assert scorecard["total_score_100"] >= 75
    assert scorecard["baseline_delta_score"] < 0
    assert scorecard["verdict"] == "보류"


def test_evaluate_scorecard_marks_worse_when_baseline_delta_is_large_negative():
    module = _load_module()

    scorecard = module.evaluate_scorecard(
        summary={
            "summary_label": "support_zone",
            "invalidation": "100.00~105.00 하향 이탈",
            "support_zone_1": "100.00~103.00",
            "resistance_zone_1": "110.00~113.00",
            "current_price": 110.0,
            "top_candidates": [
                {"confluence_sources": ["MA150", "POC"]},
                {"confluence_sources": ["HVNx1"]},
            ],
        },
        diff_summary={
            "changed_slots": 1,
            "invalidation_changed": False,
            "churn_count": 0,
            "max_total_delta": 0.8,
        },
        baseline_total_score_100=103.0,
    )

    assert scorecard["baseline_delta_score"] <= -3.0
    assert scorecard["verdict"] == "악화"


def test_evaluate_scorecard_marks_worse_for_no_clear_and_large_drift():
    module = _load_module()

    scorecard = module.evaluate_scorecard(
        summary={
            "summary_label": "no_clear_structure",
            "invalidation": "-",
            "support_zone_1": "-",
            "resistance_zone_1": "-",
            "current_price": 0.0,
            "top_candidates": [],
        },
        diff_summary={
            "changed_slots": 8,
            "invalidation_changed": True,
            "churn_count": 2,
            "max_total_delta": 6.5,
        },
    )

    assert scorecard["total_score_100"] < 65
    assert scorecard["verdict"] == "악화"


def test_build_markdown_report_escapes_cells():
    module = _load_module()

    report = module.build_markdown_report(
        rows=[
            {
                "symbol": "A|LAB",
                "variant": "v1\nline",
                "summary": {
                    "summary_label": "support_zone",
                    "support_zone_1": "100.00~103.00",
                    "resistance_zone_1": "110.00~113.00",
                },
                "diff": {
                    "changed_slots": 1,
                    "churn_count": 0,
                    "max_total_delta": 0.8,
                },
                "scorecard": {
                    "verdict": "보류",
                    "total_score_100": 77.1,
                    "baseline_delta_score": -1.2,
                    "structure_quality_score_60": 45.0,
                    "stability_proxy_score_40": 32.1,
                },
            }
        ],
        run_id="test",
    )

    assert "A\\|LAB" in report
    assert "v1<br>line" in report

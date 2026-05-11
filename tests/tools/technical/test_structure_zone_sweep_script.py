from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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
    assert summary["max_total_delta"] == 1.1

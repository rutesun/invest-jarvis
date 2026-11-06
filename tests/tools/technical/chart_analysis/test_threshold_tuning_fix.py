"""Compatibility tuning reaches numerical owners and request identity together."""

import numpy as np
import pandas as pd
import pytest

from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.models import FactRef
from src.tools.technical.components.patterns import PatternThresholds, _detect_vcp, analyze_patterns
from src.tools.technical.context import common_analysis_for_frame
from src.tools.technical.scorer import technical_rule_requests


def vcp_frame():
    return pd.DataFrame(
        {
            "Open": 10.5,
            "Close": 10.5,
            "High": 11.0,
            "Low": 10.0,
            "Volume": 10.0,
            "ATR": [10.0] * 16 + [7.0] * 4,
        },
        index=pd.bdate_range("2024-01-02", periods=20),
    )


def test_nondefault_vcp_reaches_public_helper_analyzer_and_common_identity(monkeypatch):
    frame = vcp_frame()
    context = AnalysisRequestContext()
    first = common_analysis_for_frame(frame, context=context, rules=technical_rule_requests())
    old_item = next(item for item in first.items if item.rule_id == "chart.vcp.legacy")
    old_ref = FactRef(first.analysis_id, old_item.id)
    assert analyze_patterns(frame).score == 20
    assert (
        old_item.parameter_id
        == next(r for r in first.requested_rules if r.rule_id == old_item.rule_id).parameter_id
    )
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.5)
    assert _detect_vcp(frame)["score"] == 0
    assert analyze_patterns(frame).score == 0
    second = common_analysis_for_frame(frame, context=context, rules=technical_rule_requests())
    assert analyze_patterns(frame, common_analysis=second).score == 0
    new_item = next(item for item in second.items if item.rule_id == "chart.vcp.legacy")
    assert second.analysis_id != first.analysis_id
    assert new_item.parameter_id != old_item.parameter_id
    assert new_item.evaluation_key != old_item.evaluation_key
    assert context.resolve(old_ref) == old_item
    assert context.resolve(old_ref).evidence["in_vcp"] is True


def test_direct_volume_helpers_keep_threshold_tuning(monkeypatch):
    from src.tools.technical.components.volume import _detect_power_gap_up

    frame = vcp_frame()
    frame["Vol_SMA_20"] = 10.0
    frame.iloc[-1, frame.columns.get_loc("Open")] = 11.55
    frame.iloc[-1, frame.columns.get_loc("Volume")] = 30.0
    assert _detect_power_gap_up(frame)["score"] == 20
    monkeypatch.setattr(PatternThresholds, "GAP_SIZE_MIN_PCT", 0.1)
    assert _detect_power_gap_up(frame)["score"] == 0


TUNING_CASES = [
    ("VCP_ATR_CONTRACTION", 0.5, "vcp", 20, 0),
    ("VCP_TIGHTNESS_MULTIPLIER", 0.05, "vcp", 20, 10),
    ("VCP_MIN_TIGHT_DAYS", 21, "vcp", 20, 10),
    ("VCP_RECENT_TIGHT_WINDOW", 1, "recent", 10, 20),
    ("PP_SMA_DISTANCE_PCT", 0.001, "pocket", 25, 0),
    ("PP_LOOKBACK_DAYS", 2, "pocket", 25, 0),
    ("TENNIS_BALL_THRESHOLD", 0.3, "tennis", 15, 0),
    ("EGG_THRESHOLD", 2.0, "egg", -15, 0),
    ("MEAN_REVERSION_LOOKBACK", 1, "tennis", 15, 0),
    ("GAP_SIZE_MIN_PCT", 0.1, "gap", 20, 0),
    ("GAP_VOLUME_MULTIPLIER", 4.0, "gap", 20, 0),
    ("VOLUME_SURGE_MULTIPLIER", 3.0, "surge", 15, 5),
    ("VOLUME_MODERATE_MULTIPLIER", 1.4, "moderate", 3, 0),
    ("VCP_TIGHTNESS_MULTIPLIER", -0.5, "vcp", 20, 10),
]


def tuning_case(kind):
    from src.tools.technical.components import volume

    frame = vcp_frame()
    if kind in ("vcp", "recent"):
        if kind == "recent":
            frame.iloc[-3:-1, frame.columns.get_loc("High")] = 20.0
        return frame, _detect_vcp, analyze_patterns, "chart.vcp.legacy"
    frame["Vol_SMA_20"] = 10.0
    frame["Open"] = 10.6
    if kind == "pocket":
        frame["SMA_50"] = 10.4
        frame.iloc[-1, frame.columns.get_loc("Volume")] = 30.0

        def direct(df):
            return volume._detect_pocket_pivot(df, df.iloc[-1])

        family = "chart.pocket_pivot.down_candle"
    elif kind in ("tennis", "egg"):
        frame.iloc[-1, frame.columns.get_loc("Volume")] = 4.0 if kind == "tennis" else 16.0

        def direct(df):
            return volume._detect_tennis_ball_egg(df, df.iloc[-1], True)

        family = "chart.legacy.volume_extra"
    elif kind == "gap":
        frame.iloc[-1, frame.columns.get_loc("Open")] = 11.55
        frame.iloc[-1, frame.columns.get_loc("Volume")] = 30.0
        direct = volume._detect_power_gap_up
        family = "chart.power_gap"
    else:
        frame.iloc[-1, frame.columns.get_loc("Close")] = 11.0
        frame.iloc[-1, frame.columns.get_loc("Volume")] = 25.0 if kind == "surge" else 13.0

        def direct(df):
            return volume.analyze_volume(df).model_dump()

        family = "chart.legacy.volume_extra"
    return frame, direct, volume.analyze_volume, family


@pytest.mark.parametrize("name,value,kind,before,after", TUNING_CASES)
def test_every_existing_tuning_seam_reaches_owner_and_common_consumer(
    monkeypatch, name, value, kind, before, after
):
    frame, direct, public, family = tuning_case(kind)
    context = AnalysisRequestContext()
    default = common_analysis_for_frame(frame, context=context, rules=technical_rule_requests())
    item = next(item for item in default.items if item.rule_id == family)
    ref = FactRef(default.analysis_id, item.id)
    assert direct(frame)["score"] == before
    assert next(r for r in default.requested_rules if r.rule_id == family).parameters == {}
    monkeypatch.setattr(PatternThresholds, name, value)
    assert direct(frame)["score"] == after
    tuned = common_analysis_for_frame(frame, context=context, rules=technical_rule_requests())
    assert public(frame, common_analysis=tuned).model_dump() == public(frame).model_dump()
    request = next(r for r in tuned.requested_rules if r.rule_id == family)
    assert request.parameters["pattern_thresholds"] == {name: value}
    assert tuned.analysis_id != default.analysis_id
    assert context.resolve(ref) == item
    with pytest.raises(ValueError, match="contract"):
        public(frame, common_analysis=default)


@pytest.mark.parametrize(
    "family,thresholds",
    [
        ("chart.vcp.legacy", {"VCP_ATR_CONTRACTION": float("nan")}),
        ("chart.vcp.legacy", {"VCP_ATR_CONTRACTION": True}),
        ("chart.vcp.legacy", {"VCP_RECENT_TIGHT_WINDOW": 0}),
        ("chart.pocket_pivot.down_candle", {"PP_LOOKBACK_DAYS": 2.5}),
        ("chart.power_gap", {"GAP_SIZE_MIN_PCT": float("inf")}),
        ("chart.power_gap", {"VCP_ATR_CONTRACTION": 0.5}),
        ("chart.legacy.volume_extra", {"ARBITRARY": 1}),
    ],
)
def test_tuned_request_rejects_invalid_or_unrelated_parameters(family, thresholds):
    from src.tools.technical.chart_analysis.registry import rule_request

    with pytest.raises(ValueError):
        common_analysis_for_frame(
            vcp_frame(), rules=(rule_request(family, {"pattern_thresholds": thresholds}),)
        )


def test_vcp_tuning_reaches_playbook_and_trigger_paths(monkeypatch):
    from src.tools.playbook.vcp import detect_vcp_breakout
    from src.tools.technical.context import compatibility_rule_request
    from src.tools.technical.scorecard import _triggers_from_common
    from src.tools.technical.triggers import detect_analysis_triggers

    frame = pd.concat([vcp_frame(), vcp_frame().iloc[-1:].set_axis([pd.Timestamp("2024-02-01")])])
    frame["High_20_Prev"] = 11.0
    frame["Vol_SMA_50"] = 5.0
    frame.iloc[-1, frame.columns.get_loc("Close")] = 12.0
    code = "analysis.patterns.vcp_breakout"
    context = AnalysisRequestContext()

    def evaluate():
        return common_analysis_for_frame(
            frame,
            context=context,
            rules=(
                compatibility_rule_request("chart.vcp.playbook"),
                compatibility_rule_request(code, {"frame_policy": "SUPPLIED_AS_IS"}),
            ),
        )

    default = evaluate()
    assert detect_vcp_breakout(frame).in_vcp is True
    assert any(event.code == code for event in detect_analysis_triggers(frame))
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.5)
    tuned = evaluate()
    assert detect_vcp_breakout(frame).in_vcp is False
    assert detect_vcp_breakout(frame, common_analysis=tuned).in_vcp is False
    assert all(event.code != code for event in detect_analysis_triggers(frame))
    assert _triggers_from_common(tuned) == []
    assert tuned.analysis_id != default.analysis_id


@pytest.mark.parametrize(
    "name,value,kind,score",
    [
        ("VCP_ATR_CONTRACTION", np.float64(0.5), "vcp", 0),
        ("PP_LOOKBACK_DAYS", np.int64(2), "pocket", 0),
    ],
)
def test_optimizer_numpy_scalars_remain_valid_tuning(monkeypatch, name, value, kind, score):
    frame, direct, public, _ = tuning_case(kind)
    monkeypatch.setattr(PatternThresholds, name, value)
    assert direct(frame)["score"] == score
    common = common_analysis_for_frame(frame, rules=technical_rule_requests())
    assert public(frame, common_analysis=common).model_dump() == public(frame).model_dump()


def test_pocket_pivot_tuned_lookback_reports_real_history_boundary(monkeypatch):
    frame, _, _, family = tuning_case("pocket")
    monkeypatch.setattr(PatternThresholds, "PP_LOOKBACK_DAYS", 30)
    analysis = common_analysis_for_frame(frame, rules=technical_rule_requests())
    item = next(item for item in analysis.items if item.rule_id == family)
    assert item.state == "UNAVAILABLE"
    assert item.evidence["reasons"] == ("HISTORY_SHORT",)

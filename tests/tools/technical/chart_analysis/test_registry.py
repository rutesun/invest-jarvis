"""Finite map expansion guards against silently missing variants or policy activation."""

from src.tools.technical.chart_analysis.registry import RULE_REGISTRY, rule_request


def test_rule_registry_has_every_map_variant():
    required = {
        "chart.features.strict",
        "legacy.indicators",
        "legacy.extrema.order5",
        "chart.pivot.span3",
        "feature.window",
        "chart.vcp.legacy",
        "chart.pocket_pivot.down_candle",
        "chart.power_gap",
        "chart.context.breakdown",
        "chart.stage2.minervini",
        "chart.velocity.legacy",
        "chart.crsi.legacy",
        "chart.supertrend.legacy",
        "chart.legacy.state_windows",
        "chart.legacy.patterns_extra",
        "chart.legacy.volume_extra",
        "legacy.confluence",
        "legacy.divergence",
        "chart.close_breakout.nanmax",
        "chart.close_breakout.strict",
        "chart.structure_breakdown.swing",
        "chart.deep_recovery.swing",
        "OBSERVATION_V1",
        "chart.momentum.deceleration",
        "chart.momentum.reacceleration",
        "chart.anchor.break_reclaim",
        "chart.vcp.playbook",
        "chart.accumulation.days",
        "chart.market.regime",
        "chart.rs",
        "chart.low_break_volume",
        "chart.down_volume_weak_close",
        "chart.extension.sma20",
        "chart.rsi.wilder",
    }
    triggers = {
        *(
            f"analysis.{source}.{sense}_cross"
            for source in ("macd", "fast_macd")
            for sense in ("golden", "dead")
        ),
        *(
            f"analysis.{source}.{sense}_cross"
            for source in ("macd_hist", "fast_macd_hist")
            for sense in ("positive", "negative")
        ),
        "analysis.crsi.upper_band_exit",
        "analysis.crsi.lower_band_reentry",
        *(f"analysis.sma.{n}.turn_{sense}" for n in (20, 50, 150, 200) for sense in ("up", "down")),
        *(
            f"analysis.price.sma{n}_cross_{sense}"
            for n in (20, 50, 150, 200)
            for sense in ("above", "below")
        ),
        *(
            f"analysis.sma.{a}_{b}.{sense}_cross"
            for a, b in ((20, 50), (50, 150), (50, 200), (150, 200))
            for sense in ("golden", "dead")
        ),
        "analysis.supertrend.turn_up",
        "analysis.supertrend.turn_down",
        "analysis.price.high_20_breakout",
        "analysis.price.high_50_breakout",
        "analysis.patterns.vcp_breakout",
        "analysis.volume.pocket_pivot",
        "analysis.volume.power_gap_up",
        "analysis.volume.breakdown",
    }
    assert {entry.rule_id for entry in RULE_REGISTRY} == required | triggers
    assert len(
        {(entry.rule_id, entry.rule_version, entry.parameter_id) for entry in RULE_REGISTRY}
    ) == len(RULE_REGISTRY)
    assert {
        tuple(entry.parameters.items())
        for entry in RULE_REGISTRY
        if entry.rule_id == "chart.pivot.span3"
    } == {
        (("final_mask", False),),
        (("final_mask", True),),
    }
    assert {
        entry.parameters["lookback"]
        for entry in RULE_REGISTRY
        if entry.rule_id == "chart.close_breakout.strict"
    } == {20, 50}
    windows = {
        entry.parameters["feature_key"]
        for entry in RULE_REGISTRY
        if entry.rule_id == "feature.window"
    }
    assert windows == {
        "SMA_150_Slope_21",
        "SMA_20_Slope_5",
        "High_20_Prev",
        "High_50_Prev",
        "Low_20",
        "Low_20_Prev",
        "Vol_SMA_20",
        "Vol_SMA_20_Prev",
        "Vol_SMA_5",
        "Vol_SMA_20_Shift5",
        "High_52w",
        "Low_52w",
    }


def test_registry_declares_role_and_alignment_dependencies():
    assert rule_request("chart.rs").input_roles == ("instrument", "market")
    assert rule_request("chart.rs").alignment_version == "PLAYBOOK_RS_ALIGNMENT_AD880AF"
    assert rule_request("chart.market.regime").input_roles == ("market",)
    assert rule_request("chart.stage2.minervini").input_roles == ("instrument",)
    assert all(not entry.rule_id.startswith(("consumer.", "policy.")) for entry in RULE_REGISTRY)

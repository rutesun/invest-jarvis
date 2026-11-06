"""Pure legacy numerical facts used by common analyses and compatibility wrappers.

4C can prepare each role once, then call frame helpers in a request-local cache.
No evaluator/registry wiring, global cache or strategy models live here.
"""

from importlib.metadata import version

from src.tools.technical.chart_analysis._legacy_components import (
    crsi_values,
    patterns_extra_values,
    pocket_pivot_values,
    power_gap_values,
    stage2_values,
    supertrend_values,
    vcp_values,
    velocity_values,
    volume_extra_values,
)
from src.tools.technical.chart_analysis._legacy_context import context_values
from src.tools.technical.chart_analysis._legacy_levels import confluence_values, divergence_values
from src.tools.technical.chart_analysis._legacy_playbook import (
    accumulation_values,
    market_regime_values,
    playbook_vcp_values,
    relative_strength_values,
)
from src.tools.technical.chart_analysis._legacy_structure import (
    calculate_legacy_windows,
    close_breakout_values,
    fixed_anchor_close_values,
    nanmax_close_breakout_values,
    observation_numerical_values,
    state_window_values,
    swing_frame_values,
    swing_numerical_values,
    swing_signal_values,
)
from src.tools.technical.chart_analysis.features import (
    LEGACY_VERSION,
    SUPPLIED_VERSION,
    feature_provider_identity,
)
from src.tools.technical.chart_analysis.legacy_features import legacy_features_for_series
from src.tools.technical.chart_analysis.models import CalculationScope, SeriesInput
from src.tools.technical.chart_analysis.pattern_parameters import FAMILY_THRESHOLDS


FRAME_FAMILIES = {
    "chart.legacy.state_windows": state_window_values,
    "feature.window": calculate_legacy_windows,
    "chart.vcp.legacy": vcp_values,
    "chart.pocket_pivot.down_candle": pocket_pivot_values,
    "chart.power_gap": power_gap_values,
    "chart.context.breakdown": context_values,
    "chart.stage2.minervini": stage2_values,
    "chart.velocity.legacy": velocity_values,
    "chart.crsi.legacy": crsi_values,
    "chart.supertrend.legacy": supertrend_values,
    "chart.legacy.patterns_extra": patterns_extra_values,
    "chart.legacy.volume_extra": volume_extra_values,
    "legacy.confluence": confluence_values,
    "legacy.divergence": divergence_values,
    "chart.close_breakout.nanmax": nanmax_close_breakout_values,
    "chart.vcp.playbook": playbook_vcp_values,
    "chart.accumulation.days": accumulation_values,
    "chart.close_breakout.strict": close_breakout_values,
    "chart.structure_breakdown.swing": swing_frame_values,
    "chart.deep_recovery.swing": swing_frame_values,
    "OBSERVATION_V1": observation_numerical_values,
    "chart.momentum.deceleration": observation_numerical_values,
    "chart.momentum.reacceleration": observation_numerical_values,
}


SUPPLIED_FRAME_FAMILIES = frozenset(
    {
        "chart.stage2.minervini",
        "chart.velocity.legacy",
        "chart.crsi.legacy",
        "chart.supertrend.legacy",
        "chart.vcp.legacy",
        "chart.legacy.patterns_extra",
        "chart.legacy.volume_extra",
        "chart.pocket_pivot.down_candle",
        "chart.power_gap",
        "legacy.confluence",
        "legacy.divergence",
        "chart.context.breakdown",
        "chart.legacy.state_windows",
    }
)


def prepare_legacy_frame(series: SeriesInput):
    """Explicit profile dispatch; centered extrema are recomputed on this raw prefix."""
    return calculate_legacy_windows(legacy_features_for_series(series))


def legacy_fact_values_from_frame(frame, *, family: str, parameters=None) -> dict:
    """Numerical family over an explicitly prepared, caller-owned as-of frame."""
    try:
        calculate = FRAME_FAMILIES[family]
    except KeyError:
        raise KeyError(f"Unknown legacy fact family: {family}") from None
    values = (
        calculate(frame, thresholds=(parameters or {}).get("pattern_thresholds"))
        if family in FAMILY_THRESHOLDS
        else calculate(frame)
    )
    # Frame-shaped primitives keep dates and exact dtypes; scalar families are dicts.
    return {"frame": values} if hasattr(values, "columns") else values


def _check_legacy_profile(series):
    if series.manifest.feature_version not in (LEGACY_VERSION, SUPPLIED_VERSION):
        raise ValueError("legacy facts require an explicit legacy feature version")


def legacy_fact_provider_identity(scope: CalculationScope, *, family: str) -> dict:
    """Feature provenance plus live preparation/calculation dependencies.

    Supplied columns skip indicator calculation, not later pandas/numpy/scipy
    arithmetic. 4C must include all three identity sections in evaluation keys.
    """
    packages = {name: version(name) for name in ("pandas", "numpy")}
    if family in ("chart.rs", "chart.market.regime"):
        roles = ("instrument", "market") if family == "chart.rs" else ("market",)
        providers = {}
        for role in roles:
            series = scope.series_for(role)
            _check_legacy_profile(series)
            providers[role] = {
                "backend": "pandas/raw-close",
                "input_feature_version": series.manifest.feature_version,
                "packages": dict(packages),
            }
        preparation = None
        calculation = {"backend": "pandas/raw-close", "packages": dict(packages)}
    else:
        if family not in FRAME_FAMILIES:
            raise KeyError(f"Unknown legacy fact family: {family}")
        _check_legacy_profile(scope.primary)
        providers = {
            "instrument": feature_provider_identity(scope.primary.manifest.feature_version)
        }
        preparation = (
            None
            if scope.primary.manifest.feature_version == SUPPLIED_VERSION
            and family in SUPPLIED_FRAME_FAMILIES
            else {"backend": "pandas/rolling-shift", "packages": dict(packages)}
        )
        if family == "legacy.divergence":
            calculation = {
                "backend": "scipy/argrelextrema",
                "packages": {**packages, "scipy": version("scipy")},
            }
        elif family == "chart.velocity.legacy":
            calculation = {"backend": "numpy/polyfit", "packages": dict(packages)}
        elif family == "feature.window":
            calculation = {"backend": "pandas/rolling-shift", "packages": dict(packages)}
        else:
            calculation = {"backend": "pandas/numpy", "packages": dict(packages)}
    return {
        "family": family,
        "providers": providers,
        "preparation": preparation,
        "calculation": calculation,
    }


def legacy_fact_values(scope: CalculationScope, *, family: str) -> dict:
    """Direct-call convenience. 4C owns actual dependency identity/cache integration."""
    if family == "chart.market.regime":
        market = scope.series_for("market")
        _check_legacy_profile(market)
        return market_regime_values(market.raw)
    if family == "chart.rs":
        market = scope.series_for("market")
        _check_legacy_profile(scope.primary)
        _check_legacy_profile(market)
        return relative_strength_values(scope.primary.raw, market.raw)
    if family not in FRAME_FAMILIES:
        raise KeyError(f"Unknown legacy fact family: {family}")
    frame = (
        scope.primary.raw
        if scope.primary.manifest.feature_version == SUPPLIED_VERSION
        and family in SUPPLIED_FRAME_FAMILIES
        else prepare_legacy_frame(scope.primary)
    )
    if family in ("chart.structure_breakdown.swing", "chart.deep_recovery.swing"):
        from src.tools.technical.chart_analysis.pivots import confirmed_pivots

        higher, lower = confirmed_pivots(
            frame["High"].to_numpy(float), frame["Low"].to_numpy(float)
        )
        if "Higher_Low" not in frame:
            frame["Higher_Low"] = higher
        if "Lower_Low_Lower_High" not in frame:
            frame["Lower_Low_Lower_High"] = lower
    return legacy_fact_values_from_frame(frame, family=family)


__all__ = [
    "legacy_fact_values",
    "legacy_fact_provider_identity",
    "legacy_fact_values_from_frame",
    "prepare_legacy_frame",
    "calculate_legacy_windows",
    "close_breakout_values",
    "swing_numerical_values",
    "observation_numerical_values",
    "fixed_anchor_close_values",
    "swing_signal_values",
    "relative_strength_values",
    "market_regime_values",
]

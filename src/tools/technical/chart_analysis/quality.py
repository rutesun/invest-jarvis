"""Experimental Quality V1 consumer of strict, already-computed feature materials."""

from math import isfinite, log, sqrt

from src.tools.technical.chart_analysis.features import STRICT_VERSION
from src.tools.technical.chart_analysis.models import (
    ChartAnalysis,
    QualityDelta,
    QualityParameters,
    QualityResult,
    plain,
)
from src.tools.technical.chart_analysis.registry import rule_request


AXES = ("trend", "structure", "momentum", "participation")


def score_quality(analysis: ChartAnalysis, *, parameters: QualityParameters) -> QualityResult:
    """Score feature values only; retain diagnostics when publication is unavailable."""
    reasons: list[str] = []
    preview = False
    components: dict[str, float | None] = {}
    contributions: dict[str, float | None] = {}
    axes: dict[str, float | None] = dict.fromkeys(AXES)
    diagnostics = {
        "analysis_id": analysis.analysis_id,
        "parameters": plain(parameters),
        "features": plain(analysis.features),
        "components": components,
        "participation": {},
        "calculated_quality": None,
    }

    def result(quality=None):
        return QualityResult(
            analysis.manifest.as_of,
            analysis.manifest,
            parameters.score_version,
            parameters.parameter_id,
            axes,
            quality,
            tuple(dict.fromkeys(reasons)),
            diagnostics,
            contributions,
        )

    if (
        analysis.manifest.feature_version != STRICT_VERSION
        or analysis.manifest.input_profile not in {"CHART_INPUT_V1", "CHART_INPUT_RESPONSE_V2"}
    ):
        reasons.append("PROFILE_UNSUPPORTED")
        return result()
    request = rule_request("chart.features.strict")
    if request not in analysis.requested_rules:
        reasons.append("STRICT_FEATURE_REQUEST_REQUIRED")
        return result()

    def read(key, *, positive=False):
        nonlocal preview
        feature = analysis.features.get(key)
        if feature is None:
            reasons.append("INPUT_MISSING")
            return None
        reasons.extend(feature.reasons)
        if feature.status == "PROVISIONAL":
            preview = True
            reasons.append("PROVISIONAL_PREVIEW")
        value = feature.value
        if value is None or not isfinite(value) or feature.status not in ("READY", "PROVISIONAL"):
            if not feature.reasons or value is not None:
                reasons.append("INPUT_MISSING")
            return None
        if positive and value <= 0:
            reasons.append("NONPOSITIVE_PRICE")
            return None
        return value

    atr = read("ATR")
    if atr is not None and atr <= 0:
        reasons.append("NONPOSITIVE_ATR")
        atr = None

    def clip(value):
        return min(100.0, max(0.0, value))

    def distance(a, b, k=1.0):
        left, right = read(a, positive=True), read(b, positive=True)
        if atr is None or left is None or right is None:
            return None
        return clip(
            parameters.normalization_center + parameters.distance_scale * (left - right) / (k * atr)
        )

    def weighted(axis, entries):
        """Preserve declared component order, including null components."""
        weight = parameters.axis_weights[AXES.index(axis)]
        available = True
        total = 0.0
        for name, value, local_weight in entries:
            key = f"{axis}.{name}"
            components[key] = value
            contributions[key] = None if value is None else weight * local_weight * value
            if value is None:
                available = False
            else:
                total += local_weight * value
        axes[axis] = total if available else None

    t_close, t_alignment, t_slope = parameters.trend_weights
    weighted(
        "trend",
        (
            ("close_sma50", distance("Close", "SMA_50"), t_close),
            ("sma50_sma150", distance("SMA_50", "SMA_150"), t_alignment / 3),
            ("sma150_sma200", distance("SMA_150", "SMA_200"), t_alignment / 3),
            (
                "close_sma200",
                distance("Close", "SMA_200", parameters.close_sma200_k),
                t_alignment / 3,
            ),
            ("sma200_slope20", distance("SMA_200", "SMA_200_Lag20"), t_slope),
        ),
    )
    close, high, low = (read(key, positive=True) for key in ("Close", "High_20_New", "Low_20_New"))
    location = None
    if close is not None and high is not None and low is not None:
        if high == low:
            reasons.append("ZERO_PRICE_RANGE")
        elif high < low or not low <= close <= high:
            reasons.append("INVALID_PRICE_RANGE")
        else:
            location = 100 * (close - low) / (high - low)
    s_low, s_high, s_location = parameters.structure_weights
    weighted(
        "structure",
        (
            ("low_progression", distance("Low_20_New", "Low_20_Prior"), s_low),
            ("high_progression", distance("High_20_New", "High_20_Prior"), s_high),
            ("close_location", location, s_location),
        ),
    )
    momentum = []
    for lag, weight in zip(parameters.momentum_lags, parameters.momentum_weights, strict=True):
        previous = read(f"Close_Lag{lag}", positive=True)
        value = None
        if close is not None and previous is not None and atr is not None:
            value = clip(
                parameters.normalization_center
                + parameters.return_scale * log(close / previous) / ((atr / close) * sqrt(lag))
            )
        momentum.append((f"return_{lag}", value, weight))
    weighted("momentum", momentum)

    volume_keys = {
        "up_volume": "Up_Volume_20",
        "down_volume": "Down_Volume_20",
        "flat_volume": "Flat_Volume_20",
        "up_days": "Up_Days_20",
        "down_days": "Down_Days_20",
        "flat_days": "Flat_Days_20",
        "directional_sample": "Directional_Sample_20",
        "max_directional_volume": "Max_Directional_Volume_20",
        "max_share": "Max_Directional_Share_20",
    }
    participation = {key: read(feature) for key, feature in volume_keys.items()}
    diagnostics["participation"] = participation
    up, down, sample = (
        participation[key] for key in ("up_volume", "down_volume", "directional_sample")
    )
    p_score = None
    if up is not None and down is not None and sample is not None:
        if up + down == 0:
            reasons.append("ZERO_DIRECTIONAL_VOLUME")
        elif sample < parameters.directional_min_samples:
            reasons.append("LOW_DIRECTIONAL_SAMPLE")
        else:
            p_score = 100 * up / (up + down)
            if up == 0 or down == 0:
                reasons.append("ONE_SIDED_SAMPLE")
    share = participation["max_share"]
    if share is not None and share >= parameters.concentration_threshold:
        reasons.append("CONCENTRATED_VOLUME")
    weighted("participation", (("directional_volume", p_score, 1.0),))

    count, streak, history_status = (
        read(key) for key in ("History_Bars", "Valid_Final_Streak", "History_Status")
    )
    if count is not None and count < parameters.calculation_min_bars:
        reasons.append("HISTORY_SHORT")
    calculated = None
    if (
        all(value is not None for value in axes.values())
        and count is not None
        and count >= parameters.calculation_min_bars
    ):
        calculated = sum(parameters.axis_weights[i] * axes[key] for i, key in enumerate(AXES))
    diagnostics["calculated_quality"] = calculated
    if count is not None and count < parameters.publication_min_final_bars:
        reasons.append("POLICY_HISTORY_SHORT")
    if (
        history_status is None
        or history_status != 1
        or streak is None
        or count is None
        or streak != count
    ):
        reasons.append("INCOMPLETE_PREFIX")
    finality = analysis.manifest.finality
    finality = (
        finality if isinstance(finality, str) else finality.get(analysis.manifest.as_of, "UNKNOWN")
    )
    if finality != "FINAL":
        reasons.append("PROVISIONAL_PREVIEW" if finality == "PROVISIONAL" else "INCOMPLETE_PREFIX")
    unpublished = (
        calculated is None
        or count < parameters.publication_min_final_bars
        or history_status != 1
        or streak != count
        or finality != "FINAL"
        or preview
    )
    return result(None if unpublished else calculated)


def explain_delta(before: QualityResult, after: QualityResult) -> QualityDelta:
    """Explain unrounded change only for compatible, published endpoints."""
    reasons = []
    for field, reason in (
        ("score_version", "SCORE_VERSION_MISMATCH"),
        ("parameter_id", "PARAMETER_MISMATCH"),
    ):
        if getattr(before, field) != getattr(after, field):
            reasons.append(reason)
    for field, reason in (
        ("feature_version", "FEATURE_VERSION_MISMATCH"),
        ("input_profile", "INPUT_PROFILE_MISMATCH"),
        ("adjustment_policy", "ADJUSTMENT_POLICY_MISMATCH"),
        ("ticker", "INSTRUMENT_MISMATCH"),
        ("exchange", "INSTRUMENT_MISMATCH"),
        ("calendar_version", "CALENDAR_VERSION_MISMATCH"),
        ("provider", "PROVIDER_MISMATCH"),
        ("revision_if_known", "REVISION_MISMATCH"),
        ("timezone", "TIMEZONE_MISMATCH"),
    ):
        if getattr(before.manifest, field) != getattr(after.manifest, field):
            reasons.append(reason)
    if before.quality is None or after.quality is None:
        reasons.extend(("QUALITY_UNAVAILABLE", *before.reasons, *after.reasons))
    keys = tuple(dict.fromkeys((*before.contributions, *after.contributions)))
    if reasons:
        return QualityDelta(
            before.as_of,
            after.as_of,
            None,
            dict.fromkeys(AXES),
            dict.fromkeys(keys),
            tuple(dict.fromkeys(reasons)),
        )
    weights = before.diagnostics["parameters"]["axis_weights"]
    axis_contributions = {
        key: weights[i] * (after.axes[key] - before.axes[key]) for i, key in enumerate(AXES)
    }
    contributions = {key: after.contributions[key] - before.contributions[key] for key in keys}
    return QualityDelta(
        before.as_of,
        after.as_of,
        sum(axis_contributions.values()),
        axis_contributions,
        contributions,
        (),
    )

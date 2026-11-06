import pandas as pd

from src.tools.technical.models import MarketContext


def _safe_float(value) -> float | None:
    from src.tools.technical.chart_analysis import _legacy_context

    return _legacy_context._safe_float(value)


def _ret_pct(df: pd.DataFrame, days: int) -> float | None:
    from src.tools.technical.chart_analysis import _legacy_context

    return _legacy_context._ret_pct(df, days)


def _distance_pct(close: float, reference: float | None) -> float | None:
    from src.tools.technical.chart_analysis import _legacy_context

    return _legacy_context._distance_pct(close, reference)


def build_market_context(df: pd.DataFrame, *, common_analysis=None) -> MarketContext:
    """Build derived OHLCV state for ScoreAggregator."""
    values = common_evidence(df, common_analysis, "chart.context.breakdown")
    return MarketContext(
        **{key: value for key, value in values.items() if key in MarketContext.model_fields}
    )


def validate_common_scope(df, analysis, *, ticker=None, as_of=None):
    """Reject stale/different input snapshots before consuming compatibility facts."""
    from src.tools.technical.chart_analysis.features import SUPPLIED_VERSION
    from src.tools.technical.chart_analysis.models import content_hash

    manifest = analysis.manifest
    if (
        not isinstance(df.index, pd.DatetimeIndex)
        or df.empty
        or manifest.as_of != (as_of or df.index[-1].date())
        or manifest.input_hash != content_hash(df)
        or manifest.feature_version != SUPPLIED_VERSION
        or (ticker is not None and manifest.ticker != ticker)
    ):
        raise ValueError("common_analysis does not match consumer evaluation scope")


def common_evidence(df, analysis, rule_id):
    """Read one explicitly requested ASOF compatibility fact, never recompute it."""
    expected = compatibility_rule_request(rule_id)
    if analysis is None:
        from src.tools.technical.chart_analysis.legacy_facts import legacy_fact_values_from_frame

        return legacy_fact_values_from_frame(df, family=rule_id, parameters=expected.parameters)
    validate_common_scope(df, analysis)
    validate_common_requests(analysis, (expected,))
    items = [item for item in analysis.items if matches_common_request(item, expected)]
    if len(items) != 1:
        raise ValueError(f"common_analysis requires exactly one {rule_id} fact contract match")
    item = items[0]
    if (
        item.rule_version != expected.rule_version
        or item.parameter_id != expected.parameter_id
        or item.status_as_of != analysis.manifest.as_of
    ):
        raise ValueError(f"common_analysis {rule_id} fact contract mismatch")
    return item.evidence


def matches_common_request(item, request):
    """Use the same exact numerical variant for consumption and reference audit."""
    return (item.rule_id, item.rule_version, item.parameter_id) == (
        request.rule_id,
        request.rule_version,
        request.parameter_id,
    )


def pattern_threshold_snapshot(family):
    """Read mutable legacy tuning once at the compatibility boundary and validate."""
    from src.tools.technical.chart_analysis.pattern_parameters import (
        FAMILY_THRESHOLDS,
        canonical_threshold_overrides,
    )
    from src.tools.technical.components.patterns import PatternThresholds

    return canonical_threshold_overrides(
        family, {key: getattr(PatternThresholds, key) for key in FAMILY_THRESHOLDS.get(family, ())}
    )


def compatibility_rule_request(rule_id, parameters=None):
    """Preserve canonical defaults; bind nondefault legacy tuning into identity."""
    from src.tools.technical.chart_analysis.registry import rule_request

    request = rule_request(rule_id, parameters)
    thresholds = pattern_threshold_snapshot(rule_id)
    if not thresholds:
        return request
    return rule_request(rule_id, {**request.parameters, "pattern_thresholds": thresholds})


def common_analysis_for_frame(df, *, ticker=None, context=None, rules):
    """Create request-owned supplied-frame facts without changing dates or columns."""
    from src.tools.technical.chart_analysis import AnalysisRequestContext
    from src.tools.technical.chart_analysis.features import SUPPLIED_VERSION
    from src.tools.technical.chart_analysis.models import (
        CalculationScope,
        InputManifest,
        SeriesInput,
    )

    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return None
    manifest = InputManifest(
        ticker=ticker or "",
        exchange="UNSPECIFIED",
        as_of=df.index[-1].date(),
        origin="technical-consumer-supplied-frame",
        input_profile="LEGACY_CONSUMER_FRAME_V1",
        feature_version=SUPPLIED_VERSION,
        input_hash="",
        adjustment_policy="AS_SUPPLIED",
        calendar_version="AS_SUPPLIED",
        finality="UNKNOWN",
        coverage={"complete": True},
    )
    scope = CalculationScope(SeriesInput(manifest, df), {})
    return (context or AnalysisRequestContext()).get(scope, rules)


def validate_common_requests(analysis, required_rules):
    """An evaluated rule with zero events differs from a rule that was never requested."""

    def contract(rule):
        return (
            rule.rule_id,
            rule.rule_version,
            rule.parameter_id,
            rule.input_roles,
            rule.alignment_version,
        )

    actual = {contract(rule) for rule in analysis.requested_rules}
    if any(contract(rule) not in actual for rule in required_rules):
        raise ValueError("common_analysis required request contract mismatch")

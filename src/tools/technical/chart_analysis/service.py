"""Request-local immutable analyses and dependency-specific shared calculations."""

from collections.abc import Callable, Mapping
from types import MappingProxyType

from src.storage.canonical import canonical_hash
from src.tools.technical.chart_analysis.models import (
    CalculationScope,
    ChartAnalysis,
    ChartAnchor,
    ChartItem,
    FactRef,
    FeatureAnchor,
    FeatureValue,
    RuleRequest,
    plain,
)


# Custom evaluators retain the original callable contract and dependency rules.
RuleEvaluator = Callable[
    [CalculationScope, RuleRequest, tuple[ChartAnchor, ...], str],
    tuple[Mapping[str, FeatureValue], tuple[ChartItem, ...]],
]


class AnalysisRequestContext:
    def __init__(self, evaluators: Mapping[str, RuleEvaluator] | None = None):
        from src.tools.technical.chart_analysis.evaluators import default_evaluator_factory

        self._evaluators = dict(default_evaluator_factory() if evaluators is None else evaluators)
        self._default = evaluators is None
        self._analyses: dict[str, ChartAnalysis] = {}
        self._cache: dict[str, tuple[Mapping[str, FeatureValue], tuple[ChartItem, ...]]] = {}

    @property
    def analyses(self) -> Mapping[str, ChartAnalysis]:
        return MappingProxyType(self._analyses)

    def get(
        self,
        scope: CalculationScope,
        rules: tuple[RuleRequest, ...],
        anchors: tuple[ChartAnchor, ...] = (),
    ) -> ChartAnalysis:
        as_of = scope.primary.manifest.as_of
        for anchor in anchors:
            if anchor.origin_on > as_of or anchor.available_on > as_of:
                raise ValueError(f"Future anchor is unavailable at as_of: {anchor.id}")
        for role, series in scope.related.items():
            if series.manifest.as_of > as_of or any(day.date() > as_of for day in series.raw.index):
                raise ValueError(f"related {role} exceeds primary as_of")
        # Set semantics make order and duplicate requests immaterial.
        rule_set = {canonical_hash("jarvis:chart-rule:v1", plain(rule)): rule for rule in rules}
        anchor_set = {
            canonical_hash("jarvis:chart-anchor:v1", plain(anchor)): anchor for anchor in anchors
        }
        if len({anchor.id for anchor in anchor_set.values()}) != len(anchor_set):
            raise ValueError("Conflicting descriptors for the same anchor id")
        normalized_rules = tuple(rule_set[key] for key in sorted(rule_set))
        normalized_anchors = tuple(anchor_set[key] for key in sorted(anchor_set))
        manifests = {
            "instrument": scope.primary.manifest,
            **{role: value.manifest for role, value in scope.related.items()},
        }
        from src.tools.technical.chart_analysis.evaluators import provider_identity

        provider_metadata = (
            {
                canonical_hash("jarvis:chart-rule:v1", plain(rule)): tuple(
                    provider_identity(scope, rule, group)
                    for group in (
                        tuple((anchor,) for anchor in normalized_anchors)
                        if rule.rule_id == "chart.anchor.break_reclaim" and normalized_anchors
                        else ((),)
                    )
                )
                for rule in normalized_rules
            }
            if self._default
            else {}
        )
        analysis_id = canonical_hash(
            "jarvis:chart-analysis:v1",
            plain(
                {
                    "manifests": manifests,
                    "rules": normalized_rules,
                    "anchors": normalized_anchors,
                    "providers": provider_metadata,
                }
            ),
        )
        if analysis_id in self._analyses:
            return self._analyses[analysis_id]
        items: list[ChartItem] = []
        features: dict[str, FeatureValue] = {}
        for rule in normalized_rules:
            if rule.rule_id not in self._evaluators:
                raise NotImplementedError(f"No chart evaluator for {rule.rule_id}")
            dependencies = {role: scope.series_for(role).manifest for role in rule.input_roles}
            relevant = normalized_anchors if rule.rule_id == "chart.anchor.break_reclaim" else ()
            # Anchor calculations cache independently so a union reuses existing facts.
            groups = tuple((anchor,) for anchor in relevant) if relevant else ((),)
            for group in groups:
                used = dict(dependencies)
                for anchor in group:
                    if isinstance(anchor, FeatureAnchor):
                        if anchor.input_role not in rule.input_roles:
                            raise ValueError("FeatureAnchor input_role not declared by rule")
                        used[anchor.input_role] = scope.series_for(anchor.input_role).manifest
                key = canonical_hash(
                    "jarvis:chart-evaluation:v1",
                    plain(
                        {
                            "manifests": used,
                            "rule": rule,
                            "anchors": group,
                            "providers": provider_identity(scope, rule, group)
                            if self._default
                            else {},
                        }
                    ),
                )
                if key not in self._cache:
                    result_features, result_items = self._evaluators[rule.rule_id](
                        scope, rule, group, key
                    )
                    if any(item.evaluation_key != key for item in result_items):
                        raise ValueError("Evaluator returned a mismatched evaluation_key")
                    self._cache[key] = (
                        MappingProxyType(dict(result_features)),
                        tuple(result_items),
                    )
                result_features, result_items = self._cache[key]
                for feature_key, value in result_features.items():
                    if feature_key in features and features[feature_key] != value:
                        raise ValueError(f"Conflicting feature values for {feature_key}")
                    features[feature_key] = value
                items.extend(result_items)
        analysis = ChartAnalysis(
            analysis_id,
            scope.primary.manifest,
            {role: value.manifest for role, value in scope.related.items()},
            features,
            tuple(sorted(items, key=lambda item: item.id)),
            requested_rules=normalized_rules,
            requested_anchors=normalized_anchors,
        )
        self._analyses[analysis_id] = analysis
        return analysis

    def resolve(self, ref: FactRef) -> ChartItem:
        try:
            analysis = self._analyses[ref.analysis_id]
        except KeyError:
            raise KeyError(f"Unknown chart analysis: {ref.analysis_id}") from None
        for item in analysis.items:
            if item.id == ref.item_id:
                return item
        raise KeyError(f"Unknown chart item: {ref.item_id}")

"""Causal Observation replay. Future labels and portfolio state stay outside Strategy."""

from collections.abc import Sequence
from decimal import Decimal

import pandas as pd

from src.strategies.models import (
    ObservationCode,
    ObservationSourceContext,
    ObservationStatus,
    SignalFinality,
    StrategyObservationEpisode,
    StrategySignal,
)
from src.strategies.observations import make_observation
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.swing_w150.features import SwingFeatureFrame
from src.strategies.swing_w150.support_ladder import number
from src.tools.technical.scorecard_models import Evidence, Importance


def evaluate_observations(
    ticker: str,
    features: SwingFeatureFrame,
    signals: Sequence[StrategySignal],
    setups: Sequence[StrategyObservationEpisode],
    *,
    source_contexts: Sequence[ObservationSourceContext],
    params: ObservationParameters,
    common_analysis=None,
) -> list[StrategyObservationEpisode]:
    """One record per confirmed event/episode; unfinished bars do not commit history."""
    if features.coverage is not None and (
        not features.coverage.complete or features.coverage.truncation_reason
    ):
        return []
    if features.frame.empty:
        return []
    if common_analysis is None:
        from src.strategies.observations.common import observation_analysis

        common_analysis = observation_analysis(ticker, features, source_contexts, params)
    return _common_history(ticker, features, setups, source_contexts, params, common_analysis)


def _common_history(ticker, features, setups, source_contexts, params, analysis):
    from src.strategies.observations.common import (
        ObservationHistory,
        observation_anchors,
        observation_rules,
    )
    from src.strategies.swing_w150.common import (
        feature_scope,
        request_identity,
        validate_analysis,
    )
    from src.tools.technical.chart_analysis.models import FactRef, FactSelection

    rules = {request_identity(rule): rule for rule in observation_rules(params)}
    validate_analysis(analysis, feature_scope(ticker, features), tuple(rules.values()))
    anchors = {anchor.id: anchor for anchor in observation_anchors(features, source_contexts)}
    if not all(anchor in analysis.requested_anchors for anchor in anchors.values()):
        raise ValueError("common_analysis observation anchor inventory mismatch")
    contexts = {context.signal.signal_id: context for context in source_contexts}
    frame = features.frame
    history = list(setups)
    selected = []

    def evidence(code, value, reference):
        return Evidence(
            code=code,
            message=code.replace("_", " ").lower(),
            observed_value=value,
            reference_value=reference,
            importance=Importance.HIGH,
            source="OBSERVATION_V1",
        )

    def number_on(day, column):
        return number(frame.loc[pd.Timestamp(day)], column)

    for item in analysis.items:
        request = rules.get(request_identity(item))
        if request is None:
            selected.append(
                FactSelection(
                    FactRef(analysis.analysis_id, item.id), False, "OBSERVATION_RULE_NOT_USED"
                )
            )
            continue
        if item.state in ("UNAVAILABLE", "NOT_SELECTED"):
            selected.append(
                FactSelection(
                    FactRef(analysis.analysis_id, item.id), False, "OBSERVATION_" + item.state
                )
            )
            continue
        code = request.parameters.get("code")
        context = {}
        if item.rule_id == "chart.anchor.break_reclaim":
            anchor = anchors.get(item.anchor_id)
            if anchor is None:
                selected.append(
                    FactSelection(
                        FactRef(analysis.analysis_id, item.id), False, "OBSERVATION_ANCHOR_NOT_USED"
                    )
                )
                continue
            source = contexts.get(anchor.source_id)
            context = {
                "anchor_id": anchor.id,
                "anchor_type": anchor.kind,
                "anchor_origin_on": anchor.origin_on,
                "anchor_origin_price": Decimal(str(anchor.origin_value)),
                "source_signal_id": anchor.source_id or None,
                "source_terminal": bool(
                    source is not None
                    and source.terminal_on is not None
                    and source.terminal_on <= item.status_as_of
                ),
            }
            # Fixed source Decimal origin remains the original metadata, not float replay.
            if source is not None:
                value = {
                    "PRIOR_BREAKOUT_LEVEL": source.anchors.breakout_level,
                    "PULLBACK_LOW": source.anchors.pullback_low,
                    "ORIGIN_SUPPORT": source.anchors.origin_support,
                }[anchor.kind]
                context["anchor_origin_price"] = value
            if item.state == "RECLAIMED":
                code = (
                    "BREAKOUT_RECLAIM"
                    if anchor.kind == "PRIOR_BREAKOUT_LEVEL"
                    else "SUPPORT_RECLAIM"
                )
                measures = [evidence(code, item.evidence["close"], item.evidence["value"])]
            else:
                code = (
                    "BREAKOUT_LEVEL_BREACH"
                    if anchor.kind == "PRIOR_BREAKOUT_LEVEL"
                    else "PULLBACK_LOW_BREACH"
                    if anchor.kind == "PULLBACK_LOW"
                    else "SUPPORT_BREAK"
                )

                def measured(values, suffix="", code=code):
                    return [
                        evidence(code + suffix, values["close"], values["reference"]),
                        evidence("ANCHOR_VALUE", values["value"], None).model_copy(
                            update={"code": "ANCHOR_VALUE" + suffix}
                        ),
                        evidence("ATR", values["atr"], None).model_copy(
                            update={"code": "ATR" + suffix}
                        ),
                    ]

                measures = measured(item.evidence["origin"])
                if item.evidence["updated"]:
                    measures += measured(item.evidence["current"], "_CURRENT")
        elif code in ("HIGHER_LOW", "HIGHER_HIGH", "LOWER_HIGH", "LOWER_LOW"):
            measures = [
                evidence(code, item.evidence["price"], item.evidence["previous_pivot_price"])
            ]
            context["pivot_date"] = item.evidence["pivot_on"]
        elif code in ("UP_VOLUME_EXPANSION", "DOWN_VOLUME_EXPANSION"):
            ratio, previous, close = (
                number_on(item.occurred_on, c)
                for c in ("Volume_Ratio_Prev20", "Previous_Close", "Close")
            )
            measures = [
                evidence(code, ratio, request.parameters["threshold"]),
                evidence("PRICE_CHANGE", close / previous - 1 if previous else None, None),
                evidence("VOLUME", number_on(item.occurred_on, "Volume"), None),
                evidence("VOLUME_RATIO", ratio, None),
                evidence("REFERENCE_VOLUME", number_on(item.occurred_on, "Vol_SMA_20_Prev"), None),
            ]
        elif item.rule_id == "chart.momentum.reacceleration":
            code = "MOMENTUM_REACCELERATION"
            measures = [evidence(code, number_on(item.occurred_on, "SMA_20_Slope_5"), 0)]
        else:
            code = "VOLUME_CONTRACTION" if code == "VOLUME_CONTRACTION" else "MOMENTUM_DECELERATION"

            def measured(day, suffix="", code=code, request=request):
                if code == "VOLUME_CONTRACTION":
                    return [
                        evidence(
                            code + suffix,
                            number_on(day, "Volume_Contraction_Ratio"),
                            request.parameters["threshold"],
                        )
                    ]
                return [
                    evidence(code + suffix, number_on(day, "Close"), number_on(day, "SMA_20")),
                    evidence("SMA20_SLOPE_5", number_on(day, "SMA_20_Slope_5"), 0).model_copy(
                        update={"code": "SMA20_SLOPE_5" + suffix}
                    ),
                ]

            measures = measured(item.occurred_on)
            if item.status_as_of != item.occurred_on:
                measures += measured(item.status_as_of, "_CURRENT")
        event = item.kind == "EVENT"
        history.append(
            make_observation(
                ticker=ticker,
                code=ObservationCode(code),
                origin=item.occurred_on,
                params=params,
                finality=SignalFinality(item.finality.lower()),
                evidence=measures,
                status=ObservationStatus.RESOLVED
                if event or item.state == "RESOLVED"
                else ObservationStatus.ACTIVE,
                status_as_of=item.status_as_of,
                ended_on=item.status_as_of if event or item.state == "RESOLVED" else None,
                confirmed_on=item.occurred_on if event else None,
                **context,
            )
        )
        selected.append(
            FactSelection(FactRef(analysis.analysis_id, item.id), True, "OBSERVATION_FACT_CONSUMED")
        )
    return ObservationHistory(
        sorted(history, key=lambda item: (item.started_on, item.code, item.observation_id)),
        common_analyses=(analysis,),
        fact_selections=selected,
    )

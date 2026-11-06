"""Compatibility observation/Decimal boundaries use actual common facts."""

from dataclasses import replace
from decimal import Decimal

import pytest

from src.strategies.observations.detectors import evaluate_observations
from src.strategies.observations.parameters import ObservationParameters
from tests.strategies.test_observations import features


def test_sparse_observation_injection_owns_episode_lifecycle(monkeypatch):
    import src.strategies.observations.detectors as detectors
    from src.strategies.observations.common import observation_analysis

    f = features(
        [{"Contraction_Context": True, "Volume_Contraction_Ratio": x} for x in (0.6, 0.6, 0.9, 0.6)]
    )
    params = ObservationParameters(contraction_ratio=0.7)
    expected = [
        item.model_dump(mode="json")
        for item in evaluate_observations("TEST", f, [], [], source_contexts=[], params=params)
    ]
    analysis = observation_analysis("TEST", f, (), params)

    def forbidden(*args, **kwargs):
        raise AssertionError("old observation predicate called")

    monkeypatch.setattr(detectors, "_truth", forbidden, raising=False)
    actual = evaluate_observations(
        "TEST", f, [], [], source_contexts=[], params=params, common_analysis=analysis
    )
    assert [item.model_dump(mode="json") for item in actual] == expected
    assert actual.fact_selections and actual.common_analyses


def test_shadow_decimal_comparison_does_not_round_a_real_breach_to_equality():
    from src.strategies.entry_shadow import evaluate_entry_shadow
    from tests.strategies.test_entry_shadow import _inputs

    opportunity, bundle = _inputs((110, 100))
    anchors = opportunity.anchors.model_copy(
        update={"breakout_level": Decimal("100.000000000000000001")}
    )
    opportunity = opportunity.model_copy(update={"anchors": anchors})
    result = evaluate_entry_shadow(opportunity, bundle)
    assert result.breakout_states["B1"].status == "BREACHED"
    assert result.fact_selections and result.common_analyses


def test_observation_injection_rejects_a_different_anchor_union():
    from src.strategies.observations.common import observation_analysis

    f = features([{"Close": 101, "ATR": 2, "SMA_50": 100}])
    params = ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0)
    analysis = observation_analysis("TEST", f, (), params)
    wrong = replace(analysis, requested_anchors=())
    with pytest.raises(ValueError, match="anchor"):
        evaluate_observations(
            "TEST", f, [], [], source_contexts=[], params=params, common_analysis=wrong
        )


def test_anchor_union_keeps_prior_refs_and_decimal_prices_exact():
    from src.strategies.observations.common import observation_anchors, observation_rules
    from src.strategies.swing_w150.common import frame_scope
    from src.tools.technical.chart_analysis import AnalysisRequestContext
    from src.tools.technical.chart_analysis.models import FactRef, FixedPriceAnchor

    f = features(
        [
            {"Close": close, "ATR": 2, "SMA_50": level}
            for close, level in [(101, 100), (99, 100), (100, 101), (103, 102)]
        ]
    )
    context = AnalysisRequestContext()
    params = ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0)
    scope = frame_scope("TEST", f.frame, finalities=f.finalities)
    anchors = observation_anchors(f, ())
    first = context.get(scope, observation_rules(params), anchors)
    item = next(item for item in first.items if item.anchor_id == "SMA50")
    ref = FactRef(first.analysis_id, item.id)
    extra = FixedPriceAnchor(
        "fixed",
        "FIXED",
        f.frame.index[0].date(),
        f.frame.index[0].date(),
        100,
        100,
        "FINAL",
        "source",
    )
    union = context.get(scope, observation_rules(params), (*anchors, extra))
    assert context.resolve(ref) is item
    assert next(x for x in union.items if x.id == item.id) is item
    assert union.requested_anchors
    with pytest.raises(ValueError, match="Future"):
        context.get(
            scope,
            observation_rules(params),
            (replace(extra, available_on=f.frame.index[-1].date().replace(year=2030)),),
        )


def test_shadow_injected_comparison_changes_policy_without_recomputing_price():
    from src.strategies.entry_shadow import EntryShadowParameters, evaluate_entry_shadow
    from src.strategies.shadow_common import shadow_analysis
    from tests.strategies.test_entry_shadow import _inputs

    opportunity, bundle = _inputs((110, 99))
    params = EntryShadowParameters()
    analysis = shadow_analysis(bundle, opportunity.anchors, params)
    selected = next(x for x in analysis.items if x.anchor_id.endswith(":shadow:breakout"))
    rows = [dict(row) for row in selected.evidence["rows"]]
    rows[-1]["below"] = False
    changed = replace(
        analysis,
        items=tuple(
            replace(x, evidence={"rows": rows}) if x is selected else x for x in analysis.items
        ),
    )
    assert (
        evaluate_entry_shadow(opportunity, bundle, common_analysis=analysis)
        .breakout_states["B1"]
        .status
        == "BREACHED"
    )
    assert (
        evaluate_entry_shadow(opportunity, bundle, common_analysis=changed)
        .breakout_states["B1"]
        .status
        == "CLEAR"
    )


def test_new_moving_anchor_breach_on_preview_is_visible_with_its_first_origin():
    f = features(
        [{"Close": 101, "ATR": 2, "SMA_50": None}, {"Close": 99, "ATR": 2, "SMA_50": 100}],
        provisional=True,
    )
    history = evaluate_observations(
        "TEST",
        f,
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0),
    )
    assert len(history) == 1
    assert history[0].anchor_origin_on == f.frame.index[-1].date()
    assert history[0].anchor_origin_price == Decimal("100")
    assert history[0].finality.value == "provisional"


def test_moving_sma_and_supertrend_inactive_rows_preserve_original_episode_values():
    rows = [
        {"Close": 101, "ATR": 2, "SMA_50": 100, "SuperTrend_Up": 100, "SuperTrend_Dir": 1},
        {"Close": 99, "ATR": 2, "SMA_50": 100, "SuperTrend_Up": 100, "SuperTrend_Dir": 1},
        {"Close": 102, "ATR": 2, "SMA_50": 103, "SuperTrend_Up": None, "SuperTrend_Dir": -1},
        {"Close": 104, "ATR": 2, "SMA_50": 103, "SuperTrend_Up": 103, "SuperTrend_Dir": 1},
        {"Close": 101, "ATR": 2, "SMA_50": 102, "SuperTrend_Up": 102, "SuperTrend_Dir": 1},
    ]
    f = features(rows)
    history = evaluate_observations(
        "TEST",
        f,
        [],
        [],
        source_contexts=[],
        params=ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0),
    )
    for kind in ("SMA50", "SUPERTREND"):
        breaches = [x for x in history if x.anchor_type == kind and x.code == "SUPPORT_BREAK"]
        assert [x.started_on for x in breaches] == [
            f.frame.index[1].date(),
            f.frame.index[4].date(),
        ]
        assert breaches[0].ended_on == f.frame.index[3].date()
        assert breaches[1].anchor_origin_on == f.frame.index[0].date()
        assert breaches[1].anchor_origin_price == Decimal(100)
        assert [(x.code, x.observed_value, x.reference_value) for x in breaches[0].evidence] == [
            ("SUPPORT_BREAK", 99, 100),
            ("ANCHOR_VALUE", 100, None),
            ("ATR", 2, None),
            ("SUPPORT_BREAK_CURRENT", 104, 103),
            ("ANCHOR_VALUE_CURRENT", 103, None),
            ("ATR_CURRENT", 2, None),
        ]

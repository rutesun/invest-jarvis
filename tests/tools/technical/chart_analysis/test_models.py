"""Identity/snapshot regressions: status and new requests must not rewrite old facts."""

from dataclasses import FrozenInstanceError, replace
from datetime import date

import pandas as pd
import pytest

from src.tools.technical.chart_analysis.models import (
    CalculationScope,
    ChartItem,
    FactRef,
    FeatureAnchor,
    FixedPriceAnchor,
    InputManifest,
    RuleRequest,
    SeriesInput,
)
from src.tools.technical.chart_analysis.service import AnalysisRequestContext


def series(values, *, ticker="ABC", origin="provider-a", adjustment="adjusted", **columns):
    index = pd.bdate_range("2026-09-01", periods=len(values))
    frame = pd.DataFrame({"Close": values, **columns}, index=index)
    manifest = InputManifest(
        ticker=ticker,
        exchange="XNYS",
        as_of=index[-1].date(),
        origin=origin,
        input_profile="LEGACY_TEST_V1",
        feature_version="COMPAT_AD880AF_V1",
        input_hash="",
        adjustment_policy=adjustment,
        calendar_version="TEST_CAL_V1",
        finality={day.date(): "FINAL" for day in index},
        coverage={"complete": True, "sessions": list(index.date)},
    )
    return SeriesInput(manifest=manifest, raw=frame)


def anchor(*, fixed=False, **changes):
    values = {
        "id": "sma-3",
        "kind": "SUPPORT",
        "origin_on": date(2026, 9, 3),
        "available_on": date(2026, 9, 3),
        "origin_value": 100.0,
        "source_id": "source-1",
    }
    if fixed:
        return FixedPriceAnchor(**(values | {"value": 100.0, "finality": "FINAL"} | changes))
    return FeatureAnchor(
        **(
            values
            | {
                "input_role": "instrument",
                "feature_key": "SMA_3",
                "feature_version": "SMA_ROLLING_V1",
                "active_when": "ALWAYS",
            }
            | changes
        )
    )


def anchor_rule():
    return RuleRequest(
        "chart.anchor.break_reclaim",
        "OBSERVATION_PARAMS_V1",
        {"break_buffer_atr": 0.0, "reclaim_buffer_atr": 0.0},
        ("instrument",),
        "SESSION_V1",
    )


def rs_rule():
    return RuleRequest(
        "chart.rs",
        "COMPAT_AD880AF_V1",
        {},
        ("instrument", "market"),
        "PLAYBOOK_RS_ALIGNMENT_AD880AF",
    )


def test_item_identity_survives_status_update():
    primary = series([100, 101, 102])
    rule = anchor_rule()
    kwargs = {
        "manifest": primary.manifest,
        "request": rule,
        "kind": "EPISODE",
        "anchor_id": "a",
        "occurred_on": date(2026, 9, 1),
        "confirmed_on": date(2026, 9, 1),
        "status_as_of": date(2026, 9, 2),
        "state": "BREACHED",
        "finality": "FINAL",
        "evaluation_key": "run-a",
        "evidence": {"nested": [{"close": 99.0}]},
    }
    first = ChartItem.create(**kwargs)
    changed = ChartItem.create(
        **(
            kwargs
            | {
                "manifest": series([100, 101, 102, 103]).manifest,
                "status_as_of": date(2026, 9, 4),
                "state": "RECLAIMED",
                "evaluation_key": "run-b",
                "evidence": {"close": 103.0},
            }
        )
    )
    assert first.id == changed.id
    assert ChartItem.create(**(kwargs | {"anchor_id": "b"})).id != first.id
    assert (
        ChartItem.create(
            **(kwargs | {"request": replace(rule, parameters={"break_buffer_atr": 1})})
        ).id
        != first.id
    )
    assert (
        ChartItem.create(
            **(kwargs | {"manifest": replace(primary.manifest, feature_version="v2")})
        ).id
        != first.id
    )
    with pytest.raises(TypeError):
        first.evidence["nested"][0]["close"] = 0
    with pytest.raises(FrozenInstanceError):
        first.state = "MUTATED"


def test_series_input_owns_raw_and_manifest_snapshots():
    value = series([100, 101, 102])
    changed = value.raw
    changed.iloc[0, 0] = 999
    assert value.raw.iloc[0, 0] == 100
    assert value.manifest.input_hash
    with pytest.raises(TypeError):
        value.manifest.coverage["complete"] = False
    with pytest.raises(ValueError, match="input_hash"):
        SeriesInput(replace(value.manifest, input_hash="false-hash"), value.raw)


@pytest.mark.parametrize("caller", ["source", "returned"])
@pytest.mark.parametrize("axis", ["index", "columns"])
def test_raw_axis_backing_mutations_cannot_change_hash_cache_or_independent_result(caller, axis):
    from src.tools.technical.chart_analysis.models import content_hash

    value = series([100 + n for n in range(30)])
    source = value.raw
    owned = SeriesInput(value.manifest, source)
    scope = CalculationScope(owned, {"market": series([100] * 30, ticker="INDEX")})
    context = AnalysisRequestContext()
    before = context.get(scope, (rs_rule(),))
    mutated = source if caller == "source" else owned.raw
    if axis == "index":
        mutated.index.array[0] = pd.Timestamp("2026-08-31")
    else:
        mutated.columns.array[0] = "Mutated"
    assert owned.raw.index[0] == pd.Timestamp("2026-09-01")
    assert tuple(owned.raw.columns) == ("Close",)
    assert content_hash(owned.raw) == owned.manifest.input_hash
    assert context.get(scope, (rs_rule(),)) is before
    independent = AnalysisRequestContext().get(scope, (rs_rule(),))
    assert independent.analysis_id == before.analysis_id
    assert independent.items == before.items


def test_original_caller_aliases_cannot_rewrite_a_returned_fact():
    original = series([100, 100, 100, 97])
    raw = original.raw
    coverage = {"complete": True, "nested": [{"sessions": [date(2026, 9, 1)]}]}
    owned = SeriesInput(replace(original.manifest, coverage=coverage), raw)
    related = {}
    scope = CalculationScope(owned, related)
    context = AnalysisRequestContext()
    analysis = context.get(scope, (anchor_rule(),), (anchor(),))
    ref = FactRef(analysis.analysis_id, analysis.items[0].id)
    before = context.resolve(ref).evidence
    raw.iloc[-1, 0] = 999
    caller_frame = scope.primary.raw
    caller_frame.iloc[-1, 0] = 999
    coverage["nested"][0]["sessions"].append(date(2026, 9, 2))
    related["market"] = series([1, 2, 3])
    assert not scope.related
    assert analysis.manifest.coverage["nested"][0]["sessions"] == (date(2026, 9, 1),)
    assert context.resolve(ref).evidence == before
    assert context.get(scope, (anchor_rule(),), (anchor(),)) is analysis
    evidence = {"nested": [{"value": 1}]}
    item = replace(analysis.items[0], evidence=evidence)
    evidence["nested"][0]["value"] = 999
    assert item.evidence["nested"][0]["value"] == 1


def test_series_input_rejects_future_and_ambiguous_session_rows():
    value = series([100, 101, 102])
    with pytest.raises(ValueError, match="as_of"):
        SeriesInput(replace(value.manifest, as_of=date(2026, 9, 1), input_hash=""), value.raw)
    frame = value.raw.iloc[::-1]
    with pytest.raises(ValueError, match="ascending"):
        SeriesInput(replace(value.manifest, input_hash=""), frame)


def test_market_only_change_invalidates_rs_cache():
    primary = series([100 + n for n in range(30)])
    first_market = series([100] * 30, ticker="INDEX")
    next_market = series([100 + 2 * n for n in range(30)], ticker="INDEX")
    context = AnalysisRequestContext()
    first = context.get(CalculationScope(primary, {"market": first_market}), (rs_rule(),))
    second_scope = CalculationScope(primary, {"market": next_market})
    second = context.get(second_scope, (rs_rule(),))
    independent = AnalysisRequestContext().get(second_scope, (rs_rule(),))
    assert first.analysis_id != second.analysis_id
    assert first.items[0].evaluation_key != second.items[0].evaluation_key
    assert first.items[0].evidence["mansfield_rs"] == 12.66
    assert second.items[0].evidence["mansfield_rs"] == -8.76
    assert second.items == independent.items
    assert first.items[0].id == second.items[0].id


def test_same_item_distinct_scope_refs():
    context = AnalysisRequestContext()
    analyses = []
    for origin, adjustment, market in (
        ("a", "adjusted", [100] * 30),
        ("b", "raw", [100 + n for n in range(30)]),
    ):
        scope = CalculationScope(
            series([100 + n for n in range(30)], origin=origin, adjustment=adjustment),
            {"market": series(market, ticker="INDEX")},
        )
        analyses.append(context.get(scope, (rs_rule(),)))
    a, b = analyses
    assert a.items[0].id == b.items[0].id
    refs = [FactRef(value.analysis_id, value.items[0].id) for value in analyses]
    assert refs[0] != refs[1]
    assert context.resolve(refs[0]).evidence["mansfield_rs"] == 12.66
    assert context.resolve(refs[1]).evidence["mansfield_rs"] == 0.0
    with pytest.raises(KeyError, match="analysis"):
        context.resolve(FactRef("absent", a.items[0].id))
    with pytest.raises(KeyError, match="item"):
        context.resolve(FactRef(a.analysis_id, "absent"))


def test_anchor_union_preserves_existing_refs():
    scope = CalculationScope(series([100, 100, 100, 97, 99, 100]), {})
    context = AnalysisRequestContext()
    first = context.get(scope, (anchor_rule(),), (anchor(),))
    old_ref = FactRef(first.analysis_id, first.items[0].id)
    old_evidence = context.resolve(old_ref).evidence
    expanded = context.get(scope, (anchor_rule(),), (anchor(), anchor(fixed=True, id="fixed")))
    assert first.analysis_id != expanded.analysis_id
    assert len(first.items) == 1 and len(expanded.items) == 2
    assert context.resolve(old_ref).evidence == old_evidence
    same = next(item for item in expanded.items if item.anchor_id == "sma-3")
    assert same is first.items[0]  # Unrelated anchor did not invalidate this evaluation.
    assert (
        context.get(
            scope, (anchor_rule(),), tuple(reversed((anchor(), anchor(fixed=True, id="fixed"))))
        ).analysis_id
        == expanded.analysis_id
    )
    with pytest.raises(TypeError):
        context.analyses["overwrite"] = expanded
    with pytest.raises(TypeError):
        expanded.features["overwrite"] = None


def test_moving_anchor_breach_equal_reclaim():
    # SMA3: 100, 99, 98.5, 98.5. Day 5 equals its moving baseline.
    context = AnalysisRequestContext()
    outputs = []
    for values in ([100, 100, 100, 97], [100, 100, 100, 97, 98.5], [100, 100, 100, 97, 98.5, 100]):
        outputs.append(
            context.get(CalculationScope(series(values), {}), (anchor_rule(),), (anchor(),))
        )
    assert [result.items[0].state for result in outputs] == ["BREACHED", "BREACHED", "RECLAIMED"]
    assert len({result.items[0].id for result in outputs}) == 1
    assert [result.items[0].evidence["origin_price"] for result in outputs] == [100.0] * 3
    assert [result.items[0].evidence["current_value"] for result in outputs] == [99.0, 98.5, 98.5]
    fixed = context.get(
        CalculationScope(series([100, 100, 100, 97, 98.5, 100]), {}),
        (anchor_rule(),),
        (anchor(fixed=True),),
    )
    assert fixed.items[0].state == "BREACHED"  # Equal to fixed 100 never reclaims.
    assert fixed.items[0].evidence["current_value"] == 100.0


def test_missing_or_inactive_anchor_preserves_breach_and_origin():
    moving = anchor(
        feature_key="Support", feature_version="COMPAT_AD880AF_V1", active_when="SUPERTREND_UP"
    )
    primary = series(
        [100, 100, 100, 97, 110, 100, 110],
        Support=[100, 100, 100, 100, 100, float("nan"), 105],
        SuperTrend_Dir=[1, 1, 1, 1, -1, 1, 1],
    )
    context = AnalysisRequestContext()
    result = context.get(CalculationScope(primary, {}), (anchor_rule(),), (moving,))
    item = result.items[0]
    assert item.state == "RECLAIMED"
    assert item.evidence["origin_price"] == 100.0
    assert item.evidence["transitions"] == (
        {"on": date(2026, 9, 4), "state": "BREACHED", "value": 100.0},
        {"on": date(2026, 9, 9), "state": "RECLAIMED", "value": 105.0},
    )


def test_rule_dependency_keys_remain_independent_when_rule_set_or_market_changes():
    primary = series([100] * 26 + [97, 98.5, 100, 101])
    market = series([100] * 30, ticker="INDEX")
    context = AnalysisRequestContext()
    first_scope = CalculationScope(primary, {"market": market})
    first = context.get(first_scope, (anchor_rule(),), (anchor(),))
    union = context.get(first_scope, (anchor_rule(), rs_rule()), (anchor(),))
    reversed_union = context.get(first_scope, (rs_rule(), anchor_rule()), (anchor(),))
    anchor_item = next(item for item in union.items if item.anchor_id)
    assert first.items[0] is anchor_item
    assert union is reversed_union
    changed_scope = CalculationScope(
        primary, {"market": series([100 + n for n in range(30)], ticker="INDEX")}
    )
    changed = context.get(changed_scope, (rs_rule(), anchor_rule()), (anchor(),))
    assert next(item for item in changed.items if item.anchor_id) is anchor_item
    assert (
        next(item for item in union.items if not item.anchor_id).evaluation_key
        != next(item for item in changed.items if not item.anchor_id).evaluation_key
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("origin", "other-provider"),
        ("adjustment_policy", "unadjusted"),
        ("calendar_version", "OTHER_CAL"),
        ("finality", "PROVISIONAL"),
        ("coverage", {"complete": False}),
        ("feature_version", "OTHER_FEATURES"),
    ],
)
def test_every_actual_manifest_dependency_invalidates_analysis_and_evaluation(field, value):
    original = series([100 + n for n in range(30)])
    market = series([100] * 30, ticker="INDEX")
    context = AnalysisRequestContext()
    first = context.get(CalculationScope(original, {"market": market}), (rs_rule(),))
    changed = SeriesInput(replace(original.manifest, **{field: value}), original.raw)
    second = context.get(CalculationScope(changed, {"market": market}), (rs_rule(),))
    assert first.analysis_id != second.analysis_id
    assert first.items[0].evaluation_key != second.items[0].evaluation_key


def test_feature_anchor_rejects_wrong_feature_version_and_undeclared_role():
    scope = CalculationScope(series([100, 100, 100, 97]), {"market": series([100] * 4)})
    with pytest.raises(ValueError, match="feature_version"):
        AnalysisRequestContext().get(scope, (anchor_rule(),), (anchor(feature_version="UNKNOWN"),))
    with pytest.raises(ValueError, match="input_role"):
        AnalysisRequestContext().get(scope, (anchor_rule(),), (anchor(input_role="market"),))


def test_anchor_finality_uses_current_feature_and_close_inputs():
    original = series([100, 100, 100, 97])
    finality = dict(original.manifest.finality) | {original.manifest.as_of: "PROVISIONAL"}
    primary = SeriesInput(replace(original.manifest, finality=finality), original.raw)
    scope = CalculationScope(primary, {})
    for selected in (anchor(), anchor(fixed=True)):
        analysis = AnalysisRequestContext().get(scope, (anchor_rule(),), (selected,))
        assert analysis.items[0].finality == "PROVISIONAL"
    future = anchor(available_on=date(2026, 10, 1))
    with pytest.raises(ValueError, match="anchor"):
        AnalysisRequestContext().get(scope, (anchor_rule(),), (future,))


@pytest.mark.parametrize("fixed", [True, False])
@pytest.mark.parametrize("field", ["origin_on", "available_on"])
def test_context_rejects_future_anchor_before_calculation_or_registration(fixed, field):
    def unexpected_evaluator(*args):
        pytest.fail("Future anchor reached evaluator")

    scope = CalculationScope(series([100, 100, 100, 97]), {})
    context = AnalysisRequestContext({anchor_rule().rule_id: unexpected_evaluator})
    selected = anchor(fixed=fixed, **{field: date(2026, 10, 1)})
    with pytest.raises(ValueError, match="anchor"):
        context.get(scope, (anchor_rule(),), (selected,))
    assert not context.analyses
    assert not context._cache


def test_available_anchor_and_empty_anchor_set_remain_valid_requests():
    scope = CalculationScope(series([100, 100, 100, 97]), {})
    context = AnalysisRequestContext()
    assert context.get(scope, (anchor_rule(),), ()).items == ()
    assert context.get(scope, (anchor_rule(),), (anchor(fixed=True),)).items[0].state == "BREACHED"


@pytest.mark.parametrize("future_raw", [False, True])
def test_context_rejects_related_manifest_or_raw_after_primary_evaluation(future_raw):
    primary = series([100 + n for n in range(30)])
    market = series([100] * (31 if future_raw else 30), ticker="INDEX")
    if not future_raw:
        market = SeriesInput(replace(market.manifest, as_of=date(2026, 10, 13)), market.raw)
    context = AnalysisRequestContext()
    scope = CalculationScope(primary, {"market": market})
    with pytest.raises(ValueError, match="related.*as_of"):
        context.get(scope, (rs_rule(),))
    assert not context.analyses and not context._cache


@pytest.mark.parametrize("used_finality", ["PROVISIONAL", "UNKNOWN"])
def test_rs_finality_comes_from_actual_aligned_inputs_not_manifest_endpoint(used_finality):
    primary = series([100 + n for n in range(30)])
    market = series([100] * 29 + [float("nan")], ticker="INDEX")
    used_day = market.raw.index[-2].date()
    statuses = dict(market.manifest.finality) | {used_day: used_finality}
    market = SeriesInput(replace(market.manifest, finality=statuses), market.raw)
    item = (
        AnalysisRequestContext()
        .get(CalculationScope(primary, {"market": market}), (rs_rule(),))
        .items[0]
    )
    assert item.finality == used_finality
    assert item.evidence["evaluated_on"] == used_day


def input_finalities(value, statuses):
    finality = dict(zip(value.raw.index.date, statuses, strict=True))
    return SeriesInput(replace(value.manifest, finality=finality), value.raw)


def early_anchor(*, fixed):
    changes = {"origin_on": date(2026, 9, 1), "available_on": date(2026, 9, 1)}
    if not fixed:
        changes |= {"feature_key": "Support", "feature_version": "COMPAT_AD880AF_V1"}
    return anchor(fixed=fixed, **changes)


@pytest.mark.parametrize("fixed", [True, False])
@pytest.mark.parametrize("middle", ["PROVISIONAL", "UNKNOWN"])
@pytest.mark.parametrize(
    "values,final_state", [([100, 97, 100], "CLEAR"), ([97, 103, 100], "BREACHED")]
)
def test_middle_nonfinal_anchor_transition_cannot_publish_or_repair_final_state(
    fixed, middle, values, final_state
):
    primary = input_finalities(series(values, Support=[100] * 3), ["FINAL", middle, "FINAL"])
    analysis = AnalysisRequestContext().get(
        CalculationScope(primary, {}), (anchor_rule(),), (early_anchor(fixed=fixed),)
    )
    item = analysis.items[0]
    assert item.state == "INCOMPLETE_PREFIX" and item.finality == "UNKNOWN"
    assert item.evidence["final_state"] == final_state
    assert item.evidence["final_as_of"] == date(2026, 9, 1)
    assert item.evidence["incomplete_on"] == date(2026, 9, 2)
    assert item.evidence["preview_state"] is None
    assert all(event["on"] == date(2026, 9, 1) for event in item.evidence["final_transitions"])
    assert item.occurred_on != date(2026, 9, 2)
    assert item.evidence["current_value"] is None


@pytest.mark.parametrize("fixed", [True, False])
@pytest.mark.parametrize(
    "values,final_state,preview_state",
    [
        ([100, 100, 97], "CLEAR", "BREACHED"),
        ([100, 97, 103], "BREACHED", "RECLAIMED"),
        ([100, 97, 100], "BREACHED", "BREACHED"),
    ],
)
def test_trailing_preview_is_separate_from_final_seed_and_revised_final_scope(
    fixed, values, final_state, preview_state
):
    selected = early_anchor(fixed=fixed)
    preview_input = input_finalities(
        series(values, Support=[100] * 3), ["FINAL", "FINAL", "PROVISIONAL"]
    )
    context = AnalysisRequestContext()
    preview = context.get(CalculationScope(preview_input, {}), (anchor_rule(),), (selected,))
    item = preview.items[0]
    ref = FactRef(preview.analysis_id, item.id)
    assert item.state == preview_state and item.finality == "PROVISIONAL"
    assert item.evidence["final_state"] == final_state
    assert item.evidence["preview_state"] == preview_state
    assert all(event["on"] < date(2026, 9, 3) for event in item.evidence["final_transitions"])
    assert all(event["on"] == date(2026, 9, 3) for event in item.evidence["preview_transitions"])
    revised = series([values[0], values[1], 100], Support=[100] * 3)
    final_scope = CalculationScope(revised, {})
    final = context.get(final_scope, (anchor_rule(),), (selected,))
    independent = AnalysisRequestContext().get(final_scope, (anchor_rule(),), (selected,))
    assert final.analysis_id != preview.analysis_id
    assert final.items == independent.items
    if final_state == "CLEAR":
        assert final.items == ()
    else:
        assert final.items[0].state == "BREACHED" and final.items[0].finality == "FINAL"
        assert final.items[0].evidence["preview_state"] is None
    assert context.resolve(ref) is item
    assert context.resolve(ref).evidence["preview_state"] == preview_state


@pytest.mark.parametrize("middle", ["PROVISIONAL", "UNKNOWN"])
@pytest.mark.parametrize("unconfirmed_position", [1, 3])
def test_sma_window_cannot_use_nonfinal_seed_or_resume_after_incomplete_prefix(
    middle, unconfirmed_position
):
    primary = series([100, 100, 100, 40, 70])
    statuses = ["FINAL"] * 5
    statuses[unconfirmed_position] = middle
    primary = input_finalities(primary, statuses)
    item = (
        AnalysisRequestContext()
        .get(CalculationScope(primary, {}), (anchor_rule(),), (anchor(),))
        .items[0]
    )
    assert item.state == "INCOMPLETE_PREFIX" and item.finality == "UNKNOWN"
    assert item.evidence["final_state"] == "CLEAR"
    assert item.evidence["final_transitions"] == ()
    assert item.evidence["current_value"] is None


@pytest.mark.parametrize("fixed", [True, False])
def test_unknown_trailing_input_is_incomplete_and_never_a_preview(fixed):
    primary = input_finalities(
        series([100, 97, 103], Support=[100] * 3), ["FINAL", "FINAL", "UNKNOWN"]
    )
    item = (
        AnalysisRequestContext()
        .get(CalculationScope(primary, {}), (anchor_rule(),), (early_anchor(fixed=fixed),))
        .items[0]
    )
    assert item.state == "INCOMPLETE_PREFIX" and item.finality == "UNKNOWN"
    assert item.evidence["final_state"] == "BREACHED"
    assert item.evidence["preview_state"] is None


@pytest.mark.parametrize("seed_finality", ["PROVISIONAL", "UNKNOWN"])
def test_related_sma_seed_before_primary_start_closes_final_prefix(seed_finality):
    initial = series([100] * 4)
    primary = SeriesInput(replace(initial.manifest, input_hash=""), initial.raw.iloc[2:])
    market = series([100, 1000, 100, 100], ticker="INDEX")
    selected = anchor(id="sma3", origin_value=400.0, input_role="market", source_id="source")
    request = replace(anchor_rule(), input_roles=("instrument", "market"))
    context = AnalysisRequestContext()
    original = context.get(CalculationScope(primary, {"market": market}), (request,), (selected,))
    original_ref = FactRef(original.analysis_id, original.items[0].id)
    market = input_finalities(market, ["FINAL", seed_finality, "FINAL", "FINAL"])
    changed_scope = CalculationScope(primary, {"market": market})
    changed = context.get(changed_scope, (request,), (selected,))
    item = changed.items[0]
    assert item.state == "INCOMPLETE_PREFIX" and item.finality == "UNKNOWN"
    assert item.evidence["final_state"] == "CLEAR"
    assert item.evidence["final_transitions"] == ()
    assert item.evidence["incomplete_on"] == date(2026, 9, 2)
    assert item.evidence["current_value"] is None
    assert item.evidence["preview_state"] is None
    assert context.resolve(original_ref).state == "BREACHED"
    assert context.resolve(original_ref).evidence["current_value"] == 400.0
    unrelated = context.get(
        CalculationScope(primary, {"market": market, "unused": initial}), (request,), (selected,)
    )
    assert unrelated.items[0] is item
    assert (
        AnalysisRequestContext().get(changed_scope, (request,), (selected,)).items == changed.items
    )


def test_fixed_source_finality_applies_only_after_anchor_becomes_available():
    primary = input_finalities(series([100, 100, 97]), ["FINAL", "FINAL", "PROVISIONAL"])
    selected = anchor(fixed=True, id="new", finality="PROVISIONAL", source_id="source")
    item = (
        AnalysisRequestContext()
        .get(CalculationScope(primary, {}), (anchor_rule(),), (selected,))
        .items[0]
    )
    assert item.state == "BREACHED" and item.finality == "PROVISIONAL"
    assert item.confirmed_on is None
    assert item.evidence["final_state"] == "CLEAR"
    assert item.evidence["final_as_of"] == date(2026, 9, 2)
    assert item.evidence["final_transitions"] == ()
    assert item.evidence["preview_state"] == "BREACHED"
    assert item.evidence["preview_transitions"] == (
        {"on": date(2026, 9, 3), "state": "BREACHED", "value": 100.0},
    )
    assert item.evidence["incomplete_on"] is None


def test_request_order_irrelevant_and_rule_cache_excludes_unrelated_roles():
    primary = series([100, 100, 100, 97, 98.5, 100])
    context = AnalysisRequestContext()
    first = context.get(CalculationScope(primary, {}), (anchor_rule(),), (anchor(),))
    second = context.get(
        CalculationScope(primary, {"unused": series([1, 2, 3])}), (anchor_rule(),), (anchor(),)
    )
    assert first.analysis_id != second.analysis_id
    assert first.items[0] is second.items[0]
    with pytest.raises(NotImplementedError):
        context.get(
            CalculationScope(primary, {}),
            (RuleRequest("missing", "v1", {}, ("instrument",), "v1"),),
        )


def test_existing_result_metadata_is_optional_and_excluded_from_legacy_serialization():
    from src.strategies.models import StrategySignalBundle, StrategyVerdict
    from src.tools.technical.chart_analysis.models import FactSelection
    from src.tools.technical.models import TechnicalResult

    for model in (StrategySignalBundle, StrategyVerdict, TechnicalResult):
        old = model.model_construct()
        attached = model.model_construct(
            chart_analysis_id="analysis-1",
            fact_selections=(FactSelection(FactRef("analysis-1", "item-1"), True, "SELECTED"),),
        )
        assert attached.chart_analysis_id == "analysis-1"
        assert old.model_dump() == attached.model_dump()

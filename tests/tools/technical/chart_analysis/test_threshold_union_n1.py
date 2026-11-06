"""A legal request union must select and audit the consumer's exact variant."""

import pytest

from src.strategies.playbook import PlaybookStrategy, _fact_selections
from src.tools.playbook.common import chart_frame, playbook_rule_requests, playbook_scope
from src.tools.playbook.vcp import detect_vcp_breakout
from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.models import FactRef
from src.tools.technical.chart_analysis.registry import rule_request
from src.tools.technical.components.patterns import PatternThresholds, analyze_patterns
from src.tools.technical.context import common_analysis_for_frame, compatibility_rule_request
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import (
    TechnicalScorer,
    _legacy_fact_selection,
    technical_rule_requests,
)
from src.tools.technical.shadow_v2 import shadow_fact_selections
from tests.harness.chart_analysis_contract import baseline_payload
from tests.strategies.test_playbook import _bundle
from tests.tools.technical.chart_analysis.test_playbook_facts import vcp_frame as playbook_frame
from tests.tools.technical.chart_analysis.test_threshold_tuning_fix import vcp_frame


def technical_union(monkeypatch, tuned, reverse):
    frame = vcp_frame()
    context = AnalysisRequestContext()
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.2)
    defaults = technical_rule_requests()
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.5)
    customized = technical_rule_requests()
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.5 if tuned else 0.2)
    single = common_analysis_for_frame(
        frame, ticker="TEST", context=context, rules=customized if tuned else defaults
    )
    old = next(item for item in single.items if item.rule_id == "chart.vcp.legacy")
    ref = FactRef(single.analysis_id, old.id)
    requests = (*defaults, *customized)
    if reverse:
        requests = tuple(reversed(requests))
    union = common_analysis_for_frame(frame, ticker="TEST", context=context, rules=requests)
    assert (
        common_analysis_for_frame(
            frame, ticker="TEST", context=context, rules=tuple(reversed(requests))
        )
        is union
    )
    assert context.resolve(ref) == old
    return frame, single, union


@pytest.mark.parametrize("tuned", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("consumer", ["patterns", "scorer"])
def test_technical_union_preserves_exact_single_variant_payload(
    monkeypatch, tuned, reverse, consumer
):
    frame, single, union = technical_union(monkeypatch, tuned, reverse)
    if consumer == "patterns":
        expected = analyze_patterns(frame, common_analysis=single)
        actual = analyze_patterns(frame, common_analysis=union)
        assert actual.model_dump() == expected.model_dump()
        assert actual.score == (0 if tuned else 20)
    else:
        scorer = TechnicalScorer()
        expected = scorer.score(frame, ticker="TEST", include_history=False, common_analysis=single)
        actual = scorer.score(frame, ticker="TEST", include_history=False, common_analysis=union)
        assert baseline_payload(actual, consumer="N1") == baseline_payload(expected, consumer="N1")
        assert_variant_audit(actual.fact_selections, union, "chart.vcp.legacy", "LEGACY")
        assert_variant_audit(actual.fact_selections, union, "chart.vcp.legacy", "APRIME")


def assert_variant_audit(selections, analysis, family, consumer):
    expected = compatibility_rule_request(family)
    by_id = {item.id: item for item in analysis.items}
    relevant = [
        s
        for s in selections
        if s.reason_code.startswith(consumer + "_") and by_id[s.ref.item_id].rule_id == family
    ]
    assert len(relevant) == 2
    for selection in relevant:
        item = by_id[selection.ref.item_id]
        assert selection.ref == FactRef(analysis.analysis_id, item.id)
        matches = (
            item.rule_version == expected.rule_version
            and item.parameter_id == expected.parameter_id
        )
        assert selection.selected == matches
        assert selection.reason_code == (
            consumer + "_CONSUMED" if matches else consumer + "_FACT_VARIANT_NOT_SELECTED"
        )


@pytest.mark.parametrize("tuned", [False, True])
@pytest.mark.parametrize("consumer", ["LEGACY", "APRIME"])
def test_technical_audit_never_claims_other_variant_was_consumed(monkeypatch, tuned, consumer):
    frame, _, union = technical_union(monkeypatch, tuned, False)
    if consumer == "LEGACY":
        selections = tuple(
            _legacy_fact_selection(union, item, frame, {"patterns": {}})
            for item in union.items
            if item.rule_id == "chart.vcp.legacy"
        )
    else:
        selections = shadow_fact_selections(union, {})
    assert_variant_audit(selections, union, "chart.vcp.legacy", consumer)


@pytest.mark.parametrize("tuned", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_playbook_helper_union_preserves_payload_refs_and_audit(monkeypatch, tuned, reverse):
    frame = playbook_frame()
    context = AnalysisRequestContext()
    requests = (
        rule_request("chart.vcp.playbook"),
        rule_request("chart.vcp.playbook", {"pattern_thresholds": {"VCP_ATR_CONTRACTION": 0.5}}),
    )
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.5 if tuned else 0.2)
    single = common_analysis_for_frame(frame, context=context, rules=(requests[int(tuned)],))
    old = single.items[0]
    ref = FactRef(single.analysis_id, old.id)
    union = common_analysis_for_frame(
        frame, context=context, rules=tuple(reversed(requests)) if reverse else requests
    )
    assert (
        common_analysis_for_frame(frame, context=context, rules=tuple(reversed(requests))) is union
    )
    assert context.resolve(ref) == old
    expected = detect_vcp_breakout(frame, common_analysis=single)
    actual = detect_vcp_breakout(frame, common_analysis=union)
    assert actual == expected
    assert actual.in_vcp is (not tuned)
    selections = _fact_selections(union, {"chart.vcp.playbook": "PLAYBOOK_CONSUMED"}, {}, "UNUSED")
    assert_variant_audit(selections, union, "chart.vcp.playbook", "PLAYBOOK")


@pytest.mark.parametrize("tuned", [False, True])
def test_playbook_audit_never_claims_other_variant_was_consumed(monkeypatch, tuned):
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.5 if tuned else 0.2)
    requests = (
        rule_request("chart.vcp.playbook"),
        rule_request("chart.vcp.playbook", {"pattern_thresholds": {"VCP_ATR_CONTRACTION": 0.5}}),
    )
    union = common_analysis_for_frame(playbook_frame(), rules=requests)
    selections = _fact_selections(union, {"chart.vcp.playbook": "PLAYBOOK_CONSUMED"}, {}, "UNUSED")
    assert_variant_audit(selections, union, "chart.vcp.playbook", "PLAYBOOK")


@pytest.mark.parametrize("tuned", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_playbook_strategy_union_preserves_payload_and_original_gate_audit(
    monkeypatch, tuned, reverse
):
    bundle = _bundle()
    stock = IndicatorCalculator().calculate(chart_frame(bundle.instrument))
    context = AnalysisRequestContext()
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.2)
    defaults = playbook_rule_requests(bundle)
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.5)
    customized = playbook_rule_requests(bundle)
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.5 if tuned else 0.2)
    scope = playbook_scope(bundle, stock)
    single = context.get(scope, customized if tuned else defaults)
    old_refs = tuple(FactRef(single.analysis_id, item.id) for item in single.items)
    requests = (*defaults, *customized)
    union = context.get(scope, tuple(reversed(requests)) if reverse else requests)
    assert context.get(scope, tuple(reversed(requests))) is union
    assert tuple(context.resolve(ref) for ref in old_refs) == single.items
    strategy = PlaybookStrategy()
    expected = strategy.evaluate(bundle, common_analysis=single)
    actual = strategy.evaluate(bundle, common_analysis=union)
    assert actual.model_dump() == expected.model_dump()
    expected_item = next(item for item in single.items if item.rule_id == "chart.vcp.playbook")
    expected_selection = next(
        s for s in expected.fact_selections if s.ref.item_id == expected_item.id
    )
    by_id = {item.id: item for item in union.items}
    for selection in actual.fact_selections:
        item = by_id[selection.ref.item_id]
        if item.rule_id != "chart.vcp.playbook":
            continue
        if item.id == expected_item.id:
            assert (selection.selected, selection.reason_code) == (
                expected_selection.selected,
                expected_selection.reason_code,
            )
        else:
            assert selection.selected is False
            assert selection.reason_code == "PLAYBOOK_FACT_VARIANT_NOT_SELECTED"


@pytest.mark.parametrize("consumer", ["patterns", "scorer", "playbook"])
def test_other_variant_cannot_substitute_for_missing_expected_request(monkeypatch, consumer):
    monkeypatch.setattr(PatternThresholds, "VCP_ATR_CONTRACTION", 0.5)
    if consumer == "playbook":
        frame = playbook_frame()
        analysis = common_analysis_for_frame(frame, rules=(rule_request("chart.vcp.playbook"),))
        with pytest.raises(ValueError, match="contract"):
            detect_vcp_breakout(frame, common_analysis=analysis)
    else:
        frame = vcp_frame()
        # All other current requests remain present; only the VCP exact request is absent.
        requests = tuple(
            rule_request("chart.vcp.legacy") if r.rule_id == "chart.vcp.legacy" else r
            for r in technical_rule_requests()
        )
        analysis = common_analysis_for_frame(frame, ticker="TEST", rules=requests)
        with pytest.raises(ValueError, match="contract"):
            if consumer == "patterns":
                analyze_patterns(frame, common_analysis=analysis)
            else:
                TechnicalScorer().score(
                    frame, ticker="TEST", include_history=False, common_analysis=analysis
                )

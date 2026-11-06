"""Resolve all request-local refs and keep legacy recording and verdicts intact."""

import importlib
import json
from dataclasses import replace

import pytest

from src.tools.technical.chart_analysis.models import (
    FactRef,
    FactSelection,
    FixedPriceAnchor,
)
from src.tools.technical.chart_analysis.registry import rule_request
from src.tools.technical.chart_analysis.service import AnalysisRequestContext
from tests.tools.technical.chart_analysis.test_features import bars, scope_for


def display_rows(analyses, selections):
    api = importlib.import_module("src.pipelines.chart_analysis")
    assert hasattr(api, "selected_fact_rows"), "display fact merge missing"
    return api.selected_fact_rows(analyses, selections)


def anchor_analysis(*, atr=2, extra=False):
    frame = bars([100.0] * 25 + [90.0, 103.0])
    frame["ATR"] = atr
    scope = scope_for(frame, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    day = frame.index[0].date()
    anchor = FixedPriceAnchor("a", "test", day, day, 100, 100, "FINAL", "source")
    anchors = (anchor, replace(anchor, id="b", source_id="other")) if extra else (anchor,)
    return AnalysisRequestContext().get(
        scope,
        (
            rule_request(
                "chart.anchor.break_reclaim", {"break_buffer_atr": 1.0, "reclaim_buffer_atr": 1.0}
            ),
        ),
        anchors,
    )


def test_union_scope_display_merges_only_rows_and_preserves_all_refs_reasons():
    first, union = anchor_analysis(), anchor_analysis(extra=True)
    first_item = first.items[0]
    union_item = next(item for item in union.items if item.id == first_item.id)
    assert first.analysis_id != union.analysis_id
    assert first_item.evaluation_key == union_item.evaluation_key
    selections = (
        FactSelection(FactRef(first.analysis_id, first_item.id), True, "FIRST"),
        FactSelection(FactRef(union.analysis_id, union_item.id), True, "SECOND"),
    )
    rows = display_rows({a.analysis_id: a for a in (first, union)}, selections)
    assert len(rows) == 1
    assert rows[0].refs == tuple(selection.ref for selection in selections)
    assert rows[0].selections == selections


def test_distinct_scope_evidence_not_deduplicated():
    first, second = anchor_analysis(atr=2), anchor_analysis(atr=4)
    a = first.items[0]
    b = next(item for item in second.items if item.id == a.id)
    selections = tuple(
        FactSelection(FactRef(analysis.analysis_id, item.id), True, "USED")
        for analysis, item in ((first, a), (second, b))
    )
    rows = display_rows({x.analysis_id: x for x in (first, second)}, selections)
    assert len(rows) == 2
    assert a.evaluation_key != b.evaluation_key
    assert a.evidence != b.evidence


def test_display_deduplicates_same_ref_retains_each_selection_and_rejects_unresolved():
    analysis = anchor_analysis()
    item = analysis.items[0]
    ref = FactRef(analysis.analysis_id, item.id)
    selections = (
        FactSelection(ref, True, "A"),
        FactSelection(ref, True, "B"),
        FactSelection(ref, False, "REJECTED"),
    )
    rows = display_rows({analysis.analysis_id: analysis}, selections)
    assert len(rows) == 1 and rows[0].refs == (ref,)
    assert rows[0].selections == selections
    with pytest.raises(KeyError):
        display_rows({}, selections)


def test_runner_retains_every_referenced_analysis_and_legacy_serialization():
    from src.strategies.runner import StrategyRunner
    from tests.strategies.test_playbook import _bundle
    from tests.strategies.test_runner import _legacy_result

    run = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    assert hasattr(run, "common_analyses"), "request result bundle missing"
    assert run.common_analyses
    assert "common_analyses" not in run.model_dump()
    from dataclasses import asdict

    from src.pipelines.strategy_analysis import AnalysisStrategyResult

    result = AnalysisStrategyResult(run.scorecard, run, (), 100)
    original = dict(run.common_analyses)
    assert result.common_analyses == original
    result.common_analyses.clear()
    assert run.common_analyses == original
    assert "common_analyses" not in asdict(result)
    for consumer in [*run.verdicts, *run.signal_bundles]:
        for selection in consumer.fact_selections or ():
            analysis = run.common_analyses[selection.ref.analysis_id]
            assert any(item.id == selection.ref.item_id for item in analysis.items)


@pytest.mark.asyncio
async def test_quality_null_does_not_change_existing_verdict():
    from src.pipelines.chart_analysis import ChartAnalysisService
    from src.strategies.runner import StrategyRunner
    from tests.strategies.test_playbook import _bundle
    from tests.strategies.test_runner import _legacy_result
    from tests.tools.technical.chart_analysis.test_history import BusinessCalendar, raw_history

    raw = raw_history()
    raw = replace(raw, finality={})
    day = raw.frame.index[-1].date()
    before = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    result = (
        await ChartAnalysisService(calendar=BusinessCalendar()).analyze(
            "TEST", sessions=(day,), raw=raw
        )
    )[0]
    after = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    assert result.quality.quality is None
    assert before.model_dump() == after.model_dump()


def test_recorder_payload_unchanged(tmp_path):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder
    from src.strategies.runner import StrategyRunner
    from tests.strategies.test_playbook import _bundle
    from tests.strategies.test_runner import _legacy_result

    bundle = _bundle()
    run = StrategyRunner().run(bundle, legacy_result=_legacy_result())
    assert hasattr(run, "common_analyses"), "request result bundle missing"
    recorder = EntryShadowJsonlRecorder(tmp_path / "snapshots.jsonl")
    recorder.record(run, bundle, pipeline="check")
    recorder.record(run.model_copy(update={"common_analyses": {}}), bundle, pipeline="check")
    rows = [json.loads(line) for line in recorder.path.read_text().splitlines()]
    for row in rows:
        row.pop("recorded_at")
    assert rows[0] == rows[1]
    assert not any("common_analys" in key or key == "quality" for key in rows[0])


def test_pipeline_property_preserves_original_dataclass_serialization():
    from src.pipelines.strategy_analysis import AnalysisStrategyResult
    from tests.harness.chart_analysis_contract import baseline_payload

    value = AnalysisStrategyResult(
        scorecard=None, strategy_run=None, exchange_sessions=(), current_close=10
    )
    assert value.common_analyses == {}
    assert "common_analyses" not in baseline_payload(value, consumer="test")["payload"]
    assert baseline_payload(value, consumer="test") != baseline_payload(
        replace(value, current_close=11), consumer="test"
    )
    assert baseline_payload(value, consumer="test") != baseline_payload(
        replace(value, warning="changed"), consumer="test"
    )


def test_same_display_fact_retains_other_analysis_rejection_in_original_order():
    first, union = anchor_analysis(), anchor_analysis(extra=True)
    item = first.items[0]
    match = next(candidate for candidate in union.items if candidate.id == item.id)
    unrelated = next(candidate for candidate in union.items if candidate.anchor_id == "b")
    assert item == match
    rejected = FactSelection(FactRef(union.analysis_id, match.id), False, "REJECTED_B")
    used = FactSelection(FactRef(first.analysis_id, item.id), True, "USED_A")
    other = FactSelection(FactRef(union.analysis_id, unrelated.id), False, "UNRELATED_REJECTED")
    rows = display_rows({a.analysis_id: a for a in (first, union)}, (rejected, other, used))
    assert len(rows) == 1
    assert rows[0].refs == (rejected.ref, used.ref)
    assert rows[0].selections == (rejected, used)
    assert display_rows({union.analysis_id: union}, (other,)) == ()

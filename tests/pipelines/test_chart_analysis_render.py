"""Common presentation preserves scoped references and legacy decisions."""

import importlib
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest

from src.pipelines.chart_analysis import ChartAnalysisResult
from src.tools.technical.chart_analysis.models import FactRef, FactSelection, QualityResult
from tests.pipelines.test_common_chart_analysis import anchor_analysis


def result_for(analysis=None, *, quality=67.123456, reasons=()):
    analysis = analysis or anchor_analysis()
    return ChartAnalysisResult(
        analysis,
        QualityResult(
            analysis.manifest.as_of,
            analysis.manifest,
            "QUALITY_V1",
            "parameters",
            {"trend": 61.23456, "structure": 70, "momentum": 80, "participation": 100},
            quality,
            reasons,
            {"calculated_quality": 67.123456, "participation": {"max_share": 0.75}},
            {},
        ),
    )


def render(result, analyses, selections=()):
    assert importlib.util.find_spec("src.pipelines.chart_analysis_render") is not None, (
        "common chart renderer is missing"
    )
    return importlib.import_module("src.pipelines.chart_analysis_render").render_chart_analysis(
        result, analyses=analyses, selections=selections
    )


@pytest.mark.parametrize("missing_kind", ["analysis", "item"])
def test_render_resolves_each_analysis_ref(missing_kind):
    first, second = anchor_analysis(atr=2), anchor_analysis(atr=4)
    item = first.items[0]
    refs = (FactRef(first.analysis_id, item.id), FactRef(second.analysis_id, item.id))
    missing = (
        FactRef("missing-analysis", item.id)
        if missing_kind == "analysis"
        else FactRef(first.analysis_id, "missing-item")
    )
    output = render(
        result_for(first),
        {a.analysis_id: a for a in (first, second)},
        tuple(
            FactSelection(ref, True, reason)
            for ref, reason in zip((*refs, missing), ("FIRST", "SECOND", "MISSING"), strict=True)
        ),
    )
    assert output.count(f"- {item.kind} {item.rule_id}") == 2
    assert "final_state=RECLAIMED" in output and "final_state=BREACHED" in output
    for ref in (*refs, missing):
        assert f"{ref.analysis_id}/{ref.item_id}" in output
    assert "근거 참조 불가" in output
    assert all(reason in output for reason in ("FIRST", "SECOND", "MISSING"))


def test_anchor_union_does_not_duplicate_identical_display_fact():
    first, second = anchor_analysis(), anchor_analysis(extra=True)
    item = first.items[0]
    refs = (FactRef(first.analysis_id, item.id), FactRef(second.analysis_id, item.id))
    output = render(
        result_for(first),
        {a.analysis_id: a for a in (first, second)},
        (FactSelection(refs[0], True, "USED_A"), FactSelection(refs[1], False, "REJECTED_B")),
    )
    assert output.count(f"- {item.kind} {item.rule_id}") == 1
    assert all(f"{ref.analysis_id}/{ref.item_id}" in output for ref in refs)
    assert "USED_A" in output and "REJECTED_B" in output
    assert "anchor=b" not in output


def test_provisional_and_missing_quality_copy():
    result = result_for(
        quality=None,
        reasons=(
            "PROVISIONAL_PREVIEW",
            "POLICY_HISTORY_SHORT",
            "ONE_SIDED_SAMPLE",
            "CONCENTRATED_VOLUME",
        ),
    )
    item = replace(result.analysis.items[0], finality="PROVISIONAL")
    result = replace(result, analysis=replace(result.analysis, items=(item,)))
    output = render(result, {result.analysis.analysis_id: result.analysis})
    assert "Quality: null" in output and "preview" in output
    assert "252" in output and "한 방향" in output and "집중" in output
    assert "확정 확인일=" not in output
    assert "가용일=" in output
    assert "입력 기간" in output


def test_score_labels_are_not_trade_thresholds():
    result = result_for()
    output = render(result, {result.analysis.analysis_id: result.analysis})
    assert "67.12" in output and "67.123456" not in output
    assert "실험적 상태 지수" in output and "매매 임계값" in output
    assert "등급 비활성" in output
    assert all(label not in output for label in ("BUY", "ADD", "EXIT"))
    assert result.quality.quality == 67.123456


def test_common_section_rendered_once():
    from src.pipelines.strategy_analysis import AnalysisStrategyResult
    from src.pipelines.strategy_render import render_strategy_sections
    from src.strategies.runner import StrategyRunner
    from tests.strategies.test_playbook import _bundle
    from tests.strategies.test_runner import _legacy_result

    run = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    original = run.model_dump()
    old_result = AnalysisStrategyResult(run.scorecard, run, (), 100)
    before = render_strategy_sections(run.scorecard, old_result, detail=True)
    result = result_for()
    run = run.model_copy(update={"chart_analysis": result})
    analysis = replace(old_result, strategy_run=run)
    output = render_strategy_sections(run.scorecard, analysis, detail=True)
    assert output.count("### 공통 차트 사실") == 1
    assert output.index("### 공통 차트 사실") < output.index("### Quality")
    assert output.index("### Quality") < output.index("### 전략 선택 근거")
    assert run.model_dump() == original
    assert set(asdict(analysis)) == set(asdict(old_result))
    for line in before.splitlines():
        if any(word in line for word in ("BUY", "ADD", "EXIT")):
            assert line in output


@pytest.mark.asyncio
async def test_existing_analysis_computes_strict_quality_without_another_fetch(tmp_path):
    from types import SimpleNamespace

    from src.pipelines.chart_analysis import ChartAnalysisService
    from src.pipelines.strategy_analysis import AnalysisStrategyService
    from src.strategies.chart_bundle import chart_bundle_from_dataframes
    from src.strategies.models import CoverageManifest
    from src.strategies.runner import StrategyRunner
    from tests.strategies.test_playbook import _bundle
    from tests.strategies.test_runner import _legacy_result
    from tests.tools.technical.chart_analysis.test_history import BusinessCalendar, raw_history

    raw = raw_history()
    frame = raw.frame
    sessions = tuple(frame.index.date)
    coverage = CoverageManifest(
        requested_start=sessions[0],
        actual_start=sessions[0],
        actual_end=sessions[-1],
        expected_sessions=sessions,
        complete=True,
    )
    bundle = chart_bundle_from_dataframes(
        profile_version="CHART_PROFILE_V1",
        ticker="TEST",
        as_of=sessions[-1],
        instrument=frame,
        instrument_coverage=coverage,
        exchange_sessions=sessions,
        observed_at=datetime(2026, 10, 29, tzinfo=UTC),
    )
    run = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    legacy_payload = run.model_dump()

    class Loader:
        async def load(self, **kwargs):
            return bundle

    class Runner:
        def run(self, *args, **kwargs):
            return run

    import json

    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    recorder = EntryShadowJsonlRecorder(tmp_path / "shadow.jsonl")
    recorder.record(run, bundle, pipeline="check")
    service = AnalysisStrategyService(
        chart_loader=Loader(),
        strategy_runner=Runner(),
        shadow_recorder=recorder,
        chart_service=ChartAnalysisService(calendar=BusinessCalendar()),
    )
    technical = SimpleNamespace(raw_dataframe=frame, score_history=())
    result = await service.evaluate("TEST", technical, as_of=sessions[-1])
    assert result.chart_analysis.analysis.manifest.input_profile == "CHART_INPUT_RESPONSE_V2"
    assert result.chart_analysis.analysis.manifest.origin == "2024-10-28"
    assert result.chart_analysis.quality.quality is not None
    assert result.strategy_run.model_dump() == legacy_payload
    assert "chart_analysis" not in asdict(result)
    assert result.chart_analysis.analysis.manifest.coverage["listing_first_session"] is None

    malformed = SimpleNamespace(raw_dataframe=frame.assign(Volume=-1), score_history=())
    unavailable = await service.evaluate("TEST", malformed, as_of=sessions[-1])
    assert unavailable.chart_analysis is None
    assert "negative volume" in unavailable.chart_analysis_unavailable
    assert unavailable.strategy_run.model_dump() == legacy_payload
    assert unavailable.warning == result.warning
    payloads = [json.loads(line) for line in recorder.path.read_text().splitlines()]
    for payload in payloads:
        payload.pop("recorded_at")
    assert len(payloads) == 3 and payloads[0] == payloads[1] == payloads[2]


def test_check_analyze_brief_share_quality_and_read_only_context():
    from src.cli.main import format_deep_dive_output
    from src.llm.models import TechnicalSummaryOutput
    from src.pipelines.brief import BriefPipeline
    from src.pipelines.quick_check import QuickCheckPipeline
    from src.pipelines.strategy_analysis import AnalysisStrategyResult
    from src.strategies.runner import StrategyRunner
    from src.tools.brief.models import BUCKET_HOLD_OK, BriefItem
    from src.tools.technical.models import IndicatorSnapshot, TechnicalResult
    from tests.strategies.test_playbook import _bundle
    from tests.strategies.test_runner import _legacy_result

    run = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    result = result_for()
    manifest = replace(result.analysis.manifest, as_of=run.scorecard.as_of)
    run.chart_analysis = replace(
        result,
        analysis=replace(result.analysis, manifest=manifest),
        quality=replace(result.quality, as_of=run.scorecard.as_of, manifest=manifest),
    )
    analysis = AnalysisStrategyResult(run.scorecard, run, (), 100)
    technical = TechnicalResult(
        ticker="TEST",
        timestamp=datetime(2026, 10, 28),
        components={},
        snapshot=IndicatorSnapshot(price=100, change_pct=0),
        scorecard=run.scorecard,
    )
    check = QuickCheckPipeline(None).format_output(
        {
            "ticker": "TEST",
            "success": True,
            "scorecard": run.scorecard,
            "strategy_analysis": analysis,
            "price": 100,
            "change_pct": 0,
            "total_score": 50,
            "assessment": "hold",
            "confidence": 50,
            "signals": [],
            "warnings": [],
            "components": [],
            "indicators": {},
        }
    )
    analyze = format_deep_dive_output(
        {
            "ticker": "TEST",
            "technical": technical,
            "scorecard": run.scorecard,
            "strategy_analysis": analysis,
            "technical_summary": TechnicalSummaryOutput(
                summary="hold",
                recommendation="hold",
                confidence=0.5,
                rationale="fixed",
                key_insights=[],
            ),
        }
    )
    item = BriefItem(
        ticker="TEST",
        kind="watch",
        action="rejected",
        bucket=BUCKET_HOLD_OK,
        scorecard=run.scorecard,
        strategy_analysis=analysis,
    )
    brief = BriefPipeline.__new__(BriefPipeline).format_output(
        {"date": technical.timestamp, "macro": None, "items": [item]}
    )
    for output, heading in (
        (check, "### 현재 유효 상태"),
        (analyze, "### 현재 상태"),
        (brief, "### 현재 상태"),
    ):
        assert output.count(heading) == 1
        assert output.count("### 차트 상태 점수(Quality)") == 1
        assert "67.12" in output
    facts = BriefPipeline._facts_for(item)
    assert facts["common_chart"]["read_only"] is True
    assert facts["common_chart"]["quality"] == 67.123456
    assert facts["action"] == "rejected"


def test_renderer_bounds_internal_arrays_and_preserves_concrete_scope_evidence():
    analysis = anchor_analysis()
    item = replace(
        analysis.items[0],
        evidence={"ATR": 2.123456789, "rows": tuple(range(10000)), "Close": 101.23456},
    )
    analysis = replace(analysis, items=(item,))
    output = render(result_for(analysis), {analysis.analysis_id: analysis})
    assert "ATR=2.12" in output and "Close=101.23" in output
    assert "9999" not in output
    assert len(output) < 2500


def test_own_history_is_bounded_but_explicit_selected_history_is_retained():
    from datetime import timedelta

    analysis = anchor_analysis()
    recent = analysis.items[0]
    old = replace(
        recent,
        id="old-item",
        kind="EVENT",
        state="OLD_UNSELECTED",
        occurred_on=analysis.manifest.as_of - timedelta(days=100),
        confirmed_on=analysis.manifest.as_of - timedelta(days=97),
    )
    analysis = replace(analysis, items=(old, recent))
    result = result_for(analysis)
    assert "OLD_UNSELECTED" not in render(result, {analysis.analysis_id: analysis})
    selected = FactSelection(FactRef(analysis.analysis_id, old.id), True, "HISTORICAL_SUPPORT")
    output = render(result, {analysis.analysis_id: analysis}, (selected,))
    assert "OLD_UNSELECTED" in output and "HISTORICAL_SUPPORT" in output


def test_original_technical_and_scorecard_selections_keep_refs_reasons_and_serializers(tmp_path):
    import json

    from src.pipelines.chart_analysis_render import render_common_strategy_analysis
    from src.pipelines.strategy_analysis import AnalysisStrategyResult
    from src.storage.entry_shadow import EntryShadowJsonlRecorder
    from src.strategies.runner import StrategyRunner
    from tests.harness.chart_analysis_contract import baseline_payload
    from tests.strategies.test_playbook import _bundle
    from tests.strategies.test_runner import _legacy_result

    technical_analysis, scorecard_analysis = anchor_analysis(atr=2), anchor_analysis(atr=4)
    technical_ref = FactRef(technical_analysis.analysis_id, technical_analysis.items[0].id)
    scorecard_ref = FactRef(scorecard_analysis.analysis_id, scorecard_analysis.items[0].id)
    technical_selections = (
        FactSelection(technical_ref, True, "ORIGINAL_TECHNICAL_SELECTED"),
        FactSelection(technical_ref, False, "ORIGINAL_TECHNICAL_REJECTION"),
    )
    scorecard_selections = (FactSelection(scorecard_ref, True, "SCORECARD_SELECTED"),)
    technical = _legacy_result()
    technical.fact_selections = technical_selections
    technical.common_analyses = (technical_analysis,)
    technical.scorecard = technical.scorecard.model_copy(
        update={
            "fact_selections": scorecard_selections,
            "common_analyses": (scorecard_analysis,),
        }
    )
    bundle = _bundle()
    run = StrategyRunner().run(bundle, legacy_result=technical)
    recording_run = run
    run = run.model_copy(
        update={
            "verdicts": [],
            "signal_bundles": [],
            "chart_analysis": result_for(anchor_analysis(atr=6)),
        }
    )
    analysis = AnalysisStrategyResult(run.scorecard, run, (), 100)
    output = render_common_strategy_analysis(analysis)
    assert all(
        reason in output
        for reason in (
            "ORIGINAL_TECHNICAL_SELECTED",
            "ORIGINAL_TECHNICAL_REJECTION",
            "SCORECARD_SELECTED",
        )
    )
    assert (
        output.index("ORIGINAL_TECHNICAL_SELECTED")
        < output.index("ORIGINAL_TECHNICAL_REJECTION")
        < output.index("SCORECARD_SELECTED")
    )
    for ref in (technical_ref, scorecard_ref):
        assert f"FactRef={ref.analysis_id}/{ref.item_id}" in output
    assert "공통 분석 단독 조회" not in output
    assert analysis.technical_fact_selections == technical_selections
    original = run.model_copy(update={"technical_fact_selections": ()})
    assert run.model_dump() == original.model_dump()
    assert baseline_payload(analysis, consumer="test") == baseline_payload(
        replace(analysis, strategy_run=original), consumer="test"
    )
    assert "technical_fact_selections" not in asdict(analysis)
    recorder = EntryShadowJsonlRecorder(tmp_path / "shadow.jsonl")
    recorder.record(recording_run, bundle, pipeline="check")
    recorder.record(
        recording_run.model_copy(update={"technical_fact_selections": ()}), bundle, pipeline="check"
    )
    payloads = [json.loads(line) for line in recorder.path.read_text().splitlines()]
    for payload in payloads:
        payload.pop("recorded_at")
    assert len(payloads) == 2 and payloads[0] == payloads[1]


def test_strict_unavailable_keeps_selected_retained_facts_without_scope_substitution():
    from src.pipelines.chart_analysis_render import render_common_strategy_analysis
    from src.pipelines.strategy_analysis import AnalysisStrategyResult
    from src.pipelines.strategy_render import render_strategy_sections
    from src.strategies.runner import StrategyRunner
    from tests.harness.chart_analysis_contract import baseline_payload
    from tests.strategies.test_playbook import _bundle
    from tests.strategies.test_runner import _legacy_result

    selected, unselected = anchor_analysis(), anchor_analysis(atr=4, extra=True)
    item = selected.items[0]
    ref = FactRef(selected.analysis_id, item.id)
    missing = FactRef("missing-scope", item.id)
    selections = (
        FactSelection(ref, True, "RETAINED_SELECTED"),
        FactSelection(ref, False, "RETAINED_REJECTED"),
        FactSelection(missing, True, "MISSING_SELECTED"),
    )
    run = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    verdict = run.verdicts[0].model_copy(update={"fact_selections": selections})
    run = run.model_copy(
        update={
            "verdicts": [verdict],
            "signal_bundles": [],
            "common_analyses": {a.analysis_id: a for a in (selected, unselected)},
            "chart_analysis": None,
            "chart_analysis_unavailable": "InputHistoryError: rejected strict raw",
        }
    )
    analysis = AnalysisStrategyResult(run.scorecard, run, (), 100)
    original = baseline_payload(analysis, consumer="test")
    common = render_common_strategy_analysis(analysis)
    full = render_strategy_sections(run.scorecard, analysis, detail=True)
    assert all(
        reason in common
        for reason in ("RETAINED_SELECTED", "RETAINED_REJECTED", "MISSING_SELECTED")
    )
    assert common.count(f"- {item.kind} {item.rule_id}") == 1
    assert f"FactRef={ref.analysis_id}/{ref.item_id}" in common
    assert "근거 참조 불가: missing-scope/" in common
    assert unselected.analysis_id not in common
    assert "anchor=b" not in common
    assert "Quality: null" in common and "rejected strict raw" in common
    assert (
        common.index("RECLAIMED") < common.index("### Quality") < common.index("### 전략 선택 근거")
    )
    assert "profile=CHART_INPUT_V1" not in common
    assert common in full and "### 전략" in full
    assert baseline_payload(analysis, consumer="test") == original

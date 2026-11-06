"""Independent strategy sizing and Quality-only history completion."""

from types import SimpleNamespace

import pandas as pd
import pytest
from typer.testing import CliRunner

from src.pipelines.chart_analysis import ChartAnalysisService
from src.pipelines.chart_analysis_render import render_common_strategy_analysis
from src.pipelines.strategy_analysis import AnalysisStrategyService
from src.pipelines.strategy_render import render_strategy_sections
from src.position.models import PositionSnapshot, QuantityStatus
from src.storage.canonical import canonical_bytes
from src.strategies.models import EntryIntent, ExitIntent
from tests.pipelines.test_chart_analysis_render import result_for
from tests.pipelines.test_quick_check import mock_technical_tool  # noqa: F401
from tests.pipelines.test_strategy_analysis import _position_service, signal_analysis  # noqa: F401
from tests.tools.technical.chart_analysis.test_history import BusinessCalendar, raw_history


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [0, 350])
async def test_conflicting_strategy_plans_remain_independent(quantity, signal_analysis):  # noqa: F811
    service, technical = _position_service(EntryIntent.WATCH, ExitIntent.REDUCE)
    original = service.strategy_runner.run
    swing = signal_analysis.strategy_run.signal_bundles[0].model_copy(
        update={"current_signals": [], "signal_history": []}
    )

    def run(*args, **kwargs):
        result = original(*args, **kwargs)
        legacy = result.verdicts[0].model_copy(update={"strategy_id": "TECHNICAL_LEGACY"})
        result.verdicts.append(legacy)
        result.signal_bundles = [swing]
        return result

    service.strategy_runner.run = run
    service.shadow_recorder = None
    result = await service.evaluate(
        "AAPL", technical, as_of=technical.scorecard.as_of, position=PositionSnapshot(quantity)
    )
    assert set(result.position_plans) == {"TECHNICAL_LEGACY", "PLAYBOOK_V1", "SWING_W150"}
    assert result.position_plans["PLAYBOOK_V1"].sell_quantity == quantity // 2
    assert result.position_plans["SWING_W150"].sell_quantity == 0
    output = render_strategy_sections(result.scorecard, result)
    assert "독립 대안" in output
    assert f"PLAYBOOK_V1: reduce_current_by_fraction: current={quantity}" in output
    assert f"SWING_W150: keep_current: current={quantity}" in output


@pytest.mark.asyncio
async def test_all_verdict_build_plans_keep_execution_guard():
    service, technical = _position_service(EntryIntent.ALLOW, ExitIntent.HOLD)
    original = service.strategy_runner.run

    def run(*args, **kwargs):
        result = original(*args, **kwargs)
        result.verdicts.append(
            result.verdicts[0].model_copy(update={"strategy_id": "TECHNICAL_LEGACY"})
        )
        return result

    service.strategy_runner.run = run
    service.shadow_recorder = None
    a = await service.evaluate(
        "AAPL", technical, as_of=technical.scorecard.as_of, position=PositionSnapshot(0)
    )
    b = await service.evaluate(
        "AAPL", technical, as_of=technical.scorecard.as_of, position=PositionSnapshot(350)
    )
    assert canonical_bytes(a.strategy_run.verdicts) == canonical_bytes(b.strategy_run.verdicts)
    for result in (a, b):
        for plan in result.position_plans.values():
            assert plan.quantity_status is QuantityStatus.UNAVAILABLE
            assert plan.buy_quantity is None


def quality_service(frame, supplement):
    raw = raw_history()
    bars = [
        SimpleNamespace(session_date=day, finality=SimpleNamespace(value="final"), close=10)
        for day in frame.index.date
    ]
    coverage = SimpleNamespace(
        actual_start=frame.index[0].date(), actual_end=frame.index[-1].date()
    )
    bundle = SimpleNamespace(
        instrument=SimpleNamespace(bars=bars, coverage=coverage),
        exchange_sessions=tuple(frame.index.date),
        market=object(),
    )

    class Loader:
        async def load(self, **kwargs):
            return bundle

    class Runner:
        def run(self, bundle, *, legacy_result):
            return SimpleNamespace(scorecard=legacy_result.scorecard, verdicts=[], errors=[])

    class Provider:
        requests = []

        async def get_price_history(self, ticker, period):
            self.requests.append((ticker, period))
            if isinstance(supplement, Exception):
                raise supplement
            return supplement

    provider = Provider()
    technical = SimpleNamespace(
        raw_dataframe=frame.copy(),
        scorecard=None,
        quality_raw_dataframe=frame.copy(),
        quality_history_provider=provider,
    )
    service = AnalysisStrategyService(
        chart_loader=Loader(),
        strategy_runner=Runner(),
        chart_service=ChartAnalysisService(calendar=BusinessCalendar()),
        shadow_recorder=None,
    )
    return service, technical, provider, raw.frame.index[-1].date()


@pytest.mark.asyncio
@pytest.mark.parametrize("short", [False, True])
async def test_quality_completion_once_without_changing_legacy_frame(short):
    full = raw_history().frame
    frame = full.iloc[-300:] if short else full
    service, technical, provider, day = quality_service(frame, full)
    before = technical.raw_dataframe.copy(deep=True)
    result = await service.evaluate("TEST", technical, as_of=day)
    assert provider.requests == ([("TEST", "3y")] if short else [])
    assert result.chart_analysis is not None
    assert result.chart_analysis.quality.quality is not None
    pd.testing.assert_frame_equal(technical.raw_dataframe, before)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["conflict", "timeout", "nan"])
async def test_quality_completion_rejects_conflict_and_preserves_missing(failure):
    full = raw_history().frame
    supplement = full.copy()
    if failure == "conflict":
        supplement.iloc[-10, supplement.columns.get_loc("Volume")] += 1
    elif failure == "timeout":
        supplement = TimeoutError("offline timeout")
    else:
        supplement.iloc[-400, supplement.columns.get_loc("Close")] = float("nan")
    service, technical, provider, day = quality_service(full.iloc[-300:], supplement)
    result = await service.evaluate("TEST", technical, as_of=day)
    assert provider.requests == [("TEST", "3y")]
    assert result.chart_analysis is None or result.chart_analysis.quality.quality is None
    if failure == "conflict":
        assert "conflict" in result.chart_analysis_unavailable.lower()
    assert result.strategy_run.errors == []


@pytest.mark.asyncio
async def test_quality_completion_normalizes_timezone_and_clips_future():
    full = raw_history().frame
    supplement = full.copy()
    supplement.index = supplement.index.tz_localize("America/New_York")
    supplement.loc[pd.Timestamp("2026-10-29", tz="America/New_York")] = [1, 2, 1, 1, 1]
    service, technical, provider, day = quality_service(full.iloc[-300:], supplement)
    result = await service.evaluate("TEST", technical, as_of=day)
    assert result.chart_analysis.quality.quality is not None
    assert result.chart_analysis.analysis.manifest.as_of == day


def test_default_common_output_omits_audit_but_detail_preserves_it():
    result = result_for(quality=None, reasons=("INCOMPLETE_PREFIX",))
    analysis = SimpleNamespace(
        strategy_run=SimpleNamespace(verdicts=[], signal_bundles=[]),
        common_analyses={},
        technical_fact_selections=(),
        chart_analysis=result,
    )
    compact = render_common_strategy_analysis(analysis, detail=False)
    detail = render_common_strategy_analysis(analysis, detail=True)
    assert "Quality: null" in compact and "INCOMPLETE_PREFIX" in compact
    assert "FactRef=" not in compact
    assert "FactRef=" in detail
    assert len(compact) < len(detail)


def test_score_is_not_registered():
    from src.cli.main import app

    result = CliRunner().invoke(app, ["score", "TEST"])
    assert result.exit_code == 2
    assert "No such command" in result.output


@pytest.mark.asyncio
async def test_check_holdings_read_failure_stays_unknown(monkeypatch, mock_technical_tool):  # noqa: F811
    from src.core.models import ToolResult
    from src.pipelines.quick_check import QuickCheckPipeline

    service, legacy = _position_service(EntryIntent.WATCH, ExitIntent.REDUCE)
    service.shadow_recorder = None
    technical = mock_technical_tool.execute.return_value.data
    technical.scorecard = legacy.scorecard
    technical.raw_dataframe = raw_history().frame

    class Tool:
        async def execute(self, ticker):
            return ToolResult(success=True, data=technical)

    def fail():
        raise ValueError("invalid holdings")

    monkeypatch.setattr("src.pipelines.quick_check.load_holdings", fail)
    pipeline = QuickCheckPipeline(Tool(), strategy_service=service)
    result = await pipeline.run("AAPL")
    assert result["success"]
    assert result["strategy_analysis"].position_plans == {}
    output = pipeline.format_output(result)
    assert "invalid holdings" in output
    assert "수량 미산정" in output
    assert "current=0" not in output


@pytest.mark.asyncio
async def test_supplement_preserves_provisional_evaluated_bar():
    full = raw_history().frame
    service, technical, _, day = quality_service(full.iloc[-300:], full)
    bundle = await service.chart_loader.load()
    bundle.instrument.bars[-1].finality.value = "provisional"
    result = await service.evaluate("TEST", technical, as_of=day)
    assert result.chart_analysis.quality.quality is None
    assert "PROVISIONAL_PREVIEW" in result.chart_analysis.quality.reasons


def test_compact_common_facts_are_bounded_by_rule_and_keep_risk_states():
    from dataclasses import replace

    from src.tools.technical.chart_analysis.models import FactRef, FactSelection
    from tests.pipelines.test_common_chart_analysis import anchor_analysis

    analysis = anchor_analysis(extra=True)
    analysis = replace(
        analysis, items=tuple(replace(item, state="BREACHED") for item in analysis.items)
    )
    item = analysis.items[0]
    selections = tuple(
        FactSelection(FactRef(analysis.analysis_id, x.id), True, "TEST") for x in analysis.items
    )
    value = SimpleNamespace(
        strategy_run=SimpleNamespace(verdicts=[], signal_bundles=[]),
        common_analyses={analysis.analysis_id: analysis},
        technical_fact_selections=selections,
        chart_analysis=None,
        chart_analysis_unavailable="offline",
    )
    compact = render_common_strategy_analysis(value, detail=False)
    detail = render_common_strategy_analysis(value, detail=True)
    assert compact.count(f"- {item.kind} {item.rule_id}") == 1
    assert detail.count(f"- {item.kind} {item.rule_id}") > 1


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [0, 7, 350])
async def test_check_reads_actual_holding_without_changing_strategy(
    quantity,
    monkeypatch,
    mock_technical_tool,  # noqa: F811
):
    from src.pipelines.quick_check import QuickCheckPipeline

    service, legacy = _position_service(EntryIntent.WATCH, ExitIntent.REDUCE)
    service.shadow_recorder = None
    technical = mock_technical_tool.execute.return_value.data
    technical.scorecard = legacy.scorecard
    config = SimpleNamespace(
        find=lambda ticker: SimpleNamespace(quantity=quantity),
        get_account_for=lambda ticker: (None, None),
    )
    monkeypatch.setattr("src.pipelines.quick_check.load_holdings", lambda: config)
    pipeline = QuickCheckPipeline(mock_technical_tool, strategy_service=service)
    result = await pipeline.run("AAPL")
    plan = result["strategy_analysis"].position_plans["PLAYBOOK_V1"]
    assert plan.current_quantity == quantity
    assert plan.sell_quantity == {0: 0, 7: 4, 350: 175}[quantity]
    assert f"| PLAYBOOK_V1 | 일부 축소 | {quantity} |" in pipeline.format_output(result)
    assert result["strategy_analysis"].strategy_run.verdicts[0].exit.intent is ExitIntent.REDUCE


@pytest.mark.asyncio
async def test_quality_supplement_does_not_infer_missing_sessions_from_calendar():
    full = raw_history().frame
    missing = full.index[-40]
    original = full.iloc[-300:].drop(index=missing)
    service, technical, _, day = quality_service(original, full)
    before = technical.raw_dataframe.copy(deep=True)

    result = await service.evaluate("TEST", technical, as_of=day)

    assert result.chart_analysis.quality.quality is not None
    assert result.chart_analysis_unavailable is None
    assert result.strategy_run.errors == []
    pd.testing.assert_frame_equal(technical.raw_dataframe, before)


@pytest.mark.asyncio
async def test_quality_supplement_cannot_replace_returned_nan_with_valid_value():
    full = raw_history().frame
    original = full.iloc[-300:].copy()
    original.iloc[-40, original.columns.get_loc("Close")] = float("nan")
    service, technical, _, day = quality_service(original, full)
    before = technical.raw_dataframe.copy(deep=True)
    result = await service.evaluate("TEST", technical, as_of=day)
    assert result.chart_analysis is None
    assert "conceal missing original OHLCV" in result.chart_analysis_unavailable
    pd.testing.assert_frame_equal(technical.raw_dataframe, before)


@pytest.mark.asyncio
async def test_quality_supplement_allows_verified_nontrading_gap():
    full = raw_history().frame
    holiday = full.index[-40].date()
    full = full.drop(index=pd.Timestamp(holiday))
    service, technical, _, day = quality_service(full.iloc[-300:], full)

    class HolidayCalendar(BusinessCalendar):
        version = "VERIFIED_HOLIDAY_TEST_V1"

        def sessions(self, start, end):
            return tuple(day for day in super().sessions(start, end) if day != holiday)

    service.chart_service.calendar = HolidayCalendar()
    result = await service.evaluate("TEST", technical, as_of=day)

    assert result.chart_analysis is not None
    assert result.chart_analysis.quality.quality is not None

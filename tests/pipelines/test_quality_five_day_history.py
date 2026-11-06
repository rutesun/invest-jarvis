"""Past Quality values are recomputed from their own date, without extra prices."""

import pandas as pd
import pytest

from src.pipelines.chart_analysis import ChartAnalysisService
from src.pipelines.quality_history import quality_history
from src.tools.technical.chart_analysis.models import plain
from tests.pipelines.test_integrated_quality_plans import quality_service
from tests.tools.technical.chart_analysis.test_history import BusinessCalendar, raw_history


@pytest.mark.asyncio
async def test_six_observed_quality_points_equal_independent_date_queries():
    full = raw_history().frame
    service, technical, provider, day = quality_service(full, full)
    bundle = await service.chart_loader.load()
    raw = await quality_history("TEST", technical, bundle, service.chart_service, day)
    result = await service.evaluate("TEST", technical, as_of=day)
    assert len(result.quality_history) == 6
    assert [row.quality.as_of for row in result.quality_history] == list(full.index[-6:].date)
    for row in result.quality_history:
        single = (
            await ChartAnalysisService(calendar=BusinessCalendar()).analyze(
                "TEST", sessions=(row.quality.as_of,), raw=raw
            )
        )[0]
        assert plain(row) == plain(single)
    assert plain(result.chart_analysis) == plain(result.quality_history[-1])
    assert result.quality_history_unavailable is None
    assert provider.requests == []


@pytest.mark.asyncio
async def test_quality_history_uses_one_supplement_and_keeps_legacy_prices():
    full = raw_history().frame
    service, technical, provider, day = quality_service(full.iloc[-300:], full)
    before = technical.raw_dataframe.copy(deep=True)
    result = await service.evaluate("TEST", technical, as_of=day)
    assert provider.requests == [("TEST", "3y")]
    assert len(result.quality_history) == 6
    assert all(row.quality.quality is not None for row in result.quality_history)
    pd.testing.assert_frame_equal(technical.raw_dataframe, before)


@pytest.mark.asyncio
async def test_current_two_year_input_is_extended_for_earliest_history_origin():
    from src.pipelines.quality_overview import compatible

    full = raw_history().frame
    supplied = full.loc["2024-10-28":]
    service, technical, provider, day = quality_service(supplied, full)
    result = await service.evaluate("TEST", technical, as_of=day)
    assert provider.requests == [("TEST", "3y")]
    assert len(result.quality_history) == 6
    assert all(row.quality.quality is not None for row in result.quality_history)
    assert compatible(result.quality_history[-2], result.chart_analysis)
    pd.testing.assert_frame_equal(technical.raw_dataframe, supplied)


@pytest.mark.asyncio
async def test_history_only_supplement_conflict_keeps_current_quality():
    full = raw_history().frame
    supplied = full.loc["2024-10-28":]
    revised = full.copy()
    revised.iloc[-1, revised.columns.get_loc("Close")] += 1
    service, technical, provider, day = quality_service(supplied, revised)
    result = await service.evaluate("TEST", technical, as_of=day)
    assert provider.requests == [("TEST", "3y")]
    assert result.chart_analysis.quality.quality is not None
    assert result.chart_analysis_unavailable is None
    assert result.quality_history == ()
    assert "conflict" in result.quality_history_unavailable


@pytest.mark.asyncio
async def test_only_latest_provisional_bar_remains_preview_in_quality_history():
    full = raw_history().frame
    service, technical, _, day = quality_service(full, full)
    bundle = await service.chart_loader.load()
    bundle.instrument.bars[-1].finality.value = "provisional"
    result = await service.evaluate("TEST", technical, as_of=day)
    assert len(result.quality_history) == 6
    assert all(row.quality.quality is not None for row in result.quality_history[:-1])
    last = result.quality_history[-1]
    assert last.quality.quality is None
    assert "PROVISIONAL_PREVIEW" in last.quality.reasons
    assert last.quality.diagnostics["calculated_quality"] is not None


@pytest.mark.asyncio
async def test_historical_calculation_failure_keeps_current_quality():
    class HistoryFailure(ChartAnalysisService):
        async def analyze(self, ticker, *, sessions, raw=None):
            if len(sessions) > 1:
                raise RuntimeError("historical calculation unavailable")
            return await super().analyze(ticker, sessions=sessions, raw=raw)

    full = raw_history().frame
    service, technical, _, day = quality_service(full, full)
    service.chart_service = HistoryFailure(calendar=BusinessCalendar())
    result = await service.evaluate("TEST", technical, as_of=day)
    assert result.chart_analysis.quality.quality is not None
    assert result.quality_history == ()
    assert "historical calculation unavailable" in result.quality_history_unavailable
    assert result.chart_analysis_unavailable is None


@pytest.mark.asyncio
async def test_historical_bars_are_never_filled_with_current_quality():
    full = raw_history().frame
    frame = full.iloc[-523:]
    service, technical, _, day = quality_service(frame, frame)
    technical.quality_history_provider = None
    result = await service.evaluate("TEST", technical, as_of=day)
    assert result.chart_analysis.quality.quality is not None
    assert len(result.quality_history) == 6
    assert result.quality_history[0].quality.quality is None
    assert "INCOMPLETE_PREFIX" in result.quality_history[0].quality.reasons


@pytest.mark.asyncio
async def test_quality_history_is_absent_from_strategy_serialization():
    from tests.pipelines.test_observation_render import _analysis

    full = raw_history().frame
    service, technical, _, day = quality_service(full, full)
    run = _analysis().strategy_run
    for signal_bundle in run.signal_bundles:
        signal_bundle.signal_history = []
    before = run.model_dump(mode="json")

    class Runner:
        def run(self, bundle, *, legacy_result):
            return run

    service.strategy_runner = Runner()
    result = await service.evaluate("AAPL", technical, as_of=day)
    payload = result.strategy_run.model_dump(mode="json")
    assert hasattr(result, "quality_history")
    assert len(result.quality_history) == 6
    assert payload == before
    assert "quality_history" not in payload
    assert "quality_history_unavailable" not in payload
    from tests.harness.chart_analysis_contract import baseline_payload

    legacy = baseline_payload(result, consumer="check")["payload"]
    assert "quality_history" not in legacy
    assert "quality_history_unavailable" not in legacy

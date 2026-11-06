"""Offline CLI modes and service date selection; no provider or LLM access."""

from datetime import date

import pytest

from src.pipelines.chart_analysis import ChartAnalysisService
from tests.tools.technical.chart_analysis.test_history import BusinessCalendar, raw_history


@pytest.mark.asyncio
async def test_default_and_history_use_observed_sessions_and_retain_requested_holiday():
    from dataclasses import replace

    raw = raw_history()
    raw = replace(raw, frame=raw.frame.loc[:"2026-10-23"])
    service = ChartAnalysisService(calendar=BusinessCalendar())
    assert hasattr(service, "analyze_query"), "observed session query seam is missing"
    latest = await service.analyze_query("TEST", raw=raw, today=date(2026, 10, 28))
    history = await service.analyze_query("TEST", raw=raw, history=2, today=date(2026, 10, 28))
    weekend = await service.analyze_query("TEST", raw=raw, as_of=date(2026, 10, 25))
    interval = await service.analyze_query(
        "TEST", raw=raw, start=date(2026, 10, 22), end=date(2026, 10, 25)
    )
    assert [r.analysis.manifest.as_of for r in latest] == [date(2026, 10, 23)]
    assert [r.analysis.manifest.as_of for r in history] == [date(2026, 10, 22), date(2026, 10, 23)]
    assert weekend[0].requested_as_of == date(2026, 10, 25)
    assert weekend[0].analysis == latest[0].analysis
    assert [r.analysis.manifest.as_of for r in interval] == [date(2026, 10, 22), date(2026, 10, 23)]

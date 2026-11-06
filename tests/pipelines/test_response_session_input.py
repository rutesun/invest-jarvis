"""Returned daily bars define chronology; external calendars cannot invent gaps."""

from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from src.pipelines.chart_analysis import ChartAnalysisService
from src.pipelines.strategy_analysis import ChartBundleLoader
from src.providers.price_history_range import HistoryFinality, InputHistoryError
from src.tools.technical.chart_analysis.models import plain
from tests.pipelines.test_strategy_analysis import MarketProvider
from tests.tools.technical.chart_analysis.test_history import raw_history


class UnavailableCalendar:
    timezone = "Asia/Seoul"
    version = "unavailable"

    def sessions(self, start, end):
        raise AssertionError("daily-history validation must not consult a calendar")


def response_with_holidays():
    raw = raw_history()
    frame = raw.frame.drop(pd.to_datetime(["2026-06-03", "2026-07-17"]))
    return replace(raw, frame=frame)


@pytest.mark.asyncio
async def test_quality_uses_returned_bars_without_calendar_gap_detection():
    raw = response_with_holidays()
    before = raw.frame.copy(deep=True)
    service = ChartAnalysisService(calendar=UnavailableCalendar())
    result = (await service.analyze("161890", sessions=(date(2026, 10, 28),), raw=raw))[0]
    assert result.quality.quality is not None
    assert result.analysis.manifest.coverage["missing_sessions"] == ()
    assert result.analysis.features["History_Status"].value == 1
    pd.testing.assert_frame_equal(raw.frame, before)


@pytest.mark.asyncio
async def test_response_based_date_range_and_holiday_queries_agree():
    service = ChartAnalysisService(calendar=UnavailableCalendar())
    raw = response_with_holidays()
    single = (await service.analyze_query("161890", as_of=date(2026, 7, 16), raw=raw))[0]
    holiday = (await service.analyze_query("161890", as_of=date(2026, 7, 17), raw=raw))[0]
    rows = await service.analyze_query(
        "161890", start=date(2026, 7, 15), end=date(2026, 7, 20), raw=raw
    )
    assert [r.analysis.manifest.as_of for r in rows] == [
        date(2026, 7, 15),
        date(2026, 7, 16),
        date(2026, 7, 20),
    ]
    assert plain(single) == plain(rows[1])
    assert plain(single.analysis) == plain(holiday.analysis)


@pytest.mark.asyncio
async def test_range_provider_selects_only_dates_in_its_response():
    class Provider:
        async def get_price_history_range(self, ticker, *, start, end):
            return response_with_holidays()

    rows = await ChartAnalysisService(
        range_provider=Provider(), calendar=UnavailableCalendar()
    ).analyze_query("161890", start=date(2026, 7, 16), end=date(2026, 7, 20))
    assert [r.analysis.manifest.as_of for r in rows] == [date(2026, 7, 16), date(2026, 7, 20)]
    assert all(row.quality.quality is not None for row in rows)


@pytest.mark.asyncio
async def test_delayed_response_date_has_same_quality_alone_and_in_union():
    raw = raw_history()
    frame = raw.frame.drop(raw.frame.loc["2026-10-01":"2026-10-15"].index)

    class Provider:
        async def get_price_history_range(self, ticker, *, start, end):
            return replace(
                raw,
                frame=frame.loc[str(start) : str(end)],
                coverage=replace(raw.coverage, requested_start=start, requested_end=end),
            )

    service = ChartAnalysisService(range_provider=Provider(), calendar=UnavailableCalendar())
    single = (await service.analyze("TEST", sessions=(date(2026, 10, 14),)))[0]
    union = await service.analyze("TEST", sessions=(date(2026, 9, 29), date(2026, 10, 14)))
    assert single.analysis.manifest.as_of == date(2026, 9, 30)
    assert single.analysis.manifest.origin == "2024-09-30"
    assert single.quality.quality is not None
    assert plain(single) == plain(union[1])


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["ohlcv", "omitted", "finality", "revision"])
async def test_delayed_response_supplement_rejects_changed_original_data(conflict):
    raw = response_with_holidays()
    frame = raw.frame.drop(raw.frame.loc["2026-10-01":"2026-10-15"].index)

    class Provider:
        async def get_price_history_range(self, ticker, *, start, end):
            result = replace(
                raw,
                frame=frame.loc[str(start) : str(end)].copy(),
                finality=dict(raw.finality),
                coverage=replace(raw.coverage, requested_start=start, requested_end=end),
            )
            if start == date(2024, 9, 30):
                if conflict == "ohlcv":
                    result.frame.loc["2026-09-30", "Close"] += 0.1
                elif conflict == "omitted":
                    result = replace(result, frame=result.frame.drop(pd.Timestamp("2026-09-30")))
                elif conflict == "finality":
                    result.finality[date(2026, 9, 30)] = HistoryFinality.UNKNOWN
                else:
                    result = replace(result, revision_if_known="changed")
            return result

    with pytest.raises(InputHistoryError, match="supplemental response changes original"):
        await ChartAnalysisService(range_provider=Provider()).analyze(
            "TEST", sessions=(date(2026, 10, 14),)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["nan", "unknown", "short"])
async def test_response_only_still_rejects_invalid_or_short_history(invalid):
    raw = response_with_holidays()
    if invalid == "nan":
        raw.frame.loc["2026-07-16", "Close"] = float("nan")
    elif invalid == "unknown":
        raw.finality.pop(date(2026, 7, 16))
    else:
        raw = replace(raw, frame=raw.frame.iloc[-251:])
    row = (await ChartAnalysisService().analyze("161890", sessions=(date(2026, 10, 28),), raw=raw))[
        0
    ]
    assert row.quality.quality is None
    assert (
        "POLICY_HISTORY_SHORT" if invalid == "short" else "INCOMPLETE_PREFIX"
    ) in row.quality.reasons


@pytest.mark.asyncio
async def test_strategy_loader_uses_response_dates_for_each_series(monkeypatch):
    import src.pipelines.strategy_analysis as module

    def no_calendar(*args):
        raise AssertionError("daily-history validation must not consult a calendar")

    monkeypatch.setattr(module, "exchange_sessions_for", no_calendar, raising=False)
    frame = response_with_holidays().frame
    bundle = await ChartBundleLoader(MarketProvider(frame)).load(
        ticker="161890",
        technical=SimpleNamespace(raw_dataframe=frame),
        as_of=date(2026, 10, 28),
    )
    assert bundle.instrument.coverage.complete
    assert bundle.market.coverage.complete
    assert date(2026, 6, 3) not in bundle.exchange_sessions
    assert date(2026, 7, 17) not in bundle.exchange_sessions

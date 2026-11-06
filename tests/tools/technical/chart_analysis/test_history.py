"""On-demand dates retain the same canonical origin and request-local identity."""

import importlib
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.providers.price_history_range import HistoryFinality, RangeCoverage, RawHistory
from src.tools.technical.chart_analysis.models import plain


class BusinessCalendar:
    version = "BUSINESS_TEST_V1"
    timezone = "America/New_York"

    def sessions(self, start, end):
        return tuple(pd.bdate_range(start, end).date)


def raw_history():
    index = pd.bdate_range("2024-01-01", "2026-10-28")
    close = 100 + np.arange(len(index)) * 0.03 + np.sin(np.arange(len(index)))
    frame = pd.DataFrame(
        {
            "Open": close,
            "High": close + 2,
            "Low": close - 2,
            "Close": close,
            "Volume": 100 + np.arange(len(index)) % 17,
        },
        index=index,
    )
    return RawHistory(
        frame,
        "offline",
        "ADJUSTED",
        "revision-1",
        dict.fromkeys(index.date, HistoryFinality.FINAL),
        RangeCoverage(index[0].date(), index[-1].date(), True),
    )


def service(**kwargs):
    assert importlib.util.find_spec("src.pipelines.chart_analysis") is not None, (
        "on-demand service missing"
    )
    api = importlib.import_module("src.pipelines.chart_analysis")
    return api.ChartAnalysisService(calendar=BusinessCalendar(), **kwargs)


@pytest.mark.asyncio
async def test_date_equals_every_overlapping_range():
    raw = raw_history()
    target = date(2026, 10, 21)
    runner = service()
    single = (await runner.analyze("TEST", sessions=(target,), raw=raw))[0]
    for sessions in [
        (date(2026, 10, 20), target),
        (date(2026, 10, 19), target, date(2026, 10, 28)),
        (date(2026, 10, 28), target, date(2026, 10, 19)),
    ]:
        rows = await runner.analyze("TEST", sessions=sessions, raw=raw)
        assert len(rows) == len(sessions)
        assert [row.analysis.manifest.as_of for row in rows] == list(sessions)
        assert plain(next(row for row in rows if row.analysis.manifest.as_of == target)) == plain(
            single
        )
        for row in rows:
            expected = BusinessCalendar().sessions(
                (pd.Timestamp(row.analysis.manifest.as_of) - pd.DateOffset(years=2)).date(),
                row.analysis.manifest.as_of,
            )[0]
            assert row.analysis.manifest.origin == str(expected)
    assert single.analysis.manifest.provider == "offline"
    assert single.analysis.manifest.revision_if_known == "revision-1"
    assert single.analysis.manifest.timezone == BusinessCalendar.timezone


@pytest.mark.asyncio
async def test_future_bars_do_not_change_T():  # noqa: N802 - specified acceptance name
    raw = raw_history()
    target = date(2026, 10, 21)
    prefix = replace(
        raw,
        frame=raw.frame.loc[: str(target)],
        coverage=replace(raw.coverage, requested_end=target),
    )
    altered = raw.frame.copy()
    altered.loc[altered.index.date > target] *= 9
    a = await service().analyze("TEST", sessions=(target,), raw=prefix)
    b = await service().analyze("TEST", sessions=(target,), raw=replace(raw, frame=altered))
    assert plain(a) == plain(b)


@pytest.mark.asyncio
async def test_revision_is_part_of_identity():
    raw = raw_history()
    a = (await service().analyze("TEST", sessions=(date(2026, 10, 21),), raw=raw))[0]
    b = (
        await service().analyze(
            "TEST", sessions=(date(2026, 10, 21),), raw=replace(raw, revision_if_known="revision-2")
        )
    )[0]
    assert a.analysis.manifest.input_hash == b.analysis.manifest.input_hash
    assert a.analysis.analysis_id != b.analysis.analysis_id


@pytest.mark.asyncio
async def test_live_range_remains_unavailable_without_explicit_offline_input():
    from src.providers.price_history_range import RangeHistoryUnavailableError

    with pytest.raises(RangeHistoryUnavailableError, match="STUB_ONLY"):
        await service().analyze("TEST", sessions=(date(2026, 10, 21),))


@pytest.mark.asyncio
async def test_provider_gets_one_union_and_no_result_cache():
    raw = raw_history()

    class Provider:
        def __init__(self):
            self.calls = []

        async def get_price_history_range(self, ticker, *, start, end):
            self.calls.append((ticker, start, end))
            return raw

    provider = Provider()
    runner = service(range_provider=provider)
    sessions = (date(2026, 10, 22), date(2026, 10, 21))
    await runner.analyze("TEST", sessions=sessions)
    await runner.analyze("TEST", sessions=sessions)
    assert provider.calls == [("TEST", date(2024, 10, 21), date(2026, 10, 22))] * 2
    assert not any("cache" in name or "context" in name for name in vars(runner))


@pytest.mark.asyncio
async def test_fixed_origin_bulk_prefix_features_agree():
    from src.tools.technical.chart_analysis.features import calculate_features
    from src.tools.technical.chart_analysis.models import CalculationScope, SeriesInput

    raw = raw_history()
    runner = service()
    target = date(2026, 10, 21)
    row = (await runner.analyze("TEST", sessions=(target,), raw=raw))[0]
    frame = raw.frame.loc[row.analysis.manifest.origin : str(target)]
    scope = CalculationScope(SeriesInput(replace(row.analysis.manifest, input_hash=""), frame), {})
    bulk = calculate_features(scope)
    assert plain(bulk[target]) == plain(row.analysis.features)
    for end in (len(frame) - 5, len(frame) - 1):
        prefix = frame.iloc[:end]
        prefix_scope = CalculationScope(
            SeriesInput(
                replace(scope.primary.manifest, as_of=prefix.index[-1].date(), input_hash=""),
                prefix,
            ),
            {},
        )
        assert plain(calculate_features(prefix_scope)[prefix.index[-1].date()]) == plain(
            bulk[prefix.index[-1].date()]
        )


@pytest.mark.asyncio
async def test_no_common_analysis_persistence(monkeypatch, tmp_path):
    import builtins

    runner = service()
    raw = raw_history()

    def fail(*args, **kwargs):
        raise AssertionError("new result persistence")

    monkeypatch.setattr(builtins, "open", fail)
    monkeypatch.setattr("pathlib.Path.write_text", fail)
    monkeypatch.setattr("pathlib.Path.write_bytes", fail)
    rows = await runner.analyze("TEST", sessions=(date(2026, 10, 21),), raw=raw)
    assert rows[0].quality.quality is not None
    assert not list(tmp_path.iterdir())


def test_strict_breakout_event_onset_false_condition_and_preview():
    from src.tools.technical.chart_analysis.registry import rule_request
    from src.tools.technical.chart_analysis.service import AnalysisRequestContext
    from tests.tools.technical.chart_analysis.test_features import bars, scope_for

    frame = bars([100.0] * 23 + [103.0, 104.0])
    rule = (rule_request("chart.close_breakout.strict"),)
    context = AnalysisRequestContext()
    before = context.get(scope_for(frame.iloc[:23]), rule)
    onset = context.get(scope_for(frame.iloc[:24]), rule)
    continued = context.get(scope_for(frame), rule)
    assert before.items == (), "false conditions cannot become events"
    assert continued.items == (), "only false-to-true onset emits an event"
    assert len(onset.items) == 1
    event = onset.items[0]
    assert event.kind == "EVENT" and event.state == "DETECTED"
    assert event.occurred_on == event.confirmed_on == frame.index[23].date()
    assert event.status_as_of == event.occurred_on and event.finality == "FINAL"
    mask = {stamp.date(): "FINAL" for stamp in frame.index[:24]}
    mask[frame.index[23].date()] = "PROVISIONAL"
    preview = context.get(scope_for(frame.iloc[:24], finality=mask), rule).items[0]
    assert preview.kind == "EVENT" and preview.finality == "PROVISIONAL"
    assert preview.id == event.id and preview.evaluation_key != event.evaluation_key
    incomplete = dict(mask)
    incomplete[frame.index[20].date()] = "UNKNOWN"
    unavailable = context.get(scope_for(frame.iloc[:24], finality=incomplete), rule)
    assert all(item.kind != "EVENT" for item in unavailable.items)


@pytest.mark.asyncio
async def test_service_delta_keeps_date_specific_origins_and_checks_provenance():
    from src.tools.technical.chart_analysis.quality import explain_delta

    before, after = await service().analyze(
        "TEST", sessions=(date(2026, 10, 21), date(2026, 10, 22)), raw=raw_history()
    )
    assert before.analysis.manifest.origin != after.analysis.manifest.origin
    assert explain_delta(before.quality, after.quality).quality == pytest.approx(
        after.quality.quality - before.quality.quality
    )
    for field, changed, reason in (
        ("provider", "OTHER", "PROVIDER_MISMATCH"),
        ("timezone", "Asia/Seoul", "TIMEZONE_MISMATCH"),
        ("revision_if_known", "revision-2", "REVISION_MISMATCH"),
        ("revision_if_known", None, "REVISION_MISMATCH"),
    ):
        modified = replace(
            after.quality, manifest=replace(after.quality.manifest, **{field: changed})
        )
        delta = explain_delta(before.quality, modified)
        assert delta.quality is None and reason in delta.reasons
    unknown = [
        replace(
            row.quality,
            manifest=replace(
                row.quality.manifest, provider=None, timezone=None, revision_if_known=None
            ),
        )
        for row in (before, after)
    ]
    assert explain_delta(*unknown).quality is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "listing,expected_start",
    [
        (date(2024, 1, 2), date(2024, 10, 21)),
        (date(2026, 2, 2), date(2026, 2, 2)),
    ],
)
async def test_listing_coverage_preserves_nominal_effective_boundaries_and_identity(
    listing, expected_start
):
    runner = service(listing_first_session=listing)
    target = date(2026, 10, 21)
    single = (await runner.analyze("TEST", sessions=(target,), raw=raw_history()))[0]
    history = await runner.analyze("TEST", sessions=(date(2026, 10, 22), target), raw=raw_history())
    assert plain(single) == plain(history[1])
    manifest = single.analysis.manifest
    assert manifest.coverage["calendar_start"] == date(2024, 10, 21)
    assert manifest.coverage["input_start"] == expected_start
    assert manifest.coverage["requested_start"] == expected_start
    assert manifest.coverage["listing_first_session"] == listing
    assert manifest.origin == str(expected_start)


@pytest.mark.asyncio
async def test_non_session_request_does_not_change_calculation_identity():
    runner = service()
    raw = raw_history()
    friday, sunday = date(2026, 10, 23), date(2026, 10, 25)
    rows = await runner.analyze("TEST", sessions=(friday, sunday), raw=raw)
    assert rows[0].requested_as_of == friday
    assert rows[1].requested_as_of == sunday
    assert rows[0].analysis.manifest.as_of == rows[1].analysis.manifest.as_of == friday
    assert plain((rows[0].analysis, rows[0].quality)) == plain((rows[1].analysis, rows[1].quality))

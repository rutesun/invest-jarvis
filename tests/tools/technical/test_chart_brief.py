"""표시 재료는 기존 지표를 재사용하고 시간·결측 경계를 보존한다."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.tools.technical.chart_analysis.models import ChartAnalysis, InputManifest
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult


def technical(*, finality="FINAL", n=30):
    index = pd.bdate_range("2026-09-01", periods=n)
    df = pd.DataFrame(
        {
            "Close": [100.0, 102.0] * (n // 2),
            "High": 110.0,
            "Low": 90.0,
            "Volume": 10.0,
            "SMA_20": 105.0,
            "SMA_50": 110.0,
            "SMA_150": 95.0,
            "SMA_200": 90.0,
            "cRSI": 24.0,
            "cRSI_LowBand": 30.0,
            "cRSI_HighBand": 72.0,
        },
        index=index,
    )
    manifest = InputManifest(
        ticker="TEST",
        exchange="XNAS",
        as_of=index[-1].date(),
        origin=str(index[0].date()),
        input_profile="TEST",
        feature_version="TEST",
        input_hash="",
        adjustment_policy="TEST",
        calendar_version="TEST",
        finality=finality,
        coverage={},
    )
    analysis = ChartAnalysis("test", manifest, {}, {}, ())
    return TechnicalResult(
        ticker="TEST",
        timestamp=datetime(2026, 11, 5),
        components={},
        raw_dataframe=df,
        snapshot=IndicatorSnapshot(
            price=102,
            change_pct=2.0,
            sma_20=105.0,
            sma_50=110.0,
            sma_150=95.0,
            sma_200=90.0,
            sma_20_slope_pct=-0.6,
            sma_50_slope_pct=-0.5,
            sma_150_slope_pct=0.6,
            sma_200_slope_pct=0.5,
            crsi=24.0,
            crsi_low_band=30.0,
            crsi_high_band=72.0,
        ),
        common_analyses=(analysis,),
    )


def build(tech):
    from src.tools.technical.chart_brief import build_chart_brief

    return build_chart_brief(tech)


def test_snapshot_slope_thresholds_dynamic_bands_and_current_array_are_distinct():
    brief = build(technical())
    assert [ma["direction"] for ma in brief["moving_averages"]] == ["down", "flat", "up", "flat"]
    assert brief["trends"] == {"short": "mixed", "long": "mixed"}
    assert brief["arrays"]["50_200"] == "above"
    assert brief["events"] == []  # above now does not prove a golden cross
    assert brief["crsi"] == {
        "value": 24.0,
        "low": 30.0,
        "high": 72.0,
        "state": "oversold",
        "reason": None,
    }
    assert brief["moving_averages"][0]["distance_pct"] == pytest.approx(-2.857142857)
    assert brief["as_of"] == "2026-10-12" and brief["finality"] == "FINAL"


def test_volume_uses_20_days_and_the_previous_21st_close_excludes_flat():
    tech = technical()
    tech.raw_dataframe.loc[:, "Close"] = [100.0] * 9 + [100.0, 101.0, 100.0] + [100.0] * 18
    tech.raw_dataframe.iloc[10, tech.raw_dataframe.columns.get_loc("Volume")] = 30
    tech.snapshot.price = 100
    volume = build(tech)["volume"]
    assert volume["up_pct"] == 75.0 and volume["down_pct"] == 25.0
    assert volume["flat_days"] == 18
    tech.raw_dataframe = tech.raw_dataframe.iloc[-20:]
    assert build(tech)["volume"]["reason"]


@pytest.mark.parametrize("bad", [float("nan"), -1.0, float("inf")])
def test_invalid_volume_is_unavailable_without_filling_or_ignoring(bad):
    tech = technical()
    tech.raw_dataframe.iloc[-5, tech.raw_dataframe.columns.get_loc("Volume")] = bad
    assert build(tech)["volume"]["up_pct"] is None
    assert build(tech)["volume"]["reason"]


def test_zero_directional_volume_and_missing_indicators_are_explicit():
    tech = technical()
    tech.raw_dataframe.loc[:, "Close"] = 102.0
    tech.snapshot.sma_200 = None
    tech.snapshot.crsi_high_band = None
    brief = build(tech)
    assert brief["volume"]["reason"]
    assert brief["moving_averages"][-1]["direction"] == "unavailable"
    assert brief["trends"]["long"] == "unavailable"
    assert brief["crsi"]["state"] == "unavailable"


def test_cross_events_have_own_date_finality_and_latest_two_limit():
    tech = technical()
    df = tech.raw_dataframe
    df.loc[:, "SMA_20"] = 120.0
    df.iloc[-3:, df.columns.get_loc("SMA_20")] = 100.0
    df.iloc[-2:, df.columns.get_loc("cRSI")] = 40.0
    tech.snapshot.crsi = 40.0
    from dataclasses import replace

    finality = {d.date(): "FINAL" for d in df.index}
    finality[df.index[-1].date()] = "PROVISIONAL"
    tech.common_analyses = (
        replace(
            tech.common_analyses[0],
            manifest=replace(tech.common_analyses[0].manifest, finality=finality),
        ),
    )
    brief = build(tech)
    assert [e["kind"] for e in brief["events"]] == ["short_cross_down", "crsi_oversold_recovery"]
    assert brief["events"][0]["date"] == str(df.index[-3].date())
    assert all(e["finality"] == "FINAL" for e in brief["events"])
    assert brief["finality"] == "PROVISIONAL"


def test_nan_between_values_does_not_create_cross_or_band_event():
    tech = technical()
    df = tech.raw_dataframe
    df.loc[:, "SMA_20"] = 120.0
    df.iloc[-2:, df.columns.get_loc("SMA_20")] = [np.nan, 100.0]
    df.iloc[-2:, df.columns.get_loc("cRSI")] = [np.nan, 40.0]
    tech.snapshot.crsi = 40.0
    assert build(tech)["events"] == []


def test_recent_events_only_use_last_20_returned_bars():
    tech = technical()
    tech.raw_dataframe.loc[:, "SMA_20"] = [120.0] * 2 + [100.0] * 28
    assert build(tech)["events"] == []


def test_confirmed_pivots_use_confirmation_date_and_known_final_contiguous_bars():
    tech = technical()
    df = tech.raw_dataframe
    df.iloc[4, df.columns.get_loc("High")] = 130.0
    df.iloc[14, df.columns.get_loc("High")] = 120.0
    df.iloc[6, df.columns.get_loc("Low")] = 70.0
    df.iloc[16, df.columns.get_loc("Low")] = 80.0
    structure = build(tech)["structure"]
    assert structure["high"]["previous"] == 130.0 and structure["high"]["value"] == 120.0
    assert structure["high"]["confirmed_on"] == str(df.index[17].date())
    assert structure["low"]["direction"] == "up"
    tech.common_analyses = ()
    assert build(tech)["structure"]["high"] is None
    assert build(tech)["finality"] == "UNKNOWN"


def test_unknown_bar_in_confirmation_window_never_becomes_confirmed_pivot():
    from dataclasses import replace

    tech = technical()
    df = tech.raw_dataframe
    df.iloc[14, df.columns.get_loc("High")] = 120.0
    finality = {d.date(): "FINAL" for d in df.index}
    finality[df.index[16].date()] = "UNKNOWN"
    tech.common_analyses = (
        replace(
            tech.common_analyses[0],
            manifest=replace(tech.common_analyses[0].manifest, finality=finality),
        ),
    )
    assert build(tech)["structure"]["high"] is None


def test_scorecard_boundary_rejects_future_or_stale_snapshot_without_mutation():
    from tests.pipelines.test_observation_story import alab

    tech = technical()
    before = tech.raw_dataframe.copy(deep=True)
    tech.scorecard = alab().scorecard.model_copy(update={"as_of": before.index[-2].date()})
    brief = build(tech)
    assert brief["reason"] and brief["moving_averages"] == []
    assert brief["events"] == []
    pd.testing.assert_frame_equal(tech.raw_dataframe, before)
    tech.scorecard = tech.scorecard.model_copy(
        update={"as_of": before.index[-1].date() + pd.Timedelta(days=1)}
    )
    assert build(tech)["reason"]


def test_invalid_current_row_is_not_silently_replaced_by_older_snapshot():
    tech = technical()
    tech.raw_dataframe.iloc[-1, tech.raw_dataframe.columns.get_loc("Close")] = np.nan
    assert build(tech)["reason"]
    tech.raw_dataframe = None
    assert build(tech)["as_of"] is None
    assert build(tech)["reason"]


@pytest.mark.parametrize("column,attr", [("SMA_50", "sma_50"), ("cRSI", "crsi")])
def test_invalid_latest_raw_indicator_does_not_reuse_snapshot_value(column, attr):
    tech = technical()
    tech.raw_dataframe.iloc[-1, tech.raw_dataframe.columns.get_loc(column)] = np.nan
    brief = build(tech)
    if attr == "crsi":
        assert brief["crsi"]["state"] == "unavailable"
    else:
        assert brief["moving_averages"][1]["value"] is None
        assert brief["moving_averages"][1]["reason"]


@pytest.mark.parametrize("direction", ["up", "down"])
def test_50_200_cross_event_is_not_the_short_cross(direction):
    tech = technical()
    frame = tech.raw_dataframe
    before, after = (80.0, 110.0) if direction == "up" else (110.0, 80.0)
    frame.loc[:, "SMA_50"] = before
    frame.iloc[-1, frame.columns.get_loc("SMA_50")] = after
    events = build(tech)["events"]
    assert any(event["kind"] == f"long_cross_{direction}" for event in events)
    assert any(
        ("골든크로스" if direction == "up" else "데드크로스") in event["label"] for event in events
    )


def test_events_keep_only_latest_two_changes():
    tech = technical()
    frame = tech.raw_dataframe
    frame.iloc[-3:, frame.columns.get_loc("cRSI")] = [40.0, 20.0, 40.0]
    assert [event["kind"] for event in build(tech)["events"]] == [
        "crsi_oversold_entry",
        "crsi_oversold_recovery",
    ]


def test_unmatched_manifest_never_promotes_unknown_finality():
    from dataclasses import replace

    tech = technical()
    original = tech.common_analyses[0]
    tech.common_analyses = (
        replace(
            original,
            manifest=replace(
                original.manifest, as_of=original.manifest.as_of - pd.Timedelta(days=1)
            ),
        ),
    )
    assert build(tech)["finality"] == "UNKNOWN"
    tech.common_analyses = (replace(original, manifest=replace(original.manifest, ticker="OTHER")),)
    assert build(tech)["finality"] == "UNKNOWN"


@pytest.mark.parametrize(
    "previous,current,want",
    [
        ("UNKNOWN", "FINAL", "UNKNOWN"),
        ("PROVISIONAL", "FINAL", "PROVISIONAL"),
        ("FINAL", "PROVISIONAL", "PROVISIONAL"),
    ],
)
def test_event_finality_preserves_both_adjacent_input_states(previous, current, want):
    from dataclasses import replace

    tech = technical()
    frame = tech.raw_dataframe
    frame.iloc[-1, frame.columns.get_loc("SMA_20")] = 120.0
    states = {day.date(): "FINAL" for day in frame.index}
    states[frame.index[-2].date()] = previous
    states[frame.index[-1].date()] = current
    analysis = tech.common_analyses[0]
    tech.common_analyses = (
        replace(analysis, manifest=replace(analysis.manifest, finality=states)),
    )
    event = build(tech)["events"][-1]
    assert event["date"] == str(frame.index[-1].date())
    assert event["finality"] == want


def test_same_day_strategy_manifest_enriches_unknown_without_promoting_conflicts():
    from dataclasses import replace

    from src.tools.technical.chart_brief import build_chart_brief

    tech = technical(finality="UNKNOWN")
    original = tech.common_analyses[0]
    known = replace(original, manifest=replace(original.manifest, finality="FINAL"))
    assert build_chart_brief(tech, common_analyses=(known,))["finality"] == "FINAL"
    assert tech.common_analyses[0].manifest.finality == "UNKNOWN"
    partial = {day.date(): "FINAL" for day in tech.raw_dataframe.index}
    partial[tech.raw_dataframe.index[-1].date()] = "PROVISIONAL"
    preview = replace(known, manifest=replace(known.manifest, finality=partial))
    assert build_chart_brief(tech, common_analyses=(preview,))["finality"] == "PROVISIONAL"
    assert build_chart_brief(tech, common_analyses=(known, preview))["finality"] == "UNKNOWN"
    stale = replace(
        known, manifest=replace(known.manifest, as_of=known.manifest.as_of - pd.Timedelta(days=1))
    )
    other = replace(known, manifest=replace(known.manifest, ticker="OTHER"))
    assert build_chart_brief(tech, common_analyses=(stale, other))["finality"] == "UNKNOWN"


def alab_headline_technical():
    """검토 HTML의 11/04 ALAB 가격·MA·slope 조건. 과거 봉은 synthetic fixture다."""
    from dataclasses import replace

    tech = technical()
    tech.ticker = "ALAB"
    tech.raw_dataframe.index = pd.bdate_range(end="2026-11-04", periods=30)
    tech.raw_dataframe.loc[:, "Close"] = 223.27
    values = {20: (284.12, -13.45), 50: (304.94, -2.33), 150: (296.38, 8.75), 200: (255.97, 5.16)}
    tech.snapshot.price = 223.27
    for period, (value, slope) in values.items():
        setattr(tech.snapshot, f"sma_{period}", value)
        setattr(tech.snapshot, f"sma_{period}_slope_pct", slope)
        tech.raw_dataframe.loc[:, f"SMA_{period}"] = value
    original = tech.common_analyses[0]
    tech.common_analyses = (
        replace(
            original,
            manifest=replace(
                original.manifest, ticker="ALAB", as_of=tech.raw_dataframe.index[-1].date()
            ),
        ),
    )
    return tech


@pytest.mark.parametrize(
    "price,missing,expected",
    [
        (223.27, False, "단기선 하락 · 장기선 상승 · 주가 150일선 아래"),
        (400.0, False, "단기선 하락 · 장기선 상승 · 주가 150일선 위"),
        (296.38, False, "단기선 하락 · 장기선 상승 · 주가 150일선 일치"),
        (223.27, True, "단기선 하락 · 장기선 미산출 · 주가 150일선 위치 미산출"),
    ],
)
def test_headline_names_ma_direction_and_price_position_separately(price, missing, expected):
    tech = alab_headline_technical()
    tech.snapshot.price = price
    tech.raw_dataframe.loc[:, "Close"] = price
    if missing:
        tech.snapshot.sma_150 = None
    brief = build(tech)
    assert brief["headline"] == expected
    if price == 223.27 and not missing:
        assert brief["trends"] == {"short": "down", "long": "up"}
        assert brief["moving_averages"][2]["distance_pct"] == pytest.approx(-24.66765638)
        assert all(ma["distance_pct"] < 0 for ma in brief["moving_averages"])


def test_headline_also_names_mixed_moving_average_direction():
    assert build(technical())["headline"] == "단기선 혼조 · 장기선 혼조 · 주가 150일선 위"

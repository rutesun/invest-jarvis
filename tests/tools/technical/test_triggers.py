import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorecard import build_scorecard
from src.tools.technical.scorecard_models import TriggerStatus
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.trigger_registry import TRIGGER_RULES
from src.tools.technical.triggers import detect_analysis_triggers


def make_cross_df(short: int, long: int) -> pd.DataFrame:
    index = pd.bdate_range("2025-01-01", periods=230)
    data = {"Close": [100.0] * len(index), "High": [101.0] * len(index)}
    for length in (20, 50, 150, 200):
        data[f"SMA_{length}"] = [100.0] * len(index)
    data[f"SMA_{short}"] = [99.0] * 225 + [101.0] * 5
    return pd.DataFrame(data, index=index)


@pytest.mark.parametrize("short,long", [(20, 50), (50, 150), (50, 200), (150, 200)])
def test_sma_cross_is_emitted_once_on_transition(short: int, long: int):
    df = make_cross_df(short, long)
    events = detect_analysis_triggers(df, as_of=df.index[-1].date())
    code = f"analysis.sma.{short}_{long}.golden_cross"
    matches = [event for event in events if event.code == code]
    assert len(matches) == 1
    assert matches[0].occurred_on == df.index[-5].date()
    assert matches[0].bars_ago == 4


def test_sma_turn_uses_scorecard_twenty_one_session_slope_not_one_day_bounce():
    df = make_cross_df(20, 50)
    df["SMA_20"] = [300.0 - i for i in range(len(df))]
    df.loc[df.index[-1], "SMA_20"] = df.iloc[-2]["SMA_20"] + 0.5
    assert df.iloc[-1]["SMA_20"] - df.iloc[-22]["SMA_20"] == -19.5

    events = detect_analysis_triggers(df, as_of=df.index[-1].date())

    assert not any(e.code == "analysis.sma.20.turn_up" for e in events)


def test_sma_turn_detects_twenty_one_session_transition_despite_last_day_decline():
    df = make_cross_df(20, 50)
    df["SMA_20"] = 100.0
    df.loc[df.index[-22], "SMA_20"] = 80.0
    df.loc[df.index[-2], "SMA_20"] = 99.0
    df.loc[df.index[-1], "SMA_20"] = 98.0
    assert df.iloc[-2]["SMA_20"] - df.iloc[-23]["SMA_20"] == -1.0
    assert df.iloc[-1]["SMA_20"] - df.iloc[-22]["SMA_20"] == 18.0

    events = detect_analysis_triggers(df, as_of=df.index[-1].date())

    assert any(e.code == "analysis.sma.20.turn_up" and e.bars_ago == 0 for e in events)
    rule = next(rule for rule in TRIGGER_RULES if rule.code == "analysis.sma.20.turn_up")
    assert rule.lookback_bars == 21
    assert "21-session" in rule.occurrence_predicate
    assert "21-session" in rule.invalidation_predicate
    assert "t-22" in rule.occurrence_predicate


def test_prefix_event_does_not_read_future_bars():
    df = make_cross_df(20, 50)
    cutoff = df.index[-3]
    prefix = detect_analysis_triggers(df.loc[:cutoff], as_of=cutoff.date())
    full_at_cutoff = detect_analysis_triggers(df, as_of=cutoff.date())
    assert prefix == full_at_cutoff


def test_undated_rows_cannot_claim_exchange_session_events():
    df = make_cross_df(20, 50).reset_index(drop=True)
    assert detect_analysis_triggers(df, as_of=pd.Timestamp("2025-12-31").date()) == []


def test_twenty_day_high_uses_intraday_high_like_pattern_component():
    df = make_cross_df(20, 50)
    df["High_20_Prev"] = 102.0
    df.loc[df.index[-1], "High"] = 105.0
    events = detect_analysis_triggers(df, as_of=df.index[-1].date())
    event = next(e for e in events if e.code == "analysis.price.high_20_breakout")
    assert event.observed_value == 105.0
    assert event.reference_value == 102.0


def test_supertrend_requires_actual_opposite_direction_before_flip():
    df = make_cross_df(20, 50)
    df["SuperTrend_Dir"] = 0.0
    df.loc[df.index[-1], "SuperTrend_Dir"] = 1.0
    assert not any(
        e.code == "analysis.supertrend.turn_up"
        for e in detect_analysis_triggers(df, as_of=df.index[-1].date())
    )
    df.loc[df.index[-2], "SuperTrend_Dir"] = -1.0
    assert any(
        e.code == "analysis.supertrend.turn_up"
        for e in detect_analysis_triggers(df, as_of=df.index[-1].date())
    )


def test_crsi_hook_requires_strict_previous_band_breach():
    df = make_cross_df(20, 50)
    df["cRSI"] = 50.0
    df["cRSI_HighBand"] = 70.0
    df["cRSI_LowBand"] = 30.0
    df.loc[df.index[-2], "cRSI"] = 70.0
    df.loc[df.index[-1], "cRSI"] = 69.0
    assert not any(
        e.code == "analysis.crsi.upper_band_exit"
        for e in detect_analysis_triggers(df, as_of=df.index[-1].date())
    )
    df.loc[df.index[-2], "cRSI"] = 71.0
    assert any(
        e.code == "analysis.crsi.upper_band_exit"
        for e in detect_analysis_triggers(df, as_of=df.index[-1].date())
    )


def test_invalidated_event_remains_visible_inside_twenty_bars():
    df = make_cross_df(20, 50)
    df.loc[df.index[-2], "SMA_20"] = 98.0
    df.loc[df.index[-1], "SMA_20"] = 98.0
    events = detect_analysis_triggers(df, as_of=df.index[-1].date())
    event = next(e for e in events if e.code == "analysis.sma.20_50.golden_cross")
    assert event.status is TriggerStatus.INVALIDATED
    assert event.invalidated_on == df.index[-2].date()
    assert event.status_as_of == df.index[-1].date()


def test_twenty_bar_display_boundary_includes_age_twenty_only():
    df = make_cross_df(20, 50)
    df.loc[df.index[-21] :, "SMA_20"] = 101.0
    events = detect_analysis_triggers(df, as_of=df.index[-1].date())
    assert any(e.code == "analysis.sma.20_50.golden_cross" and e.bars_ago == 20 for e in events)
    assert not any(e.bars_ago > 20 for e in events)
    assert not any(
        e.code == "analysis.sma.20_50.golden_cross"
        for e in detect_analysis_triggers(df, as_of=df.index[-1].date(), display_bars=19)
    )


def test_power_gap_expires_after_five_completed_sessions_without_breakdown():
    df = make_cross_df(20, 50)
    df["Open"] = 100.0
    df["Volume"] = 100.0
    df["Vol_SMA_20"] = 100.0
    event_day = df.index[-7]
    df.loc[event_day, ["Open", "High", "Close", "Volume"]] = [106.0, 107.0, 106.0, 400.0]
    df.loc[df.index[-6] :, "Close"] = 106.0
    events = detect_analysis_triggers(df, as_of=df.index[-1].date())
    event = next(e for e in events if e.code == "analysis.volume.power_gap_up")
    assert event.occurred_on == event_day.date()
    assert event.bars_ago == 6
    assert event.status is TriggerStatus.EXPIRED
    assert event.expired_on == df.index[-1].date()


@pytest.mark.parametrize(
    ("source", "left", "right", "code"),
    [
        ("macd", "MACD", "MACD_Signal", "analysis.macd.golden_cross"),
        ("fast_macd", "MACD_Fast", "MACD_Fast_Signal", "analysis.fast_macd.golden_cross"),
        ("macd_hist", "MACD_Hist", None, "analysis.macd_hist.positive_cross"),
        ("fast_macd_hist", "MACD_Fast_Hist", None, "analysis.fast_macd_hist.positive_cross"),
        ("price", "Close", "SMA_200", "analysis.price.sma200_cross_above"),
    ],
)
def test_indicator_cross_families_emit_observed_transition(source, left, right, code):
    df = make_cross_df(20, 50)
    df[left] = -1.0 if right is None else 99.0
    if right is not None:
        df[right] = 100.0
    df.loc[df.index[-1], left] = 1.0 if right is None else 101.0
    events = detect_analysis_triggers(df, as_of=df.index[-1].date())
    assert [e.code for e in events].count(code) == 1


def test_vcp_breakout_reuses_contraction_component_then_invalidates():
    df = make_cross_df(20, 50)
    df["Low"] = 99.0
    df["ATR"] = 10.0
    df.loc[df.index[-4] :, "ATR"] = 5.0
    df["High_20_Prev"] = 102.0
    df.loc[df.index[-2], ["Close", "High"]] = [104.0, 105.0]
    df.loc[df.index[-1], "Close"] = 100.0
    events = detect_analysis_triggers(df, as_of=df.index[-1].date())
    event = next(e for e in events if e.code == "analysis.patterns.vcp_breakout")
    assert event.occurred_on == df.index[-2].date()
    assert event.status is TriggerStatus.INVALIDATED
    assert event.invalidated_on == df.index[-1].date()


def test_pocket_pivot_reuses_volume_component():
    df = make_cross_df(20, 50)
    df["Open"] = 101.0
    df["Volume"] = 100.0
    df.loc[df.index[-1], "Volume"] = 200.0
    events = detect_analysis_triggers(df, as_of=df.index[-1].date())
    assert any(e.code == "analysis.volume.pocket_pivot" for e in events)


def test_pocket_pivot_is_active_at_age_seven_and_expires_after_ten_completed_sessions():
    df = make_cross_df(20, 50)
    df["Open"] = 101.0
    df["Volume"] = 100.0
    event_day = df.index[-12]
    df.loc[event_day, "Volume"] = 200.0

    at_seven = detect_analysis_triggers(df, as_of=df.index[-5].date())
    at_eleven = detect_analysis_triggers(df, as_of=df.index[-1].date())
    active = next(e for e in at_seven if e.code == "analysis.volume.pocket_pivot")
    expired = next(e for e in at_eleven if e.code == "analysis.volume.pocket_pivot")

    assert active.occurred_on == event_day.date()
    assert active.bars_ago == 7
    assert active.status is TriggerStatus.ACTIVE
    assert active.expires_after_bars == 10
    assert expired.bars_ago == 11
    assert expired.status is TriggerStatus.EXPIRED
    assert expired.expired_on == df.index[-1].date()


def test_volume_breakdown_reuses_market_context():
    df = make_cross_df(20, 50)
    df["Volume"] = 100.0
    df["Vol_SMA_20"] = 100.0
    df.loc[df.index[-1], ["Close", "Volume"]] = [90.0, 200.0]
    events = detect_analysis_triggers(df, as_of=df.index[-1].date())
    event = next(e for e in events if e.code == "analysis.volume.breakdown")
    assert event.direction.value == "falling"
    assert event.status is TriggerStatus.ACTIVE


def test_scorecard_populates_real_analysis_events():
    index = pd.bdate_range("2025-01-01", periods=230)
    raw = pd.DataFrame(
        {
            "Open": [100.0] * 230,
            "High": [101.0] * 230,
            "Low": [99.0] * 230,
            "Close": [100.0] * 230,
            "Volume": [1_000_000.0] * 230,
        },
        index=index,
    )
    calculated = IndicatorCalculator().calculate(raw)
    calculated.loc[index[-5] :, "SMA_20"] = 101.0
    calculated.loc[index[-6], "SMA_20"] = 99.0
    legacy = TechnicalScorer().score(calculated, ticker="AAPL", include_history=False)

    result = build_scorecard(calculated, legacy, ticker="AAPL", as_of=index[-1].date())

    assert any(e.code == "analysis.sma.20_50.golden_cross" for e in result.triggers)
    assert all(e.source not in {"swing_w150", "overheat_cycle"} for e in result.triggers)


def test_registry_declares_all_required_metadata_and_no_strategy_events():
    assert len({rule.code for rule in TRIGGER_RULES}) == len(TRIGGER_RULES)
    for rule in TRIGGER_RULES:
        assert rule.code.startswith("analysis.")
        assert rule.trigger_version and rule.required_inputs
        assert rule.occurrence_predicate and rule.equality_policy
        assert rule.invalidation_predicate is not None
        assert rule.event_date_rule and rule.source and rule.missing_policy
        assert "swing_w150" not in rule.code and "overheat_cycle" not in rule.code

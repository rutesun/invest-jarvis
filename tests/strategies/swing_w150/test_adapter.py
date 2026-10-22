from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from src.strategies.chart_bundle import chart_bundle_from_dataframes
from src.strategies.models import (
    CoverageManifest,
    EntryIntent,
    ExitIntent,
    SignalFinality,
    SwingRuntimeState,
)
from src.strategies.swing_w150 import adapter as swing_adapter
from src.strategies.swing_w150 import rules
from src.strategies.swing_w150.adapter import SwingW150SignalStrategy, SwingW150Strategy
from src.strategies.swing_w150.engine import _replay, _walk
from src.strategies.swing_w150.features import build_swing_features
from src.strategies.swing_w150.models import SwingReplayEvent, SwingReplayTrace
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.strategies.swing_w150.signals import detect_swing
from src.tools.technical.scorecard_models import DataStatus


def _bundle(
    frame: pd.DataFrame,
    *,
    complete: bool = True,
    requested_start: date | None = None,
    listing_first_session: date | None = None,
    market: pd.DataFrame | None = None,
    observed_at: datetime | None = None,
):
    days = tuple(day.date() for day in frame.index)
    coverage = CoverageManifest(
        requested_start=requested_start or days[0],
        actual_start=days[0],
        actual_end=days[-1],
        expected_sessions=days,
        complete=complete,
        truncation_reason=None if complete else "provider_limit",
        listing_first_session=listing_first_session,
    )
    return chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="COIN",
        as_of=days[-1],
        instrument=frame,
        instrument_coverage=coverage,
        exchange_sessions=days,
        market=market,
        market_coverage=coverage if market is not None else None,
        observed_at=observed_at,
        **({"market_ticker": "SPY"} if market is not None else {}),
    )


def test_incomplete_v2_is_rejected_without_v1_fallback():
    from src.strategies.swing_w150.parameters import SwingW150ParametersV2

    with pytest.raises(ValueError, match="UNRESOLVED.*immediate"):
        SwingW150SignalStrategy(SwingW150ParametersV2())


def test_explicit_v2_selection_reaches_bundle_and_keeps_observation_independence(v2_raw_fixture):
    from src.strategies.swing_w150.parameters import SupportCycleParameters, SwingW150ParametersV2

    params = SwingW150ParametersV2(
        support_cycle=SupportCycleParameters(
            normal_failure_closes=2,
            immediate_failure_volume_ratio=2,
            immediate_failure_close_location=0.25,
            support_break_buffer_atr=0,
            restart_mode="D",
        )
    )
    bundle = _bundle(v2_raw_fixture)
    on = SwingW150SignalStrategy(params).evaluate_signals(bundle)
    off = SwingW150SignalStrategy(params, observations_enabled=False).evaluate_signals(bundle)
    assert on.parameter_set_version == "SWING_W150_V2_PARAMS_V2"
    assert on.up_cycle is not None
    assert on.support_tests is not None
    assert on.signal_history == off.signal_history
    assert on.entry_opportunity == off.entry_opportunity
    assert on.up_cycle == off.up_cycle
    assert on.support_tests == off.support_tests


def test_v1_payload_fingerprint_and_non_gate_product_projection_remain_frozen():
    import json
    from pathlib import Path

    from scripts.research_trading_observations import replay_product_projection

    assert SwingW150SignalStrategy().parameters.parameter_fingerprint == (
        "3dca481189c1263c57ac26544fceb43cb2447e17923f890f3f65a30b0b0342f2"
    )
    products = Path("tmp/trading_observation_v1/baseline/products")
    records = list(products.glob("*.json"))
    if not records:
        pytest.skip("frozen Task0 local product records are unavailable")
    evaluated = 0
    for path in records:
        record = json.loads(path.read_text())
        if "projection" in record:
            actual = replay_product_projection(record)
            expected = record["projection"]
            assert {key: value for key, value in actual.items() if key != "entry_opportunity"} == {
                key: value for key, value in expected.items() if key != "entry_opportunity"
            }, path.name
            assert (
                actual["entry_opportunity"]["policy_version"]
                == "SWING_W150_ENTRY_OPPORTUNITY_PRODUCTION_V2"
            )
            old_gate = json.loads(
                json.dumps(expected["entry_opportunity"]).replace(
                    "SWING_W150_ENTRY_OPPORTUNITY_PRODUCTION_V1",
                    "SWING_W150_ENTRY_OPPORTUNITY_PRODUCTION_V2",
                )
            )
            new_gate = actual["entry_opportunity"]
            if path.name == "INTC.json":
                # Only this frozen record has a representative changed by same-day priority.
                assert old_gate["entry_signal"]["code"] == "TREND_BREAKOUT_ENTRY"
                assert old_gate["entry_signal"]["occurred_on"] == "2025-12-02"
                same_day = [
                    signal
                    for signal in expected["signal_history"]
                    if signal["occurred_on"] == "2025-12-02"
                ]
                assert {signal["code"] for signal in same_day} == {
                    "PULLBACK_REVERSAL_ENTRY",
                    "TREND_BREAKOUT_ENTRY",
                }
                preferred = next(
                    signal for signal in same_day if signal["code"] == "PULLBACK_REVERSAL_ENTRY"
                )
                assert new_gate["entry_signal"] == preferred
                changed = {"entry_signal", "anchors"}
                assert {k: v for k, v in new_gate.items() if k not in changed} == {
                    k: v for k, v in old_gate.items() if k not in changed
                }, path.name
                assert new_gate["anchors"] == old_gate["anchors"] | {
                    "source_id": preferred["signal_id"],
                    "source_type": "PULLBACK_REVERSAL_ENTRY",
                    "breakout_level": None,
                    "origin_support": "36.50060009002686",
                    "pullback_low": "37.34000015258789",
                }
            elif new_gate["evidence"][0]["code"] != "BREAKOUT_ATR_INVALIDATED":
                assert new_gate == old_gate, path.name
            else:
                from decimal import Decimal

                assert new_gate["entry_signal"]["code"] == "TREND_BREAKOUT_ENTRY"
                changed = {
                    "status",
                    "structure_status",
                    "evidence",
                    "terminal_on",
                    "terminal_finality",
                    "invalidated_by",
                }
                assert {k: v for k, v in new_gate.items() if k not in changed} == {
                    k: v for k, v in old_gate.items() if k not in changed
                }, path.name
                anchor = new_gate["anchors"]
                threshold = Decimal(anchor["breakout_level"]) - Decimal(anchor["atr_at_signal"])
                bar = next(
                    bar
                    for bar in record["inputs"]["chart_bundle"]["instrument"]["bars"]
                    if bar["session_date"] == new_gate["terminal_on"]
                )
                assert Decimal(bar["close"]) <= threshold
                assert new_gate["status"] == "invalidated"
            evaluated += 1
    assert evaluated > 0


def test_incomplete_rolling_coverage_returns_not_evaluated(golden_case):
    _, frame, _ = golden_case
    frame = frame.loc["2025-01-01":]
    verdict = SwingW150Strategy().evaluate(_bundle(frame, complete=False))
    assert verdict.entry.intent is EntryIntent.NOT_EVALUATED
    assert verdict.exit.intent is ExitIntent.NOT_EVALUATED


def test_missing_exchange_session_cannot_produce_final_structure_observations():
    from src.providers.exchange_calendar import exchange_sessions_for
    from src.strategies.models import EntryOpportunityStatus

    days = exchange_sessions_for("XNYS", date(2025, 1, 2), date(2026, 3, 1))[:270]
    frame = pd.DataFrame(
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 100.0},
        index=pd.to_datetime(days),
    )
    frame.iloc[[252, 258, 264], frame.columns.get_loc("High")] = [106, 108, 110]
    assert days[260] == date(2026, 1, 16)
    frame = frame.drop(pd.Timestamp(days[260]))
    coverage = CoverageManifest(
        requested_start=days[0],
        actual_start=days[0],
        actual_end=days[-1],
        expected_sessions=days,
        complete=False,
        truncation_reason="instrument_history_incomplete",
    )
    bundle = chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="COIN",
        as_of=days[-1],
        instrument=frame,
        instrument_coverage=coverage,
        exchange_sessions=days,
    )
    result = SwingW150SignalStrategy().evaluate_signals(bundle)
    assert result.data_status is DataStatus.PARTIAL
    assert result.signal_history == result.current_signals == []
    assert result.entry_opportunity.status is EntryOpportunityStatus.NOT_EVALUATED
    assert result.observation_history == []


def test_short_complete_window_cannot_claim_a_three_year_origin(golden_case):
    _, frame, _ = golden_case
    verdict = SwingW150Strategy().evaluate(_bundle(frame.loc["2025-01-01":]))
    assert verdict.entry.intent is EntryIntent.NOT_EVALUATED


def test_unverified_late_start_fails_closed(pypl):
    frame, _ = pypl
    short = frame.loc["2025-01-01":]
    verdict = SwingW150Strategy().evaluate(_bundle(short, requested_start=date(2023, 9, 28)))
    assert verdict.entry.intent is EntryIntent.NOT_EVALUATED


def test_verified_young_listing_evaluates(pypl):
    frame, _ = pypl
    short = frame.loc["2025-01-01":]
    first = short.index[0].date()
    bundle = _bundle(short, requested_start=date(2023, 9, 28), listing_first_session=first)
    assert bundle.instrument.coverage.listing_first_session == first
    verdict = SwingW150Strategy().evaluate(bundle)
    assert verdict.entry.intent is not EntryIntent.NOT_EVALUATED


def _runtime_state():
    return SwingRuntimeState(
        state_type="swing_w150",
        state_version="SWING_W150_V1",
        lifecycle="active",
        cycle_phase="active",
        kind="S",
        entry=100,
        stop=94,
        risk=6,
        graduated=True,
        overheat_armed=False,
        previous_below_exit_line=False,
    )


def test_recent_events_are_preserved_and_today_exit_wins(pypl, monkeypatch):
    frame, _ = pypl

    def trace(df):
        end = len(df) - 1
        return SwingReplayTrace(
            (
                SwingReplayEvent("D_ENTRY", end - 21, "D", 100, 94),
                SwingReplayEvent("S_ENTRY", end - 20, "S", 100, 94),
                SwingReplayEvent("OVERHEAT_SELL", end - 2, "S", 100, 94),
                SwingReplayEvent("SMA150_EXIT", end, "S", 100, 94),
            ),
            _runtime_state(),
        )

    monkeypatch.setattr(swing_adapter, "replay_trace", trace)
    verdict = SwingW150Strategy().evaluate(_bundle(frame))
    assert [event.code for event in verdict.events] == [
        "S_ENTRY",
        "OVERHEAT_SELL",
        "SMA150_EXIT",
    ]
    assert verdict.entry.intent is EntryIntent.BLOCK
    assert verdict.exit.intent is ExitIntent.EXIT


def test_historical_entry_event_keeps_signal_close_reference():
    count = 252
    hundred = np.full(count, 100.0)
    trigger = np.zeros(count, dtype=bool)
    trigger[250] = True
    opened = hundred.copy()
    opened[251] = 103
    features = rules.SwingFeatures(
        dates=list(pd.date_range("2025-01-01", periods=count, freq="B").date),
        open=opened,
        high=hundred + 4,
        low=hundred - 1,
        close=hundred,
        sma20=hundred,
        sma50=hundred,
        sma150=hundred,
        slope150=hundred,
        atr=np.full(count, 2.0),
        low20=hundred - 1,
        s_trigger=trigger,
        d_trigger=np.zeros(count, dtype=bool),
        deep=np.zeros(count, dtype=bool),
    )
    events: list[SwingReplayEvent] = []
    _replay(features, events)
    assert events[0].entry == 100
    assert events[0].stop == 94


@pytest.mark.parametrize(("close", "intent"), [(100, EntryIntent.ALLOW), (106, EntryIntent.WATCH)])
def test_signal_two_sessions_ago_rechecks_entry(close, intent, monkeypatch):
    from src.strategies.swing_w150 import engine

    days = pd.date_range("2022-01-03", periods=1100, freq="B")
    frame = pd.DataFrame(
        {
            "Open": [100] * len(days),
            "High": [101] * (len(days) - 1) + [max(101, close + 1)],
            "Low": [99] * len(days),
            "Close": [100] * (len(days) - 1) + [close],
            "Volume": [1000] * len(days),
        },
        index=days,
    )
    market = frame.copy()
    market["Close"] = [90] * (len(days) - 51) + [100] * 50 + [110]

    def trace(df):
        return SwingReplayTrace(
            (SwingReplayEvent("S_ENTRY", len(df) - 3, "S", 100, 94),), _runtime_state()
        )

    monkeypatch.setattr(swing_adapter, "replay_trace", trace)
    monkeypatch.setattr(engine, "replay_trace", trace)
    verdict = SwingW150Strategy().evaluate(_bundle(frame, market=market))
    assert verdict.entry.intent is intent
    assert verdict.entry.opportunity is not None
    assert verdict.entry.opportunity.age_bars == 2


def test_replay_uses_only_the_rolling_origin(golden_case):
    ticker, frame, _ = golden_case
    if ticker != "COIN":
        return
    verdict = SwingW150Strategy().evaluate(_bundle(frame))
    assert verdict.as_of == date(2026, 9, 28)
    assert verdict.strategy_version == "SWING_W150_V1"
    assert verdict.strategy_state is not None
    assert all(event.occurred_on >= date(2023, 9, 28) for event in verdict.events)


def _features(*, low: float):
    data = np.array([100.0, 100.0, 100.0])
    return rules.SwingFeatures(
        dates=[date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)],
        open=data,
        high=data + 2,
        low=np.array([99.0, low, 99.0]),
        close=data,
        sma20=data,
        sma50=data,
        sma150=data,
        slope150=data,
        atr=data,
        low20=data,
        s_trigger=np.array([False] * 3),
        d_trigger=np.array([False] * 3),
        deep=np.array([False] * 3),
    )


def test_stop_short_circuits_later_rules(monkeypatch):
    monkeypatch.setattr(rules, "overheat_armed", lambda *_: True)
    monkeypatch.setattr(rules, "overheat_sell", lambda *_: True)
    events: list[SwingReplayEvent] = []
    _walk(_features(low=90), "S", 1, 100, 95, events)
    assert [event.code for event in events] == ["STOP"]


def test_same_day_overheat_sell_and_sma_exit_are_both_recorded(monkeypatch):
    monkeypatch.setattr(rules, "overheat_armed", lambda *_: True)
    monkeypatch.setattr(rules, "overheat_sell", lambda *_: True)
    monkeypatch.setattr(rules, "below_exit_line", lambda *_: True)
    monkeypatch.setattr(rules, "exit_150", lambda *_: True)
    events: list[SwingReplayEvent] = []
    run = _walk(_features(low=99), "S", 1, 100, 95, events)
    assert run.why == "sma150"
    assert [event.code for event in events] == ["OVERHEAT_SELL", "SMA150_EXIT"]


def test_v2_adapter_assembles_detection_and_opportunity_with_chart_finality(v2_raw_fixture):
    frame = v2_raw_fixture
    market = frame.copy()
    market["Close"] = [90] * (len(frame) - 51) + [100] * 50 + [110]
    observed_at = datetime.combine(frame.index[-1].date(), time(12), ZoneInfo("America/New_York"))
    bundle = _bundle(frame, market=market, observed_at=observed_at)
    result = SwingW150SignalStrategy().evaluate_signals(bundle)
    expected = detect_swing(
        "COIN",
        build_swing_features(
            frame.astype(float),
            SwingW150Parameters(),
            finalities=[bar.finality for bar in bundle.instrument.bars],
        ),
        SwingW150Parameters(),
    )
    assert [item for item in result.observation_history if item.kind == "SETUP"] == (
        expected.observation_history
    )
    assert result.signal_history == expected.signal_history
    assert result.current_signals == expected.current_signals
    assert result.data_status is DataStatus.COMPLETE
    assert result.current_signals[-1].finality is SignalFinality.PROVISIONAL
    assert result.entry_opportunity.finality is SignalFinality.PROVISIONAL
    assert result.entry_opportunity.evidence
    anchors = result.entry_opportunity.anchors
    assert anchors is not None
    assert anchors.source_id == result.entry_opportunity.entry_signal.signal_id
    assert anchors.source_date == result.entry_opportunity.entry_signal.occurred_on
    assert anchors.anchor_finality == result.entry_opportunity.entry_signal.finality


def test_v2_adapter_full_bundle_is_suffix_invariant(v2_raw_fixture):
    frame = v2_raw_fixture
    market = frame.copy()
    market["Close"] = [90] * (len(frame) - 51) + [100] * 50 + [110]
    target_day = frame.index[-2].date()
    prefix = _bundle(frame.iloc[:-1], market=market.iloc[:-1])
    from_future = _bundle(frame, market=market).prefix(target_day)
    expected = SwingW150SignalStrategy().evaluate_signals(prefix)
    actual = SwingW150SignalStrategy().evaluate_signals(from_future)
    assert actual.model_dump(mode="json") == expected.model_dump(mode="json")


def test_shadow_parameters_and_toggle_cannot_change_production_bundle(v2_raw_fixture):
    from decimal import Decimal

    from src.strategies.entry_shadow import EntryShadowParameters

    market = v2_raw_fixture.copy()
    market["Close"] = [90] * (len(market) - 51) + [100] * 50 + [110]
    bundle = _bundle(v2_raw_fixture, market=market)
    baseline = SwingW150SignalStrategy(shadow_enabled=False).evaluate_signals(bundle)
    enabled = SwingW150SignalStrategy().evaluate_signals(bundle)
    changed = SwingW150SignalStrategy(
        shadow_parameters=EntryShadowParameters(adverse_atr_multiple=Decimal("2"))
    ).evaluate_signals(bundle)
    assert enabled.entry_shadow is not None
    assert changed.entry_shadow.parameter_fingerprint != enabled.entry_shadow.parameter_fingerprint
    for result in (enabled, changed):
        assert result.model_dump(exclude={"entry_shadow"}) == baseline.model_dump(
            exclude={"entry_shadow"}
        )


def test_anchor_attachment_failure_preserves_valid_production_detection(
    v2_raw_fixture, monkeypatch
):
    market = v2_raw_fixture.copy()
    market["Close"] = [90] * (len(market) - 51) + [100] * 50 + [110]
    bundle = _bundle(v2_raw_fixture, market=market)
    baseline = SwingW150SignalStrategy(shadow_enabled=False).evaluate_signals(bundle)
    assert baseline.entry_opportunity.entry_signal is not None

    def fail(*_args):
        raise ValueError("anchor unavailable")

    monkeypatch.setattr(swing_adapter, "build_entry_source_anchors", fail)
    result = SwingW150SignalStrategy().evaluate_signals(bundle)
    assert result.signal_history == baseline.signal_history
    assert [item for item in result.observation_history if item.kind == "SETUP"] == [
        item for item in baseline.observation_history if item.kind == "SETUP"
    ]
    assert result.data_status == baseline.data_status
    assert result.entry_opportunity.model_dump(exclude={"anchors"}) == (
        baseline.entry_opportunity.model_dump(exclude={"anchors"})
    )
    assert result.entry_opportunity.anchors is None
    assert "anchor unavailable" in result.diagnostic_errors[0]
    assert result.entry_shadow.data_status is DataStatus.NOT_EVALUATED
    assert result.entry_shadow.risk_level is None
    assert any(
        item.kind == "EVIDENCE" and item.source_signal_id is None
        for item in result.observation_history
    )


def test_observation_toggle_and_settings_preserve_signal_opportunity_and_planner(v2_raw_fixture):
    from datetime import UTC
    from decimal import Decimal

    from src.position.models import AccountSnapshot, MarketSnapshot, PositionSnapshot
    from src.position.planner import plan_position_from_signals
    from src.strategies.observations.parameters import ObservationParameters

    frame = v2_raw_fixture
    market = frame.copy()
    market["Close"] = [90] * (len(frame) - 51) + [100] * 50 + [110]
    bundle = _bundle(frame, market=market)
    disabled = SwingW150SignalStrategy(observations_enabled=False).evaluate_signals(bundle)
    enabled = SwingW150SignalStrategy().evaluate_signals(bundle)
    changed = SwingW150SignalStrategy(
        observation_parameters=ObservationParameters(
            up_volume_ratio=0.5,
            down_volume_ratio=0.5,
            contraction_ratio=2,
            break_buffer_atr=1,
            reclaim_buffer_atr=1,
            zone_distance_atr=2,
        )
    ).evaluate_signals(bundle)
    assert any(item.kind == "EVIDENCE" for item in enabled.observation_history)
    assert all(item.kind == "SETUP" for item in disabled.observation_history)
    assert disabled.observation_history
    stamp = datetime(2024, 12, 19, tzinfo=UTC)

    def plan(result):
        return plan_position_from_signals(
            result,
            PositionSnapshot(3),
            AccountSnapshot(Decimal(10000), Decimal(100), Decimal(2)),
            MarketSnapshot(bundle.as_of, Decimal(110), "fixed"),
            calculated_at=stamp,
        )

    for result in [enabled, changed]:
        assert result.signal_history == disabled.signal_history
        assert result.current_signals == disabled.current_signals
        assert result.entry_opportunity == disabled.entry_opportunity
        assert result.parameter_fingerprint == disabled.parameter_fingerprint
        assert plan(result) == plan(disabled)
        assert [item for item in result.observation_history if item.kind == "SETUP"] == (
            disabled.observation_history
        )


def test_coin_same_day_entries_share_opportunity_source_and_authorize_planner():
    from decimal import Decimal
    from pathlib import Path

    from src.position.models import AccountSnapshot, DirectiveKind, MarketSnapshot, PositionSnapshot
    from src.position.planner import plan_position_from_signals
    from src.strategies.models import EntryOpportunityStatus

    path = Path(__file__).resolve().parents[2] / "fixtures" / "swing_w150" / "COIN.csv"
    frame = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")
    frame = frame.loc["2022-07-22":"2024-07-22"]
    assert len(frame) == 502
    # Deliberately synthetic bull benchmark isolates source selection from market gating.
    market = pd.DataFrame(index=frame.index)
    for column in ("Open", "High", "Low", "Close"):
        market[column] = np.linspace(100, 200, len(frame))
    market["High"] += 1
    market["Low"] -= 1
    market["Volume"] = 1000
    bundle = _bundle(frame, market=market)
    result = SwingW150SignalStrategy().evaluate_signals(bundle)
    assert {signal.code for signal in result.current_signals} == {
        "PULLBACK_REVERSAL_ENTRY",
        "TREND_BREAKOUT_ENTRY",
    }
    assert all(signal.occurred_on == date(2024, 7, 22) for signal in result.current_signals)
    assert result.entry_opportunity.entry_signal.code == "PULLBACK_REVERSAL_ENTRY"
    assert result.entry_opportunity.status is EntryOpportunityStatus.ALLOW
    plan = plan_position_from_signals(
        result,
        PositionSnapshot(0),
        AccountSnapshot(Decimal("100000"), Decimal("1000"), Decimal("10")),
        MarketSnapshot(bundle.as_of, bundle.instrument.bars[-1].close, "coin-fixture-close"),
    )
    assert plan.directive.kind is DirectiveKind.BUILD_ONLY_TO_RISK_TARGET
    assert plan.buy_quantity > 0


def test_terminal_source_reclaim_does_not_revive_opportunity_or_mix_live_source(
    v2_raw_fixture,
    monkeypatch,
):
    from decimal import Decimal

    from src.strategies.models import EntryOpportunityStatus

    frame = v2_raw_fixture.copy()
    for offset, close in [(-5, 105), (-4, 99), (-3, 115), (-2, 95), (-1, 105)]:
        frame.iloc[offset] = [close, close + 1, close - 1, close, 100]
    market = frame.copy()
    market["Close"] = [90] * (len(frame) - 51) + [100] * 50 + [110]
    bundle = _bundle(frame, market=market)
    params = SwingW150Parameters()
    f = build_swing_features(frame, params)
    f.frame.loc[frame.index[-5], "Trend_Breakout_High_Prev"] = 100
    f.frame.loc[frame.index[-3], "Trend_Breakout_High_Prev"] = 110
    # B may breach its breakout line while remaining above the production ATR cancellation line.
    f.frame.loc[frame.index[-3], "ATR"] = 20
    detection = detect_swing("COIN", f, params)
    prototype = detection.signal_history[0]

    def signal(identity, code, offset):
        return prototype.model_copy(
            update={
                "signal_id": identity,
                "code": code,
                "occurred_on": frame.index[offset].date(),
                "finality": SignalFinality.FINAL,
                "signal_price": Decimal(str(frame.Close.iloc[offset])),
            }
        )

    source_a = signal("source-A", "TREND_BREAKOUT_ENTRY", -5)
    exit_a = signal("exit-A", "OVERHEAT_CORRECTION", -4)
    source_b = signal("source-B", "TREND_BREAKOUT_ENTRY", -3)
    detection = detection.model_copy(
        update={
            "signal_history": [source_a, exit_a, source_b],
            "current_signals": [],
        }
    )
    monkeypatch.setattr(swing_adapter, "build_swing_features", lambda *_args, **_kwargs: f)
    monkeypatch.setattr(swing_adapter, "detect_swing", lambda *_args: detection)
    result = SwingW150SignalStrategy().evaluate_signals(bundle)
    assert result.entry_opportunity.entry_signal == source_b
    assert result.entry_opportunity.status not in {
        EntryOpportunityStatus.INVALIDATED,
        EntryOpportunityStatus.EXPIRED,
    }
    reclaims = [item for item in result.observation_history if item.code == "BREAKOUT_RECLAIM"]
    today_a = next(item for item in reclaims if item.started_on == bundle.as_of)
    assert today_a.source_signal_id == "source-A"
    assert today_a.source_terminal is True
    assert today_a.anchor_origin_on == source_a.occurred_on
    assert today_a.anchor_origin_price == Decimal(100)
    b_breach = next(
        item
        for item in result.observation_history
        if item.code == "BREAKOUT_LEVEL_BREACH" and item.source_signal_id == "source-B"
    )
    assert b_breach.status.value == "active"
    assert b_breach.source_terminal is False
    assert b_breach.anchor_origin_on == source_b.occurred_on
    assert b_breach.anchor_origin_price == Decimal(110)

    original_builder = swing_adapter.build_entry_source_anchors

    def fail_old_source(source, *args):
        if source.signal_id == "source-A":
            raise ValueError("historical anchor unavailable")
        return original_builder(source, *args)

    monkeypatch.setattr(swing_adapter, "build_entry_source_anchors", fail_old_source)
    degraded = SwingW150SignalStrategy().evaluate_signals(bundle)
    assert degraded.entry_opportunity == result.entry_opportunity
    assert any(item.source_signal_id == "source-B" for item in degraded.observation_history)
    assert any(
        item.kind == "EVIDENCE" and item.source_signal_id is None
        for item in degraded.observation_history
    )
    assert any("historical anchor unavailable" in item for item in degraded.diagnostic_errors)

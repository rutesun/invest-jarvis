from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from src.strategies.entry_opportunity import (
    evaluate_entry_opportunity,
    evaluate_signal_entry_opportunity,
)
from src.strategies.models import (
    BarFinality,
    ChartBar,
    ChartBundle,
    ChartSeries,
    CoverageManifest,
    EntryIntent,
    EntryOpportunityStatus,
    SignalFinality,
    StrategyEvent,
    StrategySignal,
)
from src.strategies.swing_w150.features import SwingFeatureFrame
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.tools.technical.scorecard_models import DataStatus, Direction, Evidence, Importance


def _breakout_features(bundle, *, atr=10, breakout=100):
    return SwingFeatureFrame(
        frame=pd.DataFrame(
            {
                "ATR": [atr] * len(bundle.instrument.bars),
                "Trend_Breakout_High_Prev": [breakout] * len(bundle.instrument.bars),
            },
            index=pd.to_datetime([bar.session_date for bar in bundle.instrument.bars]),
        ),
        data_status=DataStatus.COMPLETE,
        finalities=tuple(bar.finality for bar in bundle.instrument.bars),
    )


@pytest.mark.parametrize(
    ("close", "expected"), [(90.01, "ALLOW"), (90, "INVALIDATED"), (89, "INVALIDATED")]
)
def test_breakout_atr_close_boundary(close, expected):
    bundle = _v2_bundle(current_close=close)
    source = _v2_signal(bundle.instrument.bars[-2].session_date, "TREND_BREAKOUT_ENTRY")
    result = evaluate_signal_entry_opportunity(
        [source], bundle, SwingW150Parameters(), features=_breakout_features(bundle)
    )
    assert result.status.name == expected
    if expected == "INVALIDATED":
        assert result.invalidated_by is None
        assert result.terminal_on == bundle.as_of
        assert result.evidence[0].code == "BREAKOUT_ATR_INVALIDATED"


def test_breakout_final_failure_survives_recovery_with_frozen_source_atr():
    bundle = _v2_bundle(current_close=100)
    bars = list(bundle.instrument.bars)
    bars[-2] = bars[-2].model_copy(update={"close": Decimal("90")})
    bundle = bundle.model_copy(
        update={"instrument": bundle.instrument.model_copy(update={"bars": tuple(bars)})}
    )
    source = _v2_signal(bars[-3].session_date, "TREND_BREAKOUT_ENTRY")
    features = _breakout_features(bundle)
    features.frame.iloc[-2:, features.frame.columns.get_loc("ATR")] = 50
    features.frame.iloc[-2:, features.frame.columns.get_loc("Trend_Breakout_High_Prev")] = 50
    result = evaluate_signal_entry_opportunity(
        [source], bundle, SwingW150Parameters(), features=features
    )
    assert result.status is EntryOpportunityStatus.INVALIDATED
    assert result.terminal_on == bars[-2].session_date
    assert result.terminal_finality is SignalFinality.FINAL
    fresh = _v2_signal(bars[-1].session_date, "TREND_BREAKOUT_ENTRY")
    assert (
        evaluate_signal_entry_opportunity(
            [source, fresh], bundle, SwingW150Parameters(), features=features
        ).status
        is EntryOpportunityStatus.ALLOW
    )


def test_breakout_provisional_failure_can_recover():
    bundle = _v2_bundle(current_close=90, finality=BarFinality.PROVISIONAL)
    source = _v2_signal(bundle.instrument.bars[-2].session_date, "TREND_BREAKOUT_ENTRY")
    result = evaluate_signal_entry_opportunity(
        [source], bundle, SwingW150Parameters(), features=_breakout_features(bundle)
    )
    assert result.terminal_finality is SignalFinality.PROVISIONAL
    recovered = _v2_bundle(current_close=100, finality=BarFinality.PROVISIONAL)
    assert (
        evaluate_signal_entry_opportunity(
            [source], recovered, SwingW150Parameters(), features=_breakout_features(recovered)
        ).status
        is EntryOpportunityStatus.ALLOW
    )


@pytest.mark.parametrize("anchor", [None, 0, float("nan"), float("inf")])
def test_breakout_missing_anchor_is_not_allowed_but_preserves_terminal(anchor):
    bundle = _v2_bundle()
    source = _v2_signal(bundle.instrument.bars[-2].session_date, "TREND_BREAKOUT_ENTRY")
    features = None if anchor is None else _breakout_features(bundle, atr=anchor)
    result = evaluate_signal_entry_opportunity(
        [source], bundle, SwingW150Parameters(), features=features
    )
    assert result.status is EntryOpportunityStatus.NOT_EVALUATED
    exit_signal = _v2_signal(bundle.as_of, "SMA150_EXIT")
    result = evaluate_signal_entry_opportunity(
        [source, exit_signal], bundle, SwingW150Parameters(), features=features
    )
    assert result.status is EntryOpportunityStatus.INVALIDATED
    assert result.invalidated_by == exit_signal


@pytest.mark.parametrize("missing", ["ATR", "Trend_Breakout_High_Prev", "source_date"])
def test_breakout_unavailable_source_feature_is_not_evaluated(missing):
    bundle = _v2_bundle()
    source = _v2_signal(bundle.instrument.bars[-2].session_date, "TREND_BREAKOUT_ENTRY")
    features = _breakout_features(bundle)
    if missing == "source_date":
        features.frame.drop(features.frame.index[-2], inplace=True)
    else:
        features.frame.drop(columns=[missing], inplace=True)
    result = evaluate_signal_entry_opportunity(
        [source], bundle, SwingW150Parameters(), features=features
    )
    assert result.status is EntryOpportunityStatus.NOT_EVALUATED


def test_breakout_explicit_exit_precedes_price_failure_and_price_precedes_expiry():
    bundle = _v2_bundle(current_close=90)
    source = _v2_signal(bundle.instrument.bars[-22].session_date, "TREND_BREAKOUT_ENTRY")
    features = _breakout_features(bundle)
    result = evaluate_signal_entry_opportunity(
        [source], bundle, SwingW150Parameters(), features=features
    )
    assert result.status is EntryOpportunityStatus.INVALIDATED
    exit_signal = _v2_signal(bundle.as_of, "SMA150_EXIT")
    result = evaluate_signal_entry_opportunity(
        [source, exit_signal], bundle, SwingW150Parameters(), features=features
    )
    assert result.invalidated_by == exit_signal


def test_breakout_source_bar_is_excluded_and_other_entries_do_not_use_price_gate():
    bundle = _v2_bundle(current_close=89)
    source = _v2_signal(bundle.as_of, "TREND_BREAKOUT_ENTRY")
    features = _breakout_features(bundle)
    assert (
        evaluate_signal_entry_opportunity(
            [source], bundle, SwingW150Parameters(), features=features
        ).status
        is EntryOpportunityStatus.ALLOW
    )
    other = _v2_signal(bundle.instrument.bars[-2].session_date)
    assert (
        evaluate_signal_entry_opportunity(
            [other], bundle, SwingW150Parameters(), features=features
        ).status
        is EntryOpportunityStatus.ALLOW
    )


def test_breakout_failure_exposes_values_and_korean_common_reason():
    from src.pipelines.strategy_render import _opportunity_reason

    bundle = _v2_bundle(current_close=90)
    source = _v2_signal(bundle.instrument.bars[-2].session_date, "TREND_BREAKOUT_ENTRY")
    result = evaluate_signal_entry_opportunity(
        [source], bundle, SwingW150Parameters(), features=_breakout_features(bundle)
    )
    values = {item.code: item.observed_value for item in result.evidence}
    assert values["BREAKOUT_FAILURE_CLOSE"] == 90
    assert values["BREAKOUT_LEVEL_AT_SIGNAL"] == 100
    assert values["ATR_AT_SIGNAL"] == 10
    assert values["BREAKOUT_ATR_MULTIPLIER"] == 1
    assert values["BREAKOUT_INVALIDATION_LEVEL"] == 90
    assert result.evidence[0].observed_value == 90
    assert result.evidence[0].reference_value == 90
    assert "진입 허가 취소" in _opportunity_reason(result)
    assert "unknown" not in _opportunity_reason(result)


def test_adapter_passes_canonical_features_to_production_and_observation_sources(monkeypatch):
    from src.pipelines.strategy_render import _opportunity_reason
    from src.strategies.swing_w150 import adapter
    from src.strategies.swing_w150.features import build_swing_features
    from src.strategies.swing_w150.signals import detect_swing

    bundle = _v2_bundle(current_close=90)
    params = SwingW150Parameters()
    features = build_swing_features(adapter._frame(bundle), params)
    source = _v2_signal(bundle.instrument.bars[-2].session_date, "TREND_BREAKOUT_ENTRY")
    detected = detect_swing(bundle.ticker, features, params).model_copy(
        update={"signal_history": [source], "current_signals": []}
    )
    monkeypatch.setattr(adapter, "detect_swing", lambda *_args: detected)
    original_observations = adapter.evaluate_observations
    captured = []

    def observe(*args, **kwargs):
        captured.extend(kwargs["source_contexts"])
        return original_observations(*args, **kwargs)

    monkeypatch.setattr(adapter, "evaluate_observations", observe)
    result = adapter.SwingW150SignalStrategy().evaluate_signals(bundle)
    assert result.entry_opportunity.status is EntryOpportunityStatus.INVALIDATED
    assert result.entry_opportunity.evidence[0].reference_value == 99
    assert "진입 허가 취소" in _opportunity_reason(result.entry_opportunity)
    breaches = [item for item in result.observation_history if item.code == "BREAKOUT_LEVEL_BREACH"]
    assert breaches
    assert all(item.source_terminal for item in breaches)
    assert captured[0].terminal_reason == "BREAKOUT_ATR_INVALIDATED"
    from scripts.research_trading_observations import _find_terminal_reclaim
    from src.strategies.observations import detectors

    captured.clear()
    monkeypatch.setattr(detectors, "evaluate_observations", observe)
    _find_terminal_reclaim(bundle, features, detected, params, bundle.as_of)
    assert captured[0].terminal_reason == "BREAKOUT_ATR_INVALIDATED"


def _bundle(*, ticker="AAPL", market_ticker="SPY", market_close=110, market_sma=100, close=105):
    days = tuple(date(2026, 1, 1) + timedelta(days=i) for i in range(201))

    def series(prices):
        bars = tuple(
            ChartBar(
                session_date=day,
                open=Decimal(str(price)),
                high=Decimal(str(price + 1)),
                low=Decimal(str(price - 1)),
                close=Decimal(str(price)),
                volume=Decimal("100"),
            )
            for day, price in zip(days, prices, strict=True)
        )
        return ChartSeries(
            bars=bars,
            coverage=CoverageManifest(
                requested_start=days[0],
                actual_start=days[0],
                actual_end=days[-1],
                expected_sessions=days,
                complete=True,
            ),
        )

    return ChartBundle(
        profile_version="chart-v1",
        ticker=ticker,
        market_ticker=market_ticker,
        as_of=days[-1],
        instrument=series([100] * 200 + [close]),
        market=series(
            ([90] * 150 + [market_sma] * 50 + [market_close])
            if market_close > market_sma
            else ([110] * 150 + [market_sma] * 50 + [market_close])
            if market_close < market_sma
            else [market_sma] * 200 + [market_close]
        ),
        exchange_sessions=days,
    )


def _event(day):
    return StrategyEvent(
        event_id="entry-1",
        code="S_ENTRY",
        event_version="SWING_W150_V1",
        occurred_on=day,
        direction=Direction.RISING,
        evidence=[
            Evidence(
                code="reference_entry",
                message="signal reference",
                observed_value=100,
                reference_value=None,
                importance=Importance.MEDIUM,
                source="SWING_W150",
            ),
            Evidence(
                code="reference_stop",
                message="stop reference",
                observed_value=90,
                reference_value=None,
                importance=Importance.MEDIUM,
                source="SWING_W150",
            ),
        ],
    )


@pytest.mark.parametrize(
    ("market_close", "market_sma", "close", "expected"),
    [
        (110, 100, 105, EntryIntent.ALLOW),
        (110, 100, 105.1, EntryIntent.WATCH),
        (100, 100, 100, EntryIntent.WATCH),
        (90, 100, 100, EntryIntent.BLOCK),
    ],
)
def test_entry_opportunity_v1(market_close, market_sma, close, expected):
    bundle = _bundle(market_close=market_close, market_sma=market_sma, close=close)
    result = evaluate_entry_opportunity(_event(bundle.as_of), bundle, bundle.as_of)
    assert result.intent is expected


def test_next_session_uses_actual_open_and_age_twenty_is_valid():
    bundle = _bundle()
    event = _event(bundle.instrument.bars[-21].session_date)
    result = evaluate_entry_opportunity(event, bundle, bundle.as_of)
    assert result.intent is EntryIntent.ALLOW
    assert result.opportunity.age_bars == 20
    assert result.opportunity.reference_entry == 100
    assert result.opportunity.reference_entry_basis.value == "next_open_actual"


def test_age_twenty_one_expires():
    bundle = _bundle()
    result = evaluate_entry_opportunity(
        _event(bundle.instrument.bars[-22].session_date), bundle, bundle.as_of
    )
    assert result.intent is EntryIntent.NOT_EVALUATED


def test_original_stop_touch_blocks_entry():
    bundle = _bundle(close=90)
    result = evaluate_entry_opportunity(
        _event(bundle.instrument.bars[-2].session_date), bundle, bundle.as_of
    )
    assert result.intent is EntryIntent.BLOCK
    assert result.opportunity.structure_status.value == "invalid"


def test_korean_ticker_is_explicitly_not_evaluated():
    bundle = _bundle(ticker="005930.KS")
    result = evaluate_entry_opportunity(_event(bundle.as_of), bundle, bundle.as_of)
    assert result.intent is EntryIntent.NOT_EVALUATED


def test_non_spy_benchmark_is_not_evaluated():
    bundle = _bundle(market_ticker="QQQ")
    result = evaluate_entry_opportunity(_event(bundle.as_of), bundle, bundle.as_of)
    assert result.intent is EntryIntent.NOT_EVALUATED


def _v2_bundle(
    *,
    ticker="AAPL",
    market_ticker="SPY",
    market="bull",
    complete=True,
    finality=BarFinality.FINAL,
    current_close=100,
    current_open=100,
):
    days = tuple(date(2025, 1, 1) + timedelta(days=i) for i in range(270))

    def series(prices, *, instrument=False):
        return ChartSeries(
            bars=tuple(
                ChartBar(
                    session_date=day,
                    open=Decimal(str(current_open if instrument and day == days[-1] else price)),
                    high=Decimal(
                        str(
                            max(price, current_open) + 1
                            if instrument and day == days[-1]
                            else price + 1
                        )
                    ),
                    low=Decimal(
                        str(
                            min(price, current_open) - 1
                            if instrument and day == days[-1]
                            else price - 1
                        )
                    ),
                    close=Decimal(str(price)),
                    volume=Decimal("100"),
                    finality=finality if day == days[-1] else BarFinality.FINAL,
                )
                for day, price in zip(days, prices, strict=True)
            ),
            coverage=CoverageManifest(
                requested_start=days[0],
                actual_start=days[0],
                actual_end=days[-1],
                expected_sessions=days,
                complete=complete,
                truncation_reason=None if complete else "provider_limit",
            ),
        )

    market_prices = (
        [90] * 219 + [100] * 50 + [110]
        if market == "bull"
        else [110] * 219 + [100] * 50 + [90]
        if market == "bear"
        else [100] * 270
    )
    return ChartBundle(
        profile_version="chart-v1",
        ticker=ticker,
        market_ticker=market_ticker,
        as_of=days[-1],
        instrument=series([100] * 269 + [current_close], instrument=True),
        market=series(market_prices),
        exchange_sessions=days,
    )


def _v2_signal(day, code="PULLBACK_REVERSAL_ENTRY", finality=SignalFinality.FINAL):
    return StrategySignal(
        signal_id=f"{day}:{code}",
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version="SWING_W150_V2_PARAMS_V1",
        parameter_fingerprint=SwingW150Parameters().parameter_fingerprint,
        code=code,
        occurred_on=day,
        finality=finality,
        direction=Direction.RISING if code.endswith("ENTRY") else Direction.FALLING,
        signal_price=Decimal("100"),
        evidence=[
            Evidence(
                code=code,
                message=code,
                observed_value=100,
                reference_value=None,
                importance=Importance.MEDIUM,
                source="SWING_W150_V2",
            )
        ],
        data_status=DataStatus.COMPLETE,
    )


@pytest.mark.parametrize(
    ("case", "status"),
    [
        ("age_20_bull_within_limit", EntryOpportunityStatus.ALLOW),
        ("age_20_bull_at_limit", EntryOpportunityStatus.ALLOW),
        ("bull_overextended", EntryOpportunityStatus.WATCH),
        ("sideways_market", EntryOpportunityStatus.WATCH),
        ("age_21", EntryOpportunityStatus.EXPIRED),
        ("no_entry_complete_history", EntryOpportunityStatus.NO_RECENT_SIGNAL),
        ("no_entry_truncated_history", EntryOpportunityStatus.NOT_EVALUATED),
        ("bear_market", EntryOpportunityStatus.BLOCK),
        ("entry_then_correction", EntryOpportunityStatus.INVALIDATED),
        ("entry_then_sma150_exit", EntryOpportunityStatus.INVALIDATED),
    ],
)
def test_signal_entry_opportunity_truth_table(case, status):
    bundle = _v2_bundle(
        market="bear"
        if case == "bear_market"
        else "sideways"
        if case == "sideways_market"
        else "bull",
        complete=case != "no_entry_truncated_history",
        current_close=105
        if case == "age_20_bull_at_limit"
        else 105.01
        if case == "bull_overextended"
        else 100,
    )
    days = bundle.exchange_sessions
    history = (
        [] if case.startswith("no_entry") else [_v2_signal(days[-22 if case == "age_21" else -21])]
    )
    if case == "entry_then_correction":
        history.append(_v2_signal(days[-1], "OVERHEAT_CORRECTION"))
    if case == "entry_then_sma150_exit":
        history.append(_v2_signal(days[-1], "SMA150_EXIT"))
    result = evaluate_signal_entry_opportunity(history, bundle, SwingW150Parameters())
    assert result.status is status
    assert result.evidence
    if case == "age_20_bull_within_limit":
        assert result.age_bars == 20
        assert result.execution_reference_price == Decimal("100")
    if case == "age_21":
        assert result.age_bars == 21
    if case.startswith("entry_then"):
        assert result.invalidated_by is history[-1]


def test_new_entry_after_correction_becomes_source():
    bundle = _v2_bundle()
    days = bundle.exchange_sessions
    history = [
        _v2_signal(days[-5], "TREND_BREAKOUT_ENTRY"),
        _v2_signal(days[-3], "OVERHEAT_CORRECTION"),
        _v2_signal(days[-2], "PULLBACK_REVERSAL_ENTRY"),
    ]
    result = evaluate_signal_entry_opportunity(history, bundle, SwingW150Parameters())
    assert result.status is EntryOpportunityStatus.ALLOW
    assert result.entry_signal is history[-1]
    assert result.invalidated_by is None
    assert result.age_bars == 1


@pytest.mark.parametrize(
    ("higher", "lower"),
    [
        ("POST_OVERHEAT_RECOVERY_ENTRY", "PULLBACK_REVERSAL_ENTRY"),
        ("PULLBACK_REVERSAL_ENTRY", "TREND_BREAKOUT_ENTRY"),
        ("TREND_BREAKOUT_ENTRY", "DEEP_RECOVERY_ENTRY"),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_same_day_entry_source_is_independent_of_signal_order(higher, lower, reverse):
    bundle = _v2_bundle()
    preferred = _v2_signal(bundle.as_of, higher)
    signals = [preferred, _v2_signal(bundle.as_of, lower)]
    result = evaluate_signal_entry_opportunity(
        signals[::-1] if reverse else signals,
        bundle,
        SwingW150Parameters(),
        features=_breakout_features(bundle),
    )
    assert result.entry_signal is preferred
    assert result.status is EntryOpportunityStatus.ALLOW


@pytest.mark.parametrize("reverse", [False, True])
def test_newest_entry_date_outranks_entry_type(reverse):
    bundle = _v2_bundle()
    latest = _v2_signal(bundle.as_of, "DEEP_RECOVERY_ENTRY")
    signals = [
        _v2_signal(bundle.exchange_sessions[-2], "POST_OVERHEAT_RECOVERY_ENTRY"),
        latest,
    ]
    result = evaluate_signal_entry_opportunity(
        signals[::-1] if reverse else signals, bundle, SwingW150Parameters()
    )
    assert result.entry_signal is latest
    assert result.status is EntryOpportunityStatus.ALLOW


@pytest.mark.parametrize("include_current", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_future_entries_cannot_become_opportunity_source(include_current, reverse):
    bundle = _v2_bundle()
    current = _v2_signal(bundle.as_of, "DEEP_RECOVERY_ENTRY")
    signals = [_v2_signal(bundle.as_of + timedelta(days=1), "POST_OVERHEAT_RECOVERY_ENTRY")]
    if include_current:
        signals.append(current)
    result = evaluate_signal_entry_opportunity(
        signals[::-1] if reverse else signals, bundle, SwingW150Parameters()
    )
    assert result.entry_signal is (current if include_current else None)
    assert result.status is (
        EntryOpportunityStatus.ALLOW if include_current else EntryOpportunityStatus.NO_RECENT_SIGNAL
    )


@pytest.mark.parametrize(
    "status",
    [
        EntryOpportunityStatus.WATCH,
        EntryOpportunityStatus.BLOCK,
        EntryOpportunityStatus.INVALIDATED,
        EntryOpportunityStatus.EXPIRED,
        EntryOpportunityStatus.NOT_EVALUATED,
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_selected_entry_status_cannot_fall_back_to_lower_or_older_source(status, reverse):
    bundle = _v2_bundle(market="bear" if status is EntryOpportunityStatus.BLOCK else "bull")
    day = (
        bundle.as_of
        if status is EntryOpportunityStatus.WATCH
        else bundle.exchange_sessions[-22 if status is EntryOpportunityStatus.EXPIRED else -2]
    )
    preferred = _v2_signal(day)
    if status is EntryOpportunityStatus.WATCH:
        preferred = preferred.model_copy(update={"signal_price": Decimal("90")})
    elif status is EntryOpportunityStatus.NOT_EVALUATED:
        preferred = preferred.model_copy(update={"parameter_fingerprint": "wrong"})
    signals = [
        _v2_signal(day - timedelta(days=1), "POST_OVERHEAT_RECOVERY_ENTRY"),
        preferred,
        _v2_signal(day, "DEEP_RECOVERY_ENTRY"),
    ]
    if status is EntryOpportunityStatus.INVALIDATED:
        signals.append(_v2_signal(bundle.as_of, "SMA150_EXIT"))
    result = evaluate_signal_entry_opportunity(
        signals[::-1] if reverse else signals, bundle, SwingW150Parameters()
    )
    assert result.entry_signal is preferred
    assert result.status is status


def test_selected_breakout_price_failure_cannot_fall_back_to_deep_recovery():
    bundle = _v2_bundle(current_close=89)
    preferred = _v2_signal(bundle.exchange_sessions[-2], "TREND_BREAKOUT_ENTRY")
    alternative = _v2_signal(preferred.occurred_on, "DEEP_RECOVERY_ENTRY")
    for signals in ([preferred, alternative], [alternative, preferred]):
        result = evaluate_signal_entry_opportunity(
            signals, bundle, SwingW150Parameters(), features=_breakout_features(bundle)
        )
        assert result.entry_signal is preferred
        assert result.status is EntryOpportunityStatus.INVALIDATED
        assert result.evidence[0].code == "BREAKOUT_ATR_INVALIDATED"


def test_past_final_source_uses_current_provisional_bar_finality():
    bundle = _v2_bundle(finality=BarFinality.PROVISIONAL)
    history = [_v2_signal(bundle.exchange_sessions[-2])]
    result = evaluate_signal_entry_opportunity(history, bundle, SwingW150Parameters())
    assert history[0].finality is SignalFinality.FINAL
    assert result.finality is SignalFinality.PROVISIONAL


def test_next_open_sets_execution_reference_and_extension():
    bundle = _v2_bundle(current_open=101, current_close=106)
    history = [_v2_signal(bundle.exchange_sessions[-2])]
    result = evaluate_signal_entry_opportunity(history, bundle, SwingW150Parameters())
    assert result.signal_price == Decimal("100")
    assert result.execution_reference_price == Decimal("101")
    assert result.extension_pct == Decimal("106") / Decimal("101") - 1
    assert result.status is EntryOpportunityStatus.ALLOW


@pytest.mark.parametrize(
    ("ticker", "benchmark", "market", "expected", "regime"),
    [
        ("005930.KS", "^KS11", "bull", EntryOpportunityStatus.ALLOW, "bull"),
        ("035720.KQ", "^KQ11", "sideways", EntryOpportunityStatus.WATCH, "sideways"),
        ("005930", "^KS11", "bear", EntryOpportunityStatus.BLOCK, "bear"),
        ("0167A0", "^KS11", "bull", EntryOpportunityStatus.ALLOW, "bull"),
    ],
)
def test_korean_signal_opportunity_uses_market_benchmark(
    ticker, benchmark, market, expected, regime
):
    bundle = _v2_bundle(ticker=ticker, market_ticker=benchmark, market=market)
    history = [_v2_signal(bundle.exchange_sessions[-2])]
    result = evaluate_signal_entry_opportunity(history, bundle, SwingW150Parameters())
    assert result.status is expected
    assert result.market_regime == regime
    assert result.entry_signal is history[0]
    assert result.evidence


@pytest.mark.parametrize(
    ("ticker", "benchmark"),
    [("AAPL", "^KS11"), ("005930.KS", "SPY"), ("035720.KQ", "^KS11"), ("005930", "^KQ11")],
)
def test_signal_opportunity_rejects_wrong_market_benchmark(ticker, benchmark):
    bundle = _v2_bundle(ticker=ticker, market_ticker=benchmark)
    history = [_v2_signal(bundle.exchange_sessions[-2])]
    result = evaluate_signal_entry_opportunity(history, bundle, SwingW150Parameters())
    assert result.status is EntryOpportunityStatus.NOT_EVALUATED
    assert result.evidence


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("strategy_id", "OTHER"),
        ("strategy_version", "SWING_W150_V1"),
        ("parameter_set_version", "OTHER_PARAMS"),
        ("parameter_fingerprint", "not-the-active-fingerprint"),
    ],
)
def test_signal_opportunity_rejects_source_identity_mismatch(field, wrong):
    bundle = _v2_bundle()
    source = _v2_signal(bundle.exchange_sessions[-2]).model_copy(update={field: wrong})
    result = evaluate_signal_entry_opportunity([source], bundle, SwingW150Parameters())
    assert result.status is EntryOpportunityStatus.NOT_EVALUATED
    assert any("IDENTITY" in item.code for item in result.evidence)


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("strategy_id", "OTHER"),
        ("strategy_version", "SWING_W150_V1"),
        ("parameter_set_version", "OTHER_PARAMS"),
        ("parameter_fingerprint", "not-the-active-fingerprint"),
    ],
)
def test_signal_opportunity_rejects_invalidator_identity_mismatch(field, wrong):
    bundle = _v2_bundle()
    source = _v2_signal(bundle.exchange_sessions[-3])
    invalidator = _v2_signal(bundle.exchange_sessions[-2], "SMA150_EXIT").model_copy(
        update={field: wrong}
    )
    result = evaluate_signal_entry_opportunity([source, invalidator], bundle, SwingW150Parameters())
    assert result.status is EntryOpportunityStatus.NOT_EVALUATED
    assert any("IDENTITY" in item.code for item in result.evidence)


def test_first_final_invalidator_is_preserved_instead_of_last_exit():
    bundle = _v2_bundle(current_close=104)
    days = bundle.exchange_sessions
    source = _v2_signal(days[-8])
    first = _v2_signal(days[-6], "OVERHEAT_CORRECTION")
    later = _v2_signal(days[-2], "SMA150_EXIT")
    result = evaluate_signal_entry_opportunity(
        [source, later, first], bundle, SwingW150Parameters()
    )
    assert result.status is EntryOpportunityStatus.INVALIDATED
    assert result.invalidated_by is first
    assert result.terminal_on == days[-6]
    assert result.terminal_finality is SignalFinality.FINAL
    assert result.market_regime == "bull"
    assert result.extension_pct == Decimal("0.04")


def test_same_day_exit_before_entry_in_signal_array_invalidates_source():
    bundle = _v2_bundle()
    source = _v2_signal(bundle.as_of)
    exit_signal = _v2_signal(bundle.as_of, "SMA150_EXIT")
    result = evaluate_signal_entry_opportunity([exit_signal, source], bundle, SwingW150Parameters())
    assert result.status is EntryOpportunityStatus.INVALIDATED
    assert result.invalidated_by is exit_signal
    assert result.terminal_on == bundle.as_of


def test_same_day_terminal_uses_exit_priority_independent_of_array_order():
    bundle = _v2_bundle()
    days = bundle.exchange_sessions
    source = _v2_signal(days[-22])
    correction = _v2_signal(days[-1], "OVERHEAT_CORRECTION")
    exit_signal = _v2_signal(days[-1], "SMA150_EXIT")
    result = evaluate_signal_entry_opportunity(
        [source, exit_signal, correction], bundle, SwingW150Parameters()
    )
    assert result.status is EntryOpportunityStatus.INVALIDATED
    assert result.invalidated_by is exit_signal
    assert result.terminal_on == days[-1]


def test_expiry_before_later_exit_stays_expired():
    bundle = _v2_bundle()
    days = bundle.exchange_sessions
    source = _v2_signal(days[-25])
    exit_signal = _v2_signal(days[-1], "SMA150_EXIT")
    result = evaluate_signal_entry_opportunity([source, exit_signal], bundle, SwingW150Parameters())
    assert result.status is EntryOpportunityStatus.EXPIRED
    assert result.terminal_on == days[-4]
    assert result.terminal_finality is SignalFinality.FINAL
    assert result.invalidated_by is None


def test_final_terminal_survives_provisional_recovery_and_later_provisional_exit():
    bundle = _v2_bundle(finality=BarFinality.PROVISIONAL, current_close=110)
    days = bundle.exchange_sessions
    source = _v2_signal(days[-5])
    final_exit = _v2_signal(days[-3], "SMA150_EXIT")
    provisional_exit = _v2_signal(days[-1], "OVERHEAT_CORRECTION", SignalFinality.PROVISIONAL)
    result = evaluate_signal_entry_opportunity(
        [source, final_exit, provisional_exit], bundle, SwingW150Parameters()
    )
    assert result.status is EntryOpportunityStatus.INVALIDATED
    assert result.invalidated_by is final_exit
    assert result.terminal_on == days[-3]
    assert result.terminal_finality is SignalFinality.FINAL
    assert result.finality is SignalFinality.PROVISIONAL


@pytest.mark.parametrize("kind", ["invalidation", "expiry"])
def test_provisional_terminal_is_explicit_and_can_recover_on_revised_prefix(kind):
    bundle = _v2_bundle(finality=BarFinality.PROVISIONAL)
    days = bundle.exchange_sessions
    source = _v2_signal(days[-22] if kind == "expiry" else days[-3])
    history = [source]
    if kind == "invalidation":
        history.append(_v2_signal(days[-1], "SMA150_EXIT", SignalFinality.PROVISIONAL))
    result = evaluate_signal_entry_opportunity(history, bundle, SwingW150Parameters())
    assert result.status is (
        EntryOpportunityStatus.EXPIRED if kind == "expiry" else EntryOpportunityStatus.INVALIDATED
    )
    assert result.terminal_on == bundle.as_of
    assert result.terminal_finality is SignalFinality.PROVISIONAL
    if kind == "invalidation":
        revised = evaluate_signal_entry_opportunity([source], bundle, SwingW150Parameters())
        assert revised.status is EntryOpportunityStatus.ALLOW
        assert revised.terminal_on is None


def test_latest_terminal_source_does_not_fall_back_to_older_entry():
    bundle = _v2_bundle()
    days = bundle.exchange_sessions
    old = _v2_signal(days[-8], "TREND_BREAKOUT_ENTRY")
    newest = _v2_signal(days[-3])
    exit_signal = _v2_signal(days[-3], "SMA150_EXIT")
    result = evaluate_signal_entry_opportunity(
        [old, exit_signal, newest], bundle, SwingW150Parameters()
    )
    assert result.entry_signal is newest
    assert result.status is EntryOpportunityStatus.INVALIDATED


def test_new_provisional_source_opens_its_own_window_after_old_final_terminal():
    bundle = _v2_bundle(finality=BarFinality.PROVISIONAL)
    days = bundle.exchange_sessions
    newest = _v2_signal(days[-1], finality=SignalFinality.PROVISIONAL)
    result = evaluate_signal_entry_opportunity(
        [_v2_signal(days[-5]), _v2_signal(days[-3], "SMA150_EXIT"), newest],
        bundle,
        SwingW150Parameters(),
    )
    assert result.entry_signal is newest
    assert result.status is EntryOpportunityStatus.ALLOW
    assert result.terminal_on is None


def test_invalidator_date_outranks_its_signal_array_position():
    bundle = _v2_bundle()
    days = bundle.exchange_sessions
    source = _v2_signal(days[-3])
    old_exit = _v2_signal(days[-5], "SMA150_EXIT")
    result = evaluate_signal_entry_opportunity([source, old_exit], bundle, SwingW150Parameters())
    assert result.status is EntryOpportunityStatus.ALLOW


def test_final_expiry_survives_later_provisional_exit():
    bundle = _v2_bundle(finality=BarFinality.PROVISIONAL)
    days = bundle.exchange_sessions
    result = evaluate_signal_entry_opportunity(
        [_v2_signal(days[-24]), _v2_signal(days[-1], "SMA150_EXIT", SignalFinality.PROVISIONAL)],
        bundle,
        SwingW150Parameters(),
    )
    assert result.status is EntryOpportunityStatus.EXPIRED
    assert result.terminal_on == days[-3]
    assert result.terminal_finality is SignalFinality.FINAL
    assert result.invalidated_by is None


def test_changed_provisional_source_identity_cannot_revive_its_final_terminal():
    bundle = _v2_bundle(finality=BarFinality.PROVISIONAL)
    days = bundle.exchange_sessions
    source = _v2_signal(days[-4], finality=SignalFinality.PROVISIONAL).model_copy(
        update={"signal_id": "recomputed-provisional-identity", "signal_price": Decimal("103")}
    )
    final_exit = _v2_signal(days[-2], "SMA150_EXIT")
    result = evaluate_signal_entry_opportunity([source, final_exit], bundle, SwingW150Parameters())
    assert result.status is EntryOpportunityStatus.INVALIDATED
    assert result.entry_signal is source
    assert result.invalidated_by is final_exit
    assert result.terminal_finality is SignalFinality.FINAL


def test_first_final_invalidator_wins_even_when_signal_array_is_chronological():
    bundle = _v2_bundle()
    days = bundle.exchange_sessions
    first = _v2_signal(days[-4], "OVERHEAT_CORRECTION")
    result = evaluate_signal_entry_opportunity(
        [_v2_signal(days[-6]), first, _v2_signal(days[-2], "SMA150_EXIT")],
        bundle,
        SwingW150Parameters(),
    )
    assert result.invalidated_by is first
    assert result.terminal_on == days[-4]

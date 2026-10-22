"""On-demand opportunity for a dated US SWING_W150 entry signal."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import isfinite

from src.providers.index_provider import index_symbol_for
from src.strategies.models import (
    BarFinality,
    ChartBundle,
    EntryIntent,
    EntryOpportunity,
    EntryOpportunityStatus,
    ReferenceEntryBasis,
    SignalEntryOpportunity,
    SignalFinality,
    StrategyEvent,
    StrategySignal,
    StructureStatus,
)
from src.strategies.signal_selection import select_latest_entry_signal
from src.strategies.swing_w150.features import SwingFeatureFrame
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.tools.disclosure import is_korean_ticker
from src.tools.technical.scorecard_models import Evidence, Importance


POLICY_VERSION = "SWING_W150_ENTRY_OPPORTUNITY_V1"
SIGNAL_POLICY_VERSION = "SWING_W150_ENTRY_OPPORTUNITY_PRODUCTION_V2"
BREAKOUT_ATR_INVALIDATION_MULTIPLIER = Decimal("1.0")
_INVALIDATING_CODES = {"OVERHEAT_CORRECTION", "SMA150_EXIT"}


@dataclass(frozen=True)
class OpportunityEvaluation:
    intent: EntryIntent
    opportunity: EntryOpportunity | None


def _observed(event: StrategyEvent, code: str) -> float | None:
    return next((item.observed_value for item in event.evidence if item.code == code), None)


def evaluate_entry_opportunity(
    event: StrategyEvent, bundle: ChartBundle, evaluation_as_of: date
) -> OpportunityEvaluation:
    if (
        event.code not in {"S_ENTRY", "D_ENTRY"}
        or event.event_version != "SWING_W150_V1"
        or is_korean_ticker(bundle.ticker)
        or bundle.market is None
        or bundle.market_ticker != "SPY"
    ):
        return OpportunityEvaluation(EntryIntent.NOT_EVALUATED, None)
    sessions = [bar.session_date for bar in bundle.instrument.bars]
    if (
        evaluation_as_of != bundle.as_of
        or event.occurred_on not in sessions
        or evaluation_as_of not in sessions
    ):
        return OpportunityEvaluation(EntryIntent.NOT_EVALUATED, None)
    age = sessions.index(evaluation_as_of) - sessions.index(event.occurred_on)
    if not 0 <= age <= 20:
        return OpportunityEvaluation(EntryIntent.NOT_EVALUATED, None)
    market_bars = [bar for bar in bundle.market.bars if bar.session_date <= evaluation_as_of]
    coverage = bundle.market.coverage
    if (
        not coverage.complete
        or coverage.truncation_reason is not None
        or len(market_bars) < 200
        or market_bars[-1].session_date != evaluation_as_of
    ):
        return OpportunityEvaluation(EntryIntent.NOT_EVALUATED, None)
    closes = [float(bar.close) for bar in market_bars]
    market_close, sma50, sma200 = closes[-1], sum(closes[-50:]) / 50, sum(closes[-200:]) / 200
    regime = (
        "bull"
        if market_close > sma50 > sma200
        else "bear"
        if market_close < sma50 < sma200
        else "sideways"
    )

    signal_index = sessions.index(event.occurred_on)
    basis = (
        ReferenceEntryBasis.SIGNAL_CLOSE_ESTIMATE
        if age == 0
        else ReferenceEntryBasis.NEXT_OPEN_ACTUAL
    )
    reference_entry = (
        _observed(event, "reference_entry")
        if age == 0
        else float(bundle.instrument.bars[signal_index + 1].open)
    )
    if reference_entry is None or reference_entry <= 0:
        return OpportunityEvaluation(EntryIntent.NOT_EVALUATED, None)
    reference_stop = _observed(event, "reference_stop")
    if reference_stop is None:
        return OpportunityEvaluation(EntryIntent.NOT_EVALUATED, None)
    features = None
    if len(bundle.instrument.bars) > 250:
        from src.strategies.swing_w150.adapter import _frame
        from src.strategies.swing_w150.engine import _features
        from src.strategies.swing_w150.rules import initial_stop

        features = _features(_frame(bundle))
        if age > 0:
            reference_stop = initial_stop(event.code[0], reference_entry, features, signal_index)
    close = float(bundle.instrument.bars[-1].close)
    extension_pct = close / reference_entry - 1
    risk = reference_entry - reference_stop
    invalid = any(
        float(bar.low) <= reference_stop for bar in bundle.instrument.bars[signal_index + 1 :]
    )
    if not invalid and features is not None and age > 0:
        # Canonical lifecycle exits are evaluated by the same SWING replay rules.
        from src.strategies.swing_w150.adapter import _frame
        from src.strategies.swing_w150.engine import replay_trace

        trace = replay_trace(_frame(bundle))
        seen_source = False
        for item in trace.events:
            day = sessions[item.index]
            if day == event.occurred_on and item.code == event.code:
                seen_source = True
            elif seen_source and item.code in {"STOP", "SMA150_EXIT"}:
                invalid = True
                break
            elif seen_source and item.code.endswith("ENTRY"):
                break
        if not seen_source:
            return OpportunityEvaluation(EntryIntent.NOT_EVALUATED, None)
    intent = (
        EntryIntent.BLOCK
        if invalid or regime == "bear"
        else EntryIntent.ALLOW
        if regime == "bull" and close <= reference_entry * 1.05
        else EntryIntent.WATCH
    )
    atr = float(features.atr[signal_index]) if features is not None else float("nan")
    lookback = 50 if event.code.startswith("S_") else 20
    prior = bundle.instrument.bars[max(0, signal_index - lookback) : signal_index]
    breakout = max((float(bar.high) for bar in prior), default=0)
    sma20 = float(features.sma20[-1]) if features is not None else float("nan")
    opportunity = EntryOpportunity(
        source_event_id=event.event_id,
        source_event_code=event.code,
        source_event_date=event.occurred_on,
        evaluation_as_of=evaluation_as_of,
        age_bars=age,
        reference_entry=reference_entry,
        reference_entry_basis=basis,
        reference_stop=reference_stop,
        extension_pct=extension_pct,
        extension_r=(close - reference_entry) / risk if risk > 0 else None,
        extension_atr=(close - reference_entry) / atr if atr > 0 else None,
        breakout_distance_pct=close / breakout - 1 if breakout > 0 else None,
        sma20_distance_pct=close / sma20 - 1 if sma20 > 0 else None,
        market_regime=regime,
        structure_status=StructureStatus.INVALID if invalid else StructureStatus.VALID,
        policy_version=POLICY_VERSION,
        next_open_recheck_required=True,
    )
    return OpportunityEvaluation(intent, opportunity)


def evaluate_signal_entry_opportunity(
    signal_history: Sequence[StrategySignal],
    bundle: ChartBundle,
    params: SwingW150Parameters,
    *,
    features: SwingFeatureFrame | None = None,
) -> SignalEntryOpportunity:
    """Evaluate the latest V2 entry from the chart available at this as-of date."""
    finality = (
        SignalFinality.FINAL
        if bundle.instrument.bars[-1].finality is BarFinality.FINAL
        else SignalFinality.PROVISIONAL
    )
    source: StrategySignal | None = None
    invalidated_by: StrategySignal | None = None
    terminal_on: date | None = None
    terminal_finality: SignalFinality | None = None
    age: int | None = None
    execution_reference: Decimal | None = None
    extension: Decimal | None = None
    regime: str | None = None
    structure = StructureStatus.UNKNOWN
    price_evidence: list[Evidence] = []

    def result(status: EntryOpportunityStatus, code: str) -> SignalEntryOpportunity:
        return SignalEntryOpportunity(
            evaluation_as_of=bundle.as_of,
            finality=finality,
            status=status,
            entry_signal=source,
            invalidated_by=invalidated_by,
            age_bars=age,
            signal_price=source.signal_price if source is not None else None,
            execution_reference_price=execution_reference,
            extension_pct=extension,
            market_regime=regime,
            structure_status=structure,
            evidence=[
                Evidence(
                    code=code,
                    message=code.lower().replace("_", " "),
                    observed_value=price_evidence[0].observed_value
                    if code == "BREAKOUT_ATR_INVALIDATED"
                    else float(extension)
                    if extension is not None
                    else None,
                    reference_value=price_evidence[0].reference_value
                    if code == "BREAKOUT_ATR_INVALIDATED"
                    else params.entry_opportunity_max_extension
                    if extension is not None
                    else None,
                    importance=Importance.MEDIUM,
                    source=SIGNAL_POLICY_VERSION,
                )
            ]
            + (price_evidence if code == "BREAKOUT_ATR_INVALIDATED" else []),
            policy_version=SIGNAL_POLICY_VERSION,
            terminal_on=terminal_on,
            terminal_finality=terminal_finality,
        )

    instrument = bundle.instrument
    market = bundle.market
    korean = is_korean_ticker(bundle.ticker)
    benchmark = index_symbol_for(bundle.ticker.upper()) if korean else "SPY"
    if korean and benchmark == "^GSPC":
        benchmark = "^KS11"  # Six-character KRX codes may contain letters.
    if (
        len(instrument.bars) < params.minimum_history_bars
        or not instrument.coverage.complete
        or instrument.coverage.truncation_reason is not None
        or market is None
        or bundle.market_ticker != benchmark
        or not market.coverage.complete
        or market.coverage.truncation_reason is not None
        or len(market.bars) < 200
        or market.bars[-1].session_date != bundle.as_of
    ):
        return result(EntryOpportunityStatus.NOT_EVALUATED, "CHART_OR_MARKET_INCOMPLETE")

    sessions = [bar.session_date for bar in instrument.bars]
    source = select_latest_entry_signal(signal_history, as_of=bundle.as_of)
    if source is None:
        return result(EntryOpportunityStatus.NO_RECENT_SIGNAL, "NO_ENTRY_SIGNAL")

    def has_active_identity(signal: StrategySignal) -> bool:
        return (
            signal.strategy_id == "SWING_W150"
            and signal.strategy_version == "SWING_W150_V2"
            and signal.parameter_set_version == params.parameter_set_version
            and signal.parameter_fingerprint == params.parameter_fingerprint
        )

    if not has_active_identity(source):
        return result(EntryOpportunityStatus.NOT_EVALUATED, "SOURCE_SIGNAL_IDENTITY_MISMATCH")
    if source.occurred_on not in sessions:
        return result(EntryOpportunityStatus.NOT_EVALUATED, "ENTRY_SESSION_MISSING")
    source_bar_index = sessions.index(source.occurred_on)
    age = len(sessions) - 1 - source_bar_index
    execution_reference = (
        source.signal_price if age == 0 else instrument.bars[source_bar_index + 1].open
    )
    closes = [bar.close for bar in market.bars]
    market_close = closes[-1]
    sma50 = sum(closes[-50:]) / 50
    sma200 = sum(closes[-200:]) / 200
    regime = (
        "bull"
        if market_close > sma50 > sma200
        else "bear"
        if market_close < sma50 < sma200
        else "sideways"
    )
    if execution_reference > 0:
        extension = instrument.bars[-1].close / execution_reference - 1

    # Dates, rather than array positions, include the same-day exit sorted before an entry.
    # A final terminal always wins over transient provisional events on a later replay.
    terminals: list[tuple[date, int, SignalFinality, StrategySignal | None]] = [
        (signal.occurred_on, 0 if signal.code == "SMA150_EXIT" else 1, signal.finality, signal)
        for signal in signal_history
        if signal.code in _INVALIDATING_CODES
        and source.occurred_on <= signal.occurred_on <= bundle.as_of
    ]
    anchors_available = source.code != "TREND_BREAKOUT_ENTRY"
    if source.code == "TREND_BREAKOUT_ENTRY" and features is not None:
        frame = features.frame
        source_rows = [
            index for index, day in enumerate(frame.index) if day.date() == source.occurred_on
        ]
        if len(source_rows) == 1 and {"ATR", "Trend_Breakout_High_Prev"} <= set(frame.columns):
            row = frame.iloc[source_rows[0]]
            atr_value = row["ATR"]
            breakout_value = row["Trend_Breakout_High_Prev"]
            anchors_available = all(
                value is not None and isfinite(float(value)) and float(value) > 0
                for value in (atr_value, breakout_value)
            )
            if anchors_available:
                atr = Decimal(str(atr_value))
                breakout = Decimal(str(breakout_value))
                threshold = breakout - BREAKOUT_ATR_INVALIDATION_MULTIPLIER * atr
                for bar in instrument.bars[source_bar_index + 1 :]:
                    if bar.close <= threshold:
                        terminals.append(
                            (bar.session_date, 2, SignalFinality(bar.finality.value), None)
                        )
                price_terminals = [item for item in terminals if item[1] == 2]
                if price_terminals:
                    first = min(
                        price_terminals,
                        key=lambda item: (item[2] is not SignalFinality.FINAL, item[0]),
                    )
                    failed_close = next(
                        bar.close for bar in instrument.bars if bar.session_date == first[0]
                    )
                    price_evidence = [
                        Evidence(
                            code=code,
                            message=message,
                            observed_value=float(value),
                            reference_value=float(threshold)
                            if code == "BREAKOUT_FAILURE_CLOSE"
                            else None,
                            importance=Importance.MEDIUM,
                            source=SIGNAL_POLICY_VERSION,
                        )
                        for code, message, value in (
                            ("BREAKOUT_FAILURE_CLOSE", "취소선 이하 종가", failed_close),
                            ("BREAKOUT_LEVEL_AT_SIGNAL", "Signal 당시 돌파선", breakout),
                            ("ATR_AT_SIGNAL", "Signal 당시 ATR(14)", atr),
                            (
                                "BREAKOUT_ATR_MULTIPLIER",
                                "진입 허가 취소 ATR 배수",
                                BREAKOUT_ATR_INVALIDATION_MULTIPLIER,
                            ),
                            ("BREAKOUT_INVALIDATION_LEVEL", "진입 허가 취소선", threshold),
                        )
                    ]
    terminals.extend(
        (bar.session_date, 3, SignalFinality(bar.finality.value), None)
        for index, bar in enumerate(instrument.bars)
        if index - source_bar_index > params.entry_opportunity_max_age_bars
    )
    if terminals:
        terminal_on, terminal_priority, terminal_finality, invalidated_by = min(
            terminals,
            key=lambda item: (item[2] is not SignalFinality.FINAL, item[0], item[1]),
        )
        if invalidated_by is not None:
            if not has_active_identity(invalidated_by):
                terminal_on = terminal_finality = None
                invalidated_by = None
                return result(
                    EntryOpportunityStatus.NOT_EVALUATED, "INVALIDATOR_SIGNAL_IDENTITY_MISMATCH"
                )
            structure = StructureStatus.INVALID
            return result(EntryOpportunityStatus.INVALIDATED, "ENTRY_INVALIDATED")
        if terminal_priority == 2:
            structure = StructureStatus.INVALID
            return result(EntryOpportunityStatus.INVALIDATED, "BREAKOUT_ATR_INVALIDATED")
        structure = StructureStatus.VALID
        return result(EntryOpportunityStatus.EXPIRED, "ENTRY_EXPIRED")
    if not anchors_available:
        return result(EntryOpportunityStatus.NOT_EVALUATED, "BREAKOUT_ATR_ANCHOR_UNAVAILABLE")
    if execution_reference <= 0:
        return result(EntryOpportunityStatus.NOT_EVALUATED, "INVALID_REFERENCE_PRICE")
    structure = StructureStatus.VALID
    if regime == "bear":
        return result(EntryOpportunityStatus.BLOCK, "BEAR_MARKET")
    if regime == "bull" and extension <= Decimal(str(params.entry_opportunity_max_extension)):
        return result(EntryOpportunityStatus.ALLOW, "ENTRY_WITHIN_EXTENSION")
    return result(EntryOpportunityStatus.WATCH, "ENTRY_WATCH")

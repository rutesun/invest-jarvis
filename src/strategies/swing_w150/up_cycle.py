"""Chart-only INITIAL and explicitly selected restart state transitions."""

from src.storage.canonical import canonical_hash
from src.strategies.models import BarFinality, SignalFinality, UpCycleState
from src.strategies.swing_w150.support_ladder import number


def advance_up_cycle(
    state,
    row,
    *,
    ticker,
    day,
    finality,
    confirmed_pivots,
    independent_entries,
    sma150_failed,
    params,
) -> UpCycleState:
    state = state or UpCycleState(finality=BarFinality.FINAL)
    if finality != BarFinality.FINAL:
        return state
    if sma150_failed and state.status == "ACTIVE":
        return state.model_copy(
            update={
                "status": "TERMINATED",
                "status_as_of": day,
                "terminated_on": day,
                "terminal_reason": "SMA150_SUPPORT_FAILED",
                "above_sma150_count": 0,
            }
        )
    if state.status == "ACTIVE":
        return state.model_copy(update={"status_as_of": day})
    if state.terminated_on is not None and day <= state.terminated_on:
        return state
    close, sma, slope = (
        number(row, key)
        for key in ("Close", "SMA_150", f"SMA_150_Slope_{params.direction_lookback_bars}")
    )
    above = close is not None and sma is not None and close > sma
    count = (
        state.above_sma150_count
        if state.status_as_of == day
        else (state.above_sma150_count + 1 if above else 0)
    )
    hh = any(getattr(pivot, "relation", None) == "HIGHER_HIGH" for pivot in confirmed_pivots)
    entries = [
        signal
        for signal in independent_entries
        if signal.code in {"TREND_BREAKOUT_ENTRY", "DEEP_RECOVERY_ENTRY"}
        and signal.occurred_on == day
        and signal.finality == SignalFinality.FINAL
    ]
    confirmation = (
        "HIGHER_HIGH"
        if hh
        else "PRICE_BREAKOUT"
        if row.get("Price_Breakout_Event") is True or row.get("Price_Breakout_Event") == 1
        else entries[0].code
        if entries
        else None
    )
    if state.status == "INACTIVE":
        history = number(row, "History_Bars")
        allowed = (
            history is not None
            and history >= params.minimum_history_bars
            and above
            and slope is not None
            and slope >= 0
            and confirmation is not None
        )
    else:
        mode = params.support_cycle.restart_mode
        base = above and count >= 2
        allowed = bool(
            above
            and (
                (mode == "A" and base)
                or (mode == "B" and base and slope is not None and slope > 0)
                or (mode == "C" and base and (hh or bool(row.get("High_Break_5", False))))
                or (mode == "D" and entries)
            )
        )
        confirmation = f"RESTART_{mode}" if allowed else None
    if not allowed:
        return state.model_copy(update={"status_as_of": day, "above_sma150_count": count})
    return UpCycleState(
        cycle_id=canonical_hash(
            "jarvis:up-cycle:v1",
            {"ticker": ticker, "started_on": day, "parameters": params.parameter_fingerprint},
        ),
        started_on=day,
        status="ACTIVE",
        status_as_of=day,
        confirmation_code=confirmation,
        confirmation_on=day,
        finality=finality,
        above_sma150_count=count,
    )

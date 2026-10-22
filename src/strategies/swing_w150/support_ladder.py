"""Pure per-anchor support tests. No portfolio, execution or outcome inputs."""

from datetime import date
from decimal import Decimal
from math import isfinite

from src.strategies.models import BarFinality, SupportAnchor, SupportTestState
from src.strategies.swing_w150.parameters import SupportCycleParameters, SwingW150ParametersV2


def number(row, key):
    value = row.get(key)
    return float(value) if value is not None and isfinite(float(value)) else None


def anchor_value(anchor: SupportAnchor, row) -> Decimal | None:
    if not anchor.is_dynamic:
        return anchor.origin_price
    column = {"SMA50": "SMA_50", "SMA150": "SMA_150", "SUPERTREND": "SuperTrend_Up"}.get(
        anchor.anchor_type
    )
    if anchor.anchor_type == "SUPERTREND" and number(row, "SuperTrend_Dir") != 1:
        return None
    value = number(row, column)
    return Decimal(str(value)) if value is not None else None


def _new_test_after_reclaim(anchor, day, finality):
    return SupportTestState(
        anchor=anchor,
        status="RECLAIMED",
        below_count=0,
        started_on=day,
        status_as_of=day,
        ended_on=None,
        finality=finality,
        reclaimed_on=day,
    )


def advance_support_tests(
    states, row, *, new_anchors, day: date, finality: BarFinality, params: SupportCycleParameters
) -> list[SupportTestState]:
    """Return new immutable states; repeated FINAL days never increment counts."""
    if finality != BarFinality.FINAL:
        return list(states)
    result = list(states)
    known = {state.anchor.anchor_id for state in states}
    for anchor in new_anchors:
        if anchor.anchor_id not in known:
            result.append(
                SupportTestState(
                    anchor=anchor,
                    status="HELD",
                    below_count=0,
                    started_on=day,
                    status_as_of=day,
                    ended_on=None,
                    finality=finality,
                )
            )
            known.add(anchor.anchor_id)
    updated = []
    for state in result:
        if state.ended_on is not None and state.reclaimed_on is not None:
            updated.append(state)
            continue
        if state in states and state.status_as_of >= day:
            updated.append(state)
            continue
        level = anchor_value(state.anchor, row)
        anchor = state.anchor.model_copy(update={"current_value": level})
        close, atr = number(row, "Close"), number(row, "ATR")
        changes = {"anchor": anchor, "status_as_of": day, "finality": finality}
        if (
            level is None
            or close is None
            or atr is None
            or atr <= 0
            or params.support_break_buffer_atr is None
        ):
            # An unassessed FINAL bar cannot bridge consecutive confirmed closes.
            if state.status != "FAILED":
                changes.update(below_count=0, status_as_of=state.status_as_of)
            updated.append(state.model_copy(update=changes))
            continue
        breached = close < float(level) - params.support_break_buffer_atr * atr
        if state.status == "FAILED":
            if close > float(level) and state.reclaimed_on is None:
                changes["reclaimed_on"] = day
                if anchor.is_dynamic:
                    updated.append(state.model_copy(update=changes))
                    updated.append(_new_test_after_reclaim(anchor, day, finality))
                    continue
            updated.append(state.model_copy(update=changes))
            continue
        count = state.below_count + 1 if breached else 0
        normal = params.normal_failure_closes is not None and count >= params.normal_failure_closes
        previous, ratio, high, low = (
            number(row, key) for key in ("Previous_Close", "Volume_Ratio_Prev20", "High", "Low")
        )
        immediate = bool(
            breached
            and params.immediate_failure_volume_ratio is not None
            and previous is not None
            and close < previous
            and ratio is not None
            and ratio >= params.immediate_failure_volume_ratio
            and high is not None
            and low is not None
            and high > low
            and (close - low) / (high - low) <= params.immediate_failure_close_location
        )
        if breached and (normal or immediate):
            changes.update(
                status="FAILED",
                below_count=count,
                ended_on=day,
                failure_latched=not anchor.is_dynamic,
                reclaimed_on=None,
            )
        elif breached:
            changes.update(status="SOFT_BREACH", below_count=count, reclaimed_on=None)
        elif state.status == "SOFT_BREACH" and close > float(level):
            changes.update(status="RECLAIMED", below_count=0, reclaimed_on=day, ended_on=day)
            updated.append(state.model_copy(update=changes))
            updated.append(_new_test_after_reclaim(anchor, day, finality))
            continue
        else:
            changes.update(status="HELD", below_count=0)
        updated.append(state.model_copy(update=changes))
    return updated


def select_support(states, *, close, low, atr, params: SwingW150ParametersV2):
    """Choose highest eligible individual price; zone display never changes this."""
    if atr is None or atr <= 0:
        return None
    distance = params.pullback_support_atr_distance * atr
    candidates = [
        state
        for state in states
        if state.status != "FAILED"
        and state.ended_on is None
        and not state.failure_latched
        and state.anchor.current_value is not None
        and (
            float(state.anchor.current_value) <= close
            or low - distance <= float(state.anchor.current_value) <= low + distance
        )
    ]
    return max(
        candidates,
        key=lambda state: (state.anchor.current_value, state.anchor.anchor_id),
        default=None,
    )


def cluster_supports(states, *, atr: float, distance_atr: float) -> list[list[SupportAnchor]]:
    """Display-only complete-width clusters, never transitive single-link chains."""
    anchors = sorted(
        (
            state.anchor
            for state in states
            if state.anchor.current_value is not None
            and state.status != "FAILED"
            and state.ended_on is None
            and not state.failure_latched
        ),
        key=lambda anchor: (anchor.current_value, anchor.anchor_id),
    )
    clusters: list[list[SupportAnchor]] = []
    for anchor in anchors:
        if (
            not clusters
            or float(anchor.current_value - clusters[-1][0].current_value) > atr * distance_atr
        ):
            clusters.append([anchor])
        else:
            clusters[-1].append(anchor)
    return clusters

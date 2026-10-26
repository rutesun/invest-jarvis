from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
import pytest

from src.strategies.models import BarFinality, SignalFinality, UpCycleState
from src.strategies.swing_w150.parameters import SupportCycleParameters, SwingW150ParametersV2


DAY = date(2024, 1, 2)


def step(
    state=None, offset=0, *, finality=BarFinality.FINAL, failed=False, entries=(), mode=None, **row
):
    from src.strategies.swing_w150.up_cycle import advance_up_cycle

    params = replace(
        SwingW150ParametersV2(), support_cycle=SupportCycleParameters(restart_mode=mode)
    )
    return advance_up_cycle(
        state or UpCycleState(finality=BarFinality.FINAL),
        pd.Series(
            {
                "History_Bars": 250,
                "Close": 101,
                "SMA_150": 100,
                "SMA_150_Slope_21": 0,
                "Price_Breakout_Event": True,
                "High_Break_5": False,
                **row,
            }
        ),
        ticker="TEST",
        day=DAY + timedelta(days=offset),
        finality=finality,
        confirmed_pivots=(),
        independent_entries=entries,
        sma150_failed=failed,
        params=params,
    )


def test_initial_flat_sma_and_breakout_is_sufficient_without_other_gates():
    state = step(SMA_50=50, SuperTrend_Dir=-1, Volume_Ratio_Prev20=0.1)
    assert state.status == "ACTIVE"
    assert state.started_on == DAY


@pytest.mark.parametrize(
    "values",
    [
        {"Close": 100},
        {"SMA_150_Slope_21": -0.1},
        {"SMA_150_Slope_21": None},
        {"Price_Breakout_Event": False},
    ],
)
def test_initial_requires_all_mandatory_conditions(values):
    assert step(**values).status == "INACTIVE"


def test_termination_is_latched_and_same_day_cannot_restart():
    state = step()
    state = step(state, 1, failed=True)
    assert state.status == "TERMINATED"
    assert step(state, 1, mode="A").status == "TERMINATED"
    assert step(state, 2).status == "TERMINATED"


def test_restart_a_needs_two_final_above_closes_and_new_cycle_identity():
    initial = step()
    ended = step(initial, 1, failed=True)
    once = step(ended, 2, mode="A")
    assert step(once, 2, mode="A").above_sma150_count == 1
    assert step(once, 3, mode="A", finality=BarFinality.PROVISIONAL).status == "TERMINATED"
    restarted = step(once, 3, mode="A")
    assert restarted.status == "ACTIVE"
    assert restarted.cycle_id != initial.cycle_id


def test_initial_provisional_never_commits_a_cycle():
    assert step(finality=BarFinality.PROVISIONAL).status == "INACTIVE"


def test_initial_minimum_history_is_enforced_at_kernel_boundary():
    assert step(History_Bars=249).status == "INACTIVE"


def test_restart_b_rejects_flat_slope_and_c_requires_new_confirmation():
    ended = step(step(), 1, failed=True)
    once = step(ended, 2, mode="B")
    assert step(once, 3, mode="B").status == "TERMINATED"
    assert step(once, 3, mode="C", High_Break_5=False).status == "TERMINATED"
    assert step(once, 3, mode="C", High_Break_5=True).status == "ACTIVE"


def test_cycle_kernel_accepts_missing_initial_state():
    from src.strategies.swing_w150.up_cycle import advance_up_cycle

    state = advance_up_cycle(
        None,
        pd.Series(
            {
                "History_Bars": 250,
                "Close": 101,
                "SMA_150": 100,
                "SMA_150_Slope_21": 0,
                "Price_Breakout_Event": True,
            }
        ),
        ticker="TEST",
        day=DAY,
        finality=BarFinality.FINAL,
        confirmed_pivots=(),
        independent_entries=(),
        sma150_failed=False,
        params=SwingW150ParametersV2(),
    )
    assert state.status == "ACTIVE"


def test_terminated_cycle_cannot_restart_from_old_confirmation():
    from types import SimpleNamespace

    ended = step(step(), 1, failed=True)
    old = SimpleNamespace(
        code="DEEP_RECOVERY_ENTRY", occurred_on=DAY, finality=SignalFinality.FINAL
    )
    assert step(ended, 2, entries=[old], mode="D").status == "TERMINATED"


@pytest.mark.parametrize("code", ["TREND_BREAKOUT_ENTRY", "DEEP_RECOVERY_ENTRY"])
def test_restart_creates_new_cycle_id(code):
    from types import SimpleNamespace

    first = step()
    ended = step(first, 1, failed=True)
    entry = SimpleNamespace(
        code=code, occurred_on=DAY + timedelta(days=2), finality=SignalFinality.FINAL
    )
    restarted = step(ended, 2, entries=[entry], mode="D", SMA_150_Slope_21=-1)
    assert restarted.status == "ACTIVE"
    assert restarted.cycle_id != first.cycle_id


@pytest.mark.parametrize("code", ["PULLBACK_REVERSAL_ENTRY", "DEEP_RECOVERY_ENTRY"])
@pytest.mark.parametrize("boundary", ["below_sma150", "provisional", "before_termination"])
def test_restart_d_rejects_ineligible_entry(code, boundary):
    from types import SimpleNamespace

    ended = step(step(), 1, failed=True)
    entry = SimpleNamespace(
        code=code,
        occurred_on=DAY if boundary == "before_termination" else DAY + timedelta(days=2),
        finality=SignalFinality.PROVISIONAL if boundary == "provisional" else SignalFinality.FINAL,
    )
    assert (
        step(
            ended, 2, entries=[entry], mode="D", Close=99 if boundary == "below_sma150" else 101
        ).status
        == "TERMINATED"
    )


def test_cycle_cannot_bootstrap_from_own_pullback_entry():
    from types import SimpleNamespace

    entry = SimpleNamespace(
        code="PULLBACK_REVERSAL_ENTRY", occurred_on=DAY, finality=SignalFinality.FINAL
    )
    assert step(entries=[entry], Price_Breakout_Event=False).status == "INACTIVE"

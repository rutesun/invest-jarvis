from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from src.strategies.models import BarFinality, SupportAnchor
from src.strategies.swing_w150.parameters import SupportCycleParameters, SwingW150ParametersV2


DAY = date(2024, 1, 2)


def anchor(kind="SMA150", price=100, dynamic=True, identity="a"):
    return SupportAnchor(
        anchor_id=identity,
        anchor_type=kind,
        is_dynamic=dynamic,
        origin_on=DAY,
        origin_price=Decimal(price),
        current_value=Decimal(price),
    )


def advance(states, close, offset=0, *, anchors=(), finality=BarFinality.FINAL, **values):
    from src.strategies.swing_w150.support_ladder import advance_support_tests

    row = pd.Series(
        {
            "Close": close,
            "Low": close - 1,
            "High": close + 1,
            "ATR": 2,
            "SMA_150": 100,
            "Previous_Close": 101,
            "Volume_Ratio_Prev20": 2,
            **values,
        }
    )
    return advance_support_tests(
        states,
        row,
        new_anchors=anchors,
        day=DAY + timedelta(days=offset),
        finality=finality,
        params=SupportCycleParameters(normal_failure_closes=2, support_break_buffer_atr=0),
    )


def test_new_anchor_is_registered_and_dynamic_origin_does_not_move():
    states = advance([], 101, anchors=[anchor()])
    states = advance(states, 103, 1, SMA_150=102)
    assert states[0].anchor.origin_price == Decimal(100)
    assert states[0].anchor.current_value == Decimal(102)


def test_same_day_does_not_double_count_and_provisional_does_not_commit_failure():
    states = advance([], 99, anchors=[anchor()])
    assert states[0].below_count == 1
    assert advance(states, 99)[0].below_count == 1
    preview = advance(states, 98, 1, finality=BarFinality.PROVISIONAL)
    assert preview[0].status != "FAILED"
    recovered = advance(states, 101, 1)
    assert recovered[0].below_count == 0
    assert states[0].below_count == 1


def test_failed_frozen_anchor_is_not_reused_but_reclaim_is_observed():
    states = advance([], 99, anchors=[anchor("PRIOR_BREAKOUT_LEVEL", dynamic=False)])
    states = advance(states, 98, 1)
    assert states[0].status == "FAILED"
    states = advance(states, 102, 2)
    assert states[0].failure_latched is True
    assert states[0].reclaimed_on == DAY + timedelta(days=2)
    from src.strategies.swing_w150.support_ladder import select_support

    assert select_support(states, close=102, low=100, atr=2, params=SwingW150ParametersV2()) is None


def test_supertrend_down_removes_support_without_freezing_old_band():
    from src.strategies.swing_w150.support_ladder import select_support

    states = advance(
        [],
        103,
        anchors=[
            anchor("SMA50", 101, identity="50"),
            anchor("SMA150", 100, identity="150"),
            anchor("SUPERTREND", 102, identity="st"),
        ],
        SMA_50=101,
        SuperTrend_Dir=-1,
        SuperTrend_Up=102,
    )
    selected = select_support(states, close=103, low=100, atr=2, params=SwingW150ParametersV2())
    assert selected.anchor.anchor_id == "50"


def test_ladder_orders_by_price_not_anchor_kind():
    from src.strategies.swing_w150.support_ladder import select_support

    states = advance(
        [],
        105,
        anchors=[
            anchor("SUPERTREND", 100, identity="st"),
            anchor("SMA50", 101, identity="50"),
            anchor("SMA150", 103, identity="150"),
            anchor("PRIOR_BREAKOUT_LEVEL", 102, False, "breakout"),
        ],
        SMA_50=101,
        SMA_150=103,
        SuperTrend_Dir=1,
        SuperTrend_Up=100,
    )
    selected = select_support(states, close=105, low=103, atr=2, params=SwingW150ParametersV2())
    assert selected.anchor.anchor_id == "150"


def test_cluster_keeps_independent_anchor_failures():
    from src.strategies.swing_w150.support_ladder import cluster_supports

    states = advance(
        [],
        101,
        anchors=[
            anchor("PRIOR_BREAKOUT_LEVEL", "100", False, "lower"),
            anchor("PRIOR_BREAKOUT_LEVEL", "100.2", False, "upper"),
        ],
    )
    assert [
        [item.anchor_id for item in group]
        for group in cluster_supports(states, atr=2, distance_atr=0.5)
    ] == [["lower", "upper"]]
    states = advance(states, 100.1, 1)
    states = advance(states, 99.9, 2)
    assert [(item.anchor.anchor_id, item.status) for item in states] == [
        ("lower", "SOFT_BREACH"),
        ("upper", "FAILED"),
    ]


def test_immediate_failure_uses_down_close_volume_and_close_location():
    from src.strategies.swing_w150.support_ladder import advance_support_tests

    params = SupportCycleParameters(
        normal_failure_closes=3,
        support_break_buffer_atr=0,
        immediate_failure_volume_ratio=1.5,
        immediate_failure_close_location=0.25,
    )
    for previous, high, expected in [
        (101, 101, "FAILED"),
        (98, 101, "SOFT_BREACH"),
        (101, 99, "SOFT_BREACH"),
    ]:
        states = advance_support_tests(
            [],
            pd.Series(
                {
                    "Close": 99,
                    "Low": 99,
                    "High": high,
                    "Previous_Close": previous,
                    "ATR": 2,
                    "SMA_150": 100,
                    "Volume_Ratio_Prev20": 1.5,
                }
            ),
            new_anchors=[anchor()],
            day=DAY,
            finality=BarFinality.FINAL,
            params=params,
        )
        assert states[0].status == expected


def test_zone_has_complete_width_bound_instead_of_transitive_chain():
    from src.strategies.swing_w150.support_ladder import cluster_supports

    states = advance(
        [], 104, anchors=[anchor("PRIOR_BREAKOUT_LEVEL", p, False, str(p)) for p in [100, 101, 102]]
    )
    groups = cluster_supports(states, atr=2, distance_atr=0.75)
    assert [[item.anchor_id for item in group] for group in groups] == [["100", "101"], ["102"]]


@pytest.mark.parametrize("missing", [{"Close": None}, {"SMA_150": None}, {"ATR": None}, {"ATR": 0}])
def test_missing_final_reference_breaks_consecutive_confirmation_without_claiming_held(missing):
    states = advance([], 99, anchors=[anchor()])
    unknown = advance(states, 99, 1, **missing)
    assert unknown[-1].status == "SOFT_BREACH"
    assert unknown[-1].below_count == 0
    assert unknown[-1].status_as_of == DAY
    next_breach = advance(unknown, 99, 2)
    assert next_breach[-1].status == "SOFT_BREACH"
    assert next_breach[-1].below_count == 1
    recovered = advance(next_breach, 101, 3)
    assert recovered[-1].status == "RECLAIMED"
    assert recovered[-1].reclaimed_on == DAY + timedelta(days=3)


def test_repeated_dynamic_failure_reclaim_preserves_old_facts_and_opens_new_episodes():
    states = []
    statuses = []
    first_reclaim = None
    for offset, close in enumerate([99, 101, 99, 99, 101, 99, 99, 101]):
        states = advance(states, close, offset, anchors=[anchor()] if offset == 0 else [])
        statuses.append(states[-1].status)
        if offset == 1:
            first_reclaim = states[0].model_dump()
        if offset in {2, 5}:
            assert states[-1].reclaimed_on is None
    assert statuses == [
        "SOFT_BREACH",
        "RECLAIMED",
        "SOFT_BREACH",
        "FAILED",
        "RECLAIMED",
        "SOFT_BREACH",
        "FAILED",
        "RECLAIMED",
    ]
    assert states[0].model_dump() == first_reclaim
    archived_reclaims = {state.reclaimed_on for state in states if state.ended_on is not None}
    assert archived_reclaims == {DAY + timedelta(days=i) for i in [1, 4, 7]}
    assert states[-1].started_on == DAY + timedelta(days=7)


def test_archived_soft_reclaim_does_not_duplicate_ladder_or_zone_anchor():
    from src.strategies.swing_w150.support_ladder import cluster_supports, select_support

    states = advance([], 99, anchors=[anchor()])
    states = advance(states, 101, 1)
    assert len(states) == 2
    assert states[0].ended_on == DAY + timedelta(days=1)
    assert states[-1].ended_on is None
    selected = select_support(states, close=101, low=100, atr=2, params=SwingW150ParametersV2())
    assert selected is states[-1]
    assert sum(map(len, cluster_supports(states, atr=2, distance_atr=0.5))) == 1


def test_frozen_failure_remains_latched_across_repeated_reclaims_and_missing_reference():
    states = []
    for offset, close in enumerate([99, 99, 101, 99, 99, 101]):
        states = advance(
            states,
            close,
            offset,
            anchors=[anchor("PRIOR_BREAKOUT_LEVEL", dynamic=False)] if offset == 0 else [],
        )
    assert len(states) == 1
    assert states[0].status == "FAILED" and states[0].failure_latched
    assert states[0].reclaimed_on == DAY + timedelta(days=2)
    unknown = advance(states, 99, 6, ATR=None)
    assert unknown[0].status == "FAILED" and unknown[0].failure_latched

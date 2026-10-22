import numpy as np
import pytest

from src.tools.technical.pivots import confirmed_pivots


def _series(lows: list[float]) -> tuple[np.ndarray, np.ndarray]:
    low = np.array(lows, dtype=float)
    return low + 1.0, low


def test_higher_low_on_small_handmade_series():
    # 저점: i=4(값 5) → i+3=7부터 확인, i=10(값 6) → i+3=13부터 확인
    high, low = _series([9, 8, 7, 6, 5, 6, 7, 8, 9, 8, 6, 7, 8, 9, 10, 11])
    higher_low, lhll = confirmed_pivots(high, low)

    assert not higher_low[:13].any()
    assert higher_low[13:].all()
    assert not lhll.any()


def test_pivot_is_invisible_before_three_bar_confirmation():
    high, low = _series([9, 8, 7, 6, 5, 6, 7, 8, 9, 8, 6, 7, 8, 9, 10, 11])
    full, _ = confirmed_pivots(high, low)

    # 12번 봉까지만 본 판정은 전체 데이터로 본 같은 구간과 같아야 한다(미래 봉 미사용).
    for end in range(8, len(low) + 1):
        partial, _ = confirmed_pivots(high[:end], low[:end])
        np.testing.assert_array_equal(partial, full[:end])


def test_lower_low_and_lower_high_together():
    # 고점 10.0(i=3) → 9.0(i=11), 저점 5.0(i=7) → 4.0(i=15)
    high = np.array([7, 8, 9, 10, 9, 8, 7, 6, 7, 8, 8.5, 9, 8, 7, 6, 5, 6, 7, 8, 9], dtype=float)
    low = high - 1.0
    higher_low, lhll = confirmed_pivots(high, low)

    assert lhll[18]
    assert not lhll[:18].any()
    assert not higher_low[18]


def test_short_series_returns_all_false():
    high, low = _series([3, 2, 1])
    higher_low, lhll = confirmed_pivots(high, low)

    assert higher_low.shape == (3,) and not higher_low.any()
    assert lhll.shape == (3,) and not lhll.any()


def test_confirmed_pivot_events_preserve_each_higher_high_and_higher_low():
    from src.tools.technical.pivots import confirmed_pivot_events

    high, low = _series(
        [5, 6, 7, 10, 8, 7, 6, 3, 7, 8, 9, 11, 9, 8, 7, 4, 8, 9, 10, 12, 10, 9, 8, 5, 9, 10, 11]
    )
    events = confirmed_pivot_events(high, low)

    assert [(e.pivot_type, e.pivot_index, e.confirmed_index, e.relation) for e in events] == [
        ("HIGH", 3, 6, None),
        ("LOW", 7, 10, None),
        ("HIGH", 11, 14, "HIGHER_HIGH"),
        ("LOW", 15, 18, "HIGHER_LOW"),
        ("HIGH", 19, 22, "HIGHER_HIGH"),
        ("LOW", 23, 26, "HIGHER_LOW"),
    ]
    assert [(e.previous_pivot_index, e.previous_pivot_price) for e in events[2:]] == [
        (3, 11.0),
        (7, 3.0),
        (11, 12.0),
        (15, 4.0),
    ]
    with pytest.raises(AttributeError):
        events[0].price = 0


def test_pivot_event_is_visible_only_on_confirmation():
    from src.tools.technical.pivots import confirmed_pivot_events

    high, low = _series([9, 8, 7, 6, 5, 6, 7, 8, 9, 8, 6, 7, 8, 9, 10, 11])
    events = confirmed_pivot_events(high, low)
    for event in events:
        assert event.confirmed_index == event.pivot_index + 3
        assert event not in confirmed_pivot_events(
            high[: event.confirmed_index], low[: event.confirmed_index]
        )
    for end in range(len(low) + 1):
        assert confirmed_pivot_events(high[:end], low[:end]) == tuple(
            event for event in events if event.confirmed_index < end
        )


def test_equal_pivots_have_no_relation_and_keep_plateau_comparison():
    from src.tools.technical.pivots import confirmed_pivot_events

    high, low = _series([5, 6, 7, 10, 10, 8, 6, 3, 7, 8, 9, 10, 10, 8, 7, 3, 8, 9, 10])
    events = confirmed_pivot_events(high, low)
    assert [(e.pivot_type, e.pivot_index, e.relation) for e in events] == [
        ("HIGH", 3, None),
        ("LOW", 7, None),
        ("HIGH", 11, None),
        ("LOW", 15, None),
    ]
    higher_low, lower_low_lower_high = confirmed_pivots(high, low)
    assert higher_low.tolist() == [False] * 19
    assert lower_low_lower_high.tolist() == [False] * 19


def test_persistent_pivot_arrays_remain_unchanged():
    high = np.array([7, 8, 9, 10, 9, 8, 7, 6, 7, 8, 8.5, 9, 8, 7, 6, 5, 6, 7, 8, 9])
    higher_low, lower_low_lower_high = confirmed_pivots(high, high - 1)
    assert higher_low.tolist() == [False] * 20
    assert lower_low_lower_high.tolist() == [False] * 18 + [True, True]


@pytest.mark.parametrize(
    "unfinished, expected",
    [
        (3, [(9, 12, None, None), (15, 18, 9, "HIGHER_HIGH")]),
        (8, [(3, 6, None, None), (9, 12, 3, "HIGHER_HIGH"), (15, 18, 9, "HIGHER_HIGH")]),
        (9, [(3, 6, None, None), (8, 12, 3, "LOWER_HIGH"), (15, 18, 8, "HIGHER_HIGH")]),
        (10, [(3, 6, None, None), (9, 13, 3, "HIGHER_HIGH"), (15, 18, 9, "HIGHER_HIGH")]),
        (12, [(3, 6, None, None), (9, 13, 3, "HIGHER_HIGH"), (15, 18, 9, "HIGHER_HIGH")]),
        (19, [(3, 6, None, None), (9, 12, 3, "HIGHER_HIGH"), (15, 18, 9, "HIGHER_HIGH")]),
    ],
)
def test_final_pivots_exclude_origin_windows_and_previous_pivot_with_original_indices(
    unfinished, expected
):
    from src.tools.technical.pivots import confirmed_pivot_events

    high = np.array([1, 2, 3, 6, 3, 2, 1, 2, 3, 8, 3, 2, 1, 2, 3, 10, 3, 2, 1, 0], float)
    low = np.zeros(len(high))
    final_mask = np.ones(len(high), dtype=bool)
    final_mask[unfinished] = False
    events = confirmed_pivot_events(high, low, final_mask=final_mask)
    assert [
        (event.pivot_index, event.confirmed_index, event.previous_pivot_index, event.relation)
        for event in events
    ] == expected
    changed = high.copy()
    changed[unfinished] = 1000
    changed_low = low.copy()
    changed_low[unfinished] = -1000
    assert confirmed_pivot_events(changed, changed_low, final_mask=final_mask) == events
    for end in range(len(high) + 1):
        assert confirmed_pivot_events(high[:end], low[:end], final_mask=final_mask[:end]) == tuple(
            event for event in events if event.confirmed_index < end
        )


def test_all_final_pivot_events_preserve_existing_output():
    from src.tools.technical.pivots import confirmed_pivot_events

    high, low = _series([9, 8, 7, 6, 5, 6, 7, 8, 9, 8, 6, 7, 8, 9, 10, 11])
    assert confirmed_pivot_events(high, low, final_mask=np.ones(len(high), dtype=bool)) == (
        confirmed_pivot_events(high, low)
    )


def test_final_low_pivot_relation_uses_final_origin_and_previous_low():
    from src.tools.technical.pivots import confirmed_pivot_events

    low = -np.array([1, 2, 3, 6, 3, 2, 1, 2, 3, 8, 3, 2, 1, 2, 3, 10, 3, 2, 1, 0], float)
    final_mask = np.ones(len(low), dtype=bool)
    final_mask[9] = False
    events = confirmed_pivot_events(np.zeros(len(low)), low, final_mask=final_mask)
    assert [
        (e.pivot_index, e.confirmed_index, e.previous_pivot_index, e.relation) for e in events
    ] == [(3, 6, None, None), (8, 12, 3, "HIGHER_LOW"), (15, 18, 8, "LOWER_LOW")]

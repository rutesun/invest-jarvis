import numpy as np

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

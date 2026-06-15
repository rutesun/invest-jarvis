import pandas as pd

from src.tools.criteria.accumulation import analyze_accumulation
from src.tools.criteria.models import AccumulationResult


def test_accumulation_result_model():
    r = AccumulationResult(
        accumulation_days=14, distribution_days=8, accumulation_ratio=0.636, window=25
    )
    assert r.accumulation_days == 14
    assert r.distribution_days == 8
    assert abs(r.accumulation_ratio - 0.636) < 1e-6
    assert r.is_accumulating is True  # ratio > 0.5


def _df(rows):
    # rows: list of (open, high, low, close, volume)
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])


def test_distribution_day_down_close_up_volume():
    # day0 기준, day1: 종가 하락(-0.5%) + 거래량 증가 → 분산일
    df = _df(
        [
            (100, 101, 99, 100, 1000),  # prev
            (100, 100, 97, 99, 1500),  # close 99 < 100*0.998, vol 1500>1000 → distribution
        ]
    )
    r = analyze_accumulation(df, window=25)
    assert r.distribution_days == 1
    assert r.accumulation_days == 0


def test_accumulation_day_up_close_high_volume_top_close():
    # day1: 상승 + 거래량 증가 + 종가가 레인지 상단(>=0.5)
    df = _df(
        [
            (100, 101, 99, 100, 1000),
            (
                100,
                105,
                100,
                104,
                1500,
            ),  # close 104>100, vol↑, (104-100)/(105-100)=0.8>=0.5 → accumulation
        ]
    )
    r = analyze_accumulation(df, window=25)
    assert r.accumulation_days == 1
    assert r.distribution_days == 0


def test_ratio_and_window():
    # 평탄(거래량 감소) → 둘 다 0, ratio 0.0
    df = _df([(100, 101, 99, 100, 1000)] * 5 + [(100, 100, 99, 100, 500)])
    r = analyze_accumulation(df, window=25)
    assert r.accumulation_days == 0 and r.distribution_days == 0
    assert r.accumulation_ratio == 0.0

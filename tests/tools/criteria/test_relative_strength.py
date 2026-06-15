import numpy as np
import pandas as pd

from src.tools.criteria.models import RelativeStrengthResult
from src.tools.criteria.relative_strength import compute_relative_strength


def test_rs_result_model():
    r = RelativeStrengthResult(
        mansfield_rs=12.3, outperform_6m=18.0, rp_slope_4w=0.5, index_symbol="^GSPC"
    )
    assert r.mansfield_rs == 12.3
    assert r.is_strong is True  # mansfield_rs > 0 and rp_slope_4w >= 0


def test_rs_weak_when_negative():
    r = RelativeStrengthResult(
        mansfield_rs=-3.0, outperform_6m=-5.0, rp_slope_4w=-0.2, index_symbol="^KS11"
    )
    assert r.is_strong is False


def _series_df(closes):
    idx = pd.date_range("2023-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"Close": closes}, index=idx)


def test_rs_strong_when_stock_outpaces_index():
    n = 300
    # 종목은 지수보다 더 가파르게 상승 → RP 우상향 → Mansfield RS > 0
    stock = _series_df(list(np.linspace(100, 200, n)))
    index = _series_df(list(np.linspace(100, 120, n)))
    r = compute_relative_strength(stock, index, index_symbol="^GSPC")
    assert r.mansfield_rs > 0
    assert r.rp_slope_4w > 0
    assert r.is_strong is True


def test_rs_handles_misaligned_dates():
    stock = _series_df(list(np.linspace(100, 150, 300)))
    index = _series_df(list(np.linspace(100, 130, 300)))
    # 인덱스가 일부 다른 경우에도 공통 날짜로 정렬
    index = index.iloc[5:]
    r = compute_relative_strength(stock, index, index_symbol="^GSPC")
    assert isinstance(r.mansfield_rs, float)

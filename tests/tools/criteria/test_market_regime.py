import numpy as np
import pandas as pd

from src.tools.playbook.market_regime import assess_market_regime
from src.tools.playbook.models import MarketRegimeResult


def _df(closes):
    idx = pd.date_range("2023-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"Close": closes}, index=idx)


def test_uptrend_allows_new_buy():
    df = _df(list(np.linspace(100, 200, 260)))  # 우상향
    r = assess_market_regime(df, "^GSPC")
    assert r.allow_new_buy is True and r.regime == "상승"


def test_downtrend_blocks():
    df = _df(list(np.linspace(200, 100, 260)))  # 우하향
    r = assess_market_regime(df, "^KS11")
    assert r.allow_new_buy is False


def test_insufficient_data_blocks():
    df = _df(list(np.linspace(100, 150, 100)))  # 100일만 (200 미달)
    r = assess_market_regime(df, "^GSPC")
    assert r.allow_new_buy is False
    assert r.regime == "unknown"


def test_result_type():
    df = _df(list(np.linspace(100, 200, 260)))
    r = assess_market_regime(df, "^GSPC")
    assert isinstance(r, MarketRegimeResult)
    assert isinstance(r.allow_new_buy, bool)
    assert r.index_symbol == "^GSPC"
    assert r.detail != ""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from tests.harness.swing_fixture_contract import (
    assert_swing_price_contract,
    assert_swing_trades_contract,
)


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "swing_w150"
TICKERS = ("COIN", "AMAT", "PYPL", "UPST")


def load_prices(ticker: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURES / f"{ticker}.csv", parse_dates=["Date"]).set_index("Date")
    assert_swing_price_contract(df)
    return df


def load_trades(ticker: str, df: pd.DataFrame) -> list[dict]:
    trades = json.loads((FIXTURES / f"{ticker}.trades.json").read_text())
    assert_swing_trades_contract(trades, df)
    return trades


@pytest.fixture(params=TICKERS)
def golden_case(request) -> tuple[str, pd.DataFrame, list[dict]]:
    df = load_prices(request.param)
    return request.param, df, load_trades(request.param, df)


@pytest.fixture
def pypl() -> tuple[pd.DataFrame, list[dict]]:
    df = load_prices("PYPL")
    return df, load_trades("PYPL", df)

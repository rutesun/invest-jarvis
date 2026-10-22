from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.strategies.models import BarFinality
from src.strategies.swing_w150.features import SwingFeatureFrame
from src.tools.technical.scorecard_models import DataStatus
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


class SignalFactory:
    """Deterministic indicator rows for testing chart-only transitions."""

    def make(self, changes: list[dict[str, float]]) -> SwingFeatureFrame:
        dates = pd.date_range("2024-01-02", periods=250 + len(changes), freq="B")
        rows = [self._row() for _ in range(250)]
        rows.extend(self._row(**change) for change in changes)
        return SwingFeatureFrame(
            frame=pd.DataFrame(rows, index=dates),
            data_status=DataStatus.COMPLETE,
            finalities=(BarFinality.FINAL,) * len(rows),
        )

    @staticmethod
    def _row(**changes: float) -> dict[str, float]:
        row = {
            "Open": 130.0,
            "High": 132.0,
            "Low": 128.0,
            "Close": 130.0,
            "Volume": 100.0,
            "SMA_20": 125.0,
            "SMA_50": 120.0,
            "SMA_150": 110.0,
            "SMA_200": 100.0,
            "SMA_20_Slope_5": 1.0,
            "SMA_50_Slope_21": 1.0,
            "SMA_150_Slope_21": 1.0,
            "SMA_200_Slope_21": 1.0,
            "ATR": 2.0,
            "SuperTrend_Up": 119.0,
            "SuperTrend_Dir": 1.0,
            "High_50_Prev": 140.0,
            "High_20_Prev": 140.0,
            "Trend_Breakout_High_Prev": 140.0,
            "Deep_Recovery_High_Prev": 140.0,
            "Vol_SMA_20": 100.0,
            "Vol_SMA_20_Prev": 100.0,
            "Low_20_Prev": 95.0,
            "Higher_Low": False,
            "Lower_Low_Lower_High": False,
            "cRSI": 50.0,
            "MACD": 1.0,
        }
        row.update(changes)
        return row

    def overheat_correction_recovery(self) -> SwingFeatureFrame:
        return self.make(
            [
                {"Close": 170, "High": 172, "SMA_50_Slope_21": 0},
                {"Close": 110, "High": 112, "Low": 109, "SMA_50_Slope_21": 0},
                {"Close": 130, "High": 132, "SMA_50_Slope_21": 0},
                {"Close": 131, "High": 133, "SMA_50_Slope_21": 0},
            ]
        )

    def overheat_then_reset_extension(self) -> SwingFeatureFrame:
        return self.make([{"Close": 170, "High": 172}, {"Close": 140, "High": 142}])

    def overheat_then_expiry(self) -> SwingFeatureFrame:
        return self.make([{"Close": 170, "High": 172}] + [{"Close": 155, "High": 157}] * 20)

    def correction_without_recovery(self, days: int) -> SwingFeatureFrame:
        return self.make(
            [{"Close": 170, "High": 172}, {"Close": 110, "High": 140}]
            + [{"Close": 130, "High": 140}] * days
        )

    def pullback_reversal(self, support: str, atr_distance: float = 0.5) -> SwingFeatureFrame:
        levels = {"SMA_50": 120, "SMA_150": 110, "SMA_200": 100, "SuperTrend_Up": 119}
        level = levels[support]
        reversal_close = max(level + 3, 112)
        return self.make(
            [
                {"Close": level + atr_distance, "Low": level, "High": level + 1},
                {"Close": reversal_close, "Low": level + 1, "High": reversal_close + 1},
                {"Close": 130, "Low": 128, "High": 132},
            ]
        )

    def pullback_invalidated(self) -> SwingFeatureFrame:
        return self.make(
            [
                {"Close": 121, "Low": 120, "High": 122},
                {"Close": 117, "Low": 116, "High": 119},
            ]
        )

    def pullback_expired_then_breakout(self) -> SwingFeatureFrame:
        return self.make(
            [{"Close": 121, "Low": 120, "High": 125}]
            + [{"Close": 123, "Low": 122, "High": 125}] * 10
            + [{"Close": 126, "Low": 125, "High": 127}]
        )

    def sma150_below_for_four_days(self) -> SwingFeatureFrame:
        return self.make(
            [
                {"Close": close, "Low": close - 2, "High": close + 2}
                for close in (108, 107, 106, 105)
            ]
        )

    def same_day_exit_and_entry(self) -> SwingFeatureFrame:
        return self.make(
            [
                {"Close": 102, "Low": 100, "High": 103},
                {"Close": 108, "Low": 100, "High": 109},
            ]
        )

    def deep_recovery_with_breakdown(self) -> SwingFeatureFrame:
        return self.make(
            [
                {"Close": 89, "Low": 88, "High": 91, "SMA_50": 90, "SMA_200": 120},
                {
                    "Close": 100,
                    "Low": 98,
                    "High": 101,
                    "SMA_20": 95,
                    "SMA_50": 90,
                    "SMA_200": 120,
                    "Higher_Low": True,
                    "Low_20_Prev": 105,
                    "Volume": 200,
                },
            ]
        )

    def new_support_approach(self) -> SwingFeatureFrame:
        return self.make(
            [
                {"Close": 121, "Low": 120, "High": 125},
                {"Close": 123, "Low": 122, "High": 125},
                {"Close": 121, "Low": 120, "High": 122},
            ]
        )

    def same_day_exit_and_overheat_correction(self) -> SwingFeatureFrame:
        return self.make(
            [
                {"Close": 170, "High": 172, "SMA_50": 70, "SMA_50_Slope_21": 0},
                {
                    "Close": 109,
                    "Low": 108,
                    "High": 111,
                    "SMA_20": 105,
                    "SMA_50": 70,
                    "SMA_50_Slope_21": 0,
                },
                {
                    "Close": 100,
                    "Low": 99,
                    "High": 102,
                    "SMA_20": 105,
                    "SMA_50": 70,
                    "SMA_50_Slope_21": 0,
                },
            ]
        )

    def below_sma150_without_rising_structure(self) -> SwingFeatureFrame:
        features = self.make(
            [
                {"Close": 130, "SMA_150_Slope_21": -1},
                {"Close": 108, "Low": 107, "High": 109, "SMA_150_Slope_21": -1},
                {"Close": 107, "Low": 106, "High": 108, "SMA_150_Slope_21": -1},
            ]
        )
        features.frame["SMA_150_Slope_21"] = -1
        return features


@pytest.fixture
def signal_factory() -> SignalFactory:
    return SignalFactory()


@pytest.fixture
def v2_raw_fixture() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "v2_signal_path.csv", parse_dates=["Date"]).set_index("Date")


@pytest.fixture
def v2_expected_fixture() -> dict:
    return json.loads((FIXTURES / "v2_signal_path.json").read_text())

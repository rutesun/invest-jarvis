from datetime import datetime

import pandas as pd
import pytest

from src.tools import macro
from src.tools.macro import MacroTool, TickerMacroSnapshot


@pytest.fixture
def synthetic_macro_history(monkeypatch):
    """Synthetic Close series, not captured yfinance data or a provider contract."""
    histories = {
        symbol: pd.DataFrame({"Close": closes})
        for symbol, closes in {
            "^VIX": [16.0, 17.0, 18.0, 19.0, 20.0],
            "CL=F": [78.0, 79.0, 80.0, 81.0, 82.5],
            "^TNX": [4.0, 4.05, 4.1, 4.2, 4.25],
            "^IRX": [4.8, 4.7, 4.6, 4.55, 4.5],
            "DX-Y.NYB": [103.0, 102.75, 102.5, 102.25, 102.0],
            "SPY": [100.0, 101.0, 102.0, 103.0, 105.0],
        }.items()
    }

    class SyntheticTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, *, period):
            assert period == "5d"
            return histories[self.symbol].copy()

    monkeypatch.setattr(macro.yf, "Ticker", SyntheticTicker)
    return histories


def test_macro_snapshot_model():
    snapshot = TickerMacroSnapshot(
        timestamp=datetime.now(),
        vix=18.5,
        vix_change=1.2,
        fear_greed=45,
        fear_greed_label="Neutral",
        wti=82.5,
        wti_change=-0.5,
        us_10y=4.25,
        us_2y=4.50,
        yield_spread=-0.25,
        dxy=102.5,
        dxy_change=0.3,
    )
    assert snapshot.vix == 18.5
    assert snapshot.fear_greed == 45
    assert snapshot.yield_spread == -0.25


@pytest.mark.asyncio
async def test_macro_tool_execute(synthetic_macro_history):
    tool = MacroTool()
    result = await tool.execute()

    assert result.success is True
    assert result.error is None
    assert isinstance(result.data, TickerMacroSnapshot)

    snapshot = result.data
    assert snapshot.vix == 20.0
    assert snapshot.vix_change == 1.0
    assert snapshot.wti == 82.5
    assert snapshot.wti_change == 1.5
    assert snapshot.us_10y == 4.25
    # Preserve the current ^IRX -> us_2y mapping; this is not a financial data claim.
    assert snapshot.us_2y == 4.5
    assert snapshot.dxy == 102.0
    assert snapshot.dxy_change == -0.25
    assert snapshot.fear_greed == 76


@pytest.mark.asyncio
async def test_macro_tool_yield_spread(synthetic_macro_history):
    tool = MacroTool()
    result = await tool.execute()

    assert result.success is True
    snapshot = result.data

    assert snapshot.us_10y == 4.25
    assert snapshot.us_2y == 4.5
    assert snapshot.yield_spread == -0.25


@pytest.mark.asyncio
async def test_macro_tool_fear_greed_label(synthetic_macro_history):
    tool = MacroTool()
    result = await tool.execute()

    assert result.success is True
    snapshot = result.data

    # VIX=20 and SPY=100->105 give the hand-calculated synthetic index 76.
    assert snapshot.fear_greed == 76
    assert snapshot.fear_greed_label == "Extreme Greed"


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["^VIX", "SPY"])
async def test_macro_tool_empty_history(synthetic_macro_history, symbol):
    synthetic_macro_history[symbol] = pd.DataFrame(columns=["Close"])

    result = await MacroTool().execute()

    assert result.success is False
    assert result.data is None
    assert result.error == f"No data found for {symbol}"


@pytest.mark.asyncio
async def test_macro_tool_provider_error(monkeypatch):
    class FailingTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, *, period):
            raise RuntimeError("synthetic macro provider failure")

    monkeypatch.setattr(macro.yf, "Ticker", FailingTicker)

    result = await MacroTool().execute()

    assert result.success is False
    assert result.data is None
    assert result.error == "synthetic macro provider failure"

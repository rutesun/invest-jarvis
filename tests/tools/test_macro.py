import pytest
from datetime import datetime
from src.tools.macro import MacroTool, MacroSnapshot


def test_macro_snapshot_model():
    snapshot = MacroSnapshot(
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
async def test_macro_tool_execute():
    tool = MacroTool()
    result = await tool.execute()

    assert result.success is True
    assert result.data is not None
    assert isinstance(result.data, MacroSnapshot)

    snapshot = result.data
    assert snapshot.vix > 0
    assert 0 <= snapshot.fear_greed <= 100
    assert snapshot.wti > 0
    assert snapshot.us_10y > 0
    assert snapshot.us_2y > 0
    assert snapshot.dxy > 0


@pytest.mark.asyncio
async def test_macro_tool_yield_spread():
    tool = MacroTool()
    result = await tool.execute()

    assert result.success is True
    snapshot = result.data

    expected_spread = snapshot.us_10y - snapshot.us_2y
    assert abs(snapshot.yield_spread - expected_spread) < 0.01


@pytest.mark.asyncio
async def test_macro_tool_fear_greed_label():
    tool = MacroTool()
    result = await tool.execute()

    assert result.success is True
    snapshot = result.data

    valid_labels = ["Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"]
    assert snapshot.fear_greed_label in valid_labels

    if snapshot.fear_greed <= 25:
        assert snapshot.fear_greed_label == "Extreme Fear"
    elif snapshot.fear_greed <= 45:
        assert snapshot.fear_greed_label == "Fear"
    elif snapshot.fear_greed <= 55:
        assert snapshot.fear_greed_label == "Neutral"
    elif snapshot.fear_greed <= 75:
        assert snapshot.fear_greed_label == "Greed"
    else:
        assert snapshot.fear_greed_label == "Extreme Greed"

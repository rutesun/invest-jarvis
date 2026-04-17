# tests/core/test_interfaces.py
import pandas as pd
import pytest

from src.core.interfaces import BaseProvider, BaseTool
from src.core.models import ToolResult


class MockTool(BaseTool):
    name = "mock"
    description = "Mock tool for testing"

    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"ticker": ticker})


class MockProvider(BaseProvider):
    async def get_price_history(self, ticker: str, period: str) -> pd.DataFrame:
        return pd.DataFrame({"Close": [100, 101, 102]})

    async def get_quote(self, ticker: str) -> dict:
        return {"price": 150.0}


@pytest.mark.asyncio
async def test_base_tool_interface():
    tool = MockTool()
    assert tool.name == "mock"
    result = await tool.execute("AAPL")
    assert result.success is True
    assert result.data["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_base_provider_interface():
    provider = MockProvider()
    df = await provider.get_price_history("AAPL", "1y")
    assert len(df) == 3
    quote = await provider.get_quote("AAPL")
    assert quote["price"] == 150.0

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.providers.llm_ticker_agent import LLMTickerAgent
from src.providers.ticker_models import TickerNotFoundError


def test_init_raises_without_api_key():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        LLMTickerAgent(api_key="")


@pytest.mark.asyncio
async def test_resolve_with_single_tool_call():
    """DuckDuckGo 1회 검색 후 티커 반환"""
    agent = LLMTickerAgent(api_key="test-key")

    tool_response = MagicMock()
    tool_response.tool_calls = [
        {
            "id": "call_1",
            "name": "duckduckgo_search",
            "args": {"query": "삼성전자 stock ticker KRX"},
        }
    ]
    tool_response.content = ""

    final_response = MagicMock()
    final_response.tool_calls = []
    final_response.content = (
        '{"ticker": "005930.KS", "display_name": "Samsung Electronics Co., Ltd."}'
    )

    mock_bound_llm = AsyncMock()
    mock_bound_llm.ainvoke = AsyncMock(side_effect=[tool_response, final_response])

    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_bound_llm)
    agent.llm = mock_llm

    with patch("src.providers.llm_ticker_agent.duckduckgo_search") as mock_ddg:
        mock_ddg.invoke.return_value = "Samsung Electronics Co., Ltd. trades on KRX as 005930.KS"
        ticker, display_name = await agent.resolve("삼성전자")

    assert ticker == "005930.KS"
    assert display_name == "Samsung Electronics Co., Ltd."


@pytest.mark.asyncio
async def test_resolve_without_tool_call():
    """LLM이 즉시 JSON 반환 (tool 호출 없음)"""
    agent = LLMTickerAgent(api_key="test-key")

    final_response = MagicMock()
    final_response.tool_calls = []
    final_response.content = '{"ticker": "RKLB", "display_name": "Rocket Lab USA, Inc."}'

    mock_bound_llm = AsyncMock()
    mock_bound_llm.ainvoke = AsyncMock(return_value=final_response)

    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_bound_llm)
    agent.llm = mock_llm

    ticker, display_name = await agent.resolve("로켓랩")

    assert ticker == "RKLB"
    assert display_name == "Rocket Lab USA, Inc."


@pytest.mark.asyncio
async def test_resolve_raises_on_invalid_json():
    """LLM이 유효하지 않은 JSON 반환 시 TickerNotFoundError"""
    agent = LLMTickerAgent(api_key="test-key")

    bad_response = MagicMock()
    bad_response.tool_calls = []
    bad_response.content = "I cannot find this ticker."

    mock_bound_llm = AsyncMock()
    mock_bound_llm.ainvoke = AsyncMock(return_value=bad_response)

    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_bound_llm)
    agent.llm = mock_llm

    with pytest.raises(TickerNotFoundError):
        await agent.resolve("존재하지않는회사")


@pytest.mark.asyncio
async def test_resolve_raises_after_max_iterations():
    """3회 tool 호출 이후에도 미해결 시 TickerNotFoundError"""
    agent = LLMTickerAgent(api_key="test-key")

    tool_response = MagicMock()
    tool_response.tool_calls = [
        {"id": "call_x", "name": "duckduckgo_search", "args": {"query": "some query"}}
    ]
    tool_response.content = ""

    mock_bound_llm = AsyncMock()
    mock_bound_llm.ainvoke = AsyncMock(return_value=tool_response)

    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_bound_llm)
    agent.llm = mock_llm

    with patch("src.providers.llm_ticker_agent.duckduckgo_search") as mock_ddg:
        mock_ddg.invoke.return_value = "no relevant results"
        with pytest.raises(TickerNotFoundError):
            await agent.resolve("알수없는종목")

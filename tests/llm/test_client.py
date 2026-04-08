import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.llm.client import LLMClient
from src.llm.models import NewsAnalysisInput, TechnicalSummaryInput


@pytest.fixture
def mock_openai_response():
    return {
        "choices": [
            {
                "message": {
                    "content": '{"sentiment": "긍정", "confidence": 0.85, "key_themes": ["신제품"], "summary": "긍정적", "impact_assessment": "좋음"}'
                }
            }
        ],
        "model": "gpt-4",
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


@pytest.mark.asyncio
async def test_llm_client_analyze_news(mock_openai_response):
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=mock_openai_response)
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        client = LLMClient(provider="openai", api_key="test-key")
        input_data = NewsAnalysisInput(
            ticker="AAPL",
            company_name="Apple Inc.",
            news=[{"title": "Test", "published": "2024-01-01", "summary": "Test"}],
        )
        result = await client.analyze_news(input_data)

        assert result.sentiment == "긍정"
        assert result.confidence == 0.85


@pytest.mark.asyncio
async def test_llm_client_generate_technical_summary(mock_openai_response):
    mock_openai_response["choices"][0]["message"]["content"] = '{"summary": "강세", "key_insights": ["골든크로스"], "recommendation": "매수", "confidence": 0.75, "rationale": "좋음"}'

    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=mock_openai_response)
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        client = LLMClient(provider="openai", api_key="test-key")
        input_data = TechnicalSummaryInput(
            ticker="AAPL",
            price=178.50,
            change_pct=2.5,
            strategies=[],
            indicators={},
        )
        result = await client.generate_technical_summary(input_data)

        assert result.summary == "강세"
        assert result.recommendation == "매수"

import pytest
from unittest.mock import AsyncMock, patch
from src.llm.client import LLMClient
from src.llm.models import (
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)


@pytest.mark.asyncio
async def test_llm_client_analyze_news():
    """Test news analysis delegates to analyzer."""
    with patch("src.llm.provider.ChatOpenAI"):
        with patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = NewsAnalysisOutput(
                sentiment="긍정",
                confidence=0.85,
                key_themes=["신제품"],
                summary="긍정적",
                impact_assessment="좋음",
            )

            client = LLMClient(provider="openai", api_key="test-key")
            input_data = NewsAnalysisInput(
                ticker="AAPL",
                company_name="Apple Inc.",
                news=[{"title": "Test", "published": "2024-01-01", "summary": "Test"}],
            )
            result = await client.analyze_news(input_data)

            assert result.sentiment == "긍정"
            assert result.confidence == 0.85
            mock_analyze.assert_called_once()


@pytest.mark.asyncio
async def test_llm_client_generate_technical_summary():
    """Test technical summary generation delegates to analyzer."""
    with patch("src.llm.provider.ChatOpenAI"):
        with patch("src.llm.analyzer.generate_technical_summary", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = TechnicalSummaryOutput(
                summary="강세",
                key_insights=["골든크로스"],
                recommendation="매수",
                confidence=0.75,
                rationale="좋음",
            )

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
            mock_generate.assert_called_once()


@pytest.mark.asyncio
async def test_llm_client_with_custom_llm():
    """Test analyzer can use custom LLM."""
    with patch("src.llm.provider.ChatOpenAI"):
        with patch("src.llm.analyzer.analyze_news", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = NewsAnalysisOutput(
                sentiment="부정",
                confidence=0.90,
                key_themes=["리콜"],
                summary="부정적",
                impact_assessment="나쁨",
            )

            client = LLMClient(provider="openai", api_key="test-key")
            mock_custom_llm = AsyncMock()

            input_data = NewsAnalysisInput(
                ticker="AAPL",
                company_name="Apple Inc.",
                news=[{"title": "Test", "published": "2024-01-01", "summary": "Test"}],
            )

            # Use custom LLM
            result = await client.analyze_news(input_data, llm=mock_custom_llm)

            assert result.sentiment == "부정"
            # Verify analyzer was called with custom LLM
            args = mock_analyze.call_args
            assert args[0][1] == mock_custom_llm


@pytest.mark.asyncio
async def test_llm_provider_openai():
    """Test client initialization with OpenAI provider."""
    with patch("src.llm.provider.ChatOpenAI") as mock_chat:
        mock_llm_instance = AsyncMock()
        mock_chat.return_value = mock_llm_instance

        client = LLMClient(provider="openai", api_key="test-key", model="gpt-4o")

        assert client.default_llm == mock_llm_instance
        mock_chat.assert_called_once()
        call_kwargs = mock_chat.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["api_key"] == "test-key"
        assert call_kwargs["temperature"] == 0


@pytest.mark.asyncio
async def test_llm_provider_anthropic():
    """Test client initialization with Anthropic provider."""
    with patch("src.llm.provider.ChatAnthropic") as mock_chat:
        mock_llm_instance = AsyncMock()
        mock_chat.return_value = mock_llm_instance

        client = LLMClient(provider="anthropic", api_key="test-key")

        assert client.default_llm == mock_llm_instance
        mock_chat.assert_called_once()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.analyzer import (
    analyze_news,
    generate_fundamental_summary,
    generate_technical_summary,
)
from src.llm.models import (
    FundamentalSummaryInput,
    FundamentalSummaryOutput,
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)


@pytest.mark.asyncio
async def test_analyze_news():
    input_data = NewsAnalysisInput(
        ticker="AAPL",
        company_name="Apple Inc.",
        news=[
            {
                "title": "Apple releases new iPhone",
                "summary": "Apple announced the new iPhone with improved features.",
            },
        ],
    )

    mock_output = NewsAnalysisOutput(
        sentiment="긍정",
        confidence=0.85,
        key_themes=["신제품 출시", "혁신"],
        summary="애플이 새로운 아이폰을 출시했습니다.",
        impact_assessment="단기 긍정적 영향이 예상됩니다.",
    )

    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_prompt_class:
        mock_prompt = MagicMock()
        mock_prompt_class.from_messages.return_value = mock_prompt

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_output)
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        mock_llm = MagicMock()

        result = await analyze_news(input_data, mock_llm)

        assert result.sentiment == "긍정"
        assert result.confidence == 0.85
        assert len(result.key_themes) == 2


@pytest.mark.asyncio
async def test_generate_technical_summary():
    input_data = TechnicalSummaryInput(
        ticker="AAPL",
        price=178.50,
        change_pct=2.5,
        strategies=[
            {
                "name": "trend",
                "status": "강세",
                "confidence": 75.0,
                "signals": ["골든크로스"],
                "evidence": ["20일선 > 50일선"],
            }
        ],
        indicators={
            "sma_20": 175.0,
            "sma_50": 170.0,
            "rsi": 58.3,
        },
    )

    mock_output = TechnicalSummaryOutput(
        summary="AAPL은 강한 상승 추세입니다.",
        key_insights=["골든크로스 발생", "RSI 중립권"],
        recommendation="매수",
        confidence=0.75,
        rationale="이동평균선 정배열과 모멘텀 지표 긍정적",
    )

    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_prompt_class:
        mock_prompt = MagicMock()
        mock_prompt_class.from_messages.return_value = mock_prompt

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_output)
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        mock_llm = MagicMock()

        result = await generate_technical_summary(input_data, mock_llm)

        assert result.summary == "AAPL은 강한 상승 추세입니다."
        assert result.recommendation == "매수"
        assert result.confidence == 0.75


@pytest.mark.asyncio
async def test_generate_fundamental_summary():
    input_data = FundamentalSummaryInput(
        ticker="AAPL",
        sector="Technology",
        industry="Consumer Electronics",
        pe_ratio=28.5,
        forward_pe=25.3,
        peg_ratio=2.1,
        ev_ebitda=20.5,
        ps_ratio=7.2,
        roe=0.48,
        revenue_growth=0.12,
        earnings_growth=0.15,
        debt_to_equity=1.8,
        free_cash_flow=95_000_000_000,
        fcf_yield=0.045,
        gross_margin=0.42,
        operating_margin=0.28,
    )

    mock_output = FundamentalSummaryOutput(
        summary="AAPL은 강한 재무 건전성을 보유하고 있습니다.",
        strengths=["높은 ROE", "강한 현금 흐름", "꾸준한 성장"],
        weaknesses=["높은 밸류에이션", "시장 포화"],
        valuation_assessment="적정",
        confidence=0.82,
    )

    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_prompt_class:
        mock_prompt = MagicMock()
        mock_prompt_class.from_messages.return_value = mock_prompt

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_output)
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        mock_llm = MagicMock()

        result = await generate_fundamental_summary(input_data, mock_llm)

        assert result.summary == "AAPL은 강한 재무 건전성을 보유하고 있습니다."
        assert len(result.strengths) == 3
        assert len(result.weaknesses) == 2
        assert result.valuation_assessment == "적정"
        assert result.confidence == 0.82


@pytest.mark.asyncio
async def test_generate_fundamental_summary_with_falsy_values():
    """Test that zero values are included in metrics text (not filtered out)."""
    input_data = FundamentalSummaryInput(
        ticker="XYZ",
        sector="Technology",
        industry="Software",
        pe_ratio=0.0,
        roe=0.0,
        revenue_growth=0.0,
        debt_to_equity=0.0,
    )

    mock_output = FundamentalSummaryOutput(
        summary="분석 결과입니다.",
        strengths=["강점"],
        weaknesses=["약점"],
        valuation_assessment="적정",
        confidence=0.70,
    )

    captured_metrics_text = None

    async def capture_ainvoke(args):
        nonlocal captured_metrics_text
        captured_metrics_text = args["metrics_text"]
        return mock_output

    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_prompt_class:
        mock_prompt = MagicMock()
        mock_prompt_class.from_messages.return_value = mock_prompt

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        mock_llm = MagicMock()

        result = await generate_fundamental_summary(input_data, mock_llm)

        assert result is not None
        assert captured_metrics_text is not None
        assert "P/E: 0.0" in captured_metrics_text
        assert "ROE: 0.0%" in captured_metrics_text
        assert "매출 성장률: 0.0%" in captured_metrics_text
        assert "D/E: 0.0" in captured_metrics_text


@pytest.mark.asyncio
async def test_generate_fundamental_summary_with_no_metrics():
    """Test that empty metrics case is handled gracefully."""
    input_data = FundamentalSummaryInput(ticker="XYZ")

    mock_output = FundamentalSummaryOutput(
        summary="데이터가 제한적입니다.",
        strengths=[],
        weaknesses=[],
        valuation_assessment="적정",
        confidence=0.30,
    )

    captured_metrics_text = None

    async def capture_ainvoke(args):
        nonlocal captured_metrics_text
        captured_metrics_text = args["metrics_text"]
        return mock_output

    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_prompt_class:
        mock_prompt = MagicMock()
        mock_prompt_class.from_messages.return_value = mock_prompt

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        mock_prompt.__or__ = MagicMock(return_value=mock_chain)

        mock_llm = MagicMock()

        result = await generate_fundamental_summary(input_data, mock_llm)

        assert result is not None
        assert captured_metrics_text is not None
        assert "No financial metrics available" in captured_metrics_text

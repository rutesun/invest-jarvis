from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.analyzer import (
    analyze_news,
    generate_actionable_signal,
    generate_fundamental_summary,
    generate_integrated_analysis,
    generate_technical_summary,
)
from src.llm.models import (
    ActionableSignalOutput,
    FundamentalSummaryInput,
    FundamentalSummaryOutput,
    IntegratedAnalysisInput,
    IntegratedAnalysisOutput,
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


@pytest.mark.asyncio
async def test_generate_integrated_analysis_calls_llm():
    """generate_integrated_analysis가 모든 팩터를 LLM에 전달하고 구조화된 결과를 반환한다."""
    mock_llm = AsyncMock()
    expected_output = IntegratedAnalysisOutput(
        recommendation="매수",
        rationale=["기술적: 골든크로스", "공시: 수주계약 체결"],
        risks=["RSI 과열 구간 접근"],
        action_summary="단기 매수 기회 포착",
    )

    with patch("src.llm.analyzer.ChatPromptTemplate") as mock_template:
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = expected_output
        mock_template.from_messages.return_value.__or__ = MagicMock(return_value=mock_chain)

        input_data = IntegratedAnalysisInput(
            ticker="AAPL",
            technical_recommendation="매수",
            technical_rationale="골든크로스 발생",
            fundamental_valuation="저평가",
            disclosure_items=[
                {
                    "form_type": "8-K",
                    "date": "2026-04-05",
                    "description": "Q1 results",
                    "url": "https://sec.gov/...",
                }
            ],
            flow_summary=None,
        )

        result = await generate_integrated_analysis(input_data, mock_llm)

    assert result.recommendation == "매수"
    assert len(result.rationale) == 2
    assert result.action_summary == "단기 매수 기회 포착"


@pytest.mark.asyncio
async def test_generate_actionable_signal():
    """Test generate_actionable_signal with Phase 2 pattern and price inputs."""
    from src.tools.technical.models import ChartPatternResult, PriceLevel, PriceLevels

    # Mock chart patterns
    chart_patterns = {
        "cup_and_handle": ChartPatternResult(
            pattern_name="Cup & Handle",
            detected=True,
            confidence=0.85,
            completed_date="2024-01-15",
            days_ago=8,
            current_price=150.0,
            breakout_level=155.0,
            support_level=145.0,
            description="Cup & Handle pattern completed 8 days ago",
            key_levels={"target": 165.0},
        ),
    }

    # Mock price levels
    price_levels = PriceLevels(
        current_price=150.0,
        support_levels=[
            PriceLevel(price=145.0, type="sma_50", distance_pct=-3.3, description="50일선"),
            PriceLevel(price=140.0, type="swing_low", distance_pct=-6.7, description="스윙 저점"),
        ],
        resistance_levels=[
            PriceLevel(price=155.0, type="pivot_r1", distance_pct=+3.3, description="피봇 저항"),
            PriceLevel(price=160.0, type="sma_200", distance_pct=+6.7, description="200일선"),
        ],
        targets={"cup_and_handle_target": 165.0},
    )

    expected_output = ActionableSignalOutput(
        action="매수",
        timing="지금",
        signal_strength=8,
        headline="Cup & Handle 돌파 직전, RSI 과매도 회복",
        primary_reason="Cup & Handle 패턴 완성 + 돌파 대기 ($155)",
        supporting_reasons=["RSI 과매도 회복", "50일선 지지"],
        risks=["돌파 실패 시 $145 이탈 위험"],
        invalidation_point="$145.00",
        confidence=0.85,
        pattern_insight="Cup & Handle 8일 전 완성, 돌파 준비",
        target_price="돌파 시 $165, 조정 시 $145 지지",
        entry_zone="현재 $150 대기, 조정 시 $145-147 분할 매수",
        key_levels="지지: $145/$140, 저항: $155/$160",
    )

    # Use patch to intercept the actual chain.ainvoke call
    with patch("src.llm.analyzer.ChatPromptTemplate"):
        mock_llm = MagicMock()
        mock_structured_llm = AsyncMock()
        mock_structured_llm.ainvoke = AsyncMock(return_value=expected_output)

        # When with_structured_output is called, return a mock that has ainvoke
        mock_llm.with_structured_output.return_value = mock_structured_llm

        result = await generate_actionable_signal(
            ticker="AAPL",
            technical_summary="RSI 과매도 회복, 50일선 지지 확인",
            chart_patterns=chart_patterns,
            price_levels=price_levels,
            llm=mock_llm,
        )

        assert result.action == "매수"
        assert result.timing == "지금"
        assert result.signal_strength == 8
        assert "Cup & Handle" in result.headline
        assert result.pattern_insight is not None
        assert result.target_price is not None
        assert result.entry_zone is not None
        assert result.key_levels is not None
        assert mock_structured_llm.ainvoke.called

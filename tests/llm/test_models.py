import pytest
from pydantic import ValidationError

from src.llm.models import (
    ActionableSignalOutput,
    FundamentalSummaryInput,
    FundamentalSummaryOutput,
    LLMRequest,
    LLMResponse,
    NewsAnalysisInput,
    NewsAnalysisOutput,
    TechnicalSummaryInput,
    TechnicalSummaryOutput,
)


def test_llm_request():
    req = LLMRequest(
        model="gpt-4",
        messages=[{"role": "user", "content": "test"}],
        temperature=0,
        seed=42,
    )
    assert req.model == "gpt-4"
    assert req.temperature == 0
    assert req.seed == 42


def test_llm_response():
    resp = LLMResponse(
        content="response text",
        model="gpt-4",
        usage={"prompt_tokens": 10, "completion_tokens": 20},
    )
    assert resp.content == "response text"
    assert resp.usage["prompt_tokens"] == 10


def test_news_analysis_input():
    input_data = NewsAnalysisInput(
        ticker="AAPL",
        company_name="Apple Inc.",
        news=[{"title": "Apple releases new product", "published": "2024-01-01", "summary": "..."}],
    )
    assert input_data.ticker == "AAPL"
    assert len(input_data.news) == 1


def test_news_analysis_output():
    output = NewsAnalysisOutput(
        sentiment="긍정",
        confidence=0.85,
        key_themes=["신제품 출시"],
        summary="애플이 새로운 제품을 출시했습니다.",
        impact_assessment="단기 긍정적 영향 예상",
    )
    assert output.sentiment == "긍정"
    assert output.confidence == 0.85


def test_technical_summary_input():
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
                "metrics": {"sma_20": 175.0},
            }
        ],
        indicators={
            "sma_20": 175.0,
            "sma_50": 170.0,
            "rsi": 58.3,
        },
    )
    assert input_data.ticker == "AAPL"
    assert len(input_data.strategies) == 1


def test_technical_summary_output():
    output = TechnicalSummaryOutput(
        summary="AAPL은 강한 상승 추세입니다.",
        key_insights=["골든크로스 발생", "RSI 중립권"],
        recommendation="매수",
        confidence=0.75,
        rationale="이동평균선 정배열과 모멘텀 지표 긍정적",
    )
    assert output.summary == "AAPL은 강한 상승 추세입니다."
    assert output.recommendation == "매수"


def test_fundamental_summary_input():
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
    assert input_data.ticker == "AAPL"
    assert input_data.pe_ratio == 28.5
    assert input_data.roe == 0.48


def test_fundamental_summary_input_with_nulls():
    input_data = FundamentalSummaryInput(
        ticker="XYZ",
        sector=None,
        industry=None,
        pe_ratio=None,
        forward_pe=None,
        peg_ratio=None,
        ev_ebitda=None,
        ps_ratio=None,
        roe=None,
        revenue_growth=None,
        earnings_growth=None,
        debt_to_equity=None,
        free_cash_flow=None,
        fcf_yield=None,
        gross_margin=None,
        operating_margin=None,
    )
    assert input_data.ticker == "XYZ"
    assert input_data.sector is None
    assert input_data.pe_ratio is None


def test_fundamental_summary_output():
    output = FundamentalSummaryOutput(
        summary="AAPL은 강한 재무 건전성을 보유하고 있습니다.",
        strengths=["높은 ROE", "강한 현금 흐름", "꾸준한 성장"],
        weaknesses=["높은 밸류에이션", "시장 포화"],
        valuation_assessment="적정",
        confidence=0.82,
    )
    assert output.summary == "AAPL은 강한 재무 건전성을 보유하고 있습니다."
    assert len(output.strengths) == 3
    assert len(output.weaknesses) == 2
    assert output.valuation_assessment == "적정"
    assert output.confidence == 0.82


def test_actionable_signal_output_valid():
    """Test valid ActionableSignalOutput creation."""
    signal = ActionableSignalOutput(
        action="매수",
        timing="지금",
        signal_strength=8,
        headline="매수. 지금. 이유: RSI 과매도",
        primary_reason="RSI 28 (과매도)",
        supporting_reasons=["실적 양호", "거래량 증가"],
        risks=["금리 인상 위험"],
        invalidation_point="$145.20",
        confidence=0.82,
    )

    assert signal.action == "매수"
    assert signal.timing == "지금"
    assert signal.signal_strength == 8
    assert "매수" in signal.headline
    assert len(signal.supporting_reasons) == 2
    assert len(signal.risks) == 1


def test_actionable_signal_output_invalid_action():
    """Test ActionableSignalOutput rejects invalid action."""
    with pytest.raises(ValidationError) as exc_info:
        ActionableSignalOutput(
            action="HOLD",  # Invalid - must be 매수/매도/관망
            timing="지금",
            signal_strength=8,
            headline="test",
            primary_reason="test",
            supporting_reasons=[],
            risks=[],
            confidence=0.8,
        )

    assert "Invalid action" in str(exc_info.value)


def test_actionable_signal_output_invalid_timing():
    """Test ActionableSignalOutput rejects invalid timing."""
    with pytest.raises(ValidationError) as exc_info:
        ActionableSignalOutput(
            action="매수",
            timing="WAIT",  # Invalid - must be 지금/조정_대기/보류
            signal_strength=8,
            headline="test",
            primary_reason="test",
            supporting_reasons=[],
            risks=[],
            confidence=0.8,
        )

    assert "Invalid timing" in str(exc_info.value)

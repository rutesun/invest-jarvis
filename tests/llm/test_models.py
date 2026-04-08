import pytest
from src.llm.models import (
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
        news=[
            {"title": "Apple releases new product", "published": "2024-01-01", "summary": "..."}
        ],
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

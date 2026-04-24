from typing import Any

from pydantic import BaseModel, Field, field_validator


class LLMRequest(BaseModel):
    """LLM request with reproducible parameters."""

    model: str
    messages: list[dict[str, str]]
    temperature: float = 0
    seed: int = 42
    max_tokens: int | None = None


class LLMResponse(BaseModel):
    """LLM response."""

    content: str
    model: str
    usage: dict[str, int]


# News Analysis I/O
class NewsAnalysisInput(BaseModel):
    """Input for news analysis."""

    ticker: str
    company_name: str
    news: list[dict[str, Any]]  # [{title, published, summary, url?}]


class NewsAnalysisOutput(BaseModel):
    """Output from news analysis."""

    sentiment: str  # "긍정", "부정", "중립"
    confidence: float  # 0-1
    key_themes: list[str]
    summary: str
    impact_assessment: str


# Technical Summary I/O
class TechnicalSummaryInput(BaseModel):
    """Input for technical summary."""

    ticker: str
    price: float
    change_pct: float
    strategies: list[dict[str, Any]]
    indicators: dict[str, float]


class TechnicalSummaryOutput(BaseModel):
    """Output from technical summary."""

    summary: str
    key_insights: list[str]
    recommendation: str  # "매수", "매도", "중립"
    confidence: float  # 0-1
    rationale: str


# Fundamental Summary I/O
class FundamentalSummaryInput(BaseModel):
    """Input for fundamental summary."""

    ticker: str
    sector: str | None = None
    industry: str | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    ev_ebitda: float | None = None
    ps_ratio: float | None = None
    roe: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    debt_to_equity: float | None = None
    free_cash_flow: float | None = None
    fcf_yield: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    pb_ratio: float | None = None
    roa: float | None = None
    profit_margin: float | None = None
    dividend_yield: float | None = None
    payout_ratio: float | None = None


class FundamentalSummaryOutput(BaseModel):
    """Output from fundamental summary."""

    summary: str
    strengths: list[str]
    weaknesses: list[str]
    valuation_assessment: str  # "저평가", "적정", "고평가"
    confidence: float  # 0-1


# 종합 분석 I/O
class IntegratedAnalysisInput(BaseModel):
    """멀티팩터 종합 분석 입력."""

    ticker: str
    technical_recommendation: str  # "매수", "매도", "중립"
    technical_rationale: str  # 기술적 분석 근거 자유 형식
    fundamental_valuation: str | None = None  # "저평가", "적정", "고평가"
    disclosure_items: list[dict[str, Any]] = []  # DisclosureItem dict 리스트
    flow_summary: str | None = None  # 사전 포맷된 마크다운 테이블 또는 None


class IntegratedAnalysisOutput(BaseModel):
    """멀티팩터 종합 분석 출력."""

    recommendation: str  # "매수", "매도", "중립"
    rationale: list[str]  # 3-4개 근거, 각 항목은 "기술적:" / "기본적:" / "공시:" / "수급:" 접두사
    risks: list[str]  # 2-3개 리스크 요인
    action_summary: str  # 한 줄 한국어 요약


class ActionableSignalOutput(BaseModel):
    """LLM output for actionable investment signal."""

    # Phase 1 fields
    action: str = Field(..., description="매수|매도|관망")
    timing: str = Field(..., description="지금|조정_대기|보류")
    signal_strength: int = Field(..., ge=1, le=10, description="1-10")
    headline: str = Field(..., description="한줄 요약")
    primary_reason: str = Field(..., description="핵심 이유")
    supporting_reasons: list[str] = Field(..., description="부차 이유")
    risks: list[str] = Field(..., description="리스크")
    invalidation_point: str | None = Field(None, description="청산/손절 가격")
    confidence: float = Field(..., ge=0.0, le=1.0, description="0.0-1.0")

    # Phase 2 fields
    pattern_insight: str | None = Field(
        None, description="차트 패턴 해석. 예: 'Cup & Handle 8일 전 완성, 돌파 준비'"
    )
    target_price: str | None = Field(
        None, description="가격 목표 (자유 서술). 예: '돌파 시 $250, 조정 시 $175 지지'"
    )
    entry_zone: str | None = Field(
        None, description="진입 구간 (자유 서술). 예: '현재 $200 횡보, 조정 시 $175-180 매수'"
    )
    key_levels: str | None = Field(
        None, description="주요 레벨 요약. 예: '지지: $187/$175, 저항: $200/$250'"
    )

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in {"매수", "매도", "관망"}:
            raise ValueError(f"Invalid action: {v}")
        return v

    @field_validator("timing")
    @classmethod
    def validate_timing(cls, v: str) -> str:
        if v not in {"지금", "조정_대기", "보류"}:
            raise ValueError(f"Invalid timing: {v}")
        return v

    @field_validator("pattern_insight", "target_price", "entry_zone", "key_levels")
    @classmethod
    def validate_non_empty(cls, v):
        """Ensure Phase 2 fields are not empty strings"""
        if v is not None and v.strip() == "":
            return None
        return v

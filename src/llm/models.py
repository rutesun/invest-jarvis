from typing import Any
from pydantic import BaseModel
from src.tools.disclosure import DisclosureItem


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
    technical_recommendation: str        # "매수", "매도", "중립"
    technical_rationale: str             # 기술적 분석 근거 자유 형식
    fundamental_valuation: str | None = None   # "저평가", "적정", "고평가"
    disclosure_items: list[dict[str, Any]] = []  # DisclosureItem dict 리스트
    flow_summary: str | None = None      # 사전 포맷된 마크다운 테이블 또는 None


class IntegratedAnalysisOutput(BaseModel):
    """멀티팩터 종합 분석 출력."""
    recommendation: str        # "매수", "매도", "중립"
    rationale: list[str]       # 3-4개 근거, 각 항목은 "기술적:" / "기본적:" / "공시:" / "수급:" 접두사
    risks: list[str]           # 2-3개 리스크 요인
    action_summary: str        # 한 줄 한국어 요약

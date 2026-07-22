from typing import Any

from pydantic import BaseModel, Field


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
    technical_verdict: dict[str, Any] | None = None
    score_history: list[dict[str, Any]] = Field(default_factory=list)
    score_history_warning: str | None = None
    aggregation_trace: list[dict[str, Any]] = Field(default_factory=list)


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
    # CAN SLIM C·A EPS growth
    eps_growth_quarterly: float | None = None  # most recent quarter YoY
    eps_cagr_annual: float | None = None  # annual EPS CAGR (last 3y)


class FundamentalSummaryOutput(BaseModel):
    """Output from fundamental summary."""

    summary: str
    strengths: list[str]
    weaknesses: list[str]
    valuation_assessment: str  # "저평가", "적정", "고평가"
    confidence: float  # 0-1


# 최종 종합 해설 I/O (설명 전용 — 규칙이 확정한 decision을 바꾸지 않는다)
class IntegratedExplanationInput(BaseModel):
    """규칙이 확정한 decision과 모든 분석 소스를 담는 최종 해설 입력.

    fixed_* 필드는 이미 확정된 규칙 출력이며 LLM은 이를 설명만 한다.
    나머지 context는 신뢰할 수 없는 데이터로 취급해 delimiter 뒤에 격리한다.
    """

    ticker: str
    fixed_action: str
    fixed_timing: str
    fixed_action_sentence: str
    technical_context: dict[str, Any]
    news_analysis: dict[str, Any] | None = None
    fundamental_summary: dict[str, Any] | None = None
    disclosure_items: list[dict[str, Any]] = Field(default_factory=list)
    flow_context: dict[str, Any] | None = None
    macro_context: dict[str, Any] | None = None
    playbook_context: dict[str, Any] | None = None
    factor_assessments: list[dict[str, Any]] = Field(default_factory=list)
    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    level_context: dict[str, Any]


class IntegratedExplanationOutput(BaseModel):
    """설명 전용 출력 — action/timing/recommendation을 새로 만들지 않는다."""

    decision_explanation: str
    rationale: list[str]
    risks: list[str]
    monitoring_points: list[str]


class TickerNarrative(BaseModel):
    """brief 종목별 서술 슬롯 — 규칙 판정 사실의 문장화만 담당."""

    ticker: str = Field(description="입력 사실 JSON의 ticker 그대로")
    technical_note: str = Field(description="기술적 근거 1-2문장 (제공된 사실만 사용)")
    flow_note: str | None = Field(default=None, description="수급 데이터가 있으면 1문장")
    news_note: str | None = Field(default=None, description="뉴스가 있으면 해석 1문장")
    next_check: str = Field(description="다음 확인 지점 1문장")


class BriefNarrativesOutput(BaseModel):
    """brief LLM 배치 1콜 출력 — 전 종목 서술 목록."""

    narratives: list[TickerNarrative]

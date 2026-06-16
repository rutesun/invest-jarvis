from typing import Any

from pydantic import BaseModel


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


class DebateCase(BaseModel):
    """한 진영의 변론."""

    stance: str  # "bull" | "bear"
    thesis: str
    points: list[str]


class DebateAdvocacyInput(BaseModel):
    """변론 콜 입력 — list[dict]는 입력에만 허용."""

    ticker: str
    mode: str  # "entry" | "holding"
    bull_evidence: list[dict]  # [{headline, detail}]
    bear_evidence: list[dict]


class DebateAdvocacyOutput(BaseModel):
    """변론 콜 출력 — 전부 타입 확정 (strict-schema)."""

    bull_case: DebateCase
    bear_case: DebateCase


class DebateJudgeInput(BaseModel):
    """판사 콜 입력."""

    ticker: str
    mode: str
    bull_case: DebateCase
    bear_case: DebateCase
    bull_weight: float
    bear_weight: float
    allowed_actions: list[str]


class DebateVerdictOutput(BaseModel):
    """판사 콜 출력 — 단일 평결."""

    action: str
    confidence: float
    swing_factor: str
    reconciliation: str

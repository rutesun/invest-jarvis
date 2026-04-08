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

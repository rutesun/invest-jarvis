from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CandidateTicker(BaseModel):
    """Candidate ticker from search results"""
    symbol: str = Field(..., min_length=1)
    name: str
    exchange: str
    score: float
    quote_type: str  # "EQUITY", "ETF", "INDEX"


class TickerResolution(BaseModel):
    """Result of ticker resolution"""
    original_query: str
    resolved_ticker: str
    display_name: str
    confidence: Literal["high", "medium", "low"]
    candidates: list[CandidateTicker]
    resolution_method: Literal[
        "direct_ticker",
        "user_cache",
        "static_mapping",
        "yfinance_search_single",
        "yfinance_search_multiple"
    ]
    source: str


class CachedMapping(BaseModel):
    """User cached ticker mapping"""
    ticker: str
    display_name: str
    created_at: datetime
    last_used: datetime
    use_count: int = Field(ge=1)

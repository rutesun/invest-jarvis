from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CandidateTicker(BaseModel):
    """Candidate ticker from search results"""
    symbol: str = Field(..., min_length=1)
    name: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    score: float = Field(ge=0)
    quote_type: str = Field(min_length=1)


class TickerResolution(BaseModel):
    """Result of ticker resolution"""
    original_query: str
    resolved_ticker: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    candidates: list[CandidateTicker]
    resolution_method: Literal[
        "direct_ticker",
        "user_cache",
        "static_mapping",
        "yfinance_search_single",
        "yfinance_search_multiple"
    ]
    source: str = Field(min_length=1)


class CachedMapping(BaseModel):
    """User cached ticker mapping"""
    ticker: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    created_at: datetime
    last_used: datetime
    use_count: int = Field(ge=1)

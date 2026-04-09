from pydantic import BaseModel, Field


class CandidateTicker(BaseModel):
    """Candidate ticker from search results"""
    symbol: str = Field(..., min_length=1)
    name: str
    exchange: str
    score: float
    quote_type: str  # "EQUITY", "ETF", "INDEX"

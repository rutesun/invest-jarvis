from datetime import datetime
from pydantic import BaseModel, Field


class TickerResolutionError(Exception):
    """Base exception for ticker resolution"""
    pass


class TickerNotFoundError(TickerResolutionError):
    """No ticker found for query"""
    pass


class TickerResolution(BaseModel):
    """티커 해결 결과"""
    original_query: str
    resolved_ticker: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    source: str = Field(min_length=1)


class CachedMapping(BaseModel):
    """유저 캐시 파일에 저장되는 개별 매핑 항목"""
    ticker: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    created_at: datetime
    last_used: datetime
    use_count: int = Field(ge=1)

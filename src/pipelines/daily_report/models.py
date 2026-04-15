"""Daily report 파이프라인 데이터 모델."""
from datetime import datetime
from typing import Dict, List, Literal
from pydantic import BaseModel, Field


class MacroSnapshot(BaseModel):
    """시장 매크로 지표 스냅샷."""
    date: str
    us_markets: Dict[str, float] = Field(
        description="미국 시장 변동률. Keys: S&P500, NASDAQ, DOW"
    )
    kr_markets: Dict[str, float] = Field(
        description="한국 시장 변동률. Keys: KOSPI, KOSDAQ"
    )
    vix: float
    fear_greed: int = Field(ge=0, le=100)
    krw_usd: float


class TelegramMessage(BaseModel):
    """텔레그램 메시지 하나."""
    channel_id: str
    message_id: str
    timestamp: datetime
    text: str


class IngestResult(BaseModel):
    """Ingest stage 출력."""
    date: str
    macro: MacroSnapshot
    messages: List[TelegramMessage]


class MappedIssue(BaseModel):
    """Map stage에서 추출한 이슈."""
    title: str = Field(description="한글 제목")
    summary: str = Field(description="한글 요약")
    themes: List[str] = Field(
        description="2-3개의 의미론적 테마 (섹터 아님)",
        min_length=1,
        max_length=3
    )
    keywords: List[str] = Field(
        description="뉴스 검색용 종목명, 기술용어"
    )
    sentiment: Literal["bull", "bear", "neutral"]
    source_ids: List[str] = Field(description="원본 메시지 ID")


class ShuffleResult(BaseModel):
    """Shuffle stage 출력 (테마 정규화)."""
    canonical_themes: Dict[str, List[str]] = Field(
        description="정규화명 → 원본 테마명 매핑"
    )
    theme_groups: Dict[str, List[MappedIssue]] = Field(
        description="정규화 테마별로 그룹핑된 이슈"
    )


class StockDetail(BaseModel):
    """관련 종목 정보."""
    name: str
    ticker: str
    catalyst: str = Field(description="한글 촉매 설명")


class NewsItem(BaseModel):
    """Reduce stage의 테마별 분석."""
    theme: str = Field(description="한글 정규화 테마명")
    emoji: str = Field(description="단일 이모지: 🚀📈⚠️ℹ️📉⚡")
    summary: str = Field(description="한글 bullet points")
    impact: str = Field(description="한글 impact 문구")
    stocks: List[StockDetail] = Field(default_factory=list)


class DailyReport(BaseModel):
    """최종 리포트 출력."""
    date: str
    macro: MacroSnapshot
    key_insights: List[str] = Field(description="한글 크로스 테마 인사이트")
    news: List[NewsItem]

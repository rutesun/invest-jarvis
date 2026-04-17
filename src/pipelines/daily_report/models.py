"""Daily report 파이프라인 데이터 모델."""

from datetime import datetime
from typing import Dict, List, Literal
from pydantic import BaseModel, Field


# 고정 카테고리 (클러스터링 키)
IssueCategory = Literal[
    # 기술/제조
    "반도체", "디스플레이", "이차전지", "소재/화학",
    # 산업
    "자동차", "조선/중공업", "방산",
    # 소프트웨어/서비스
    "AI/소프트웨어", "통신",
    # 헬스케어
    "바이오/제약",
    # 소비
    "유통/소비재", "K-푸드",
    # 에너지/인프라
    "에너지", "건설/부동산",
    # 금융/거시
    "금융/보험", "매크로", "정책/규제",
    # 기타
    "기타",
]


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
    category: IssueCategory = Field(description="고정 카테고리 (클러스터링 키)")
    title: str = Field(description="이슈를 관통하는 핵심 한글 제목")
    summary: str = Field(
        description="숫자와 팩트 중심의 통합 요약 (2-3문장). 구체적 수치 반드시 포함."
    )
    themes: List[str] = Field(
        description="투자 내러티브 테마 (예: 'HBM 선단공정 전환 가속', 'DRAM 업사이클')",
        min_length=1,
        max_length=3,
    )
    impact: str = Field(description="이 이슈가 시장/종목에 주는 핵심 시사점 (단문)")
    keywords: List[str] = Field(description="종목명, 티커, 기술용어")
    sentiment: Literal["bull", "bear", "neutral"]
    source_ids: List[str] = Field(description="원본 메시지 ID 리스트")


class ShuffleResult(BaseModel):
    """Shuffle stage 출력 (카테고리 그룹핑 + 테마 정규화)."""

    category_groups: Dict[str, Dict[str, List[MappedIssue]]] = Field(
        description="{ category: { theme: [issues] } } 2단계 그룹핑"
    )


class StockDetail(BaseModel):
    """관련 종목 정보."""

    name: str
    ticker: str
    catalyst: str = Field(description="한글 촉매 설명")


class NewsItem(BaseModel):
    """Reduce stage의 테마별 분석."""

    category: IssueCategory = Field(description="카테고리 (정렬/필터링용)")
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


class MappedIssueList(BaseModel):
    """Map stage의 구조화된 이슈 리스트 래퍼."""

    issues: List[MappedIssue] = Field(description="추출된 이슈 배열")


class ThemeMapping(BaseModel):
    """Shuffle stage의 구조화된 테마 매핑 래퍼."""

    mapping: Dict[str, List[str]] = Field(
        description="정규화명 → 원본 테마명 배열 매핑"
    )


class KeyInsightsList(BaseModel):
    """Wrapup stage의 구조화된 인사이트 리스트 래퍼."""

    insights: List[str] = Field(description="도출된 메타 인사이트 배열")

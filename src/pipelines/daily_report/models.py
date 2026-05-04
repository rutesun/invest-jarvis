"""Daily report 파이프라인 데이터 모델."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


class Sentiment(StrEnum):
    """이슈 감성 분류."""

    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


# 고정 카테고리 (클러스터링 키)
IssueCategory = Literal[
    # 기술/제조
    "반도체",
    "디스플레이",
    "이차전지",
    "소재/화학",
    # 산업
    "자동차",
    "조선/중공업",
    "방산",
    # 소프트웨어/서비스
    "AI/소프트웨어",
    "통신",
    # 헬스케어
    "바이오/제약",
    # 소비
    "유통/소비재",
    "K-푸드",
    "엔터/미디어",
    # 운송/물류
    "운송/물류",
    # 에너지/인프라
    "에너지",
    "건설/부동산",
    # 금융/거시
    "금융/보험",
    "매크로",
    "정책/규제",
    # 기타
    "기타",
]

# 카테고리 alias 매핑 (LLM이 자연스럽게 생성하는 변형 → 정규 카테고리)
CATEGORY_ALIASES: dict[str, IssueCategory] = {
    "의료/제약": "바이오/제약",
    "제약": "바이오/제약",
    "헬스케어": "바이오/제약",
    "운송": "운송/물류",
    "물류": "운송/물류",
    "항공": "운송/물류",
    "엔터테인먼트": "엔터/미디어",
    "게임": "엔터/미디어",
    "미디어": "엔터/미디어",
}


class MacroSnapshot(BaseModel):
    """시장 매크로 지표 스냅샷."""

    date: str
    us_markets: dict[str, float | None] = Field(
        description="미국 시장 변동률. Keys: S&P500, NASDAQ, DOW"
    )
    kr_markets: dict[str, float | None] = Field(description="한국 시장 변동률. Keys: KOSPI, KOSDAQ")
    vix: float | None = None
    fear_greed: int | None = Field(default=None, ge=0, le=100)
    krw_usd: float | None = None
    missing_fields: list[str] = Field(default_factory=list)


class TelegramMessage(BaseModel):
    """텔레그램 메시지 하나."""

    channel_id: str
    message_id: str
    timestamp: datetime
    text: str
    row_index: int | None = None
    source_file: str | None = None


class IngestResult(BaseModel):
    """Ingest stage 출력."""

    date: str
    macro: MacroSnapshot
    messages: list[TelegramMessage]


class SourceType(StrEnum):
    """Evidence source type for confidence control."""

    PRIMARY_NEWS = "primary_news"
    PRIMARY_RESEARCH = "primary_research"
    BROKER_SUMMARY = "broker_summary"
    MARKET_SIGNAL = "market_signal"
    VIDEO_SOCIAL = "video_social"
    UNKNOWN = "unknown"


class ArticleFragment(BaseModel):
    """Split unit from a raw telegram message row."""

    fragment_id: str
    raw_message_id: str
    channel_id: str
    title: str
    body: str
    url: str | None = None
    fragment_index: int
    source_type: SourceType = SourceType.UNKNOWN


class MappedIssue(BaseModel):
    category: IssueCategory = Field(description="고정 카테고리 (클러스터링 키)")
    title: str = Field(description="이슈를 관통하는 핵심 한글 제목")
    summary: str = Field(
        description="숫자와 팩트 중심의 통합 요약 (2-3문장). 구체적 수치 반드시 포함."
    )
    themes: list[str] = Field(
        description="투자 내러티브 테마 (예: 'HBM 선단공정 전환 가속', 'DRAM 업사이클')",
        min_length=1,
        max_length=3,
    )
    keywords: list[str] = Field(default_factory=list, description="종목/지표/기술 키워드")
    impact: str = Field(description="이 이슈가 시장/종목에 주는 핵심 시사점 (단문)")
    sentiment: Sentiment
    source_ids: list[str] = Field(default_factory=list, description="원본 메시지 ID 리스트")
    entities: list[str] = Field(default_factory=list, description="핵심 엔티티(기업/지표/상품)")
    event_type: str = Field(default="general_event", description="이벤트 타입")
    stance: Sentiment | None = Field(default=None, description="이벤트 스탠스")
    source_fragment_ids: list[str] = Field(
        default_factory=list,
        description="fragment 추적 ID 리스트 (예: channel-123#f0)",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    summary_fact: str = Field(default="", description="팩트 요약")
    summary_interpretation: str = Field(default="", description="해석 요약")
    source_type: SourceType = Field(default=SourceType.UNKNOWN)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        """카테고리 정규화 (LLM이 생성한 alias → 정규 카테고리)."""
        return CATEGORY_ALIASES.get(v, v)

    @model_validator(mode="after")
    def fill_event_fields(self) -> "MappedIssue":
        """신규 이벤트 필드의 하위호환 기본값 채우기."""
        if self.stance is None:
            self.stance = self.sentiment

        if not self.source_fragment_ids and self.source_ids:
            self.source_fragment_ids = [f"{source_id}#f0" for source_id in self.source_ids]

        if not self.source_ids and self.source_fragment_ids:
            self.source_ids = sorted(
                {
                    fragment_id.split("#", 1)[0]
                    for fragment_id in self.source_fragment_ids
                    if fragment_id
                }
            )

        if not self.entities:
            self.entities = list(dict.fromkeys(self.keywords))[:8]

        if not self.summary_fact:
            self.summary_fact = self.summary

        return self


class ShuffleResult(BaseModel):
    """Shuffle stage 출력 (카테고리 그룹핑 + 테마 정규화)."""

    category_groups: dict[str, dict[str, list[MappedIssue]]] = Field(
        description="{ category: { theme: [issues] } } 2단계 그룹핑"
    )


class StockDetail(BaseModel):
    """관련 종목 정보."""

    name: str
    ticker: str
    catalyst: str = Field(description="한글 촉매 설명")


class ThemeAnalysis(BaseModel):
    """Reduce stage LLM 출력용 (category 제외)."""

    theme: str | None = Field(
        default=None, description="한글 정규화 테마명 (backward compatibility, deprecated)"
    )
    investment_theme: str = Field(
        description="투자 인사이트 테마명 (20-40자). "
        "패턴: [트렌드] + [방향성] + [수혜/리스크]. "
        "예: 'GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜'"
    )
    keywords: list[str] = Field(description="검색용 키워드 5-10개 (종목명, 기술용어, 트렌드)")
    emoji: str = Field(description="단일 이모지: 🚀📈⚠️ℹ️📉⚡")
    summary: str = Field(description="한글 bullet points")
    impact: str = Field(description="한글 impact 문구")
    stocks: list[StockDetail] = Field(default_factory=list)

    @field_validator("investment_theme")
    @classmethod
    def validate_theme_length(cls, v):
        """투자 테마 길이 검증 (20-40자)."""
        length = len(v)
        if not (20 <= length <= 40):
            raise PydanticCustomError(
                "theme_length_error",
                "investment_theme 길이는 20-40자여야 합니다 (현재: {length}자)",
                {
                    "length": length,
                    "value": v,
                    "spec": """📋 investment_theme 요구사항:
- 길이: 20-40자 (쉼표 포함)
- 구조: [전반부 10-15자, 후반부 10-15자]
- 방향성 명확히 (가속/둔화/전환 등)
- 가능하면 구체적 종목/섹터 언급""",
                    "examples": [
                        '"GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜" (29자)',
                        '"엔터프라이즈 AI 채택 본격화, SaaS 가격 파워 회복" (31자)',
                        '"스트리밍 가이던스 실망, 광고 전환 시급" (22자)',
                    ],
                },
            )
        return v

    @field_validator("keywords")
    @classmethod
    def validate_keywords_count(cls, v):
        """키워드 개수 검증 (5-10개)."""
        count = len(v)
        if not (5 <= count <= 10):
            raise PydanticCustomError(
                "keywords_count_error",
                "keywords는 5-10개여야 합니다 (현재: {count}개)",
                {
                    "count": count,
                    "spec": """📋 keywords 요구사항:
- 개수: 5-10개 (정확히)
- 포함: 종목명 (한글/영문), 기술용어, 트렌드""",
                    "examples": [
                        '["GPU", "엔비디아", "AMD", "세레브라스", "AI 칩", "공급망", "데이터센터"] (7개)',
                        '["팔란티어", "세일스포스", "AI 에이전트", "SaaS", "엔터프라이즈"] (5개)',
                    ],
                },
            )
        return v


class NewsItem(BaseModel):
    """Reduce stage의 테마별 분석."""

    category: IssueCategory = Field(description="카테고리 (정렬/필터링용)")

    # 테마 (2개 필드로 분리)
    technical_theme: str = Field(description="Shuffle에서 정규화한 기술적 테마명 (검색 키)")
    investment_theme: str = Field(description="투자 인사이트 테마명 (리포트 표시용)")

    # 검색
    keywords: list[str] = Field(description="검색용 키워드")
    source_ids: list[str] = Field(description="원본 텔레그램 메시지 ID 리스트 (증거 추적용)")

    emoji: str = Field(description="단일 이모지: 🚀📈⚠️ℹ️📉⚡")
    summary: str = Field(description="한글 bullet points")
    impact: str = Field(description="한글 impact 문구")
    stocks: list[StockDetail] = Field(default_factory=list)


class DailyReport(BaseModel):
    """최종 리포트 출력."""

    date: str
    macro: MacroSnapshot
    key_insights: list[str] = Field(default_factory=list, description="한글 크로스 테마 인사이트")
    category_insights: dict[str, str] = Field(
        default_factory=dict,
        description="카테고리별 인사이트 (카테고리 → 인사이트 문자열)",
    )
    news: list[NewsItem] = Field(default_factory=list)
    brief_items: list[NewsItem] = Field(default_factory=list)
    extended_items: list[NewsItem] = Field(default_factory=list)
    broker_pulse_items: list[NewsItem] = Field(default_factory=list)


class MappedIssueList(BaseModel):
    """Map stage의 구조화된 이슈 리스트 래퍼."""

    issues: list[MappedIssue] = Field(description="추출된 이슈 배열")


class ThemeMapping(BaseModel):
    """Shuffle stage의 구조화된 테마 매핑 래퍼."""

    mapping: dict[str, list[str]] = Field(description="정규화명 → 원본 테마명 배열 매핑")


class KeyInsightsList(BaseModel):
    """Wrapup stage의 구조화된 인사이트 리스트 래퍼."""

    insights: list[str] = Field(description="도출된 메타 인사이트 배열")


class CategoryInsightsList(BaseModel):
    """Wrapup stage의 카테고리별 인사이트."""

    insights: dict[str, str] = Field(
        description=(
            "카테고리 → 인사이트 매핑. 예: {'반도체': 'HBM 가격 상승 + 엔비디아 독점 완화 → 국내 메모리 수혜'}"
        )
    )

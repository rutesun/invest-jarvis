"""Daily report 파이프라인 데이터 모델."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator
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


class IngestResult(BaseModel):
    """Ingest stage 출력."""

    date: str
    macro: MacroSnapshot
    messages: list["TelegramMessage | IngestedMessage"]


class MessageType(StrEnum):
    """Ingested message type."""

    RAW_INTELLIGENCE = "raw_intelligence"
    BROKER_SUMMARY = "broker_summary"
    MARKET_SIGNAL = "market_signal"
    OTHER = "other"


class IngestedMessage(BaseModel):
    """Normalized message with source metadata."""

    source_id: str
    channel_id: str
    message_id: str
    timestamp: datetime
    raw_text: str
    message_type: MessageType
    source_file: str

    @property
    def text(self) -> str:
        """Legacy compatibility for map-stage consumers."""
        return self.raw_text


class ClaimType(StrEnum):
    """Claim semantic type."""

    FACT = "fact"
    OPINION = "opinion"
    BROKER_VIEW = "broker_view"
    MARKET_DATA = "market_data"


class Fact(BaseModel):
    """Structured fact extracted from source text."""

    fact_id: str
    source_id: str
    kind: str
    label: str
    value: str
    numeric_value: float | None = None
    unit: str | None = None


class Claim(BaseModel):
    """Claim unit linked to one or more source messages."""

    claim_id: str
    category: IssueCategory
    claim_type: ClaimType
    text: str
    canonical_entities: list[str]
    target_scope: str
    polarity: Sentiment
    source_ids: list[str]
    fact_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractResult(BaseModel):
    """Extract stage output."""

    claims: list[Claim]
    facts: list[Fact]


class ClaimEdge(BaseModel):
    """Edge score between two claims."""

    left_claim_id: str
    right_claim_id: str
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    contradiction: bool = False


class ClaimCluster(BaseModel):
    """Grouped claims in link/select stages."""

    cluster_id: str
    category: IssueCategory
    claim_ids: list[str]
    source_ids: list[str]
    bull_claim_ids: list[str] = Field(default_factory=list)
    bear_claim_ids: list[str] = Field(default_factory=list)
    title: str


class SelectedCluster(BaseModel):
    """Selection result metadata."""

    cluster_id: str
    score: float = Field(ge=0.0, le=1.0)
    selected_for_brief: bool
    selected_for_dump: bool
    reasons: list[str] = Field(default_factory=list)


class ContrarianSignal(BaseModel):
    """Contradictory signals preserved for final report."""

    cluster_id: str
    summary: str
    supporting_claim_ids: list[str]


class ResearchDump(BaseModel):
    """Expanded research markdown output."""

    date: str
    markdown: str


class KnowledgeCandidate(BaseModel):
    """Candidate item for approved knowledge update queue."""

    candidate_type: Literal["alias", "concept", "relation", "message_type"]
    key: str
    reason: str
    evidence_source_ids: list[str]
    priority: int = Field(ge=0, le=3)
    confidence: float = Field(ge=0.0, le=1.0)


class OpsKnowledgeReport(BaseModel):
    """Ops review output for knowledge governance."""

    date: str
    candidates: list[KnowledgeCandidate]
    markdown: str


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
    impact: str = Field(description="이 이슈가 시장/종목에 주는 핵심 시사점 (단문)")
    sentiment: Sentiment
    source_ids: list[str] = Field(description="원본 메시지 ID 리스트")

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        """카테고리 정규화 (LLM이 생성한 alias → 정규 카테고리)."""
        return CATEGORY_ALIASES.get(v, v)


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
    key_insights: list[str] = Field(description="한글 크로스 테마 인사이트")
    category_insights: dict[str, str] = Field(
        default_factory=dict,
        description="카테고리별 인사이트 (카테고리 → 인사이트 문자열)",
    )
    news: list[NewsItem]


class DailyReportRun(BaseModel):
    """Pipeline runtime output bundle."""

    date: str
    main_report: DailyReport
    research_dump: ResearchDump
    ops_report: OpsKnowledgeReport
    artifacts_dir: str


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

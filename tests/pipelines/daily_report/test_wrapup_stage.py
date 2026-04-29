"""Wrapup V3 단위 테스트."""

from src.pipelines.daily_report.examples.wrapup_examples import get_wrapup_examples
from src.pipelines.daily_report.models import (
    CategoryInsightsList,
    DailyReport,
    MacroSnapshot,
)
from src.pipelines.daily_report.prompts import (
    WRAPUP_SYSTEM_PROMPT,
    WRAPUP_SYSTEM_PROMPT_V3,
    WRAPUP_USER_PROMPT,
    WRAPUP_USER_PROMPT_V3,
)


def test_daily_report_has_category_insights_field():
    """DailyReport에 category_insights 필드가 존재하고, 기본값은 빈 dict."""
    report = DailyReport(
        date="2026-04-20",
        macro=MacroSnapshot(
            date="2026-04-20",
            us_markets={"S&P500": 1.0, "NASDAQ": 0.5, "DOW": 0.3},
            kr_markets={"KOSPI": 0.2, "KOSDAQ": -0.1},
            vix=18.0,
            fear_greed=55,
            krw_usd=1320.0,
        ),
        key_insights=["test insight"],
        news=[],
    )
    assert report.category_insights == {}


def test_daily_report_with_category_insights():
    """DailyReport에 category_insights를 설정할 수 있다."""
    report = DailyReport(
        date="2026-04-20",
        macro=MacroSnapshot(
            date="2026-04-20",
            us_markets={"S&P500": 1.0, "NASDAQ": 0.5, "DOW": 0.3},
            kr_markets={"KOSPI": 0.2, "KOSDAQ": -0.1},
            vix=18.0,
            fear_greed=55,
            krw_usd=1320.0,
        ),
        key_insights=["test"],
        category_insights={
            "반도체": "HBM 가격 상승 + 엔비디아 독점 완화 → 국내 메모리 수혜",
            "에너지": "AI DC 전력 수요 급증 → 전력기기 업체 수주 가속",
        },
        news=[],
    )
    assert len(report.category_insights) == 2
    assert "반도체" in report.category_insights


def test_category_insights_list_model():
    """CategoryInsightsList 모델 검증."""
    result = CategoryInsightsList(
        insights={"반도체": "테스트 인사이트", "에너지": "전력 수요 인사이트"}
    )
    assert len(result.insights) == 2


def test_wrapup_examples_not_empty():
    """Wrapup 예시가 비어있지 않다."""
    examples = get_wrapup_examples()
    assert len(examples) > 100  # 충분한 길이


def test_wrapup_examples_contains_chain_arrow():
    """Wrapup 예시에 인과관계 체인(→)이 포함된다."""
    examples = get_wrapup_examples()
    assert "→" in examples


def test_wrapup_examples_contains_bad_example():
    """Wrapup 예시에 나쁜 예시가 포함된다."""
    examples = get_wrapup_examples()
    assert "나쁜 예시" in examples or "BAD" in examples.upper()


def test_wrapup_v3_system_prompt_exists():
    """V3 system prompt가 존재하고 핵심 지시를 포함한다."""
    assert len(WRAPUP_SYSTEM_PROMPT_V3) > 100
    assert "인과관계" in WRAPUP_SYSTEM_PROMPT_V3 or "→" in WRAPUP_SYSTEM_PROMPT_V3
    assert "{examples}" in WRAPUP_SYSTEM_PROMPT_V3


def test_wrapup_v3_user_prompt_exists():
    """V3 user prompt가 존재하고 필수 placeholder를 포함한다."""
    assert "{macro}" in WRAPUP_USER_PROMPT_V3
    assert "{news_items}" in WRAPUP_USER_PROMPT_V3
    assert "{news_count}" in WRAPUP_USER_PROMPT_V3


def test_wrapup_active_prompt_is_v3():
    """활성 Wrapup 프롬프트가 V3이다."""
    assert WRAPUP_SYSTEM_PROMPT is WRAPUP_SYSTEM_PROMPT_V3
    assert WRAPUP_USER_PROMPT is WRAPUP_USER_PROMPT_V3


def test_wrapup_input_uses_full_summary():
    """Wrapup 입력이 summary[:100]이 아닌 전체 summary를 사용한다."""
    # wrapup_stage.py의 news_text 포맷팅 로직을 직접 검증
    # _build_news_text 함수를 분리하여 테스트
    from src.pipelines.daily_report.models import NewsItem
    from src.pipelines.daily_report.stages.wrapup_stage import _build_news_text

    items = [
        NewsItem(
            category="반도체",
            technical_theme="HBM 메모리",
            investment_theme="HBM 가격 상승으로 메모리 업사이클 본격화",
            keywords=["HBM", "삼성전자", "SK하이닉스"],
            source_ids=["msg1"],
            emoji="🚀",
            summary="🚀 HBM3E 가격 70-75% 추가 상승 전망\n📈 삼성전자 HBM 검증 통과로 점유율 확대\n⚡ SK하이닉스 12단 양산 본격화로 공급 확대",
            impact="메모리 반도체 실적 턴어라운드 가속. 2026 영업이익 역대 최고치 전망.",
            stocks=[],
        ),
    ]

    text = _build_news_text(items)

    # summary 전체가 포함되어야 함 ([:100] 잘림 없음)
    assert "SK하이닉스 12단 양산 본격화로 공급 확대" in text
    # impact도 포함되어야 함
    assert "메모리 반도체 실적 턴어라운드" in text
    # stocks name도 포함 가능 (stocks 있을 경우)


def test_wrapup_input_includes_impact():
    """Wrapup 입력에 impact가 포함된다."""
    from src.pipelines.daily_report.models import NewsItem
    from src.pipelines.daily_report.stages.wrapup_stage import _build_news_text

    items = [
        NewsItem(
            category="에너지",
            technical_theme="전력 인프라",
            investment_theme="AI DC 전력 수요 급증, 전력기기 수주 가속",
            keywords=["LS ELECTRIC", "전력기기"],
            source_ids=["msg1"],
            emoji="⚡",
            summary="⚡ 전력 수요 +220% 전망",
            impact="전력기기 섹터 수주 레벨업. LS ELECTRIC 목표주가 상향.",
            stocks=[],
        ),
    ]

    text = _build_news_text(items)
    assert "전력기기 섹터 수주 레벨업" in text

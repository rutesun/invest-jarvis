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

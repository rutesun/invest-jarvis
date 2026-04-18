"""Daily report Pydantic 모델 테스트."""

import pytest

from src.pipelines.daily_report.models import (
    MacroSnapshot,
    MappedIssue,
    NewsItem,
)


def test_macro_snapshot_validation():
    """MacroSnapshot 필드 검증 테스트."""
    macro = MacroSnapshot(
        date="2026-04-14",
        us_markets={"S&P500": 1.2, "NASDAQ": 1.5, "DOW": 0.8},
        kr_markets={"KOSPI": 2.1, "KOSDAQ": 1.8},
        vix=19.1,
        fear_greed=52,
        krw_usd=1320.0,
    )
    assert macro.fear_greed == 52

    # Fear & Greed는 0-100이어야 함
    with pytest.raises(ValueError):
        MacroSnapshot(
            date="2026-04-14",
            us_markets={},
            kr_markets={},
            vix=19.1,
            fear_greed=101,
            krw_usd=1320.0,
        )


def test_mapped_issue_themes_constraint():
    """MappedIssue themes 길이 제약 테스트."""
    # 유효: 1-3개 테마
    issue = MappedIssue(
        title="테스트",
        summary="요약",
        themes=["AI 전력", "데이터센터"],
        keywords=["Bloom Energy"],
        sentiment="bull",
        source_ids=["msg1"],
    )
    assert len(issue.themes) == 2

    # 무효: 0개 테마
    with pytest.raises(ValueError):
        MappedIssue(
            title="테스트",
            summary="요약",
            themes=[],
            keywords=[],
            sentiment="bull",
            source_ids=[],
        )

    # 무효: >3개 테마
    with pytest.raises(ValueError):
        MappedIssue(
            title="테스트",
            summary="요약",
            themes=["A", "B", "C", "D"],
            keywords=[],
            sentiment="bull",
            source_ids=[],
        )


def test_news_item_emoji_field():
    """NewsItem emoji 필드 테스트."""
    item = NewsItem(
        theme="AI 전력",
        emoji="🚀",
        summary="- 내용",
        impact="Impact: 긍정적",
    )
    assert item.emoji == "🚀"


def test_theme_analysis_with_investment_theme():
    """ThemeAnalysis should have investment_theme and keywords fields."""
    from src.pipelines.daily_report.models import ThemeAnalysis

    data = {
        "investment_theme": "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",
        "keywords": ["GPU", "엔비디아", "AMD", "세레브라스", "AI 칩"],
        "emoji": "🚀",
        "summary": "테스트 요약",
        "impact": "테스트 영향",
        "stocks": [],
    }

    analysis = ThemeAnalysis(**data)

    assert analysis.investment_theme == "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜"
    assert len(analysis.keywords) == 5
    assert "GPU" in analysis.keywords

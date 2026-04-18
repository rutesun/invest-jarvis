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
        category="AI/소프트웨어",
        title="테스트",
        summary="요약",
        themes=["AI 전력", "데이터센터"],
        impact="긍정적 영향",
        keywords=["Bloom Energy"],
        sentiment="bull",
        source_ids=["msg1"],
    )
    assert len(issue.themes) == 2

    # 무효: 0개 테마
    with pytest.raises(ValueError):
        MappedIssue(
            category="AI/소프트웨어",
            title="테스트",
            summary="요약",
            themes=[],
            impact="긍정적 영향",
            keywords=[],
            sentiment="bull",
            source_ids=[],
        )

    # 무효: >3개 테마
    with pytest.raises(ValueError):
        MappedIssue(
            category="AI/소프트웨어",
            title="테스트",
            summary="요약",
            themes=["A", "B", "C", "D"],
            impact="긍정적 영향",
            keywords=[],
            sentiment="bull",
            source_ids=[],
        )


def test_news_item_emoji_field():
    """NewsItem emoji 필드 테스트."""
    item = NewsItem(
        category="에너지",
        technical_theme="AI 전력",
        investment_theme="AI 전력 수요 급증으로 친환경 에너지 인프라 강화",
        keywords=["AI", "전력", "데이터센터"],
        emoji="🚀",
        summary="- 내용",
        impact="Impact: 긍정적",
    )
    assert item.emoji == "🚀"


def test_theme_analysis_with_investment_theme():
    """ThemeAnalysis should have investment_theme and keywords fields."""
    from pydantic import ValidationError

    from src.pipelines.daily_report.models import ThemeAnalysis

    data = {
        "theme": "GPU 공급망",
        "investment_theme": "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",
        "keywords": ["GPU", "엔비디아", "AMD", "세레브라스", "AI 칩"],
        "emoji": "🚀",
        "summary": "테스트 요약",
        "impact": "테스트 영향",
        "stocks": [],
    }

    analysis = ThemeAnalysis(**data)

    assert analysis.theme == "GPU 공급망"
    assert analysis.investment_theme == "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜"
    assert len(analysis.keywords) == 5
    assert "GPU" in analysis.keywords

    # Test investment_theme too short (19 chars)
    with pytest.raises(ValidationError, match="20-40자여야 합니다"):
        ThemeAnalysis(
            theme="GPU 공급망",
            investment_theme="GPU 공급망 다변화 가속 완화",  # 19 chars
            keywords=["GPU", "엔비디아", "AMD", "세레브라스", "AI 칩"],
            emoji="🚀",
            summary="테스트 요약",
            impact="테스트 영향",
        )

    # Test investment_theme too long (41 chars)
    with pytest.raises(ValidationError, match="20-40자여야 합니다"):
        ThemeAnalysis(
            theme="GPU 공급망",
            investment_theme="GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜, AI 칩셋 경쟁 심화",  # 41 chars
            keywords=["GPU", "엔비디아", "AMD", "세레브라스", "AI 칩"],
            emoji="🚀",
            summary="테스트 요약",
            impact="테스트 영향",
        )

    # Test keywords too few (4 items)
    with pytest.raises(ValidationError, match="5-10개여야 합니다"):
        ThemeAnalysis(
            theme="GPU 공급망",
            investment_theme="GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",
            keywords=["GPU", "엔비디아", "AMD", "세레브라스"],  # 4 items
            emoji="🚀",
            summary="테스트 요약",
            impact="테스트 영향",
        )

    # Test keywords too many (11 items)
    with pytest.raises(ValidationError, match="5-10개여야 합니다"):
        ThemeAnalysis(
            theme="GPU 공급망",
            investment_theme="GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",
            keywords=[
                "GPU",
                "엔비디아",
                "AMD",
                "세레브라스",
                "AI 칩",
                "반도체",
                "데이터센터",
                "클라우드",
                "머신러닝",
                "딥러닝",
                "HPC",
            ],  # 11 items
            emoji="🚀",
            summary="테스트 요약",
            impact="테스트 영향",
        )


def test_news_item_with_split_themes():
    """NewsItem should have both technical_theme and investment_theme."""
    data = {
        "category": "반도체",
        "technical_theme": "AI 인프라 및 칩 수요",
        "investment_theme": "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",
        "keywords": ["GPU", "엔비디아", "AMD"],
        "emoji": "🚀",
        "summary": "테스트 요약",
        "impact": "테스트 영향",
        "stocks": [],
    }

    news = NewsItem(**data)

    assert news.technical_theme == "AI 인프라 및 칩 수요"
    assert news.investment_theme == "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜"
    assert len(news.keywords) == 3

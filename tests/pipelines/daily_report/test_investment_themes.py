"""Integration tests for investment theme generation."""

import pytest

from src.pipelines.daily_report.models import MacroSnapshot, MappedIssue
from src.pipelines.daily_report.stages.reduce_stage import reduce_stage


@pytest.fixture
def macro_snapshot():
    """Sample macro data."""
    return MacroSnapshot(
        date="2026-04-19",
        us_markets={"S&P500": 1.2, "NASDAQ": 1.5, "DOW": 0.8},
        kr_markets={"KOSPI": 0.5, "KOSDAQ": 0.3},
        vix=15.2,
        fear_greed=65,
        krw_usd=1320.5,
    )


@pytest.fixture
def sample_category_groups():
    """Sample shuffled issues grouped by category and theme."""
    issue1 = MappedIssue(
        category="반도체",
        title="세레브라스 오픈AI 계약",
        summary="오픈AI가 세레브라스와 200억 달러 규모 계약 체결",
        themes=["AI 인프라 및 칩 수요"],
        impact="GPU 공급망 다변화 가속",
        keywords=["세레브라스", "오픈AI", "GPU"],
        sentiment="bull",
        source_ids=["msg1"],
    )

    return {"반도체": {"AI 인프라 및 칩 수요": [issue1]}}


def test_reduce_generates_investment_theme(sample_category_groups, macro_snapshot):
    """Reduce stage should generate investment_theme and keywords."""
    result = reduce_stage(sample_category_groups, macro_snapshot, date="2026-04-19")

    assert len(result) == 1
    news_item = result[0]

    # Should have both theme fields
    assert hasattr(news_item, "technical_theme")
    assert hasattr(news_item, "investment_theme")
    assert hasattr(news_item, "keywords")

    # technical_theme should match Shuffle output
    assert news_item.technical_theme == "AI 인프라 및 칩 수요"

    # investment_theme should be different (LLM-generated insight)
    assert news_item.investment_theme != news_item.technical_theme

    # Should have length constraint
    assert 20 <= len(news_item.investment_theme) <= 40

    # Should have keywords
    assert 5 <= len(news_item.keywords) <= 10

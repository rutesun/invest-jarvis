"""Daily report Pydantic 모델 테스트."""

import pytest

from src.pipelines.daily_report.models import (
    KeyInsightsList,
    MacroSnapshot,
    MappedIssue,
    MappedIssueList,
    NewsItem,
    Sentiment,
    ThemeAnalysis,
    ThemeMapping,
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
        stocks=[],
        source_ids=["test-123"],
    )
    assert item.emoji == "🚀"


def test_theme_analysis_with_investment_theme():
    """ThemeAnalysis should have investment_theme and keywords fields."""
    from pydantic import ValidationError

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
        "source_ids": ["test-456"],
    }

    news = NewsItem(**data)

    assert news.technical_theme == "AI 인프라 및 칩 수요"
    assert news.investment_theme == "GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜"
    assert len(news.keywords) == 3


def test_validation_error_context():
    """ValidationError should include spec and examples in context."""
    from pydantic import ValidationError

    # Test investment_theme validation error context
    try:
        ThemeAnalysis(
            theme="GPU 공급망",
            investment_theme="짧음",  # Too short (2 chars)
            keywords=["GPU", "엔비디아", "AMD", "세레브라스", "AI 칩"],
            emoji="🚀",
            summary="테스트 요약",
            impact="테스트 영향",
        )
    except ValidationError as e:
        errors = e.errors()
        assert len(errors) == 1
        error = errors[0]

        # Check error structure
        assert error["type"] == "theme_length_error"
        assert "ctx" in error

        # Check context contains spec and examples
        ctx = error["ctx"]
        assert "spec" in ctx
        assert "examples" in ctx
        assert "length" in ctx
        assert ctx["length"] == 2

        # Check spec content
        assert "20-40자" in ctx["spec"]
        assert "방향성 명확히" in ctx["spec"]

        # Check examples
        assert isinstance(ctx["examples"], list)
        assert len(ctx["examples"]) == 3
        assert "엔비디아" in ctx["examples"][0]

    # Test keywords validation error context
    try:
        ThemeAnalysis(
            theme="GPU 공급망",
            investment_theme="GPU 공급망 다변화 가속, 엔비디아 독점 완화 수혜",
            keywords=["GPU", "엔비디아", "AMD"],  # Too few (3 items)
            emoji="🚀",
            summary="테스트 요약",
            impact="테스트 영향",
        )
    except ValidationError as e:
        errors = e.errors()
        assert len(errors) == 1
        error = errors[0]

        # Check error structure
        assert error["type"] == "keywords_count_error"

        # Check context
        ctx = error["ctx"]
        assert "spec" in ctx
        assert "examples" in ctx
        assert "count" in ctx
        assert ctx["count"] == 3

        # Check spec content
        assert "5-10개" in ctx["spec"]

        # Check examples
        assert isinstance(ctx["examples"], list)
        assert len(ctx["examples"]) == 2


def test_mapped_issue_normalizes_common_category_aliases():
    issue = MappedIssue(
        category="전기전자",
        title="AI 서버 부품 수요 확대",
        summary="AI 서버 부품 수요가 늘고 있다.",
        themes=["AI 서버 부품"],
        impact="반도체 밸류체인 수혜",
        sentiment=Sentiment.BULL,
        source_ids=["1"],
    )

    assert issue.category == "반도체"


def test_mapped_issue_normalizes_steel_metal_category_alias():
    issue = MappedIssue(
        category="철강금속",
        title="철강 수요 회복",
        summary="철강 수요 회복과 금속 가격 변화가 나타났다.",
        themes=["철강 수요 회복"],
        impact="소재 업종 수혜",
        sentiment=Sentiment.BULL,
        source_ids=["1"],
    )

    assert issue.category == "소재/화학"


def test_mapped_issue_normalizes_stock_name_used_as_category():
    issue = MappedIssue(
        category="현대백화점",
        title="백화점 소비 회복",
        summary="백화점 소비 회복 신호가 나타났다.",
        themes=["백화점 소비 회복"],
        impact="유통 업종 수혜",
        sentiment=Sentiment.BULL,
        source_ids=["1"],
    )

    assert issue.category == "유통/소비재"


def test_mapped_issue_normalizes_space_and_resource_category_aliases():
    cases = [
        ("우주개발", "방산"),
        ("철강/소재", "소재/화학"),
        ("광산/에너지", "에너지"),
    ]

    for raw_category, expected in cases:
        issue = MappedIssue(
            category=raw_category,
            title="카테고리 정규화",
            summary="LLM category alias를 정규화한다.",
            themes=["카테고리 정규화"],
            impact="리포트 생성 안정화",
            sentiment=Sentiment.NEUTRAL,
            source_ids=["1"],
        )

        assert issue.category == expected


# invoke_llm_with_retry에 전달되는 구조화 출력 모델 전체
LLM_OUTPUT_MODELS = [MappedIssueList, ThemeMapping, ThemeAnalysis, KeyInsightsList]


def _free_form_object_paths(schema: dict, path: str = "<root>") -> list[str]:
    """properties 없는 object(자유형 dict) 경로 수집."""
    found = []
    if schema.get("type") == "object" and "properties" not in schema:
        found.append(path)
    for section in ("properties", "$defs"):
        for name, sub in schema.get(section, {}).items():
            found.extend(_free_form_object_paths(sub, f"{path}.{name}"))
    if isinstance(schema.get("items"), dict):
        found.extend(_free_form_object_paths(schema["items"], f"{path}[]"))
    for i, sub in enumerate(schema.get("anyOf", [])):
        found.extend(_free_form_object_paths(sub, f"{path}|{i}"))
    return found


@pytest.mark.parametrize("model", LLM_OUTPUT_MODELS)
def test_llm_output_models_are_openai_strict_schema_compatible(model):
    """OpenAI strict structured output은 자유형 dict 필드를 400으로 거부한다."""
    offending = _free_form_object_paths(model.model_json_schema())

    assert not offending, (
        f"{model.__name__}에 OpenAI strict json_schema가 거부하는 "
        f"자유형 dict 필드가 있습니다: {offending}"
    )

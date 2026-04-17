"""Reduce stage: 테마별 뉴스 검색 및 분석 리포트 생성."""

import asyncio
import json
from pathlib import Path

from ddgs import DDGS
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from src.llm.provider import LLMProvider
from src.pipelines.daily_report.models import (
    MacroSnapshot,
    MappedIssue,
    NewsItem,
)
from src.pipelines.daily_report.prompts import REDUCE_SYSTEM_PROMPT, REDUCE_USER_PROMPT


load_dotenv()


@traceable(name="Reduce Stage")
def reduce_stage(
    category_groups: dict[str, dict[str, list[MappedIssue]]],
    macro: MacroSnapshot,
    date: str = None,
    max_news_per_theme: int = 5,
) -> list[NewsItem]:
    """
    테마별로 뉴스 검색 + LLM 분석 리포트 생성.

    Args:
        category_groups: Shuffle stage 출력 { category: { theme: [issues] } }
        macro: 매크로 데이터
        date: 날짜 문자열
        max_news_per_theme: 테마당 최대 뉴스 개수

    Returns:
        테마별 NewsItem 리스트 (카테고리 포함)
    """
    if not category_groups:
        return []

    # 병렬 처리
    loop = asyncio.get_event_loop()
    news_items = loop.run_until_complete(
        _analyze_themes_parallel(
            category_groups,
            macro,
            date,
            max_news_per_theme,
        )
    )

    return news_items


async def _analyze_themes_parallel(
    category_groups: dict[str, dict[str, list[MappedIssue]]],
    macro: MacroSnapshot,
    date: str,
    max_news_per_theme: int,
) -> list[NewsItem]:
    """카테고리/테마별 병렬 분석."""
    tasks = []
    for category, theme_map in category_groups.items():
        for theme, issues in theme_map.items():
            tasks.append(_analyze_theme(category, theme, issues, macro, date, max_news_per_theme))
    return await asyncio.gather(*tasks)


async def _analyze_theme(
    category: str,
    theme: str,
    issues: list[MappedIssue],
    macro: MacroSnapshot,
    date: str,
    max_news: int,
) -> NewsItem:
    """단일 테마 분석."""
    # 1. 뉴스 검색
    news_articles = _search_news(theme, date, max_news)

    # 2. LLM 분석
    llm = LLMProvider.create(
        provider="anthropic",
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        temperature=0.3,
    )

    # 프롬프트 구성
    issues_text = "\n\n".join(
        [
            f"**{issue.title}**\n{issue.summary}\n"
            f"키워드: {', '.join(issue.keywords)}\n"
            f"감성: {issue.sentiment}"
            for issue in issues
        ]
    )

    news_text = (
        "\n\n".join(
            [
                f"**{article['title']}**\n{article['body']}\n출처: {article['url']}"
                for article in news_articles
            ]
        )
        if news_articles
        else "관련 뉴스 없음"
    )

    system_prompt = REDUCE_SYSTEM_PROMPT
    user_prompt = REDUCE_USER_PROMPT.format(
        theme=theme,
        issues=issues_text,
        news_articles=news_text,
    )

    # LangSmith 태깅
    run_name = f"Reduce Stage - {date} - {category}/{theme[:20]}"
    config = {
        "run_name": run_name,
        "tags": [
            "daily_report",
            "reduce_stage",
            f"date:{date}",
            f"category:{category}",
            f"theme:{theme}",
        ],
        "metadata": {
            "stage": "reduce",
            "date": date,
            "category": category,
            "theme": theme,
            "issue_count": len(issues),
            "news_count": len(news_articles),
        },
    }

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        # NewsItem without category (LLM output)

        from pydantic import BaseModel, Field

        class NewsItemOutput(BaseModel):
            """Reduce stage LLM 출력용 (category 제외)."""

            theme: str = Field(description="한글 정규화 테마명")
            emoji: str = Field(description="단일 이모지: 🚀📈⚠️ℹ️📉⚡")
            summary: str = Field(description="한글 bullet points")
            impact: str = Field(description="한글 impact 문구")
            stocks: list[dict] = Field(default_factory=list)

        llm_with_output = llm.with_structured_output(NewsItemOutput)
        response = await llm_with_output.ainvoke(messages, config=config)

        # category 추가하여 NewsItem 생성
        from src.pipelines.daily_report.models import StockDetail

        stocks = [StockDetail(**s) for s in response.stocks] if response.stocks else []

        return NewsItem(
            category=category,
            theme=response.theme,
            emoji=response.emoji,
            summary=response.summary,
            impact=response.impact,
            stocks=stocks,
        )
    except Exception as e:
        print(f"⚠️  테마 '{theme}' 분석 실패: {e}")
        return NewsItem(
            category=category,
            theme=theme,
            emoji="ℹ️",
            summary=f"{theme} 관련 {len(issues)}개 이슈",
            impact="분석 실패",
            stocks=[],
        )


def _search_news(theme: str, date: str, max_results: int) -> list[dict]:
    """DuckDuckGo로 뉴스 검색."""
    try:
        query = f"{theme} 주식 시장"

        ddgs = DDGS()
        results = ddgs.news(
            query,
            region="kr-kr",
            max_results=max_results,
        )

        return list(results) if results else []
    except Exception as e:
        print(f"⚠️  뉴스 검색 실패 ({theme}): {e}")
        return []


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"

    # Shuffle stage 출력 로드
    shuffle_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/shuffle_{date}.json"
    with open(shuffle_file, encoding="utf-8") as f:
        shuffle_data = json.load(f)

    # category_groups 복원
    category_groups = {
        category: {
            theme: [MappedIssue(**issue) for issue in issues] for theme, issues in theme_map.items()
        }
        for category, theme_map in shuffle_data["category_groups"].items()
    }

    # Ingest stage에서 매크로 로드
    ingest_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/ingest_{date}.json"
    with open(ingest_file, encoding="utf-8") as f:
        ingest_data = json.load(f)
    macro = MacroSnapshot(**ingest_data["macro"])

    total_themes = sum(len(theme_map) for theme_map in category_groups.values())
    print(f"✓ {len(category_groups)}개 카테고리, {total_themes}개 테마 그룹 로드")

    # Reduce stage 실행
    news_items = reduce_stage(category_groups, macro, date)

    print(f"✓ {len(news_items)}개 테마 분석")

    # 카테고리별 출력
    for item in news_items:
        print(f"  [{item.category}] {item.emoji} {item.theme}")

    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/reduce_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            [item.model_dump() for item in news_items],
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"✓ {output_file}에 저장")

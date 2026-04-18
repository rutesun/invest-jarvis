"""Reduce stage: 테마별 LLM 분석 리포트 생성."""

import asyncio
import json
import logging
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()
from langsmith import traceable

from src.pipelines.daily_report.config import REDUCE_LLM
from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.daily_report.models import (
    MacroSnapshot,
    MappedIssue,
    NewsItem,
    ThemeAnalysis,
)
from src.pipelines.daily_report.prompts import REDUCE_SYSTEM_PROMPT, REDUCE_USER_PROMPT


logger = logging.getLogger(__name__)


@traceable(name="Reduce Stage")
def reduce_stage(
    category_groups: dict[str, dict[str, list[MappedIssue]]],
    macro: MacroSnapshot,
    date: str = None,
) -> list[NewsItem]:
    """
    테마별 LLM 분석 리포트 생성.

    Args:
        category_groups: Shuffle stage 출력 { category: { theme: [issues] } }
        macro: 매크로 데이터
        date: 날짜 문자열

    Returns:
        테마별 NewsItem 리스트 (카테고리 포함)
    """
    if not category_groups:
        return []

    news_items = asyncio.run(_analyze_themes_parallel(category_groups, macro, date))

    return news_items


async def _analyze_themes_parallel(
    category_groups: dict[str, dict[str, list[MappedIssue]]],
    macro: MacroSnapshot,
    date: str,
) -> list[NewsItem]:
    """카테고리/테마별 병렬 분석."""
    llm = REDUCE_LLM.create_llm()
    tasks = []
    for category, theme_map in category_groups.items():
        for theme, issues in theme_map.items():
            tasks.append(_analyze_theme(llm, category, theme, issues, macro, date))
    return await asyncio.gather(*tasks)


async def _analyze_theme(
    llm,
    category: str,
    theme: str,
    issues: list[MappedIssue],
    macro: MacroSnapshot,
    date: str,
) -> NewsItem:
    """단일 테마 분석."""

    issues_text = "\n\n".join(
        [
            f"**{issue.title}**\n{issue.summary}\n"
            f"키워드: {', '.join(issue.keywords)}\n"
            f"감성: {issue.sentiment}"
            for issue in issues
        ]
    )

    system_prompt = REDUCE_SYSTEM_PROMPT
    user_prompt = REDUCE_USER_PROMPT.format(
        theme=theme,
        issues=issues_text,
    )

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
        },
    }

    messages = REDUCE_LLM.build_messages(system_prompt, user_prompt)

    try:
        response = await invoke_llm_with_retry(llm, ThemeAnalysis, messages, config)

        return NewsItem(
            category=category,
            technical_theme=theme,
            investment_theme=theme,
            keywords=[],
            emoji=response.emoji,
            summary=response.summary,
            impact=response.impact,
            stocks=response.stocks,
        )
    except Exception as e:
        logger.error("Theme '%s' analysis failed: %s", theme, e, exc_info=True)
        return NewsItem(
            category=category,
            technical_theme=theme,
            investment_theme=theme,
            keywords=[],
            emoji="ℹ️",
            summary=f"{theme} 관련 {len(issues)}개 이슈",
            impact="분석 실패",
            stocks=[],
        )


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
        print(f"  [{item.category}] {item.emoji} {item.investment_theme}")

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

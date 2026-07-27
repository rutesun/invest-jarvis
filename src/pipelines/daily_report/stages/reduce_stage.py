"""Reduce stage: 테마별 LLM 분석 리포트 생성."""

import asyncio
import json
import logging
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()
from langsmith import traceable

from src.pipelines.daily_report.config import get_stage_llm
from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.daily_report.models import (
    MacroSnapshot,
    MappedIssue,
    NewsItem,
    ThemeAnalysis,
)
from src.pipelines.daily_report.prompts import (
    REDUCE_SYSTEM_PROMPT_V2,
    REDUCE_USER_PROMPT_V2,
)


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
    import time

    if not category_groups:
        return []

    start_time = time.time()
    total_themes = sum(len(themes) for themes in category_groups.values())

    logger.info(
        "Reduce stage started: %d categories, %d themes",
        len(category_groups),
        total_themes,
    )

    news_items = asyncio.run(_analyze_themes_parallel(category_groups, macro, date))

    elapsed = time.time() - start_time

    logger.info(
        "Reduce stage completed: %d themes → %d news items in %.1fs",
        total_themes,
        len(news_items),
        elapsed,
    )

    return news_items


async def _analyze_themes_parallel(
    category_groups: dict[str, dict[str, list[MappedIssue]]],
    macro: MacroSnapshot,
    date: str,
) -> list[NewsItem]:
    """카테고리/테마별 병렬 분석 (실패율 체크 포함)."""
    llm = get_stage_llm("reduce").create_llm()

    # 테마명과 함께 태스크 저장
    theme_tasks = []
    for category, theme_map in category_groups.items():
        for theme, issues in theme_map.items():
            task = _analyze_theme(llm, category, theme, issues, macro, date)
            theme_tasks.append((category, theme, task))

    # 병렬 실행 (예외 수집)
    results = await asyncio.gather(*[task for _, _, task in theme_tasks], return_exceptions=True)

    # 성공/실패 분류
    success = []
    failed_info = []

    for (category, theme, _), result in zip(theme_tasks, results, strict=True):
        if isinstance(result, Exception):
            failed_info.append(
                {
                    "category": category,
                    "theme": theme,
                    "error_type": type(result).__name__,
                    "error_message": str(result),
                }
            )
        else:
            success.append(result)

    # 실패 정보 로깅
    for fail in failed_info:
        logger.error(
            "❌ 테마 분석 실패 - [%s] %s: %s (%s)",
            fail["category"],
            fail["theme"],
            fail["error_type"],
            fail["error_message"],
        )

    # 실패율 체크
    failure_rate = len(failed_info) / len(results) if results else 0

    if failure_rate > 0.2:
        logger.error(
            "🛑 테마 분석 실패율 %.1f%% 초과 (%d/%d), 파이프라인 중단",
            failure_rate * 100,
            len(failed_info),
            len(results),
        )
        raise RuntimeError(
            f"Theme analysis failure rate too high: {len(failed_info)}/{len(results)} "
            f"({failure_rate:.1%})"
        )

    if failed_info:
        logger.warning(
            "⚠️ %d개 테마 분석 실패 (성공률: %.1f%%)", len(failed_info), (1 - failure_rate) * 100
        )

    return success


async def _analyze_theme(
    llm,
    category: str,
    theme: str,
    issues: list[MappedIssue],
    macro: MacroSnapshot,
    date: str,
) -> NewsItem:
    """단일 테마 분석 (투자 인사이트 생성)."""

    issues_text = "\n\n".join(
        [f"**{issue.title}**\n{issue.summary}\n감성: {issue.sentiment}" for issue in issues]
    )

    system_prompt = REDUCE_SYSTEM_PROMPT_V2
    user_prompt = REDUCE_USER_PROMPT_V2.format(
        technical_theme=theme,
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

    messages = get_stage_llm("reduce").build_messages(system_prompt, user_prompt)

    try:
        response = await invoke_llm_with_retry(llm, ThemeAnalysis, messages, config)

        # Flatten source_ids from all issues
        all_source_ids = [sid for issue in issues for sid in issue.source_ids]

        return NewsItem(
            category=category,
            technical_theme=theme,
            investment_theme=response.investment_theme,
            keywords=response.keywords,
            source_ids=all_source_ids,
            emoji=response.emoji,
            summary=response.summary,
            impact=response.impact,
            stocks=response.stocks,
        )
    except Exception as e:
        logger.error(
            "테마 분석 실패 - [%s] %s: %s (%s)",
            category,
            theme,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        raise


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

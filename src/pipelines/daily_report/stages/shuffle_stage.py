"""Shuffle stage: 카테고리 그룹핑 + 테마 정규화."""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from src.llm.provider import LLMProvider
from src.pipelines.daily_report.models import MappedIssue, ShuffleResult, ThemeMapping
from src.pipelines.daily_report.prompts import SHUFFLE_SYSTEM_PROMPT, SHUFFLE_USER_PROMPT


load_dotenv()


@traceable(name="Shuffle Stage")
def shuffle_stage(
    issues: list[MappedIssue],
    date: str = None,
) -> ShuffleResult:
    """
    2단계 그룹핑: 카테고리 버킷팅 → 카테고리 내 테마 정규화.

    Args:
        issues: Map stage 출력 이슈 리스트
        date: 날짜 문자열 (LangSmith 그룹핑용)

    Returns:
        category_groups: { category: { theme: [issues] } }
    """
    if not issues:
        return ShuffleResult(category_groups={})

    # 1단계: 결정론적 카테고리 그룹핑 (LLM 불필요)
    category_buckets: dict[str, list[MappedIssue]] = {}
    for issue in issues:
        category_buckets.setdefault(issue.category, []).append(issue)

    # 2단계: 카테고리 내 테마 정규화 (LLM, 병렬)
    loop = asyncio.get_event_loop()
    category_groups = loop.run_until_complete(_normalize_themes_by_category(category_buckets, date))

    return ShuffleResult(category_groups=category_groups)


async def _normalize_themes_by_category(
    category_buckets: dict[str, list[MappedIssue]],
    date: str,
) -> dict[str, dict[str, list[MappedIssue]]]:
    """카테고리별 병렬 테마 정규화."""
    tasks = [
        _normalize_themes_for_category(category, issues, date)
        for category, issues in category_buckets.items()
    ]
    results = await asyncio.gather(*tasks)

    return dict(zip(category_buckets.keys(), results, strict=True))


async def _normalize_themes_for_category(
    category: str,
    issues: list[MappedIssue],
    date: str,
) -> dict[str, list[MappedIssue]]:
    """단일 카테고리 내 테마 정규화."""
    # 카테고리 내 모든 테마 수집
    all_themes = []
    for issue in issues:
        all_themes.extend(issue.themes)
    unique_themes = list(set(all_themes))

    # 테마가 적으면 정규화 생략
    if len(unique_themes) <= 2:
        theme_mapping = {theme: [theme] for theme in unique_themes}
    else:
        theme_mapping = await _normalize_themes(unique_themes, category, date)

    # 이슈를 정규화된 테마로 그룹핑
    theme_groups: dict[str, list[MappedIssue]] = {}

    for issue in issues:
        # 이슈의 첫 번째 테마로 대표 테마 결정
        primary_theme = issue.themes[0] if issue.themes else "기타"

        # 정규화된 테마 찾기
        normalized_theme = primary_theme
        for norm_theme, orig_themes in theme_mapping.items():
            if primary_theme in orig_themes:
                normalized_theme = norm_theme
                break

        # 그룹에 추가
        if normalized_theme not in theme_groups:
            theme_groups[normalized_theme] = []
        theme_groups[normalized_theme].append(issue)

    return theme_groups


async def _normalize_themes(
    themes: list[str],
    category: str,
    date: str,
) -> dict[str, list[str]]:
    """LLM으로 테마 정규화."""
    llm = LLMProvider.create(
        provider="anthropic",
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        temperature=0.1,
    )

    themes_text = "\n".join([f"- {theme}" for theme in themes])

    system_prompt = SHUFFLE_SYSTEM_PROMPT
    user_prompt = SHUFFLE_USER_PROMPT.format(themes=themes_text)

    # LangSmith 태깅
    run_name = f"Shuffle Stage - {date} - {category}"
    config = {
        "run_name": run_name,
        "tags": ["daily_report", "shuffle_stage", f"date:{date}", f"category:{category}"],
        "metadata": {
            "stage": "shuffle",
            "date": date,
            "category": category,
            "theme_count": len(themes),
        },
    }

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        llm_with_output = llm.with_structured_output(ThemeMapping)
        response = await llm_with_output.ainvoke(messages, config=config)
        return response.mapping
    except Exception as e:
        print(f"⚠️  [{category}] 테마 정규화 실패: {e}")
        return {theme: [theme] for theme in themes}


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"

    # Map stage 출력 로드
    map_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/map_{date}.json"
    with open(map_file, encoding="utf-8") as f:
        issues_data = json.load(f)
    issues = [MappedIssue(**issue) for issue in issues_data]

    print(f"✓ {len(issues)}개 이슈 로드")

    # Shuffle stage 실행
    result = shuffle_stage(issues, date)

    # 통계 출력
    total_categories = len(result.category_groups)
    total_themes = sum(len(themes) for themes in result.category_groups.values())
    total_issues = sum(
        len(issues) for themes in result.category_groups.values() for issues in themes.values()
    )

    print(f"✓ {total_categories}개 카테고리")
    print(f"✓ {total_themes}개 테마 그룹")
    print(f"✓ 총 {total_issues}개 이슈")

    for category, theme_map in result.category_groups.items():
        print(f"\n[{category}]")
        for theme, issues in theme_map.items():
            print(f"  - {theme}: {len(issues)}개 이슈")

    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/shuffle_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "category_groups": {
            category: {
                theme: [issue.model_dump() for issue in issues]
                for theme, issues in theme_map.items()
            }
            for category, theme_map in result.category_groups.items()
        },
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n✓ {output_file}에 저장")

"""Shuffle stage: 테마 정규화 및 클러스터 재구성."""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.provider import LLMProvider


load_dotenv()
from langsmith import traceable

from src.pipelines.daily_report.models import MappedIssue, ShuffleResult, ThemeMapping
from src.pipelines.daily_report.prompts import SHUFFLE_SYSTEM_PROMPT, SHUFFLE_USER_PROMPT


@traceable(name="Shuffle Stage")
def shuffle_stage(
    issues: list[MappedIssue],
    date: str = None,
) -> ShuffleResult:
    """
    테마를 정규화하고 이슈를 재그룹핑.

    Args:
        issues: Map stage 출력 이슈 리스트
        date: 날짜 문자열 (LangSmith 그룹핑용)

    Returns:
        정규화된 테마와 재그룹핑된 이슈
    """
    if not issues:
        return ShuffleResult(theme_mapping={}, regrouped_issues=issues)

    # 모든 테마 추출
    all_themes = []
    for issue in issues:
        all_themes.extend(issue.themes)

    unique_themes = list(set(all_themes))

    # LLM으로 테마 정규화
    loop = asyncio.get_event_loop()
    theme_mapping = loop.run_until_complete(_normalize_themes(unique_themes, date))

    # 이슈 테마 업데이트 및 그룹핑
    theme_groups = {}
    for issue in issues:
        normalized_themes = []
        for theme in issue.themes:
            # theme_mapping에서 정규화된 테마 찾기
            for norm_theme, orig_themes in theme_mapping.items():
                if theme in orig_themes:
                    normalized_themes.append(norm_theme)
                    break
            else:
                # 매핑 없으면 원본 유지
                normalized_themes.append(theme)

        # 중복 제거
        normalized_themes = list(set(normalized_themes))[:3]  # 최대 3개

        new_issue = MappedIssue(
            title=issue.title,
            summary=issue.summary,
            themes=normalized_themes,
            impact=issue.impact,
            keywords=issue.keywords,
            sentiment=issue.sentiment,
            source_ids=issue.source_ids,
        )

        # 각 테마별로 그룹핑
        for theme in normalized_themes:
            if theme not in theme_groups:
                theme_groups[theme] = []
            theme_groups[theme].append(new_issue)

    return ShuffleResult(
        canonical_themes=theme_mapping,
        theme_groups=theme_groups,
    )


async def _normalize_themes(themes: list[str], date: str) -> dict[str, list[str]]:
    """LLM으로 테마 정규화."""
    llm = LLMProvider.create(
        provider="anthropic", model="us.anthropic.claude-haiku-4-5-20251001-v1:0", temperature=0.1
    )

    themes_text = "\n".join([f"- {theme}" for theme in themes])

    # prompts.py에서 프롬프트 가져오기
    system_prompt = SHUFFLE_SYSTEM_PROMPT
    user_prompt = SHUFFLE_USER_PROMPT.format(themes=themes_text)

    # LangSmith 태깅
    run_name = f"Shuffle Stage - {date}"
    config = {
        "run_name": run_name,
        "tags": ["daily_report", "shuffle_stage", f"date:{date}"],
        "metadata": {
            "stage": "shuffle",
            "date": date,
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
        print(f"⚠️  테마 정규화 실패: {e}")
        # fallback: 원본 테마 그대로 사용
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

    print(f"✓ {len(result.canonical_themes)}개 정규화 테마")
    total_issues = sum(len(group) for group in result.theme_groups.values())
    print(f"✓ {len(result.theme_groups)}개 그룹, 총 {total_issues}개 이슈")

    # 출력 저장 (JSON 직렬화를 위해 theme_groups를 dict로 변환)
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/shuffle_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "canonical_themes": result.canonical_themes,
        "theme_groups": {
            theme: [issue.model_dump() for issue in issues]
            for theme, issues in result.theme_groups.items()
        },
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")

"""Reduce stage: 테마별 뉴스 검색 및 분석 리포트 생성."""
import asyncio
import json
from typing import List, Dict
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from ddgs import DDGS
from src.llm.provider import LLMProvider

load_dotenv()
from langsmith import traceable
from src.pipelines.daily_report.models import (
    MappedIssue,
    NewsItem,
    StockDetail,
    MacroSnapshot,
)
from src.pipelines.daily_report.prompts import REDUCE_SYSTEM_PROMPT, REDUCE_USER_PROMPT


@traceable(name="Reduce Stage")
def reduce_stage(
    theme_groups: Dict[str, List[MappedIssue]],
    macro: MacroSnapshot,
    date: str = None,
    max_news_per_theme: int = 5,
) -> List[NewsItem]:
    """
    테마별로 뉴스 검색 + LLM 분석 리포트 생성.

    Args:
        theme_groups: Shuffle stage 출력 (테마별로 그룹핑된 이슈)
        macro: 매크로 데이터
        date: 날짜 문자열
        max_news_per_theme: 테마당 최대 뉴스 개수

    Returns:
        테마별 NewsItem 리스트
    """
    if not theme_groups:
        return []

    # 병렬 처리
    loop = asyncio.get_event_loop()
    news_items = loop.run_until_complete(
        _analyze_themes_parallel(
            theme_groups,
            macro,
            date,
            max_news_per_theme,
        )
    )

    return news_items


async def _analyze_themes_parallel(
    theme_groups: Dict[str, List[MappedIssue]],
    macro: MacroSnapshot,
    date: str,
    max_news_per_theme: int,
) -> List[NewsItem]:
    """테마별 병렬 분석."""
    tasks = [
        _analyze_theme(theme, issues, macro, date, max_news_per_theme)
        for theme, issues in theme_groups.items()
    ]
    return await asyncio.gather(*tasks)


async def _analyze_theme(
    theme: str,
    issues: List[MappedIssue],
    macro: MacroSnapshot,
    date: str,
    max_news: int,
) -> NewsItem:
    """단일 테마 분석."""
    # 1. 뉴스 검색
    news_articles = _search_news(theme, date, max_news)

    # 2. LLM 분석
    llm = LLMProvider.create(provider="openai", model="gpt-4o", temperature=0.3)

    # 프롬프트 구성
    issues_text = "\n\n".join([
        f"**{issue.title}**\n{issue.summary}\n"
        f"키워드: {', '.join(issue.keywords)}\n"
        f"감성: {issue.sentiment}"
        for issue in issues
    ])

    news_text = "\n\n".join([
        f"**{article['title']}**\n{article['body']}\n출처: {article['url']}"
        for article in news_articles
    ]) if news_articles else "관련 뉴스 없음"

    # prompts.py에서 프롬프트 가져오기
    system_prompt = REDUCE_SYSTEM_PROMPT
    user_prompt = REDUCE_USER_PROMPT.format(
        theme=theme,
        issues=issues_text,
        news_articles=news_text,
    )

    # LangSmith 태깅
    run_name = f"Reduce Stage - {date} - {theme[:30]}"
    config = {
        "run_name": run_name,
        "tags": ["daily_report", "reduce_stage", f"date:{date}", f"theme:{theme}"],
        "metadata": {
            "stage": "reduce",
            "date": date,
            "theme": theme,
            "issue_count": len(issues),
            "news_count": len(news_articles),
        },
    }

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    response = await llm.ainvoke(messages, config=config)

    # JSON 파싱
    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        data = json.loads(content)

        # StockDetail 변환
        stocks = [StockDetail(**stock) for stock in data.get("stocks", [])]

        return NewsItem(
            theme=data["theme"],
            emoji=data.get("emoji", "ℹ️"),
            summary=data["summary"],
            impact=data["impact"],
            stocks=stocks,
        )
    except Exception as e:
        print(f"⚠️  테마 '{theme}' 분석 실패: {e}")
        # fallback
        return NewsItem(
            theme=theme,
            emoji="ℹ️",
            summary=f"{theme} 관련 {len(issues)}개 이슈",
            impact="분석 실패",
            stocks=[],
        )


def _search_news(theme: str, date: str, max_results: int) -> List[Dict]:
    """DuckDuckGo로 뉴스 검색."""
    try:
        # 검색 키워드 구성 (한글 테마 + 영문 번역 필요시)
        query = f"{theme} 주식 시장"

        # 날짜 범위 (당일 ± 1일)
        date_obj = datetime.strptime(date, "%Y-%m-%d")

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
    shuffle_file = (
        f"tests/pipelines/daily_report/fixtures/stage_outputs/shuffle_{date}.json"
    )
    with open(shuffle_file, "r", encoding="utf-8") as f:
        shuffle_data = json.load(f)

    # theme_groups 복원
    theme_groups = {
        theme: [MappedIssue(**issue) for issue in issues]
        for theme, issues in shuffle_data["theme_groups"].items()
    }

    # Ingest stage에서 매크로 로드
    ingest_file = (
        f"tests/pipelines/daily_report/fixtures/stage_outputs/ingest_{date}.json"
    )
    with open(ingest_file, "r", encoding="utf-8") as f:
        ingest_data = json.load(f)
    macro = MacroSnapshot(**ingest_data["macro"])

    print(f"✓ {len(theme_groups)}개 테마 그룹 로드")

    # Reduce stage 실행
    news_items = reduce_stage(theme_groups, macro, date)

    print(f"✓ {len(news_items)}개 테마 분석")

    # 출력 저장
    output_file = (
        f"tests/pipelines/daily_report/fixtures/stage_outputs/reduce_{date}.json"
    )
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            [item.model_dump() for item in news_items],
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"✓ {output_file}에 저장")

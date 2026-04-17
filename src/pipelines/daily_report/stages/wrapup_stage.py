"""Wrapup stage: 전체 테마 종합 및 메타 인사이트 도출."""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.provider import LLMProvider


load_dotenv()
from langsmith import traceable

from src.pipelines.daily_report.models import DailyReport, KeyInsightsList, MacroSnapshot, NewsItem
from src.pipelines.daily_report.prompts import WRAPUP_SYSTEM_PROMPT, WRAPUP_USER_PROMPT


@traceable(name="Wrapup Stage")
def wrapup_stage(
    news_items: list[NewsItem],
    macro: MacroSnapshot,
    date: str = None,
) -> DailyReport:
    """
    전체 테마를 종합하여 일일 리포트 생성.

    Args:
        news_items: Reduce stage 출력 (테마별 분석)
        macro: 매크로 데이터
        date: 날짜 문자열

    Returns:
        최종 DailyReport
    """
    if not news_items:
        return DailyReport(
            date=date or macro.date,
            macro=macro,
            news=[],
            key_insights=[],
        )

    # LLM으로 메타 인사이트 도출
    loop = asyncio.get_event_loop()
    key_insights = loop.run_until_complete(_generate_insights(news_items, macro, date))

    return DailyReport(
        date=date or macro.date,
        macro=macro,
        news=news_items,
        key_insights=key_insights,
    )


async def _generate_insights(
    news_items: list[NewsItem],
    macro: MacroSnapshot,
    date: str,
) -> list[str]:
    """LLM으로 메타 인사이트 생성."""
    llm = LLMProvider.create(
        provider="anthropic", model="us.anthropic.claude-haiku-4-5-20251001-v1:0", temperature=0.4
    )

    # 프롬프트 구성
    news_text = "\n\n".join(
        [
            f"{item.emoji} **{item.theme}**\n{item.summary}\n**(Impact: {item.impact})**"
            for item in news_items
        ]
    )

    # prompts.py에서 프롬프트 가져오기
    system_prompt = WRAPUP_SYSTEM_PROMPT
    user_prompt = WRAPUP_USER_PROMPT.format(news_items=news_text)

    # LangSmith 태깅
    run_name = f"Wrapup Stage - {date}"
    config = {
        "run_name": run_name,
        "tags": ["daily_report", "wrapup_stage", f"date:{date}"],
        "metadata": {
            "stage": "wrapup",
            "date": date,
            "theme_count": len(news_items),
            "vix": macro.vix,
            "fear_greed": macro.fear_greed,
        },
    }

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        llm_with_output = llm.with_structured_output(KeyInsightsList)
        response = await llm_with_output.ainvoke(messages, config=config)
        return response.insights
    except Exception as e:
        print(f"⚠️  인사이트 생성 실패: {e}")
        return [
            f"총 {len(news_items)}개 테마 분석 완료",
            f"VIX: {macro.vix}, Fear & Greed: {macro.fear_greed}",
        ]


# 테스트용 CLI 진입점
if __name__ == "__main__":
    import sys

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-04-14"

    # Reduce stage 출력 로드
    reduce_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/reduce_{date}.json"
    with open(reduce_file, encoding="utf-8") as f:
        news_data = json.load(f)
    news_items = [NewsItem(**item) for item in news_data]

    # Ingest stage에서 매크로 로드
    ingest_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/ingest_{date}.json"
    with open(ingest_file, encoding="utf-8") as f:
        ingest_data = json.load(f)
    macro = MacroSnapshot(**ingest_data["macro"])

    print(f"✓ {len(news_items)}개 테마 분석 로드")

    # Wrapup stage 실행
    report = wrapup_stage(news_items, macro, date)

    print(f"✓ {len(report.key_insights)}개 핵심 인사이트 생성")
    print("\n핵심 인사이트:")
    for insight in report.key_insights:
        print(f"  - {insight}")

    # 출력 저장
    output_file = f"tests/pipelines/daily_report/fixtures/stage_outputs/wrapup_{date}.json"
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")

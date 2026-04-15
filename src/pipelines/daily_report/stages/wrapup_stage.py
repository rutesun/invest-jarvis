"""Wrapup stage: 전체 테마 종합 및 메타 인사이트 도출."""
import asyncio
import json
from typing import List
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from src.llm.provider import LLMProvider

load_dotenv()
from src.pipelines.daily_report.models import NewsItem, DailyReport, MacroSnapshot
from src.pipelines.daily_report.prompts import WRAPUP_PROMPT


def wrapup_stage(
    news_items: List[NewsItem],
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
    key_insights = loop.run_until_complete(
        _generate_insights(news_items, macro, date)
    )

    return DailyReport(
        date=date or macro.date,
        macro=macro,
        news=news_items,
        key_insights=key_insights,
    )


async def _generate_insights(
    news_items: List[NewsItem],
    macro: MacroSnapshot,
    date: str,
) -> List[str]:
    """LLM으로 메타 인사이트 생성."""
    llm = LLMProvider.create(provider="openai", model="gpt-4o", temperature=0.4)

    # 프롬프트 구성
    news_text = "\n\n".join([
        f"{item.emoji} **{item.theme}**\n{item.summary}\n"
        f"**(Impact: {item.impact})**"
        for item in news_items
    ])

    # System/User 메시지 분리 (캐싱 가능)
    system_prompt = """당신은 시장 전략가입니다.
여러 테마들을 종합하여 오늘의 핵심 시장 내러티브를 도출하세요.

**작성 지침**:
1. 한글로 작성
2. 여러 테마를 연결하는 메타 인사이트 3-5개 도출
3. 각 인사이트는 2-3줄로 간결하게
4. 이모지 활용 (🔥💡🌊⚠️ 등)
5. 단순 요약 금지 - 테마 간 연결과 시사점 도출

**출력 형식**: JSON array of strings
```json
[
  "🔥 AI 슈퍼사이클: 데이터센터 전력 인프라 + 반도체 메모리 업사이클 + 전력기기 수주 급증 → 통합 투자 테마 형성",
  "💡 공급망 리쇼어링: 미국 CHIPS Act + 한국 전력기기 수출 + 일본 소재 확대 → 비중국 밸류체인 재편 가속"
]
```"""

    user_prompt = f"""**테마별 분석**:
{news_text}

위 테마들을 종합하여 핵심 시장 내러티브를 도출하세요."""

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
    response = await llm.ainvoke(messages, config=config)

    # JSON 파싱
    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        insights = json.loads(content)
        return insights if isinstance(insights, list) else []
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
    reduce_file = (
        f"tests/pipelines/daily_report/fixtures/stage_outputs/reduce_{date}.json"
    )
    with open(reduce_file, "r", encoding="utf-8") as f:
        news_data = json.load(f)
    news_items = [NewsItem(**item) for item in news_data]

    # Ingest stage에서 매크로 로드
    ingest_file = (
        f"tests/pipelines/daily_report/fixtures/stage_outputs/ingest_{date}.json"
    )
    with open(ingest_file, "r", encoding="utf-8") as f:
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
    output_file = (
        f"tests/pipelines/daily_report/fixtures/stage_outputs/wrapup_{date}.json"
    )
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    print(f"✓ {output_file}에 저장")

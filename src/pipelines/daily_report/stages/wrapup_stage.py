"""Wrapup stage: 전체 테마 종합 및 인과관계 인사이트 도출."""

import json
import logging
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()
from langsmith import traceable

from src.pipelines.daily_report.config import WRAPUP_LLM
from src.pipelines.daily_report.examples.wrapup_examples import get_wrapup_examples
from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.daily_report.models import DailyReport, KeyInsightsList, MacroSnapshot, NewsItem
from src.pipelines.daily_report.prompts import (
    WRAPUP_SYSTEM_PROMPT_V3,
    WRAPUP_USER_PROMPT_V3,
)


logger = logging.getLogger(__name__)


def _build_news_text(news_items: list[NewsItem]) -> str:
    """테마별 분석을 Wrapup 입력 텍스트로 포맷팅.

    summary 전체 + impact 전체 + stocks 이름을 포함한다.
    """
    parts = []
    for item in news_items:
        section = (
            f"[{item.category}] {item.investment_theme}\n"
            f"(기술 테마: {item.technical_theme})\n"
            f"{item.summary}\n"
            f"Impact: {item.impact}"
        )
        if item.stocks:
            stock_names = ", ".join(s.name for s in item.stocks)
            section += f"\n종목: {stock_names}"
        parts.append(section)
    return "\n\n".join(parts)


@traceable(name="Wrapup Stage")
def wrapup_stage(
    news_items: list[NewsItem],
    macro: MacroSnapshot,
    date: str = None,
) -> DailyReport:
    """
    전체 시장 인사이트 도출 (테마 간 인과관계 체인 + 매크로 연결).

    Args:
        news_items: Reduce stage 출력 (테마별 분석)
        macro: 매크로 데이터
        date: 날짜 문자열

    Returns:
        DailyReport (key_insights + category_insights 포함)
    """
    import asyncio
    import time

    if not news_items:
        return DailyReport(
            date=date or macro.date, macro=macro, key_insights=["분석할 뉴스가 없습니다."], news=[]
        )

    start_time = time.time()

    logger.info("Wrapup stage started: %d news items to synthesize", len(news_items))

    report = asyncio.run(_wrapup_stage_async(news_items, macro, date))

    elapsed = time.time() - start_time

    logger.info(
        "Wrapup stage completed: %d key insights generated in %.1fs",
        len(report.key_insights),
        elapsed,
    )

    return report


async def _wrapup_stage_async(
    news_items: list[NewsItem],
    macro: MacroSnapshot,
    date: str = None,
) -> DailyReport:
    """Async implementation of wrapup stage."""
    llm = WRAPUP_LLM.create_llm()

    # 매크로 데이터 포맷팅
    macro_text = f"""VIX: {macro.vix}
Fear & Greed: {macro.fear_greed}
미국 시장: {", ".join(f"{k} {v:+.2f}%" for k, v in macro.us_markets.items())}
한국 시장: {", ".join(f"{k} {v:+.2f}%" for k, v in macro.kr_markets.items())}
KRW/USD: {macro.krw_usd}"""

    # 테마별 분석 포맷팅 (V3: summary 전체 + impact 전체 + stocks)
    news_text = _build_news_text(news_items)

    # V3 프롬프트 + examples 주입
    examples = get_wrapup_examples()
    system_prompt = WRAPUP_SYSTEM_PROMPT_V3.format(examples=examples)
    user_prompt = WRAPUP_USER_PROMPT_V3.format(
        macro=macro_text, news_count=len(news_items), news_items=news_text
    )

    run_name = f"Wrapup Stage - {date}"
    config = {
        "run_name": run_name,
        "tags": ["daily_report", "wrapup_stage", f"date:{date}"],
        "metadata": {
            "stage": "wrapup",
            "date": date,
            "theme_count": len(news_items),
        },
    }

    messages = WRAPUP_LLM.build_messages(system_prompt, user_prompt)

    try:
        response = await invoke_llm_with_retry(llm, KeyInsightsList, messages, config)
        key_insights = response.insights
    except Exception as e:
        logger.error("Wrapup stage failed: %s", e, exc_info=True)
        key_insights = ["전체 인사이트 도출 실패"]

    return DailyReport(
        date=date or macro.date,
        macro=macro,
        key_insights=key_insights,
        news=news_items,
    )


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

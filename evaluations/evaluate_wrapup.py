# evaluations/evaluate_wrapup.py
"""Wrapup stage V2 vs V3 평가 스크립트 (LLM-as-Judge).

Usage:
    uv run python evaluations/evaluate_wrapup.py
    uv run python evaluations/evaluate_wrapup.py --dates 2026-04-20
    uv run python evaluations/evaluate_wrapup.py --runs 5

Reduce fixture를 고정 입력으로 사용하여 Wrapup만 순수 비교.
Judge 모델: Anthropic Sonnet 4.5 (생성 Haiku 4.5와 다른 티어).
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from src.llm.provider import LLMProvider
from src.pipelines.daily_report.config import WRAPUP_LLM
from src.pipelines.daily_report.examples.wrapup_examples import get_wrapup_examples
from src.pipelines.daily_report.llm_utils import invoke_llm_with_retry
from src.pipelines.daily_report.models import (
    KeyInsightsList,
    MacroSnapshot,
    NewsItem,
)
from src.pipelines.daily_report.prompts import (
    WRAPUP_SYSTEM_PROMPT_V2,
    WRAPUP_SYSTEM_PROMPT_V3,
    WRAPUP_USER_PROMPT_V2,
    WRAPUP_USER_PROMPT_V3,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FIXTURE_DIR = Path("tests/pipelines/daily_report/fixtures/stage_outputs")


# ============================================================================
# Judge 모델
# ============================================================================

JUDGE_SYSTEM_PROMPT = """당신은 투자 리포트 품질 평가자입니다.
Daily report의 key_insights를 5개 차원으로 평가하세요.

**평가 차원 (각 0-2점, 총 0-10점)**:

| 차원 | 0점 | 1점 | 2점 |
|------|-----|-----|-----|
| chain_presence | 인과 체인(→) 없음 | 1단계만 | 2단계+ 체인 포함 |
| chain_validity | 논리적 비약 있음 | 일부 연결 약함 | 모든 연결 타당 |
| actionability | 투자 시사점 없음 | 모호한 시사점 | 구체적 섹터/종목 제시 |
| data_grounding | 숫자/팩트 없음 | 일부 포함 | 충분히 포함 |
| conciseness | 500자+ 덩어리 | 구조 있지만 장황 | 구조화 + 간결 |

JSON으로 응답하세요."""

JUDGE_USER_PROMPT = """**평가 대상 (key_insights)**:
{insights}

위 인사이트를 5개 차원으로 평가하세요."""


class JudgeScore(BaseModel):
    """Judge 채점 결과."""

    chain_presence: int = Field(ge=0, le=2)
    chain_validity: int = Field(ge=0, le=2)
    actionability: int = Field(ge=0, le=2)
    data_grounding: int = Field(ge=0, le=2)
    conciseness: int = Field(ge=0, le=2)
    reasoning: str = Field(description="채점 이유 (한 줄)")

    @property
    def total(self) -> int:
        return (
            self.chain_presence
            + self.chain_validity
            + self.actionability
            + self.data_grounding
            + self.conciseness
        )


# ============================================================================
# Wrapup 실행 (V2/V3)
# ============================================================================


def _build_news_text_v2(news_items: list[NewsItem]) -> str:
    """V2 포맷: summary[:100] 잘림."""
    return "\n\n".join(
        f"[{item.category}] {item.investment_theme}\n"
        f"(기술 테마: {item.technical_theme})\n"
        f"{item.emoji} {item.summary[:100]}..."
        for item in news_items
    )


def _build_news_text_v3(news_items: list[NewsItem]) -> str:
    """V3 포맷: summary 전체 + impact + stocks."""
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


def _build_macro_text(macro: MacroSnapshot) -> str:
    """매크로 데이터 포맷팅."""
    return (
        f"VIX: {macro.vix}\n"
        f"Fear & Greed: {macro.fear_greed}\n"
        f"미국 시장: {', '.join(f'{k} {v:+.2f}%' for k, v in macro.us_markets.items())}\n"
        f"한국 시장: {', '.join(f'{k} {v:+.2f}%' for k, v in macro.kr_markets.items())}\n"
        f"KRW/USD: {macro.krw_usd}"
    )


async def run_wrapup(
    version: str,
    news_items: list[NewsItem],
    macro: MacroSnapshot,
) -> list[str]:
    """Wrapup stage를 V2 또는 V3로 실행."""
    llm = WRAPUP_LLM.create_llm()
    macro_text = _build_macro_text(macro)

    if version == "v2":
        news_text = _build_news_text_v2(news_items)
        system_prompt = WRAPUP_SYSTEM_PROMPT_V2
        user_prompt = WRAPUP_USER_PROMPT_V2.format(
            macro=macro_text, news_count=len(news_items), news_items=news_text
        )
    else:
        news_text = _build_news_text_v3(news_items)
        examples = get_wrapup_examples()
        system_prompt = WRAPUP_SYSTEM_PROMPT_V3.format(examples=examples)
        user_prompt = WRAPUP_USER_PROMPT_V3.format(
            macro=macro_text, news_count=len(news_items), news_items=news_text
        )

    messages = WRAPUP_LLM.build_messages(system_prompt, user_prompt)
    config = {"run_name": f"Eval Wrapup {version}", "tags": ["evaluation"]}

    response = await invoke_llm_with_retry(llm, KeyInsightsList, messages, config)
    return response.insights


# ============================================================================
# Judge
# ============================================================================


async def judge_insights(insights: list[str]) -> JudgeScore:
    """LLM-as-Judge로 인사이트 채점."""
    judge_llm = LLMProvider.create(
        provider="anthropic",
        model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0,
    )

    insights_text = "\n\n".join(insights)
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=JUDGE_SYSTEM_PROMPT),
        HumanMessage(content=JUDGE_USER_PROMPT.format(insights=insights_text)),
    ]

    llm_with_output = judge_llm.with_structured_output(JudgeScore)
    return await asyncio.wait_for(
        llm_with_output.ainvoke(messages),
        timeout=60.0,
    )


# ============================================================================
# Main
# ============================================================================


def load_fixture(date: str) -> tuple[list[NewsItem], MacroSnapshot]:
    """Reduce + Ingest fixture 로드."""
    reduce_file = FIXTURE_DIR / f"reduce_{date}.json"
    ingest_file = FIXTURE_DIR / f"ingest_{date}.json"

    with open(reduce_file, encoding="utf-8") as f:
        news_data = json.load(f)
    with open(ingest_file, encoding="utf-8") as f:
        ingest_data = json.load(f)

    news_items = [NewsItem(**item) for item in news_data]
    macro = MacroSnapshot(**ingest_data["macro"])
    return news_items, macro


async def evaluate_date(date: str, runs: int) -> dict:
    """한 날짜에 대해 V2/V3 비교 평가."""
    news_items, macro = load_fixture(date)
    print(f"\n{'=' * 60}")
    print(f"📅 {date} ({len(news_items)} themes, {runs} runs)")
    print(f"{'=' * 60}")

    results = {"date": date, "v2": [], "v3": []}

    for run_idx in range(runs):
        print(f"\n  Run {run_idx + 1}/{runs}...")

        for version in ["v2", "v3"]:
            try:
                insights = await run_wrapup(version, news_items, macro)
                score = await judge_insights(insights)

                results[version].append(
                    {
                        "run": run_idx + 1,
                        "total": score.total,
                        "chain_presence": score.chain_presence,
                        "chain_validity": score.chain_validity,
                        "actionability": score.actionability,
                        "data_grounding": score.data_grounding,
                        "conciseness": score.conciseness,
                        "reasoning": score.reasoning,
                        "insights": insights,
                    }
                )

                print(f"    {version.upper()}: {score.total}/10 — {score.reasoning}")
            except Exception as e:
                print(f"    {version.upper()}: ERROR — {e}")
                results[version].append({"run": run_idx + 1, "total": 0, "error": str(e)})

    return results


def print_summary(all_results: list[dict]):
    """전체 요약 출력."""
    v2_scores = []
    v3_scores = []

    for result in all_results:
        for entry in result["v2"]:
            if "total" in entry and "error" not in entry:
                v2_scores.append(entry["total"])
        for entry in result["v3"]:
            if "total" in entry and "error" not in entry:
                v3_scores.append(entry["total"])

    v2_avg = sum(v2_scores) / len(v2_scores) if v2_scores else 0
    v3_avg = sum(v3_scores) / len(v3_scores) if v3_scores else 0

    print(f"\n{'=' * 60}")
    print("📊 EVALUATION SUMMARY")
    print(f"{'=' * 60}")
    print(f"  V2 average: {v2_avg:.1f}/10 ({len(v2_scores)} runs)")
    print(f"  V3 average: {v3_avg:.1f}/10 ({len(v3_scores)} runs)")
    print(f"  Delta: {v3_avg - v2_avg:+.1f}")
    print(f"  Target: V3 ≥ 7.0 ({'✅ PASS' if v3_avg >= 7.0 else '❌ FAIL'})")


async def main_async(dates: list[str], runs: int):
    """비동기 메인."""
    all_results = []
    for date in dates:
        result = await evaluate_date(date, runs)
        all_results.append(result)

    print_summary(all_results)

    # 결과 저장
    output_dir = Path("evaluations/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_file = output_dir / f"{timestamp}_wrapup_v2_vs_v3.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Results saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Wrapup V2 vs V3 평가")
    parser.add_argument(
        "--dates",
        default="2026-04-20",
        help="평가할 날짜 (쉼표 구분). reduce fixture 필요. 기본: 2026-04-20",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="날짜당 실행 횟수 (기본: 3)",
    )
    args = parser.parse_args()

    dates = [d.strip() for d in args.dates.split(",")]

    # fixture 존재 확인
    for date in dates:
        reduce_file = FIXTURE_DIR / f"reduce_{date}.json"
        ingest_file = FIXTURE_DIR / f"ingest_{date}.json"
        if not reduce_file.exists():
            print(f"❌ Reduce fixture 없음: {reduce_file}")
            return
        if not ingest_file.exists():
            print(f"❌ Ingest fixture 없음: {ingest_file}")
            return

        # NewsItem 포맷 확인 (category 필드 필요)
        with open(reduce_file, encoding="utf-8") as f:
            first_item = json.load(f)[0]
        if "category" not in first_item:
            print(f"⚠️  {date} fixture는 구버전 포맷 (category 없음). 2026-04-20 이후 사용 권장.")
            return

    print("🚀 Wrapup V2 vs V3 Evaluation")
    print(f"   Dates: {dates}")
    print(f"   Runs per date: {args.runs}")
    print("   Judge: Anthropic Sonnet 4.5")

    asyncio.run(main_async(dates, args.runs))


if __name__ == "__main__":
    main()

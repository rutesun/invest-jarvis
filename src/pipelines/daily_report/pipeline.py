"""Daily Report 전체 파이프라인 통합."""

from typing import Optional
from src.pipelines.daily_report.models import DailyReport
from src.pipelines.daily_report.stages.ingest_stage import ingest
from src.pipelines.daily_report.stages.map_stage import map_stage
from src.pipelines.daily_report.stages.shuffle_stage import shuffle_stage
from src.pipelines.daily_report.stages.reduce_stage import reduce_stage
from src.pipelines.daily_report.stages.wrapup_stage import wrapup_stage
from langsmith import traceable


@traceable
def run_pipeline(date: str, data_dir: str = "data") -> DailyReport:
    """
    전체 5단계 파이프라인 실행.

    Args:
        date: 날짜 문자열 (YYYY-MM-DD)
        data_dir: 데이터 디렉토리 경로

    Returns:
        최종 DailyReport

    Raises:
        FileNotFoundError: 텔레그램 데이터가 없을 때
    """
    # 1. Ingest: 텔레그램 메시지 + 매크로 로드
    print(f"[1/5] Ingest Stage...")
    ingest_result = ingest(date, data_dir)
    print(f"  ✓ {len(ingest_result.messages)}개 메시지 로드")

    # 2. Map: 이슈 추출
    print(f"[2/5] Map Stage...")
    issues = map_stage(ingest_result.messages, date)
    print(f"  ✓ {len(issues)}개 이슈 추출")

    # # 3. Shuffle: 테마 정규화
    # print(f"[3/5] Shuffle Stage...")
    # shuffle_result = shuffle_stage(issues, date)
    # print(f"  ✓ {len(shuffle_result.canonical_themes)}개 정규화 테마")

    # # 4. Reduce: 테마별 분석
    # print(f"[4/5] Reduce Stage...")
    # news_items = reduce_stage(
    #     shuffle_result.theme_groups,
    #     ingest_result.macro,
    #     date,
    # )
    # print(f"  ✓ {len(news_items)}개 테마 분석")

    # # 5. Wrapup: 최종 리포트
    # print(f"[5/5] Wrapup Stage...")
    # report = wrapup_stage(news_items, ingest_result.macro, date)
    # print(f"  ✓ {len(report.key_insights)}개 핵심 인사이트")

    return report


def format_report(report: DailyReport) -> str:
    """
    DailyReport를 Markdown으로 포맷팅.

    Args:
        report: 최종 리포트

    Returns:
        Markdown 문자열
    """
    output = f"# Daily Market Report - {report.date}\n\n"

    # 매크로 스냅샷
    output += "## 📊 Macro Snapshot\n\n"
    macro = report.macro
    output += f"- **VIX**: {macro.vix:.1f}\n"
    output += f"- **Fear & Greed Index**: {macro.fear_greed}\n"
    output += f"- **KRW/USD**: {macro.krw_usd:.1f}\n\n"

    output += "**US Markets**:\n"
    for market, change in macro.us_markets.items():
        output += f"- {market}: {change:+.2f}%\n"

    output += "\n**KR Markets**:\n"
    for market, change in macro.kr_markets.items():
        output += f"- {market}: {change:+.2f}%\n"

    output += "\n"

    # 핵심 인사이트
    output += "## 💡 Key Insights\n\n"
    for insight in report.key_insights:
        output += f"{insight}\n\n"

    # 테마별 분석
    output += "## 📰 Theme Analysis\n\n"
    for news_item in report.news:
        output += f"### {news_item.emoji} {news_item.theme}\n\n"
        output += f"{news_item.summary}\n\n"
        output += f"**Impact**: {news_item.impact}\n\n"

        if news_item.stocks:
            output += "**관련 종목**:\n"
            for stock in news_item.stocks:
                output += f"- **{stock.name}** ({stock.ticker}): {stock.catalyst}\n"
            output += "\n"

    return output


if __name__ == "__main__":
    report = run_pipeline("2026-04-14")
    print(format_report(report))

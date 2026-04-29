"""Daily Report 전체 파이프라인 통합."""

import csv
import logging
from pathlib import Path

from langsmith import get_current_run_tree, traceable

from src.pipelines.daily_report.models import DailyReport
from src.pipelines.daily_report.stages.ingest_stage import ingest
from src.pipelines.daily_report.stages.map_stage import map_stage
from src.pipelines.daily_report.stages.reduce_stage import reduce_stage
from src.pipelines.daily_report.stages.shuffle_stage import shuffle_stage
from src.pipelines.daily_report.stages.wrapup_stage import wrapup_stage


logger = logging.getLogger(__name__)


def _load_source_messages(source_ids: list[str], date: str, data_dir: str) -> dict[str, str]:
    """
    source_ids로 원본 메시지를 CSV에서 로드.

    Args:
        source_ids: "{channel_id}-{message_id}" 형식 리스트
        date: YYYY-MM-DD
        data_dir: 데이터 디렉토리

    Returns:
        {source_id: content} dict
    """
    messages = {}
    year_month = "-".join(date.split("-")[:2])  # YYYY-MM
    data_path = Path(data_dir) / year_month

    # 채널별로 그룹핑
    by_channel: dict[str, list[str]] = {}
    for source_id in source_ids:
        if "-" not in source_id:
            continue
        channel_id, msg_id = source_id.rsplit("-", 1)
        by_channel.setdefault(channel_id, []).append(msg_id)

    # 채널별 CSV 로드
    for channel_id, msg_ids in by_channel.items():
        csv_file = data_path / f"{date}-{channel_id}.csv"
        if not csv_file.exists():
            logger.warning("CSV not found: %s", csv_file)
            continue

        try:
            with open(csv_file, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["message_id"] in msg_ids:
                        source_id = f"{channel_id}-{row['message_id']}"
                        messages[source_id] = row.get("content", "")
        except Exception as e:
            logger.error("Failed to load CSV %s: %s", csv_file, e)

    return messages


def _extract_relevant_text(content: str, keywords: list[str], max_length: int = 300) -> str:
    """
    키워드와 관련된 부분을 발췌.

    Args:
        content: 원본 텍스트
        keywords: 검색 키워드 리스트
        max_length: 최대 발췌 길이

    Returns:
        발췌된 텍스트 (없으면 전체 반환)
    """
    if not content:
        return ""

    content_lower = content.lower()

    # 키워드가 등장하는 첫 위치 찾기
    first_match = None
    for keyword in keywords:
        keyword_lower = keyword.lower()
        pos = content_lower.find(keyword_lower)
        if pos != -1 and (first_match is None or pos < first_match):
            first_match = pos

    # 키워드 발견 시 그 주변 추출
    if first_match is not None:
        # 키워드 앞뒤로 max_length//2씩
        start = max(0, first_match - max_length // 2)
        end = min(len(content), first_match + max_length // 2)

        # 문장 경계로 자르기 (개행 또는 마침표)
        excerpt = content[start:end]

        # 앞에 ... 추가
        if start > 0:
            excerpt = "..." + excerpt.lstrip()

        # 뒤에 ... 추가
        if end < len(content):
            excerpt = excerpt.rstrip() + "..."

        return excerpt.strip()

    # 키워드 없으면 전체 반환
    return content


@traceable(name="Daily Report Pipeline")
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

    # 현재 실행 중인 트레이스(Run Tree)를 가져와서 런타임에 이름을 바꿀 수 있습니다.
    run_tree = get_current_run_tree()
    if run_tree:
        run_tree.name = f"Daily Report Generation - {date}"

    # 1. Ingest: 텔레그램 메시지 + 매크로 로드
    logger.info("[1/5] Ingest Stage...")
    ingest_result = ingest(date, data_dir)
    logger.info("  %d messages loaded", len(ingest_result.messages))

    # 2. Map: 이슈 추출
    logger.info("[2/5] Map Stage...")
    issues = map_stage(ingest_result.messages, date)
    logger.info("  %d issues extracted", len(issues))

    # 3. Shuffle: 카테고리 그룹핑 + 테마 정규화
    logger.info("[3/5] Shuffle Stage...")
    shuffle_result = shuffle_stage(issues, date)
    total_themes = sum(len(t) for t in shuffle_result.category_groups.values())
    logger.info("  %d categories, %d themes", len(shuffle_result.category_groups), total_themes)

    # 4. Reduce: 테마별 분석
    logger.info("[4/5] Reduce Stage...")
    news_items = reduce_stage(
        shuffle_result.category_groups,
        ingest_result.macro,
        date,
    )
    logger.info("  %d themes analyzed", len(news_items))

    # 5. Wrapup: 최종 리포트
    logger.info("[5/5] Wrapup Stage...")
    report = wrapup_stage(news_items, ingest_result.macro, date)
    logger.info("  %d key insights", len(report.key_insights))

    return report


def format_report(report: DailyReport, data_dir: str = "data") -> str:
    """
    DailyReport를 Markdown으로 포맷팅.

    Args:
        report: 최종 리포트
        data_dir: 데이터 디렉토리 (원본 메시지 로드용)

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

    # 테마별 분석 (카테고리별로 그룹핑)
    current_category = None
    for news_item in report.news:
        # 카테고리가 바뀌면 헤딩 추가
        if news_item.category != current_category:
            current_category = news_item.category
            output += f"## {current_category}\n\n"
            if report.category_insights and current_category in report.category_insights:
                output += f"> {report.category_insights[current_category]}\n\n"

        output += f"### {news_item.emoji} {news_item.investment_theme}\n\n"

        # Summary를 bullet list로 포맷팅
        summary_lines = news_item.summary.split("\n")
        for line in summary_lines:
            line = line.strip()
            if line:
                # 이미 bullet이 있으면 그대로, 없으면 추가
                if line.startswith("•") or line.startswith("-"):
                    output += f"{line}\n"
                else:
                    output += f"- {line}\n"
        output += "\n"

        output += f"**Impact**: {news_item.impact}\n\n"

        if news_item.stocks:
            output += "**관련 종목**:\n"
            for stock in news_item.stocks:
                output += f"- **{stock.name}** ({stock.ticker}): {stock.catalyst}\n"
            output += "\n"

        # 출처 (원본 메시지 발췌)
        if news_item.source_ids:
            source_messages = _load_source_messages(news_item.source_ids, report.date, data_dir)
            if source_messages:
                output += "**출처**:\n"
                for idx, (_source_id, content) in enumerate(source_messages.items(), 1):
                    excerpt = _extract_relevant_text(content, news_item.keywords, max_length=200)
                    if excerpt:
                        # 번호 리스트 (2칸 들여쓰기)
                        output += f"  {idx}. {excerpt}\n"
                output += "\n"

    return output


if __name__ == "__main__":
    report = run_pipeline("2026-04-14")
    print(format_report(report))

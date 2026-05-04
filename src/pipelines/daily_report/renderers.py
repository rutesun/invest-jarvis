"""Renderers for main brief, research dump, and ops report."""

import csv
import logging
from pathlib import Path

from src.pipelines.daily_report.models import DailyReport, OpsKnowledgeReport, ResearchDump


logger = logging.getLogger(__name__)


def _load_source_messages(source_ids: list[str], date: str, data_dir: str) -> dict[str, str]:
    messages: dict[str, str] = {}
    year_month = "-".join(date.split("-")[:2])
    data_path = Path(data_dir) / year_month

    by_channel: dict[str, list[str]] = {}
    for source_id in source_ids:
        if "-" not in source_id:
            continue
        channel_id, msg_id = source_id.rsplit("-", 1)
        by_channel.setdefault(channel_id, []).append(msg_id)

    for channel_id, msg_ids in by_channel.items():
        csv_file = data_path / f"{date}-{channel_id}.csv"
        if not csv_file.exists():
            continue

        try:
            with open(csv_file, encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if row["message_id"] in msg_ids:
                        source_id = f"{channel_id}-{row['message_id']}"
                        messages[source_id] = row.get("content") or row.get("text", "")
        except Exception as exc:
            logger.warning("Failed to load source csv %s: %s", csv_file, exc)

    return messages


def _extract_relevant_text(content: str, keywords: list[str], max_length: int = 300) -> str:
    if not content:
        return ""

    lowered = content.lower()
    first_match = None
    for keyword in keywords:
        pos = lowered.find(keyword.lower())
        if pos != -1 and (first_match is None or pos < first_match):
            first_match = pos

    if first_match is not None:
        start = max(0, first_match - max_length // 2)
        end = min(len(content), first_match + max_length // 2)
        excerpt = content[start:end]
        if start > 0:
            excerpt = "..." + excerpt.lstrip()
        if end < len(content):
            excerpt = excerpt.rstrip() + "..."
        return excerpt.strip()

    return content[:max_length].strip()


def _format_metric(value: float | int | None, fmt: str = ".1f") -> str:
    if value is None:
        return "N/A"
    return format(value, fmt)


def _format_change(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def render_main_report(report: DailyReport, data_dir: str = "data") -> str:
    output = f"# Daily Market Report - {report.date}\n\n"

    output += "## 📊 Macro Snapshot\n\n"
    macro = report.macro
    output += f"- **VIX**: {_format_metric(macro.vix)}\n"
    output += f"- **Fear & Greed Index**: {_format_metric(macro.fear_greed, 'd')}\n"
    output += f"- **KRW/USD**: {_format_metric(macro.krw_usd)}\n\n"

    output += "**US Markets**:\n"
    for market, change in macro.us_markets.items():
        output += f"- {market}: {_format_change(change)}\n"

    output += "\n**KR Markets**:\n"
    for market, change in macro.kr_markets.items():
        output += f"- {market}: {_format_change(change)}\n"

    output += "\n## 💡 Key Insights\n\n"
    for insight in report.key_insights:
        output += f"{insight}\n\n"

    current_category = None
    for news_item in report.news:
        if news_item.category != current_category:
            current_category = news_item.category
            output += f"## {current_category}\n\n"
            if report.category_insights and current_category in report.category_insights:
                output += f"> {report.category_insights[current_category]}\n\n"

        output += f"### {news_item.emoji} {news_item.investment_theme}\n\n"

        for line in news_item.summary.split("\n"):
            line = line.strip()
            if not line:
                continue
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

        if news_item.source_ids:
            source_messages = _load_source_messages(news_item.source_ids, report.date, data_dir)
            if source_messages:
                output += "**출처**:\n"
                for idx, (_source_id, content) in enumerate(source_messages.items(), 1):
                    excerpt = _extract_relevant_text(content, news_item.keywords, max_length=200)
                    if excerpt:
                        output += f"  {idx}. {excerpt}\n"
                output += "\n"

    return output


def render_research_dump(dump: ResearchDump) -> str:
    return dump.markdown


def render_ops_knowledge_report(report: OpsKnowledgeReport) -> str:
    return report.markdown

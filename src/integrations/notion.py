"""Notion API integration for Daily Report upload."""

import logging
import os
import re
from pathlib import Path
from typing import Any

from notion_client import Client

from src.pipelines.daily_report.models import DailyReport


logger = logging.getLogger(__name__)


def _parse_markdown_text(text: str) -> list[dict]:
    """Parse markdown text to Notion rich_text with annotations.

    Supports:
    - **bold**
    - *italic*
    - `code`

    Optimized for performance with large texts.
    """
    # Strip leading/trailing whitespace and newlines
    text = text.strip()

    if not text:
        return [{"type": "text", "text": {"content": ""}}]

    # 간단한 처리: **bold**만 지원 (성능 최적화)
    # 복잡한 정규식은 느리므로 split 방식 사용
    rich_text = []

    # **bold** 처리
    parts = text.split("**")
    for i, part in enumerate(parts):
        if not part:
            continue

        is_bold = i % 2 == 1  # 홀수 인덱스는 bold

        if is_bold:
            rich_text.append(
                {
                    "type": "text",
                    "text": {"content": part},
                    "annotations": {
                        "bold": True,
                        "italic": False,
                        "strikethrough": False,
                        "underline": False,
                        "code": False,
                        "color": "default",
                    },
                }
            )
        else:
            # Plain text
            rich_text.append({"type": "text", "text": {"content": part}})

    return rich_text if rich_text else [{"type": "text", "text": {"content": text}}]


def update_screener_report(result: dict[str, Any], date: str) -> str:
    """
    Upload Screener Report to Notion.

    Args:
        result: Screener pipeline result dictionary
        date: 날짜 (YYYY-MM-DD)

    Returns:
        생성된 Notion 페이지 URL

    Raises:
        ValueError: NOTION_TOKEN 또는 NOTION_DATABASE_ID가 설정되지 않았을 때
        Exception: Notion API 호출 실패 시

    Environment Variables:
        NOTION_TOKEN: Notion Integration Token (시작: secret_)
        NOTION_DATABASE_ID: Daily Report를 저장할 Database ID
    """
    # 환경 변수 확인
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")

    if not notion_token:
        raise ValueError(
            "NOTION_TOKEN이 설정되지 않았습니다. .env 파일에 NOTION_TOKEN=secret_xxx 추가하세요."
        )

    if not database_id:
        raise ValueError(
            "NOTION_DATABASE_ID가 설정되지 않았습니다. "
            ".env 파일에 NOTION_DATABASE_ID=xxx 추가하세요."
        )

    # Notion 클라이언트 초기화
    notion = Client(auth=notion_token)

    # 데이터 추출
    kr_leaders = result.get("kr_leaders", [])
    us_leaders = result.get("us_leaders", [])
    themes = result.get("themes", [])
    naver_themes = result.get("naver_themes", [])
    news = result.get("news", {})

    # 페이지 제목
    title = f"Screener - {date}"

    # 페이지 속성
    properties = {
        "이름": {"title": [{"text": {"content": title}}]},
        "Type": {"select": {"name": "Screener"}},
        "Date": {"date": {"start": date}},
    }

    # Optional properties (데이터가 있을 때만)
    if themes:
        properties["Top Theme"] = {
            "rich_text": [{"text": {"content": themes[0]["name"].replace(",", " ·")}}]
        }
        properties["Theme Count"] = {"number": len(themes)}
        top_theme_names = [t["name"].replace(",", " ·") for t in themes[:5]]
        properties["Top Themes"] = {"multi_select": [{"name": name} for name in top_theme_names]}

    if kr_leaders:
        properties["KR Leaders"] = {"number": len(kr_leaders)}

    if us_leaders:
        properties["US Leaders"] = {"number": len(us_leaders)}

    # 페이지 내용 구성
    children = []

    # 1. 네이버 테마 (토글)
    if naver_themes:
        naver_children = []
        headers = ["#", "테마명", "등락률"]
        rows = []
        for i, t in enumerate(naver_themes, 1):
            rows.append([str(i), t["name"], f"{t['change_rate']:+.2f}%"])

        # 5개씩 묶어서 표시
        for chunk_start in range(0, len(rows), 5):
            chunk = rows[chunk_start : chunk_start + 5]
            naver_children.append(_table(headers, chunk))

        children.append(_toggle(f"🎯 상위 테마 (네이버 {len(naver_themes)}개)", naver_children))
        children.append(_divider())

    # 2. 주도 테마 TOP 10
    if themes:
        children.append(_heading2("📈 주도 테마 TOP 10"))
        headers = ["#", "테마", "등락률", "종목수", "주요 종목"]
        rows = []
        for i, t in enumerate(themes[:10], 1):
            stocks_str = ", ".join(t["top_stocks"])
            rate = t.get("change_rate") or 0
            rows.append(
                [
                    str(i),
                    t["name"],
                    f"{rate:+.1f}%",
                    str(t["stock_count"]),
                    stocks_str,
                ]
            )
        children.append(_table(headers, rows))
        children.append(_divider())

    # 3. 주도주 TOP 50 (한국) - 토글
    if kr_leaders:
        kr_children = []
        headers = [
            "#",
            "종목",
            "시장",
            "모멘텀",
            "당일외인",
            "당일기관",
            "10일외인",
            "10일기관",
            "거래량",
            "소스",
        ]
        rows = []

        for i, item in enumerate(kr_leaders[:50], 1):
            s = item.stock
            sources_str = ",".join(s.sources)
            daily_f = _format_net(item.daily_foreign)
            daily_i = _format_net(item.daily_institution)
            ten_f = f"{item.foreign_days_count}/10 ({_format_net(item.foreign_net)})"
            ten_i = f"{item.institution_days_count}/10 ({_format_net(item.institution_net)})"

            rows.append(
                [
                    str(i),
                    s.name,
                    s.market,
                    f"{item.momentum_total:.0f}",
                    daily_f,
                    daily_i,
                    ten_f,
                    ten_i,
                    f"{item.vol_ratio:.1f}x",
                    sources_str,
                ]
            )

        # 10개씩 묶어서 표시
        for chunk_start in range(0, len(rows), 10):
            chunk = rows[chunk_start : chunk_start + 10]
            kr_children.append(_table(headers, chunk))

        children.append(_toggle("🇰🇷 주도주 TOP 50 (한국)", kr_children))
        children.append(_divider())

    # 4. 주도주 TOP 50 (미국) - 토글
    if us_leaders:
        us_children = []
        headers = ["#", "티커", "종목명", "시장", "모멘텀", "거래량", "소스"]
        rows = []

        for i, item in enumerate(us_leaders[:50], 1):
            s = item.stock
            sources_str = ",".join(s.sources)
            rows.append(
                [
                    str(i),
                    s.ticker,
                    s.name,
                    s.market,
                    f"{item.momentum_total:.0f}",
                    f"{item.vol_ratio:.1f}x",
                    sources_str,
                ]
            )

        # 10개씩 묶어서 표시
        for chunk_start in range(0, len(rows), 10):
            chunk = rows[chunk_start : chunk_start + 10]
            us_children.append(_table(headers, chunk))

        children.append(_toggle("🇺🇸 주도주 TOP 50 (미국)", us_children))
        children.append(_divider())

    # 5. 상위 종목 뉴스 (토글)
    if news:
        news_children = []
        for name, articles in news.items():
            stock_children = []
            for a in articles:
                stock_children.append(_paragraph(f"• {a['title']} ({a['published']})"))
            news_children.append(_toggle(name, stock_children))

        children.append(_toggle(f"📰 상위 종목 뉴스 ({len(news)}개)", news_children))

    # 페이지 생성 (children 없이)
    try:
        response = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties,
        )
        page_id = response["id"]
        page_url = response["url"]

        # 블록 추가 (100개씩)
        if children:
            _append_blocks_in_batches(notion, page_id, children)

        return page_url

    except Exception as e:
        raise Exception(f"Notion 페이지 생성 실패: {str(e)}") from e


def _format_net(value: int) -> str:
    """Format net buy quantity with sign and unit."""
    if value == 0:
        return "-"

    abs_val = abs(value)
    sign = "+" if value > 0 else ""

    if abs_val >= 1_000_000:
        return f"{sign}{value / 1_000_000:.1f}M"
    elif abs_val >= 1_000:
        return f"{sign}{value // 1_000}K"
    else:
        return f"{sign}{value}"


def _append_blocks_in_batches(
    notion: Client, block_id: str, children: list[dict], batch_size: int = 100
):
    """Append blocks in batches to avoid 100 children limit."""
    for i in range(0, len(children), batch_size):
        batch = children[i : i + batch_size]
        notion.blocks.children.append(block_id=block_id, children=batch)


def _load_source_excerpts(
    source_ids: list[str],
    keywords: list[str],
    date: str,
    data_dir: str = "data",
    cache: dict = None,
) -> list[str]:
    """Load source message excerpts for Notion display.

    Args:
        cache: CSV 캐시 딕셔너리 (성능 최적화)
    """
    from src.pipelines.daily_report.renderers import _extract_relevant_text, _load_source_messages

    # 캐시가 없으면 새로 로드
    if cache is None:
        source_messages = _load_source_messages(source_ids, date, data_dir)
    else:
        # 캐시에서 가져오기
        source_messages = {sid: cache.get(sid, "") for sid in source_ids if sid in cache}

    excerpts = []
    for _source_id, content in source_messages.items():
        if not content:
            continue
        excerpt = _extract_relevant_text(content, keywords, max_length=200)
        if excerpt:
            excerpts.append(excerpt)
    return excerpts


def update_daily_report(report: DailyReport, date: str, data_dir: str = "data") -> str:
    """
    Upload Daily Report to Notion.

    Args:
        report: DailyReport 객체
        date: 날짜 (YYYY-MM-DD)

    Returns:
        생성된 Notion 페이지 URL

    Raises:
        ValueError: NOTION_TOKEN 또는 NOTION_DATABASE_ID가 설정되지 않았을 때
        Exception: Notion API 호출 실패 시

    Environment Variables:
        NOTION_TOKEN: Notion Integration Token (시작: secret_)
        NOTION_DATABASE_ID: Daily Report를 저장할 Database ID
    """
    # 환경 변수 확인
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")

    if not notion_token:
        raise ValueError(
            "NOTION_TOKEN이 설정되지 않았습니다. .env 파일에 NOTION_TOKEN=secret_xxx 추가하세요."
        )

    if not database_id:
        raise ValueError(
            "NOTION_DATABASE_ID가 설정되지 않았습니다. "
            ".env 파일에 NOTION_DATABASE_ID=xxx 추가하세요."
        )

    # Notion 클라이언트 초기화
    notion = Client(auth=notion_token)

    # 페이지 제목
    title = f"Daily Market Report - {date}"

    # 페이지 속성 (Database에 맞게 조정 필요)
    properties = {
        "이름": {"title": [{"text": {"content": title}}]},
        "Type": {"select": {"name": "Daily"}},
        "Date": {"date": {"start": date}},
        "VIX": {"number": report.macro.vix},
        "Fear & Greed": {"number": report.macro.fear_greed},
        "KRW/USD": {"number": report.macro.krw_usd},
        "Insights Count": {"number": len(report.key_insights)},
    }

    # Top Themes 추출 (상위 5개, 쉼표 제거)
    if report.news:
        top_themes = [
            news_item.investment_theme.replace(",", " ·") for news_item in report.news[:5]
        ]
        properties["Top Themes"] = {"multi_select": [{"name": theme} for theme in top_themes]}

    # 페이지 내용 구성
    children = []

    # 1. 매크로 스냅샷
    children.append(_heading2("📊 Macro Snapshot"))
    children.append(
        _paragraph(
            f"**VIX**: {report.macro.vix:.1f} | "
            f"**Fear & Greed**: {report.macro.fear_greed} | "
            f"**KRW/USD**: {report.macro.krw_usd:.1f}"
        )
    )

    # US Markets
    us_markets_text = " | ".join([f"{k}: {v:+.2f}%" for k, v in report.macro.us_markets.items()])
    children.append(_paragraph(f"🇺🇸 **US Markets**: {us_markets_text}"))

    # KR Markets
    kr_markets_text = " | ".join([f"{k}: {v:+.2f}%" for k, v in report.macro.kr_markets.items()])
    children.append(_paragraph(f"🇰🇷 **KR Markets**: {kr_markets_text}"))

    children.append(_divider())

    # 2. 핵심 인사이트
    children.append(_heading2("💡 Key Insights"))
    for insight in report.key_insights:
        children.append(_callout(insight, "💡"))

    children.append(_divider())

    # 3. 테마별 분석 (카테고리로 그룹핑)
    children.append(_heading2("📰 Theme Analysis"))

    # CSV 캐시 생성 (한 번만 로드)
    logger.info(f"Loading CSV cache for {len(report.news)} themes...")
    csv_cache = {}
    all_source_ids = set()
    for news_item in report.news:
        all_source_ids.update(news_item.source_ids)

    if all_source_ids:
        from src.pipelines.daily_report.renderers import _load_source_messages

        csv_cache = _load_source_messages(list(all_source_ids), date, data_dir)
        logger.info(f"CSV cache loaded: {len(csv_cache)} messages")

    # 카테고리별로 그룹핑
    from collections import defaultdict

    category_groups = defaultdict(list)
    for news_item in report.news:
        category_groups[news_item.category].append(news_item)

    # 카테고리 정렬 (매크로, 정책/규제 우선, 나머지는 알파벳 순서)
    priority_categories = ["매크로", "정책/규제"]
    sorted_categories = []

    # 우선순위 카테고리 먼저
    for cat in priority_categories:
        if cat in category_groups:
            sorted_categories.append(cat)

    # 나머지 카테고리 (알파벳 순)
    remaining = sorted([cat for cat in category_groups if cat not in priority_categories])
    sorted_categories.extend(remaining)

    # 카테고리별로 렌더링
    total_themes = 0
    for category in sorted_categories:
        items = category_groups[category]
        # 카테고리 헤딩
        children.append(_heading2(f"📂 {category}"))

        # 해당 카테고리의 테마들
        for news_item in items:
            total_themes += 1
            logger.info(
                f"Processing theme {total_themes}/{len(report.news)}: {news_item.investment_theme[:50]}..."
            )

            # 테마 제목 (Heading 3, 접히지 않음)
            children.append(_heading3(f"{news_item.emoji} {news_item.investment_theme}"))

            # 요약 (bullet points, 접히지 않음)
            # summary는 "• bullet1 • bullet2" 형태이거나 "bullet1\nbullet2" 형태일 수 있음
            summary_text = news_item.summary.strip()

            # 먼저 실제 newline으로 split 시도
            lines = [line.strip() for line in summary_text.split("\n") if line.strip()]

            # 한 줄만 있으면 escaped 백슬래시-n으로 split 시도
            if len(lines) == 1:
                lines = [line.strip() for line in summary_text.split(r"\n") if line.strip()]

            # 여전히 한 줄이면 "•"로 split 시도
            if len(lines) == 1:
                bullets = [b.strip() for b in summary_text.split("•") if b.strip()]
            else:
                bullets = lines

            for bullet in bullets:
                # 앞의 이모지 제거 (🚀, 📈, ⚡, 💡 등)
                clean_bullet = re.sub(
                    r"^[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]\s*", "", bullet
                )
                children.append(_bullet_item(clean_bullet))

            # Impact & 관련 종목 (Toggle)
            impact_children = []
            impact_children.append(_callout(f"**Impact**: {news_item.impact}", "📊"))

            if news_item.stocks:
                impact_children.append(_paragraph("**관련 종목**:"))
                for stock in news_item.stocks[:5]:
                    impact_children.append(
                        _bullet_item(f"**{stock.name}** ({stock.ticker}): {stock.catalyst}")
                    )

            children.append(_toggle("📊 Impact & 관련 종목", impact_children))

            # 출처 (Toggle, 캐시 사용)
            if news_item.source_ids:
                excerpts = _load_source_excerpts(
                    news_item.source_ids, news_item.keywords, date, data_dir, cache=csv_cache
                )
                if excerpts:
                    source_children = []
                    for idx_src, excerpt in enumerate(excerpts, 1):
                        source_children.append(_paragraph(f"{idx_src}. {excerpt}"))
                    children.append(_toggle("📎 출처", source_children))

            # 테마 간 구분선
            children.append(_divider())

        # 카테고리 간 구분선 (더 명확하게)
        children.append(_divider())

    # 페이지 생성 (children 없이)
    try:
        response = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties,
        )
        page_id = response["id"]
        page_url = response["url"]

        # 블록 추가 (100개씩)
        if children:
            _append_blocks_in_batches(notion, page_id, children)

        return page_url

    except Exception as e:
        raise Exception(f"Notion 페이지 생성 실패: {str(e)}") from e


# ==================== Notion Block Builders ====================


def _heading2(text: str, max_length: int = 1900) -> dict:
    """Heading 2 블록 생성."""
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": _parse_markdown_text(text),
        },
    }


def _heading3(text: str, max_length: int = 1900) -> dict:
    """Heading 3 블록 생성."""
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": _parse_markdown_text(text),
        },
    }


def _paragraph(text: str, max_length: int = 1900) -> dict:
    """Paragraph 블록 생성.

    Notion API 제한: rich_text는 2000자까지만 허용.
    긴 텍스트는 자동으로 잘림 (여유를 위해 1900자로 제한).
    """
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": _parse_markdown_text(text),
        },
    }


def _callout(text: str, emoji: str = "💡", max_length: int = 1900) -> dict:
    """Callout 블록 생성.

    Notion API 제한: rich_text는 2000자까지만 허용 (여유를 위해 1900자로 제한).
    """
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": _parse_markdown_text(text),
        },
    }


def _bullet_item(text: str, max_length: int = 1900) -> dict:
    """Bulleted list item 블록 생성.

    Notion API 제한: rich_text는 2000자까지만 허용 (여유를 위해 1900자로 제한).
    """
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": _parse_markdown_text(text),
        },
    }


def _divider() -> dict:
    """Divider 블록 생성."""
    return {
        "object": "block",
        "type": "divider",
        "divider": {},
    }


def _toggle(title: str, children: list[dict], max_length: int = 1900) -> dict:
    """Toggle 블록 생성 (접을 수 있는 블록).

    Notion API 제한: rich_text는 2000자까지만 허용 (여유를 위해 1900자로 제한).
    """
    if len(title) > max_length:
        title = title[: max_length - 3] + "..."

    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": _parse_markdown_text(title),
            "children": children,
        },
    }


def upload_report_from_file(file_path: Path, date: str) -> str:
    """
    Upload report from MD file to Notion.

    Args:
        file_path: Path to MD file
        date: Date string (YYYY-MM-DD)

    Returns:
        Created Notion page URL
    """
    # 환경 변수 확인
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")

    if not notion_token or not database_id:
        raise ValueError("NOTION_TOKEN and NOTION_DATABASE_ID must be set")

    notion = Client(auth=notion_token)

    # 파일명으로 타입 판단
    filename = file_path.stem
    if filename.startswith("daily_"):
        report_type = "Daily"
        title = f"Daily Report - {date}"
    elif filename.startswith("screen-"):
        report_type = "Screener"
        title = f"Screener - {date}"
    else:
        raise ValueError(f"Unknown report type: {filename}")

    # MD 파일 읽기
    content = file_path.read_text(encoding="utf-8")

    # 간단한 MD → Notion blocks 변환
    children = _markdown_to_blocks(content)

    # Properties
    properties = {
        "이름": {"title": [{"text": {"content": title}}]},
        "Type": {"select": {"name": report_type}},
        "Date": {"date": {"start": date}},
    }

    # 페이지 생성 (children 없이)
    try:
        response = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties,
        )
        page_id = response["id"]
        page_url = response["url"]

        # 블록 추가 (100개씩)
        if children:
            _append_blocks_in_batches(notion, page_id, children)

        return page_url
    except Exception as e:
        raise Exception(f"Notion page creation failed: {str(e)}") from e


def _markdown_to_blocks(content: str) -> list[dict]:
    """Convert simple markdown to Notion blocks."""
    blocks = []
    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Heading 1
        if line.startswith("# "):
            blocks.append(_heading2(line[2:].strip()))
            i += 1

        # Heading 2
        elif line.startswith("## "):
            blocks.append(_heading2(line[3:].strip()))
            i += 1

        # Heading 3
        elif line.startswith("### "):
            blocks.append(_heading3(line[4:].strip()))
            i += 1

        # Table
        elif line.startswith("|") and i + 1 < len(lines) and lines[i + 1].startswith("|"):
            # Parse table
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1

            if len(table_lines) >= 3:  # Header + separator + data
                headers = [cell.strip() for cell in table_lines[0].split("|")[1:-1]]
                rows = []
                for row_line in table_lines[2:]:  # Skip separator
                    cells = [cell.strip() for cell in row_line.split("|")[1:-1]]
                    if cells:
                        rows.append(cells)
                if headers and rows:
                    blocks.append(_table(headers, rows))
            continue

        # Divider
        elif line.strip() in ["---", "***", "___"]:
            blocks.append(_divider())
            i += 1

        # Empty line
        elif not line.strip():
            i += 1

        # Paragraph
        else:
            # Collect consecutive non-empty lines as single paragraph
            para_lines = []
            while (
                i < len(lines)
                and lines[i].strip()
                and not lines[i].startswith("#")
                and not lines[i].startswith("|")
            ):
                para_lines.append(lines[i].strip())
                i += 1
            if para_lines:
                blocks.append(_paragraph(" ".join(para_lines)))

    return blocks


def _table(headers: list[str], rows: list[list[str]]) -> dict:
    """Table 블록 생성."""
    # Notion table은 has_column_header + table_rows로 구성
    table_rows = []

    # Header row
    header_cells = [[{"type": "text", "text": {"content": h}}] for h in headers]
    table_rows.append(
        {
            "type": "table_row",
            "table_row": {"cells": header_cells},
        }
    )

    # Data rows
    for row in rows:
        cells = [[{"type": "text", "text": {"content": str(cell)}}] for cell in row]
        table_rows.append(
            {
                "type": "table_row",
                "table_row": {"cells": cells},
            }
        )

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": len(headers),
            "has_column_header": True,
            "children": table_rows,
        },
    }

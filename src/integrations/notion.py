"""Notion API integration for Daily Report upload."""

import os
from typing import Optional
from notion_client import Client
from src.pipelines.daily_report.models import DailyReport


def update_daily_report(report: DailyReport, date: str) -> str:
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
            "NOTION_TOKEN이 설정되지 않았습니다. "
            ".env 파일에 NOTION_TOKEN=secret_xxx 추가하세요."
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
        "Name": {"title": [{"text": {"content": title}}]},
        "Date": {"date": {"start": date}},
        "VIX": {"number": report.macro.vix},
        "Fear & Greed": {"number": report.macro.fear_greed},
    }

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
    us_markets_text = " | ".join(
        [f"{k}: {v:+.2f}%" for k, v in report.macro.us_markets.items()]
    )
    children.append(_paragraph(f"🇺🇸 **US Markets**: {us_markets_text}"))

    # KR Markets
    kr_markets_text = " | ".join(
        [f"{k}: {v:+.2f}%" for k, v in report.macro.kr_markets.items()]
    )
    children.append(_paragraph(f"🇰🇷 **KR Markets**: {kr_markets_text}"))

    children.append(_divider())

    # 2. 핵심 인사이트
    children.append(_heading2("💡 Key Insights"))
    for insight in report.key_insights:
        children.append(_callout(insight, "💡"))

    children.append(_divider())

    # 3. 테마별 분석 (상위 10개만)
    children.append(_heading2("📰 Theme Analysis"))
    for news_item in report.news[:10]:
        # 테마 제목
        children.append(_heading3(f"{news_item.emoji} {news_item.theme}"))

        # 요약
        children.append(_paragraph(news_item.summary))

        # Impact
        children.append(_callout(f"**Impact**: {news_item.impact}", "📊"))

        # 관련 종목 (상위 5개)
        if news_item.stocks:
            children.append(_paragraph("**관련 종목**:"))
            for stock in news_item.stocks[:5]:
                children.append(
                    _bullet_item(
                        f"**{stock.name}** ({stock.ticker}): {stock.catalyst}"
                    )
                )

        children.append(_divider())

    # 페이지 생성
    try:
        response = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            children=children,
        )
        page_url = response["url"]
        return page_url

    except Exception as e:
        raise Exception(f"Notion 페이지 생성 실패: {str(e)}")


# ==================== Notion Block Builders ====================


def _heading2(text: str) -> dict:
    """Heading 2 블록 생성."""
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _heading3(text: str) -> dict:
    """Heading 3 블록 생성."""
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _paragraph(text: str) -> dict:
    """Paragraph 블록 생성."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _callout(text: str, emoji: str = "💡") -> dict:
    """Callout 블록 생성."""
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _bullet_item(text: str) -> dict:
    """Bulleted list item 블록 생성."""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _divider() -> dict:
    """Divider 블록 생성."""
    return {
        "object": "block",
        "type": "divider",
        "divider": {},
    }

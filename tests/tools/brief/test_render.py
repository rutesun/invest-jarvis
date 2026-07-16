"""render_markdown — 규칙 원문 fallback 포함 마크다운 조립 검증."""

from datetime import datetime

from src.tools.brief.models import (
    BUCKET_BUY_ELIGIBLE,
    BUCKET_HOLD_OK,
    BUCKET_REDUCE,
    BriefItem,
)
from src.tools.brief.render import render_markdown


def _items():
    return [
        BriefItem(
            ticker="NVDA",
            kind="watch",
            action="eligible",
            bucket=BUCKET_BUY_ELIGIBLE,
            price=165.2,
            change_pct=1.2,
        ),
        BriefItem(
            ticker="005930",
            kind="holding",
            action="reduce",
            bucket=BUCKET_REDUCE,
            price=71200.0,
            change_pct=-1.1,
            markers=["스탑 근접"],
        ),
        BriefItem(
            ticker="AAPL",
            kind="holding",
            action="hold",
            bucket=BUCKET_HOLD_OK,
            price=210.0,
            change_pct=0.3,
        ),
    ]


def test_render_contains_sections_and_top3():
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=_items())
    assert "# Daily Brief — 2026-07-14" in md
    assert "## ⚡ 오늘의 액션" in md
    assert "## 보유" in md
    assert "## 워치리스트" in md
    # Top-3에 랭킹 순서대로 (입력이 이미 정렬됨)
    action_section = md.split("## ⚡ 오늘의 액션")[1].split("## 보유")[0]
    assert action_section.index("NVDA") < action_section.index("005930")


def test_render_all_items_present_no_omission():
    """전 종목 누락 없음 — 스펙 D5."""
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=_items())
    for ticker in ("NVDA", "005930", "AAPL"):
        assert md.count(ticker) >= 2  # Top-N 또는 상세 섹션 + 헤더


def test_render_marker_shown():
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=_items())
    assert "스탑 근접" in md


def test_render_error_item():
    items = [
        BriefItem(
            ticker="FAIL",
            kind="watch",
            action="error",
            bucket=BUCKET_HOLD_OK,
            error="기술분석 실패: timeout",
        )
    ]
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=items)
    assert "데이터 조회 실패" in md
    assert "timeout" in md


def test_render_empty_items():
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=[])
    assert "설정된 종목 없음" in md

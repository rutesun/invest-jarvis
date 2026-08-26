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


def test_render_markdown_shows_technical_verdict_reason():
    item = BriefItem(
        ticker="AAPL",
        kind="holding",
        action="hold",
        bucket=BUCKET_HOLD_OK,
        price=210.0,
        change_pct=0.3,
        technical_verdict={
            "action": "hold",
            "reasons": ["상승 추세 유지"],
            "cautions": ["단기 과열"],
            "score_trend_summary": "최근 5거래일 adjusted score 둔화",
        },
        score_history=[
            {
                "date": "2026-07-16",
                "close": 100.0,
                "component_raw_total": 80,
                "adjusted_score": 62,
                "verdict_action": "hold",
                "one_line_reason": "단기 과열",
            }
        ],
    )

    output = render_markdown(datetime(2026, 7, 16), None, [item])

    assert "hold" in output
    assert "상승 추세 유지" in output
    assert "주의: 단기 과열" in output
    assert "최근 5거래일" in output


def test_render_markdown_shows_technical_verdict_action_without_details():
    item = BriefItem(
        ticker="AAPL",
        kind="holding",
        action="hold",
        bucket=BUCKET_HOLD_OK,
        price=210.0,
        change_pct=0.3,
        technical_verdict={"action": "watch"},
    )

    output = render_markdown(datetime(2026, 7, 16), None, [item])

    assert "- **기술 Verdict**: watch" in output


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


def test_render_shows_name_with_ticker():
    """종목명이 있으면 헤더와 Top-N에 '종목명 (코드)'로 표기."""
    item = BriefItem(
        ticker="005930",
        kind="holding",
        name="삼성전자",
        action="reduce",
        bucket=BUCKET_REDUCE,
        price=71200.0,
        change_pct=-1.1,
    )
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=[item])
    assert "삼성전자 (005930)" in md
    assert "### 삼성전자 (005930) — 비중축소" in md


def test_render_falls_back_to_ticker_without_name():
    item = BriefItem(
        ticker="005930",
        kind="holding",
        action="reduce",
        bucket=BUCKET_REDUCE,
        price=71200.0,
        change_pct=-1.1,
    )
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=[item])
    assert "### 005930 — 비중축소" in md
    assert "(005930)" not in md


def test_render_empty_items():
    md = render_markdown(datetime(2026, 7, 14), macro=None, items=[])
    assert "설정된 종목 없음" in md


def test_render_shows_turnaround_line():
    """BriefItem.turnaround가 있으면 상세 섹션에 노출."""
    items = [
        BriefItem(
            ticker="066970",
            kind="watch",
            action="eligible",
            bucket=BUCKET_BUY_ELIGIBLE,
            price=121600.0,
            change_pct=2.1,
            turnaround="턴어라운드 3/4 · [거래량 수반 양봉 · 저점 높이기] · check 확인됨(추세 on) · ★후보",
        ),
    ]
    md = render_markdown(datetime(2026, 8, 25), macro=None, items=items)
    assert "턴어라운드 3/4" in md
    assert "저점 높이기" in md

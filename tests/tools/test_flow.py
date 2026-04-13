# tests/tools/test_flow.py
import pytest
from unittest.mock import AsyncMock
from src.tools.flow import InvestorFlowEntry, InvestorFlow, FlowTool
from src.core.models import ToolResult


# 10일치 샘플 데이터 (최신일이 index 0)
SAMPLE_10D = [
    {"date": "20260411", "foreign_net":  500, "institution_net":  300, "total_net":  800},
    {"date": "20260410", "foreign_net": -200, "institution_net":  100, "total_net": -100},
    {"date": "20260409", "foreign_net":  300, "institution_net": -150, "total_net":  150},
    {"date": "20260408", "foreign_net":  400, "institution_net":  200, "total_net":  600},
    {"date": "20260407", "foreign_net": -100, "institution_net": -200, "total_net": -300},
    {"date": "20260404", "foreign_net":  200, "institution_net":  100, "total_net":  300},
    {"date": "20260403", "foreign_net": -300, "institution_net":  250, "total_net":  -50},
    {"date": "20260402", "foreign_net":  150, "institution_net": -100, "total_net":   50},
    {"date": "20260401", "foreign_net":  100, "institution_net":  200, "total_net":  300},
    {"date": "20260331", "foreign_net": -400, "institution_net": -300, "total_net": -700},
]


def test_investor_flow_entry_creation():
    entry = InvestorFlowEntry(date="2026-04-11", foreign_net=320, institution_net=850)
    assert entry.foreign_net == 320
    assert entry.institution_net == 850


def _make_flow(raw: list[dict]) -> InvestorFlow:
    entries = [
        InvestorFlowEntry(
            date=f"{d['date'][:4]}-{d['date'][4:6]}-{d['date'][6:]}",
            foreign_net=d["foreign_net"],
            institution_net=d["institution_net"],
        )
        for d in raw
    ]
    return InvestorFlow(code="005930", entries=entries)


# ── 1일 방향 ──────────────────────────────────────────────────────────────────

def test_foreign_direction_1d_buy():
    flow = _make_flow(SAMPLE_10D)
    # 최신일(index 0) foreign_net=500 → 매수
    assert flow.foreign_direction_1d == "매수"


def test_institution_direction_1d_buy():
    flow = _make_flow(SAMPLE_10D)
    # 최신일(index 0) institution_net=300 → 매수
    assert flow.institution_direction_1d == "매수"


# ── 5일 방향 ──────────────────────────────────────────────────────────────────

def test_foreign_direction_5d():
    flow = _make_flow(SAMPLE_10D)
    # 최근 5일: 500, -200, 300, 400, -100 → 순매수 3일, 순매도 2일 → 매수
    assert flow.foreign_direction_5d == "매수"


def test_institution_direction_5d():
    flow = _make_flow(SAMPLE_10D)
    # 최근 5일: 300, 100, -150, 200, -200 → 순매수 3일, 순매도 2일 → 매수
    assert flow.institution_direction_5d == "매수"


# ── 10일 방향 ─────────────────────────────────────────────────────────────────

def test_foreign_direction_10d():
    flow = _make_flow(SAMPLE_10D)
    # 10일: 500,-200,300,400,-100,200,-300,150,100,-400
    # 순매수일: 500,300,400,200,150,100 = 6일 → 매수
    assert flow.foreign_direction_10d == "매수"


def test_institution_direction_10d():
    flow = _make_flow(SAMPLE_10D)
    # 10일: 300,100,-150,200,-200,100,250,-100,200,-300
    # 순매수일: 300,100,200,100,250,200 = 6일 → 매수
    assert flow.institution_direction_10d == "매수"


# ── 순매수 일수 ───────────────────────────────────────────────────────────────

def test_foreign_buy_days():
    flow = _make_flow(SAMPLE_10D)
    # 500,300,400,200,150,100 = 6일
    assert flow.foreign_buy_days == 6


def test_institution_buy_days():
    flow = _make_flow(SAMPLE_10D)
    # 300,100,200,100,250,200 = 6일
    assert flow.institution_buy_days == 6


# ── 구간별 순매수 합계 ─────────────────────────────────────────────────────────

def test_foreign_net_1d():
    flow = _make_flow(SAMPLE_10D)
    assert flow.foreign_net_1d == 500


def test_foreign_net_5d():
    flow = _make_flow(SAMPLE_10D)
    assert flow.foreign_net_5d == 500 + (-200) + 300 + 400 + (-100)  # 900


def test_foreign_net_10d():
    flow = _make_flow(SAMPLE_10D)
    assert flow.foreign_net_10d == sum(d["foreign_net"] for d in SAMPLE_10D)  # 750


def test_institution_net_5d():
    flow = _make_flow(SAMPLE_10D)
    assert flow.institution_net_5d == 300 + 100 + (-150) + 200 + (-200)  # 250


# ── FlowTool ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flow_tool_fetches_10_days():
    """FlowTool이 days=10으로 KIS API를 호출한다."""
    mock_kis = AsyncMock()
    mock_kis.get_investor_trend.return_value = SAMPLE_10D

    tool = FlowTool(kis_provider=mock_kis)
    result = await tool.execute("005930")

    assert result.success is True
    flow: InvestorFlow = result.data
    assert flow.code == "005930"
    assert len(flow.entries) == 10
    assert flow.entries[0].date == "2026-04-11"
    assert flow.entries[0].foreign_net == 500
    mock_kis.get_investor_trend.assert_called_once_with("005930", days=10)


@pytest.mark.asyncio
async def test_flow_tool_kis_error_returns_failed_result():
    """KIS API 오류 시 ToolResult(success=False) 반환."""
    mock_kis = AsyncMock()
    mock_kis.get_investor_trend.side_effect = Exception("KIS API unauthorized")

    tool = FlowTool(kis_provider=mock_kis)
    result = await tool.execute("005930")

    assert result.success is False
    assert "KIS API unauthorized" in result.error


@pytest.mark.asyncio
async def test_flow_tool_no_kis_provider_returns_failed_result():
    """KISProvider 미설정 시 실패 ToolResult 반환."""
    tool = FlowTool(kis_provider=None)
    result = await tool.execute("005930")

    assert result.success is False
    assert "KIS" in result.error

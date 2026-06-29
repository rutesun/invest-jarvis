from unittest.mock import AsyncMock

import httpx
import pytest

from src.providers.kis import KISProvider
from src.tools.fundamental import FundamentalSnapshot, FundamentalTool


@pytest.mark.asyncio
async def test_fundamental_tool_uses_kis_for_korean_ticker():
    kis_provider = KISProvider(app_key="test", app_secret="test")
    tool = FundamentalTool(kis_provider=kis_provider)
    tool._fetch_kis_fundamentals = AsyncMock(  # type: ignore[method-assign]
        return_value=FundamentalSnapshot(roe=0.253)
    )

    result = await tool.execute("033100.KQ")

    assert result.success is True
    tool._fetch_kis_fundamentals.assert_awaited_once_with("033100.KQ")


def test_normalize_kis_snapshot_sets_missing_values_to_none():
    tool = FundamentalTool()

    snapshot = tool._normalize_kis_snapshot(  # type: ignore[attr-defined]
        ticker="033100.KQ",
        quote_data={"price": 88200.0},
        profit_ratio=[],
        financial_ratio=[],
        profit_ratio_q=[],
        profit_ratio_a=[],
        other_major_ratios=[],
        income_statement=[],
        balance_sheet=[],
        balance_sheet_q=[],
    )

    assert snapshot.pe_ratio is None
    assert snapshot.pb_ratio is None
    assert snapshot.roe is None
    assert snapshot.current_ratio is None
    assert snapshot.quarterly_data is None


def test_normalize_kis_snapshot_maps_core_metrics_and_growth():
    tool = FundamentalTool()

    snapshot = tool._normalize_kis_snapshot(  # type: ignore[attr-defined]
        ticker="005930.KS",
        quote_data={"price": 55000.0},
        profit_ratio=[
            {
                "stac_yymm": "202512",
                "roe_val": "10.85",
                "eps": "6564.00",
                "sps": "49471",
                "bps": "63997.00",
                "lblt_rate": "29.94",
            }
        ],
        financial_ratio=[
            {
                "stac_yymm": "202512",
                "cras": "2476846.00",
                "flow_lblt": "1064113.00",
                "total_lblt": "1306218.00",
                "total_cptl": "4363203.00",
            }
        ],
        profit_ratio_q=[],
        profit_ratio_a=[],
        other_major_ratios=[
            {
                "stac_yymm": "202512",
                "ebitda": "500000.00",
                "ev_ebitda": "5.20",
                "payout_rate": "25.10",
            }
        ],
        income_statement=[
            {
                "stac_yymm": "202512",
                "cptl_ntin_rate": "8.36",
                "self_cptl_ntin_inrt": "10.85",
                "sale_ntin_rate": "13.55",
                "sale_totl_rate": "39.38",
            }
        ],
        balance_sheet=[
            {
                "stac_yymm": "202512",
                "sale_account": "3336059.00",
                "sale_totl_prfi": "1313704.00",
                "op_prfi": "494815.00",
                "thtr_ntin": "452068.00",
            },
            {
                "stac_yymm": "202412",
                "sale_account": "3008709.00",
                "sale_totl_prfi": "1143086.00",
                "op_prfi": "375297.00",
                "thtr_ntin": "344514.00",
            },
        ],
        balance_sheet_q=[],
    )

    assert snapshot.roe == pytest.approx(0.1085)
    assert snapshot.roa == pytest.approx(0.0836)
    assert snapshot.profit_margin == pytest.approx(0.1355)
    assert snapshot.gross_margin == pytest.approx(0.3938)
    assert snapshot.operating_margin == pytest.approx(494815.0 / 3336059.0)
    assert snapshot.debt_to_equity == pytest.approx(1306218.0 / 4363203.0)
    assert snapshot.current_ratio == pytest.approx(2476846.0 / 1064113.0)
    assert snapshot.pe_ratio == pytest.approx(55000.0 / 6564.0)
    assert snapshot.pb_ratio == pytest.approx(55000.0 / 63997.0)
    assert snapshot.ps_ratio == pytest.approx(55000.0 / 49471.0)
    assert snapshot.ev_ebitda == pytest.approx(5.20)
    assert snapshot.payout_ratio == pytest.approx(0.251)
    # 연간 성장률은 balance_sheet의 결산월(XX12) 행끼리만 비교한다 (분기행 혼입 방지)
    assert snapshot.earnings_growth == pytest.approx((452068.0 - 344514.0) / 344514.0)
    assert snapshot.revenue_growth == pytest.approx((3336059.0 - 3008709.0) / 3008709.0)
    # 분기 매출/이익은 balance_sheet_q(div=1) 기반이며, 별도 테스트가 검증한다.


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://openapi.koreainvestment.com")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"status={status_code}",
        request=request,
        response=response,
    )


@pytest.mark.asyncio
async def test_fetch_kis_fundamentals_retries_endpoint_and_keeps_partial_success():
    provider = AsyncMock()
    provider.get_quote.return_value = {"price": 10000.0}
    provider.get_financial_ratio.return_value = []
    provider.get_balance_sheet.return_value = []
    provider.get_profit_ratio.return_value = [
        {"stac_yymm": "202512", "eps": "1000.0", "roe_val": "12.5"}
    ]
    provider.get_income_statement.side_effect = _http_status_error(500)
    provider.get_other_major_ratios.return_value = []

    tool = FundamentalTool(kis_provider=provider)
    snapshot = await tool._fetch_kis_fundamentals("000000.KQ")  # type: ignore[attr-defined]

    assert snapshot.pe_ratio == pytest.approx(10.0)
    assert snapshot.roe == pytest.approx(0.125)
    assert provider.get_income_statement.await_count == 3


@pytest.mark.asyncio
async def test_fetch_kis_fundamentals_uses_profit_ratio_for_eps_not_financial_ratio():
    """EPS 소스는 get_financial_ratio(div_cls_code) 가 아닌 get_profit_ratio 여야 한다."""
    provider = AsyncMock()
    provider.get_quote.return_value = {"price": 55000.0}
    provider.get_financial_ratio.return_value = []  # financial_ratio에 eps 없음
    provider.get_balance_sheet.return_value = []
    # profit_ratio div=0(연간) — _normalize_kis_snapshot에서 profit_row.eps를 쓴다
    provider.get_profit_ratio.return_value = [
        {"stac_yymm": "202512", "eps": "6564.00", "roe_val": "10.85"}
    ]
    provider.get_income_statement.return_value = []
    provider.get_other_major_ratios.return_value = []

    tool = FundamentalTool(kis_provider=provider)
    snapshot = await tool._fetch_kis_fundamentals("005930.KS")  # type: ignore[attr-defined]

    # profit_ratio에서 eps를 가져와 PE를 계산한다
    assert snapshot.pe_ratio == pytest.approx(55000.0 / 6564.0)
    assert snapshot.roe == pytest.approx(0.1085)


@pytest.mark.asyncio
async def test_fetch_kis_fundamentals_quarterly_eps_via_profit_ratio_q():
    """분기 EPS는 get_profit_ratio(div_cls_code='1') 결과를 _build_quarterly_eps에 넘겨야 한다."""
    provider = AsyncMock()
    provider.get_quote.return_value = {"price": 55000.0}
    provider.get_financial_ratio.return_value = []
    provider.get_balance_sheet.return_value = []
    # profit_ratio div=0 (기본, 연간)
    provider.get_profit_ratio.return_value = [
        {"stac_yymm": "202512", "eps": "6564.00", "roe_val": "10.85"}
    ]
    provider.get_income_statement.return_value = []
    provider.get_other_major_ratios.return_value = []

    tool = FundamentalTool(kis_provider=provider)
    await tool._fetch_kis_fundamentals("005930.KS")  # type: ignore[attr-defined]

    # profit_ratio_q 호출이 div_cls_code="1" 로 이루어져야 한다
    calls = provider.get_profit_ratio.call_args_list
    quarterly_call_args = [
        c for c in calls if c.kwargs.get("div_cls_code") == "1" or (c.args and "1" in c.args)
    ]
    assert len(quarterly_call_args) >= 1, (
        "get_profit_ratio(div_cls_code='1') must be called for quarterly EPS"
    )
    # annual call: div_cls_code="0"
    annual_call_args = [
        c for c in calls if c.kwargs.get("div_cls_code") == "0" or (c.args and "0" in c.args)
    ]
    assert len(annual_call_args) >= 1, (
        "get_profit_ratio(div_cls_code='0') must be called for annual EPS"
    )


@pytest.mark.asyncio
async def test_fetch_kis_fundamentals_annual_eps_from_profit_ratio_a():
    """연간 EPS(annual_data)는 get_profit_ratio(div_cls_code='0') 결과를 사용해야 한다."""
    provider = AsyncMock()
    provider.get_quote.return_value = {"price": 55000.0}
    provider.get_financial_ratio.return_value = []
    provider.get_balance_sheet.return_value = []

    def profit_ratio_side_effect(ticker, div_cls_code="0"):
        if div_cls_code == "0":
            return [
                {"stac_yymm": "202512", "eps": "6564.00", "roe_val": "10.85"},
                {"stac_yymm": "202412", "eps": "4950.00", "roe_val": "9.20"},
                {"stac_yymm": "202312", "eps": "4100.00", "roe_val": "8.50"},
            ]
        # div_cls_code="1" (분기)
        return [
            {"stac_yymm": "202506", "eps": "1920.00"},
            {"stac_yymm": "202503", "eps": "1186.00"},
            {"stac_yymm": "202412", "eps": "4950.00"},
            {"stac_yymm": "202409", "eps": "3834.00"},
            {"stac_yymm": "202406", "eps": "2394.00"},  # 전년 동기
        ]

    provider.get_profit_ratio.side_effect = profit_ratio_side_effect
    provider.get_income_statement.return_value = []
    provider.get_other_major_ratios.return_value = []

    tool = FundamentalTool(kis_provider=provider)
    snapshot = await tool._fetch_kis_fundamentals("005930.KS")  # type: ignore[attr-defined]

    # 연간 annual_data는 profit_ratio div=0에서 나와야 한다
    assert snapshot.annual_data is not None
    assert snapshot.annual_data[0].year == "2025"
    assert snapshot.annual_data[0].eps == pytest.approx(6564.0)

    # 분기 quarterly_data는 profit_ratio div=1에서 나와야 한다.
    # KIS 분기 EPS는 누적값이므로 순수 분기(standalone)로 변환된다:
    #   2025-06 = 1920(반기 누적) - 1186(Q1 누적) = 734
    #   2024-06 = 2394 (해당 연도 첫 행, 누적=standalone)
    assert snapshot.quarterly_data is not None
    eps_by_period = {q.period: q for q in snapshot.quarterly_data}
    q0 = eps_by_period.get("2025-06")
    assert q0 is not None
    assert q0.eps == pytest.approx(734.0)
    expected_yoy = (734.0 - 2394.0) / abs(2394.0)
    assert q0.eps_yoy == pytest.approx(expected_yoy, rel=1e-5)


def test_normalize_kis_snapshot_quarterly_data_eps_series_based():
    """quarterly_data는 profit-ratio 분기 EPS 기준이어야 한다 — balance-sheet 연간 행 혼입 없음."""
    tool = FundamentalTool()

    # balance_sheet에 연간 행(202312, 202412)이 섞인 경우
    balance_sheet_mixed = [
        {
            "stac_yymm": "202503",
            "sale_account": "800000",
            "sale_totl_prfi": "200000",
            "op_prfi": "80000",
            "thtr_ntin": "70000",
        },
        {
            "stac_yymm": "202412",  # 연간 행 (12월 = 연간일 수 있음)
            "sale_account": "3000000",
            "sale_totl_prfi": "1000000",
            "op_prfi": "300000",
            "thtr_ntin": "250000",
        },
        {
            "stac_yymm": "202312",  # 연간 행
            "sale_account": "2500000",
            "sale_totl_prfi": "900000",
            "op_prfi": "250000",
            "thtr_ntin": "200000",
        },
    ]
    profit_ratio_q = [
        {"stac_yymm": "202506", "eps": "1920.00"},
        {"stac_yymm": "202503", "eps": "1186.00"},
        {"stac_yymm": "202412", "eps": "4950.00"},
        {"stac_yymm": "202409", "eps": "3701.00"},
        {"stac_yymm": "202406", "eps": "1186.00"},  # 전년 동기
    ]
    # 분기 매출/이익은 balance_sheet_q(div=1, 누적)에서 가져온다.
    balance_sheet_q = [
        {"stac_yymm": "202506", "sale_account": "1500000", "op_prfi": "150000", "thtr_ntin": "130000"},
        {"stac_yymm": "202503", "sale_account": "800000", "op_prfi": "80000", "thtr_ntin": "70000"},
    ]

    snap = tool._normalize_kis_snapshot(  # type: ignore[attr-defined]
        ticker="005930.KS",
        quote_data={"price": 55000.0},
        profit_ratio=[],
        financial_ratio=[],
        profit_ratio_q=profit_ratio_q,
        profit_ratio_a=[],
        other_major_ratios=[],
        income_statement=[],
        balance_sheet=balance_sheet_mixed,
        balance_sheet_q=balance_sheet_q,
    )

    assert snap.quarterly_data is not None
    # 최신 4개 분기만
    assert len(snap.quarterly_data) == 4
    # 모든 period가 YYYY-MM 형식(6자리 숫자 아님)
    periods = [q.period for q in snap.quarterly_data]
    assert "2025-06" in periods, f"Expected 2025-06 in {periods}"
    assert "2025-03" in periods, f"Expected 2025-03 in {periods}"
    # KIS 분기 EPS는 누적값 → 순수 분기로 변환: 2025-06 = 1920 - 1186 = 734
    eps_by_period = {q.period: q for q in snap.quarterly_data}
    assert eps_by_period["2025-06"].eps == pytest.approx(734.0)
    assert eps_by_period["2025-06"].eps_yoy is not None, "eps_yoy should be set for 2025-06"
    # balance_sheet_q에서 분기 매칭된 것은 revenue 있음 (2025-03은 Q1이라 누적=순수)
    assert eps_by_period["2025-03"].revenue == pytest.approx(800000.0)


@pytest.mark.asyncio
async def test_fetch_kis_fundamentals_raises_when_all_endpoints_fail():
    provider = AsyncMock()
    provider.get_quote.side_effect = _http_status_error(500)
    provider.get_financial_ratio.side_effect = _http_status_error(500)
    provider.get_balance_sheet.side_effect = _http_status_error(500)
    provider.get_profit_ratio.side_effect = _http_status_error(500)
    provider.get_income_statement.side_effect = _http_status_error(500)
    provider.get_other_major_ratios.side_effect = _http_status_error(500)

    tool = FundamentalTool(kis_provider=provider)

    with pytest.raises(RuntimeError, match="모든 재무 엔드포인트 응답이 비어 있습니다"):
        await tool._fetch_kis_fundamentals("000000.KQ")  # type: ignore[attr-defined]

    assert provider.get_quote.await_count == 3

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
        other_major_ratios=[],
        income_statement=[],
        balance_sheet=[],
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
    assert snapshot.earnings_growth == pytest.approx((452068.0 - 344514.0) / 344514.0)
    assert snapshot.revenue_growth == pytest.approx((3336059.0 - 3008709.0) / 3008709.0)
    assert snapshot.quarterly_data is not None
    assert snapshot.quarterly_data[0].period == "2025-12"
    assert snapshot.quarterly_data[0].revenue_qoq == pytest.approx(
        (3336059.0 - 3008709.0) / 3008709.0
    )


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

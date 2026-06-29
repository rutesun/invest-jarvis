# tests/tools/test_disclosure.py
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tools.disclosure import (
    DARTDisclosureFetcher,
    DisclosureItem,
    DisclosureTool,
    SECDisclosureFetcher,
    extract_kr_code,
    is_korean_ticker,
)


def test_disclosure_item_defaults():
    item = DisclosureItem(
        form_type="8-K",
        date="2026-04-01",
        description="Q1 Results announced",
        url="https://sec.gov/Archives/edgar/data/320193/000032019326000001/q1.htm",
    )
    assert item.form_type == "8-K"
    assert item.score == 1.0  # 기본값


def test_disclosure_item_custom_score():
    item = DisclosureItem(
        form_type="DART",
        date="2026-04-01",
        description="수주계약 체결",
        url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260401000001",
        score=2.0,
    )
    assert item.score == 2.0


def test_is_korean_ticker_ks_suffix():
    assert is_korean_ticker("005930.KS") is True


def test_is_korean_ticker_kq_suffix():
    assert is_korean_ticker("000660.KQ") is True


def test_is_korean_ticker_bare_six_digits():
    assert is_korean_ticker("005930") is True


def test_is_korean_ticker_us_stock():
    assert is_korean_ticker("AAPL") is False
    assert is_korean_ticker("NVDA") is False
    assert is_korean_ticker("MSFT") is False


def test_extract_kr_code_with_ks():
    assert extract_kr_code("005930.KS") == "005930"


def test_extract_kr_code_with_kq():
    assert extract_kr_code("000660.KQ") == "000660"


def test_extract_kr_code_bare():
    assert extract_kr_code("005930") == "005930"


def test_extract_kr_code_pads_short_code():
    # 짧은 코드는 6자리로 0-패딩
    assert extract_kr_code("5930.KS") == "005930"


# ── SEC EDGAR Fetcher Tests ───────────────────────────────────────────────────


@pytest.fixture
def sec_fetcher(tmp_path):
    fetcher = SECDisclosureFetcher()
    fetcher.CACHE_PATH = tmp_path / "sec_cik_cache.json"
    return fetcher


@pytest.fixture
def sec_cik_response():
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    }


@pytest.fixture
def sec_submissions_response():
    return {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "8-K", "DEF 14A"],
                "filingDate": ["2026-04-05", "2026-03-30", "2025-12-01", "2026-03-01"],
                "primaryDocument": ["q1.htm", "10q.htm", "old.htm", "proxy.htm"],
                "accessionNumber": [
                    "0000320193-26-000001",
                    "0000320193-26-000002",
                    "0000320193-25-000099",
                    "0000320193-26-000003",
                ],
            }
        }
    }


@pytest.mark.asyncio
async def test_sec_fetcher_returns_filtered_filings(
    sec_fetcher, sec_cik_response, sec_submissions_response
):
    """최근 3개월 이내의 10-Q, 8-K만 반환하고 오래된 공시와 다른 유형은 제외."""
    # 시간 고정: cutoff = 2026-03-22 → 04-05(8-K), 03-30(10-Q) 포함 / 2025-12-01 제외
    fixed_now = datetime(2026, 6, 20)
    with patch("src.tools.disclosure.datetime") as mock_dt, patch(
        "httpx.AsyncClient"
    ) as mock_client_cls:
        mock_dt.now.return_value = fixed_now
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        cik_resp = AsyncMock()
        cik_resp.json = MagicMock(return_value=sec_cik_response)
        cik_resp.raise_for_status = MagicMock()

        sub_resp = AsyncMock()
        sub_resp.json = MagicMock(return_value=sec_submissions_response)
        sub_resp.raise_for_status = MagicMock()

        mock_client.get.side_effect = [cik_resp, sub_resp]

        items = await sec_fetcher.fetch("AAPL")

    # DEF 14A 제외; 2025-12-01의 8-K는 3개월 범위 밖
    assert len(items) == 2
    assert all(i.form_type in ("8-K", "10-Q") for i in items)
    # 최신순 정렬
    assert items[0].date == "2026-04-05"
    assert items[1].date == "2026-03-30"


@pytest.mark.asyncio
async def test_sec_fetcher_unknown_ticker_returns_empty(sec_fetcher, sec_cik_response):
    """SEC DB에 없는 티커는 빈 리스트 반환."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        cik_resp = AsyncMock()
        cik_resp.json = MagicMock(return_value=sec_cik_response)
        cik_resp.raise_for_status = MagicMock()

        mock_client.get.return_value = cik_resp

        items = await sec_fetcher.fetch("UNKNOWN_XYZ")

    assert items == []


@pytest.mark.asyncio
async def test_sec_fetcher_uses_cache(sec_fetcher, sec_submissions_response, tmp_path):
    """두 번째 호출 시 파일 캐시를 사용해 CIK 재조회 없이 처리."""
    # AAPL -> 320193 캐시 사전 저장
    cache_data = {"AAPL": 320193}
    sec_fetcher.CACHE_PATH.write_text(json.dumps(cache_data))
    sec_fetcher.CACHE_PATH.touch()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        sub_resp = AsyncMock()
        sub_resp.json = MagicMock(return_value=sec_submissions_response)
        sub_resp.raise_for_status = MagicMock()

        mock_client.get.return_value = sub_resp

        items = await sec_fetcher.fetch("AAPL")

    # submissions 조회 1회만 호출 (CIK 조회 없음)
    assert mock_client.get.call_count == 1
    assert len(items) >= 1


# ── DART Fetcher Tests ────────────────────────────────────────────────────────


@pytest.fixture
def dart_fetcher(tmp_path):
    fetcher = DARTDisclosureFetcher(api_key="test_key")
    fetcher.CACHE_PATH = tmp_path / "dart_corp_code_cache.json"
    return fetcher


@pytest.fixture
def dart_corp_response():
    return {"status": "000", "corp_code": "00126380", "corp_name": "삼성전자"}


@pytest.fixture
def dart_list_response():
    return {
        "status": "000",
        "list": [
            {"report_nm": "수주계약 체결", "rcept_dt": "20260405", "rcp_no": "20260405000001"},
            {"report_nm": "분기보고서", "rcept_dt": "20260401", "rcp_no": "20260401000002"},
            {"report_nm": "유상증자결정", "rcept_dt": "20260320", "rcp_no": "20260320000003"},
            {"report_nm": "사업보고서", "rcept_dt": "20260301", "rcp_no": "20260301000004"},
            {"report_nm": "매출계약", "rcept_dt": "20260310", "rcp_no": "20260310000005"},
        ],
    }


@pytest.mark.asyncio
async def test_dart_fetcher_filters_by_score(dart_fetcher, dart_corp_response, dart_list_response):
    """score >= 1.0 인 공시만 반환, score 내림차순 정렬."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        corp_resp = AsyncMock()
        corp_resp.json = MagicMock(return_value=dart_corp_response)
        corp_resp.status_code = 200
        corp_resp.raise_for_status = MagicMock()

        list_resp = AsyncMock()
        list_resp.json = MagicMock(return_value=dart_list_response)
        list_resp.raise_for_status = MagicMock()

        mock_client.get.side_effect = [corp_resp, list_resp]

        items = await dart_fetcher.fetch("005930")

    # 분기보고서(-1.0), 사업보고서(-1.0)는 임계값 미달로 제외
    report_names = [i.description for i in items]
    assert "분기보고서" not in report_names
    assert "사업보고서" not in report_names
    # 수주계약(1.0), 유상증자결정(1.0), 매출계약(1.0)은 통과
    assert len(items) == 3


@pytest.mark.asyncio
async def test_dart_fetcher_date_formatting(dart_fetcher, dart_corp_response, dart_list_response):
    """YYYYMMDD 날짜를 YYYY-MM-DD 형식으로 변환."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        corp_resp = AsyncMock()
        corp_resp.json = MagicMock(return_value=dart_corp_response)
        corp_resp.status_code = 200
        corp_resp.raise_for_status = MagicMock()

        list_resp = AsyncMock()
        list_resp.json = MagicMock(return_value=dart_list_response)
        list_resp.raise_for_status = MagicMock()

        mock_client.get.side_effect = [corp_resp, list_resp]

        items = await dart_fetcher.fetch("005930")

    for item in items:
        assert len(item.date) == 10
        assert item.date[4] == "-"
        assert item.date[7] == "-"


@pytest.mark.asyncio
async def test_dart_fetcher_corp_not_found(dart_fetcher):
    """종목코드에 해당하는 corp_code를 찾지 못하면 빈 리스트 반환."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        corp_resp = AsyncMock()
        corp_resp.json = MagicMock(
            return_value={"status": "013", "message": "조회된 데이터가 없습니다."}
        )
        corp_resp.status_code = 200
        corp_resp.raise_for_status = MagicMock()

        mock_client.get.return_value = corp_resp

        items = await dart_fetcher.fetch("999999")

    assert items == []


@pytest.mark.asyncio
async def test_dart_fetcher_uses_cache(dart_fetcher, dart_list_response, tmp_path):
    """두 번째 조회 시 파일 캐시를 사용해 corp_code API 재호출을 방지한다."""
    # 캐시 사전 저장: 005930 → 00126380
    cache_data = {"005930": "00126380"}
    dart_fetcher.CACHE_PATH.write_text(json.dumps(cache_data))
    dart_fetcher.CACHE_PATH.touch()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        list_resp = AsyncMock()
        list_resp.json = MagicMock(return_value=dart_list_response)
        list_resp.raise_for_status = MagicMock()

        mock_client.get.return_value = list_resp

        items = await dart_fetcher.fetch("005930")

    # list.json 조회 1회만 (company.json corp_code 조회 없음)
    assert mock_client.get.call_count == 1
    assert len(items) > 0


# ── DisclosureTool Integration Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_disclosure_tool_routes_us_to_sec():
    """미국 티커는 SEC 페처로 라우팅."""
    mock_sec = AsyncMock()
    mock_sec.fetch.return_value = [
        DisclosureItem(
            form_type="8-K", date="2026-04-05", description="q1.htm", url="https://sec.gov/..."
        )
    ]
    mock_dart = AsyncMock()

    tool = DisclosureTool(sec_fetcher=mock_sec, dart_fetcher=mock_dart)
    result = await tool.execute("AAPL")

    assert result.success is True
    assert len(result.data) == 1
    mock_sec.fetch.assert_called_once_with("AAPL")
    mock_dart.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_disclosure_tool_routes_kr_to_dart():
    """한국 티커(.KS)는 6자리 코드를 추출하여 DART 페처로 라우팅."""
    mock_sec = AsyncMock()
    mock_dart = AsyncMock()
    mock_dart.fetch.return_value = [
        DisclosureItem(
            form_type="DART",
            date="2026-04-05",
            description="수주계약",
            url="https://dart.fss.or.kr/...",
        )
    ]

    tool = DisclosureTool(sec_fetcher=mock_sec, dart_fetcher=mock_dart)
    result = await tool.execute("005930.KS")

    assert result.success is True
    mock_dart.fetch.assert_called_once_with("005930")
    mock_sec.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_disclosure_tool_no_dart_fetcher_returns_error():
    """DART 페처 없이 한국주식 조회 시 실패 ToolResult 반환."""
    mock_sec = AsyncMock()

    tool = DisclosureTool(sec_fetcher=mock_sec, dart_fetcher=None)
    result = await tool.execute("005930.KS")

    assert result.success is False
    assert "DART" in result.error


@pytest.mark.asyncio
async def test_disclosure_tool_wraps_exceptions():
    """페처 예외는 실패 ToolResult로 래핑."""
    mock_sec = AsyncMock()
    mock_sec.fetch.side_effect = Exception("network timeout")

    tool = DisclosureTool(sec_fetcher=mock_sec, dart_fetcher=None)
    result = await tool.execute("AAPL")

    assert result.success is False
    assert "network timeout" in result.error

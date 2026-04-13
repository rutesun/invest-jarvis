# tests/tools/test_disclosure.py
import json
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.disclosure import DisclosureItem, is_korean_ticker, extract_kr_code


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

from src.tools.disclosure import SECDisclosureFetcher


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
    with patch("httpx.AsyncClient") as mock_client_cls:
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

# tests/tools/test_disclosure.py
import pytest
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

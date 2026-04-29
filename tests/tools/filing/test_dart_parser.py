from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.tools.filing.dart_parser import DARTFilingParser


@pytest.fixture
def parser():
    return DARTFilingParser(api_key="test_key")


@pytest.fixture
def mock_dart_financials():
    """삼성전자 fnlttSinglAcntAll 응답 mock."""
    return {
        "status": "000",
        "message": "정상",
        "list": [
            {
                "account_nm": "매출액",
                "thstrm_amount": "333605938000000",
                "frmtrm_amount": "300870903000000",
                "sj_div": "IS",
            },
            {
                "account_nm": "영업이익",
                "thstrm_amount": "43601051000000",
                "frmtrm_amount": "32725961000000",
                "sj_div": "IS",
            },
            {
                "account_nm": "당기순이익",
                "thstrm_amount": "45206805000000",
                "frmtrm_amount": "34451351000000",
                "sj_div": "IS",
            },
            {
                "account_nm": "자산총계",
                "thstrm_amount": "566942110000000",
                "frmtrm_amount": "514531948000000",
                "sj_div": "BS",
            },
            {
                "account_nm": "자본총계",
                "thstrm_amount": "436320337000000",
                "frmtrm_amount": "402192070000000",
                "sj_div": "BS",
            },
            {
                "account_nm": "부채총계",
                "thstrm_amount": "130621773000000",
                "frmtrm_amount": "112339878000000",
                "sj_div": "BS",
            },
        ],
    }


@patch("src.tools.filing.dart_parser.httpx.AsyncClient")
async def test_parse_extracts_financials(mock_client_cls, parser, mock_dart_financials):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_dart_financials
    mock_response.raise_for_status = Mock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    facts = await parser.parse("005930", corp_code="00126380", bsns_year="2025")

    assert facts is not None
    assert facts.ticker == "005930"
    assert facts.market == "KR"
    assert "revenue" in facts.financials
    assert facts.financials["revenue"].value == Decimal("333605938000000")
    assert facts.financials["revenue"].unit == "KRW"


@patch("src.tools.filing.dart_parser.httpx.AsyncClient")
async def test_parse_calculates_yoy(mock_client_cls, parser, mock_dart_financials):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_dart_financials
    mock_response.raise_for_status = Mock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    facts = await parser.parse("005930", corp_code="00126380", bsns_year="2025")

    assert "revenue_yoy" in facts.comparisons
    assert abs(facts.comparisons["revenue_yoy"].change_pct - 10.88) < 0.1


@patch("src.tools.filing.dart_parser.httpx.AsyncClient")
@patch("src.tools.filing.dart_parser.Path.exists")
async def test_parse_handles_api_failure(mock_exists, mock_client_cls, parser):
    # Ensure no cache is found
    mock_exists.return_value = False

    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Connection timeout")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    facts = await parser.parse("005930", corp_code="00126380", bsns_year="2025")
    assert facts is None

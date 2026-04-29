from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.tools.filing.sec_parser import SECFilingParser


@pytest.fixture
def parser():
    return SECFilingParser()


@pytest.fixture
def mock_companyfacts_aapl():
    """AAPL companyfacts API 응답 mock (핵심 필드만)."""
    return {
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "val": 391_035_000_000,
                                "form": "10-K",
                                "filed": "2024-11-01",
                            },
                            {
                                "fy": 2025,
                                "fp": "FY",
                                "val": 416_200_000_000,
                                "form": "10-K",
                                "filed": "2025-10-31",
                            },
                        ]
                    }
                },
                "OperatingIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "val": 123_216_000_000,
                                "form": "10-K",
                                "filed": "2024-11-01",
                            },
                            {
                                "fy": 2025,
                                "fp": "FY",
                                "val": 133_100_000_000,
                                "form": "10-K",
                                "filed": "2025-10-31",
                            },
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "val": 93_736_000_000,
                                "form": "10-K",
                                "filed": "2024-11-01",
                            },
                            {
                                "fy": 2025,
                                "fp": "FY",
                                "val": 112_010_000_000,
                                "form": "10-K",
                                "filed": "2025-10-31",
                            },
                        ]
                    }
                },
                "CommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "fy": 2025,
                                "fp": "FY",
                                "val": 15_115_786_000,
                                "form": "10-K",
                                "filed": "2025-10-31",
                            },
                        ]
                    }
                },
            },
            "dei": {},
        },
    }


@patch("src.tools.filing.sec_parser.httpx.AsyncClient")
async def test_parse_extracts_financials(mock_client_cls, parser, mock_companyfacts_aapl):
    # Mock response for both CIK lookup and companyfacts
    mock_cik_response = Mock()
    mock_cik_response.status_code = 200
    mock_cik_response.json.return_value = {"0": {"ticker": "AAPL", "cik_str": 320193}}
    mock_cik_response.raise_for_status = Mock()

    mock_facts_response = Mock()
    mock_facts_response.status_code = 200
    mock_facts_response.json.return_value = mock_companyfacts_aapl
    mock_facts_response.raise_for_status = Mock()

    mock_client = AsyncMock()
    mock_client.get.side_effect = [mock_cik_response, mock_facts_response]
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    facts = await parser.parse("AAPL")

    assert facts is not None
    assert facts.ticker == "AAPL"
    assert facts.market == "US"
    assert "revenue" in facts.financials
    assert facts.financials["revenue"].value == Decimal("416200000000")
    assert facts.financials["revenue"].confidence == "high"
    assert facts.financials["revenue"].source == "XBRL"


@patch("src.tools.filing.sec_parser.httpx.AsyncClient")
async def test_parse_calculates_yoy(mock_client_cls, parser, mock_companyfacts_aapl):
    # Mock response for both CIK lookup and companyfacts
    mock_cik_response = Mock()
    mock_cik_response.status_code = 200
    mock_cik_response.json.return_value = {"0": {"ticker": "AAPL", "cik_str": 320193}}
    mock_cik_response.raise_for_status = Mock()

    mock_facts_response = Mock()
    mock_facts_response.status_code = 200
    mock_facts_response.json.return_value = mock_companyfacts_aapl
    mock_facts_response.raise_for_status = Mock()

    mock_client = AsyncMock()
    mock_client.get.side_effect = [mock_cik_response, mock_facts_response]
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    facts = await parser.parse("AAPL")

    assert "revenue_yoy" in facts.comparisons
    # (416.2 - 391.0) / 391.0 * 100 ≈ 6.4%
    assert abs(facts.comparisons["revenue_yoy"].change_pct - 6.43) < 0.1


@patch("src.tools.filing.sec_parser.httpx.AsyncClient")
async def test_parse_handles_api_failure(mock_client_cls, parser):
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Connection timeout")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    facts = await parser.parse("AAPL")
    assert facts is None


def test_extract_section_item7():
    from src.tools.filing.sec_parser import _extract_section

    markdown = """## Item 6. Reserved
Some text.
## Item 7. Management's Discussion and Analysis
Revenue increased to $416.2B. We expect Q2 revenue between $100B and $105B.
## Item 7A. Quantitative
Market risk stuff."""

    section = _extract_section(markdown, r"Item 7\.")
    assert "Revenue increased" in section
    assert "Market risk" not in section


def test_extract_section_item1a():
    from src.tools.filing.sec_parser import _extract_section

    markdown = """## Item 1. Business
Apple designs.
## Item 1A. Risk Factors
Supply chain risks. AI regulation uncertainty.
## Item 1B. Unresolved Staff Comments
Nothing."""

    section = _extract_section(markdown, r"Item 1A\.")
    assert "Supply chain" in section
    assert "Apple designs" not in section


def test_extract_section_not_found():
    from src.tools.filing.sec_parser import _extract_section

    section = _extract_section("## Item 1. Business\nSome text.", r"Item 7\.")
    assert section == ""

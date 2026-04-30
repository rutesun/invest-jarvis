from decimal import Decimal

import pytest

from src.tools.filing.impact import ImpactCalculator
from src.tools.filing.models import (
    Comparison,
    DisclosureDetail,
    FilingFacts,
    FinancialMetric,
)


def _make_metric(val, unit="USD", source="XBRL"):
    return FinancialMetric(
        value=Decimal(str(val)), unit=unit, scale="billions", source=source, confidence="high"
    )


def _make_base_facts(**overrides):
    defaults = {
        "ticker": "TEST",
        "market": "US",
        "filing_type": "10-K",
        "filing_date": "2025-10-31",
        "fiscal_period": "FY2025",
        "source_url": "https://example.com",
        "financials": {},
        "comparisons": {},
        "text_insights": [],
    }
    defaults.update(overrides)
    return FilingFacts(**defaults)


@pytest.fixture
def calculator():
    return ImpactCalculator()


def test_earnings_impact(calculator):
    facts = _make_base_facts(
        financials={
            "revenue": _make_metric(416_200_000_000),
            "operating_income": _make_metric(133_100_000_000),
        },
        comparisons={
            "revenue_yoy": Comparison(
                change_pct=6.4, previous=Decimal("391000000000"), period="FY2024"
            ),
            "operating_income_yoy": Comparison(
                change_pct=8.0, previous=Decimal("123200000000"), period="FY2024"
            ),
        },
    )

    impact = calculator.calculate(facts)

    assert impact.impact_type == "실적발표"
    assert impact.metrics["revenue_yoy_pct"] == 6.4
    assert impact.metrics["operating_income_yoy_pct"] == 8.0
    assert impact.direction == "긍정"
    assert impact.facts.ticker == "TEST"


def test_earnings_negative_direction(calculator):
    facts = _make_base_facts(
        comparisons={
            "revenue_yoy": Comparison(change_pct=-15.0, previous=Decimal("100"), period="FY2024"),
            "operating_income_yoy": Comparison(
                change_pct=-25.0, previous=Decimal("50"), period="FY2024"
            ),
        },
    )
    impact = calculator.calculate(facts)
    assert impact.direction == "부정"


def test_equity_issuance_impact(calculator):
    facts = _make_base_facts(
        filing_type="주요사항보고서",
        financials={
            "shares_outstanding": _make_metric(10_000_000),
            "total_equity": _make_metric(500_000_000_000),
        },
        disclosure_detail=DisclosureDetail(
            detail_type="유상증자",
            new_shares=1_000_000,
            issue_price=Decimal("50000"),
            purpose="시설투자",
        ),
    )

    impact = calculator.calculate(facts)

    assert impact.impact_type == "유상증자"
    assert abs(impact.metrics["dilution_pct"] - 9.09) < 0.1
    assert impact.direction == "부정"


def test_convertible_bond_impact(calculator):
    facts = _make_base_facts(
        filing_type="주요사항보고서",
        financials={"shares_outstanding": _make_metric(10_000_000)},
        disclosure_detail=DisclosureDetail(
            detail_type="전환사채",
            conversion_price=Decimal("45000"),
            conversion_shares=2_222_222,
            cb_amount=Decimal("100000000000"),
            maturity_date="2028-06",
        ),
    )

    impact = calculator.calculate(facts)

    assert impact.impact_type == "전환사채"
    assert abs(impact.metrics["overhang_pct"] - 22.22) < 0.1


def test_supply_contract_impact(calculator):
    facts = _make_base_facts(
        filing_type="주요사항보고서",
        financials={"revenue": _make_metric(3_000_000_000_000, "KRW")},
        disclosure_detail=DisclosureDetail(
            detail_type="공급계약",
            contract_amount=Decimal("500000000000"),
            counterparty="글로벌 반도체사",
            contract_period="24개월",
        ),
    )

    impact = calculator.calculate(facts)

    assert impact.impact_type == "공급계약"
    assert abs(impact.metrics["revenue_ratio_pct"] - 16.67) < 0.1
    assert impact.direction == "긍정"


def test_no_comparisons_returns_neutral(calculator):
    facts = _make_base_facts(financials={"revenue": _make_metric(100)})
    impact = calculator.calculate(facts)
    assert impact.direction == "중립"

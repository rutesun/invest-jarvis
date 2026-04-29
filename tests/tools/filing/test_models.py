# tests/tools/filing/test_models.py
from decimal import Decimal

from src.tools.filing.models import (
    Comparison,
    DisclosureDetail,
    FilingFacts,
    FilingImpact,
    FinancialMetric,
    GuidanceInfo,
    TextInsight,
)


def test_financial_metric_creation():
    m = FinancialMetric(
        value=Decimal("416200000000"),
        unit="USD",
        scale="billions",
        source="XBRL",
        confidence="high",
    )
    assert m.value == Decimal("416200000000")
    assert m.confidence == "high"


def test_financial_metric_display_value():
    m = FinancialMetric(
        value=Decimal("416200000000"),
        unit="USD",
        scale="billions",
        source="XBRL",
        confidence="high",
    )
    assert m.display_value() == "$416.2B"


def test_financial_metric_display_value_krw():
    m = FinancialMetric(
        value=Decimal("333605938000000"),
        unit="KRW",
        scale="billions",
        source="XBRL",
        confidence="high",
    )
    assert m.display_value() == "333.6조"


def test_comparison_creation():
    c = Comparison(change_pct=6.4, previous=Decimal("391000000000"), period="FY2024")
    assert c.change_pct == 6.4


def test_guidance_info():
    g = GuidanceInfo(
        period="Q2 FY2026",
        metric="revenue",
        range_low=Decimal("100000000000"),
        range_high=Decimal("105000000000"),
        direction="상향",
        raw_text="We expect revenue between $100B and $105B",
    )
    assert g.direction == "상향"


def test_text_insight():
    t = TextInsight(
        section="주요 제품 및 서비스",
        extracted={"매출비중": "반도체 71%", "비중변화": "+6pp", "신규": None},
        additional=["파운드리 매출 YoY +42%"],
        raw_section="원문 텍스트...",
    )
    assert t.extracted["신규"] is None
    assert len(t.additional) == 1


def test_disclosure_detail_equity_issuance():
    d = DisclosureDetail(
        detail_type="유상증자",
        new_shares=1_000_000,
        issue_price=Decimal("50000"),
        purpose="시설투자",
    )
    assert d.detail_type == "유상증자"
    assert d.conversion_price is None


def test_filing_facts_minimal():
    facts = FilingFacts(
        ticker="AAPL",
        market="US",
        filing_type="10-K",
        filing_date="2025-10-31",
        fiscal_period="FY2025",
        source_url="https://sec.gov/...",
        financials={
            "revenue": FinancialMetric(
                value=Decimal("416200000000"),
                unit="USD",
                scale="billions",
                source="XBRL",
                confidence="high",
            )
        },
        comparisons={},
        text_insights=[],
    )
    assert facts.market == "US"
    assert "revenue" in facts.financials


def test_filing_impact_preserves_facts():
    facts = FilingFacts(
        ticker="AAPL",
        market="US",
        filing_type="10-K",
        filing_date="2025-10-31",
        fiscal_period="FY2025",
        source_url="https://sec.gov/...",
        financials={},
        comparisons={},
        text_insights=[],
    )
    impact = FilingImpact(
        facts=facts,
        impact_type="실적발표",
        metrics={"revenue_yoy_pct": 6.4},
        severity="High",
        direction="긍정",
        summary="매출 YoY +6.4%",
        confidence="high",
    )
    assert impact.facts.ticker == "AAPL"
    assert impact.metrics["revenue_yoy_pct"] == 6.4

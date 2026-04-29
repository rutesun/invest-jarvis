# src/tools/filing/models.py
"""공시 파싱 데이터 모델."""

from decimal import Decimal

from pydantic import BaseModel


class FinancialMetric(BaseModel):
    """개별 재무 숫자."""

    value: Decimal
    unit: str  # "USD" | "KRW"
    scale: str  # "millions" | "billions"
    source: str  # "XBRL" | "regex" | "LLM"
    confidence: str  # "high" | "medium" | "low"

    def display_value(self) -> str:
        """사람이 읽기 좋은 포맷. 예: '$416.2B', '333.6조'."""
        v = float(self.value)
        if self.unit == "KRW":
            cho = v / 1e12
            if cho >= 1:
                return f"{cho:,.1f}조"
            eok = v / 1e8
            return f"{eok:,.0f}억"
        billions = v / 1e9
        if abs(billions) >= 1:
            return f"${billions:,.1f}B"
        millions = v / 1e6
        return f"${millions:,.1f}M"


class Comparison(BaseModel):
    """전기/전년 대비 비교."""

    change_pct: float
    previous: Decimal
    period: str  # "FY2024" | "Q2 2025"


class GuidanceInfo(BaseModel):
    """Guidance 정보 (US 전용)."""

    period: str
    metric: str
    range_low: Decimal | None = None
    range_high: Decimal | None = None
    direction: str  # "상향" | "하향" | "유지"
    raw_text: str


class TextInsight(BaseModel):
    """텍스트 섹션에서 구조화 추출한 인사이트."""

    section: str
    extracted: dict[str, str | None]
    additional: list[str] = []
    raw_section: str = ""


class DisclosureDetail(BaseModel):
    """공시 유형별 상세 (주요사항보고서용)."""

    detail_type: str  # "전환사채" | "유상증자" | "공급계약"
    # 전환사채
    conversion_price: Decimal | None = None
    conversion_shares: int | None = None
    maturity_date: str | None = None
    cb_amount: Decimal | None = None
    # 유상증자
    new_shares: int | None = None
    issue_price: Decimal | None = None
    purpose: str | None = None
    # 공급계약
    contract_amount: Decimal | None = None
    counterparty: str | None = None
    contract_period: str | None = None


class FilingFacts(BaseModel):
    """공시 파싱 결과 (Task 1 출력)."""

    ticker: str
    market: str  # "US" | "KR"
    filing_type: str  # "10-K" | "사업보고서" | ...
    filing_date: str
    fiscal_period: str
    source_url: str

    financials: dict[str, FinancialMetric]
    comparisons: dict[str, Comparison]
    text_insights: list[TextInsight] = []
    guidance: GuidanceInfo | None = None
    disclosure_detail: DisclosureDetail | None = None


class FilingImpact(BaseModel):
    """정량 시뮬레이션 결과 (Task 6 출력)."""

    facts: FilingFacts
    impact_type: str  # "실적발표" | "유상증자" | "전환사채" | "공급계약"
    metrics: dict[str, float]
    severity: str  # "High" | "Medium" | "Low"
    direction: str  # "긍정" | "부정" | "중립"
    summary: str
    confidence: str  # "high" | "medium" | "low"

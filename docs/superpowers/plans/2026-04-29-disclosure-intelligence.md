# Disclosure Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SEC/DART 공시 원문에서 재무 숫자 + 텍스트 인사이트를 자동 추출하고, 공시 유형별 임팩트를 정량화하여 `jarvis analyze` CLI에 출력

**Architecture:** 하이브리드 (규칙 기반 XBRL 숫자 추출 + LLM 텍스트 해석). SECFilingParser / DARTFilingParser → FilingFacts → ImpactCalculator → FilingImpact. 각 컴포넌트 독립적, DeepDivePipeline에 선택적 주입.

**Tech Stack:** edgartools (SEC 텍스트), httpx (SEC/DART API), Pydantic (모델), LangChain (LLM 구조화 출력), Rich (CLI 테이블)

**Design Spec:** `docs/superpowers/specs/2026-04-29-disclosure-intelligence-design.md`

---

## File Structure

```
src/tools/filing/
├── __init__.py          # 공개 API export
├── models.py            # FinancialMetric, FilingFacts, FilingImpact 등 데이터 모델
├── concepts.py          # SEC XBRL 태그 fallback 체인 + DART 계정명 매핑
├── sec_parser.py        # SECFilingParser (companyfacts API + edgartools 텍스트)
├── dart_parser.py       # DARTFilingParser (fnlttSinglAcntAll API + document.xml)
├── impact.py            # ImpactCalculator (4가지 유형별 정량 계산)
tests/tools/filing/
├── __init__.py
├── test_models.py       # 데이터 모델 테스트
├── test_concepts.py     # XBRL concept mapping 테스트
├── test_sec_parser.py   # SECFilingParser 테스트 (API mock)
├── test_dart_parser.py  # DARTFilingParser 테스트 (API mock)
├── test_impact.py       # ImpactCalculator 테스트
```

**수정할 기존 파일:**
- `src/pipelines/deep_dive.py` — FilingParser + ImpactCalculator 주입
- `src/llm/models.py` — IntegratedAnalysisInput 확장
- `src/llm/analyzer.py` — 종합 분석 프롬프트에 filing 컨텍스트 추가
- `src/cli/main.py` — 재무 테이블 + 임팩트 패널 + 사업 인사이트 출력
- `pyproject.toml` — edgartools 의존성 추가
- `docs/FEATURES.md` — 기능명세 업데이트

---

### Task 1: 의존성 추가 + 패키지 구조

**Files:**
- Modify: `pyproject.toml`
- Create: `src/tools/filing/__init__.py`
- Create: `tests/tools/filing/__init__.py`

- [ ] **Step 1: edgartools 의존성 추가**

`pyproject.toml`의 `dependencies`에 추가:
```toml
"edgartools>=3.0.0",
```

Run: `uv add edgartools`

- [ ] **Step 2: 패키지 디렉토리 생성**

```bash
mkdir -p src/tools/filing tests/tools/filing
touch src/tools/filing/__init__.py tests/tools/filing/__init__.py
```

- [ ] **Step 3: uv sync 확인**

Run: `uv sync`
Expected: 정상 설치

- [ ] **Step 4: 커밋**

```bash
git add pyproject.toml uv.lock src/tools/filing/__init__.py tests/tools/filing/__init__.py
git commit -m "chore: add edgartools dependency and filing package structure"
```

---

### Task 2: 데이터 모델 (models.py)

**Files:**
- Create: `src/tools/filing/models.py`
- Create: `tests/tools/filing/test_models.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/tools/filing/test_models.py
from decimal import Decimal

import pytest

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


def test_disclosure_detail_유상증자():
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/tools/filing/test_models.py -v`
Expected: FAIL — import 에러

- [ ] **Step 3: models.py 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/tools/filing/test_models.py -v`
Expected: ALL PASS

- [ ] **Step 5: __init__.py에 공개 API export**

```python
# src/tools/filing/__init__.py
from src.tools.filing.models import (
    Comparison,
    DisclosureDetail,
    FilingFacts,
    FilingImpact,
    FinancialMetric,
    GuidanceInfo,
    TextInsight,
)

__all__ = [
    "Comparison",
    "DisclosureDetail",
    "FilingFacts",
    "FilingImpact",
    "FinancialMetric",
    "GuidanceInfo",
    "TextInsight",
]
```

- [ ] **Step 6: 커밋**

```bash
git add src/tools/filing/models.py src/tools/filing/__init__.py tests/tools/filing/test_models.py
git commit -m "feat(filing): add data models for disclosure intelligence"
```

---

### Task 3: XBRL Concept Mapping (concepts.py)

**Files:**
- Create: `src/tools/filing/concepts.py`
- Create: `tests/tools/filing/test_concepts.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/tools/filing/test_concepts.py
import pytest

from src.tools.filing.concepts import (
    DART_ACCOUNT_MAPPING,
    SEC_CONCEPT_CHAINS,
    resolve_dart_metric,
    resolve_sec_metric,
)


def test_sec_revenue_primary_tag():
    """RevenueFromContract... 태그가 있으면 revenue로 매핑."""
    facts = {"RevenueFromContractWithCustomerExcludingAssessedTax": 416_200_000_000}
    result = resolve_sec_metric("revenue", facts)
    assert result == 416_200_000_000


def test_sec_revenue_fallback():
    """Primary 태그 없으면 Revenues fallback."""
    facts = {"Revenues": 215_900_000_000}
    result = resolve_sec_metric("revenue", facts)
    assert result == 215_900_000_000


def test_sec_revenue_not_found():
    """모든 fallback 실패 시 None."""
    facts = {"SomeOtherTag": 999}
    result = resolve_sec_metric("revenue", facts)
    assert result is None


def test_sec_operating_income():
    facts = {"OperatingIncomeLoss": 133_100_000_000}
    result = resolve_sec_metric("operating_income", facts)
    assert result == 133_100_000_000


def test_sec_unknown_metric():
    """정의되지 않은 metric 요청 시 None."""
    facts = {}
    result = resolve_sec_metric("unknown_metric", facts)
    assert result is None


def test_dart_매출액():
    result = resolve_dart_metric("매출액")
    assert result == "revenue"


def test_dart_영업이익():
    result = resolve_dart_metric("영업이익")
    assert result == "operating_income"


def test_dart_unknown():
    result = resolve_dart_metric("알수없는계정")
    assert result is None


def test_sec_concept_chains_has_all_required():
    required = ["revenue", "operating_income", "net_income", "shares_outstanding"]
    for key in required:
        assert key in SEC_CONCEPT_CHAINS, f"{key} missing from SEC_CONCEPT_CHAINS"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/tools/filing/test_concepts.py -v`
Expected: FAIL

- [ ] **Step 3: concepts.py 구현**

```python
# src/tools/filing/concepts.py
"""SEC XBRL 태그 fallback 체인 + DART 계정명 매핑."""

# SEC: metric → XBRL 태그 fallback 체인 (우선순위 순)
SEC_CONCEPT_CHAINS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "cost_of_revenue": ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss", "IncomeLossFromOperations"],
    "ebitda": [
        "EarningsBeforeInterestTaxesDepreciationAndAmortization",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps": [
        "EarningsPerShareBasic",
        "EarningsPerShareDiluted",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByOperatingActivities",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
    ],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    "total_debt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
    ],
}

# DART: 계정명 → metric key
DART_ACCOUNT_MAPPING: dict[str, str] = {
    "매출액": "revenue",
    "매출원가": "cost_of_revenue",
    "매출총이익": "gross_profit",
    "영업이익": "operating_income",
    "당기순이익": "net_income",
    "기본주당이익": "eps",
    "자산총계": "total_assets",
    "부채총계": "total_liabilities",
    "자본총계": "total_equity",
    "현금및현금성자산": "cash_and_equivalents",
    "영업활동으로인한현금흐름": "operating_cash_flow",
    "영업활동현금흐름": "operating_cash_flow",
    "유형자산의취득": "capex",
    "유형자산취득": "capex",
}


def resolve_sec_metric(metric: str, facts: dict[str, float | int]) -> float | None:
    """SEC XBRL facts에서 metric에 해당하는 값을 fallback 체인으로 검색."""
    chain = SEC_CONCEPT_CHAINS.get(metric)
    if not chain:
        return None
    for tag in chain:
        if tag in facts:
            return float(facts[tag])
    return None


def resolve_dart_metric(account_nm: str) -> str | None:
    """DART 계정명을 metric key로 변환."""
    return DART_ACCOUNT_MAPPING.get(account_nm)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/tools/filing/test_concepts.py -v`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add src/tools/filing/concepts.py tests/tools/filing/test_concepts.py
git commit -m "feat(filing): add XBRL concept mapping with fallback chains"
```

---

### Task 4: SECFilingParser — XBRL 숫자 추출

**Files:**
- Create: `src/tools/filing/sec_parser.py`
- Create: `tests/tools/filing/test_sec_parser.py`

핵심: companyfacts API에서 19개 재무 숫자를 추출하고 FilingFacts로 반환.
텍스트 추출 (Guidance/Risk)은 Task 6에서 추가.

- [ ] **Step 1: 테스트 작성 — XBRL 숫자 추출**

```python
# tests/tools/filing/test_sec_parser.py
from decimal import Decimal
from unittest.mock import AsyncMock, patch

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
                            {"fy": 2024, "fp": "FY", "val": 391_035_000_000, "form": "10-K", "filed": "2024-11-01"},
                            {"fy": 2025, "fp": "FY", "val": 416_200_000_000, "form": "10-K", "filed": "2025-10-31"},
                        ]
                    }
                },
                "OperatingIncomeLoss": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "val": 123_216_000_000, "form": "10-K", "filed": "2024-11-01"},
                            {"fy": 2025, "fp": "FY", "val": 133_100_000_000, "form": "10-K", "filed": "2025-10-31"},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "val": 93_736_000_000, "form": "10-K", "filed": "2024-11-01"},
                            {"fy": 2025, "fp": "FY", "val": 112_010_000_000, "form": "10-K", "filed": "2025-10-31"},
                        ]
                    }
                },
                "CommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {"fy": 2025, "fp": "FY", "val": 15_115_786_000, "form": "10-K", "filed": "2025-10-31"},
                        ]
                    }
                },
            },
            "dei": {},
        },
    }


@patch("src.tools.filing.sec_parser.httpx.AsyncClient")
async def test_parse_extracts_financials(mock_client_cls, parser, mock_companyfacts_aapl):
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_companyfacts_aapl
    mock_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
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
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_companyfacts_aapl
    mock_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/tools/filing/test_sec_parser.py -v`
Expected: FAIL

- [ ] **Step 3: sec_parser.py 구현 — XBRL 숫자 추출**

```python
# src/tools/filing/sec_parser.py
"""SEC EDGAR 공시 파싱: companyfacts API (XBRL) + edgartools (텍스트)."""

import json
import logging
import re
import time
from decimal import Decimal
from pathlib import Path

import httpx
from langchain_core.language_models import BaseChatModel

from src.tools.filing.concepts import SEC_CONCEPT_CHAINS
from src.tools.filing.models import (
    Comparison,
    FilingFacts,
    FinancialMetric,
)

logger = logging.getLogger(__name__)

_SEC_USER_AGENT = "invest-jarvis research@example.com"
_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_CIK_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
_CACHE_DIR = Path("data/cache/filings")
_CACHE_TTL = 24 * 3600  # 24시간


class SECFilingParser:
    """SEC EDGAR에서 10-K/10-Q XBRL 재무 데이터를 추출한다."""

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        self.llm = llm

    async def parse(self, ticker: str) -> FilingFacts | None:
        """ticker에 대한 최신 10-K/10-Q 재무 데이터를 추출한다."""
        try:
            cik = await self._resolve_cik(ticker.upper())
            if cik is None:
                logger.warning("CIK not found for %s", ticker)
                return None

            raw = await self._fetch_companyfacts(cik)
            if raw is None:
                return None

            facts = self._build_filing_facts(ticker.upper(), raw)
            if facts and self.llm:
                await self._enrich_with_text(ticker.upper(), facts)
            return facts
        except Exception:
            logger.exception("SEC filing parse failed for %s", ticker)
            return None

    async def _resolve_cik(self, ticker: str) -> int | None:
        """ticker → CIK 변환."""
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _SEC_USER_AGENT}
        ) as client:
            resp = await client.get(_CIK_LOOKUP_URL)
            resp.raise_for_status()
            data = resp.json()
        for entry in data.values():
            if entry["ticker"].upper() == ticker:
                return entry["cik_str"]
        return None

    async def _fetch_companyfacts(self, cik: int) -> dict | None:
        """companyfacts API 호출. 캐시 있으면 사용."""
        cache_path = _CACHE_DIR / f"sec_facts_{cik}.json"
        if cache_path.exists():
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime < _CACHE_TTL:
                return json.loads(cache_path.read_text(encoding="utf-8"))

        url = _COMPANYFACTS_URL.format(cik=cik)
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _SEC_USER_AGENT}
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def _build_filing_facts(self, ticker: str, raw: dict) -> FilingFacts | None:
        """companyfacts 응답에서 FilingFacts를 구성한다."""
        us_gaap = raw.get("facts", {}).get("us-gaap", {})

        latest_values: dict[str, float] = {}
        prev_values: dict[str, float] = {}
        filing_date = ""
        fiscal_period = ""

        for metric, chain in SEC_CONCEPT_CHAINS.items():
            for tag in chain:
                if tag not in us_gaap:
                    continue
                unit_key = "shares" if "Shares" in tag or "shares" in tag.lower() else "USD"
                entries = us_gaap[tag].get("units", {}).get(unit_key, [])
                annual = [e for e in entries if e.get("form") == "10-K" and e.get("fp") == "FY"]
                if not annual:
                    continue
                annual.sort(key=lambda e: e.get("filed", ""))
                latest = annual[-1]
                latest_values[metric] = float(latest["val"])
                if not filing_date or latest.get("filed", "") > filing_date:
                    filing_date = latest.get("filed", "")
                    fiscal_period = f"FY{latest.get('fy', '')}"
                if len(annual) >= 2:
                    prev_values[metric] = float(annual[-2]["val"])
                break

        if not latest_values:
            return None

        financials: dict[str, FinancialMetric] = {}
        for metric, val in latest_values.items():
            unit = "shares" if metric == "shares_outstanding" else "USD"
            financials[metric] = FinancialMetric(
                value=Decimal(str(val)),
                unit=unit,
                scale="billions" if abs(val) >= 1e9 else "millions",
                source="XBRL",
                confidence="high",
            )

        rev = latest_values.get("revenue")
        if rev and rev > 0:
            for margin_key, numerator_key in [
                ("gross_margin", "gross_profit"),
                ("operating_margin", "operating_income"),
                ("net_margin", "net_income"),
            ]:
                num = latest_values.get(numerator_key)
                if num is not None:
                    margin_pct = num / rev * 100
                    financials[margin_key] = FinancialMetric(
                        value=Decimal(str(round(margin_pct, 2))),
                        unit="percent",
                        scale="percent",
                        source="XBRL",
                        confidence="high",
                    )

        ocf = latest_values.get("operating_cash_flow")
        capex = latest_values.get("capex")
        if ocf is not None and capex is not None:
            fcf = ocf - capex
            financials["fcf"] = FinancialMetric(
                value=Decimal(str(fcf)),
                unit="USD",
                scale="billions" if abs(fcf) >= 1e9 else "millions",
                source="XBRL",
                confidence="high",
            )

        comparisons: dict[str, Comparison] = {}
        for metric, current in latest_values.items():
            prev = prev_values.get(metric)
            if prev and prev != 0:
                change = (current - prev) / abs(prev) * 100
                comparisons[f"{metric}_yoy"] = Comparison(
                    change_pct=round(change, 2),
                    previous=Decimal(str(prev)),
                    period=f"FY{int(fiscal_period[2:]) - 1}" if fiscal_period.startswith("FY") else "",
                )

        return FilingFacts(
            ticker=ticker,
            market="US",
            filing_type="10-K",
            filing_date=filing_date,
            fiscal_period=fiscal_period,
            source_url=_COMPANYFACTS_URL.format(cik=0),
            financials=financials,
            comparisons=comparisons,
            text_insights=[],
        )

    async def _enrich_with_text(self, ticker: str, facts: FilingFacts) -> None:
        """edgartools로 10-K 텍스트 추출 후 Guidance/Risk LLM 추출. Task 6에서 구현."""
        pass
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/tools/filing/test_sec_parser.py -v`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add src/tools/filing/sec_parser.py tests/tools/filing/test_sec_parser.py
git commit -m "feat(filing): implement SECFilingParser XBRL number extraction"
```

---

### Task 5: DARTFilingParser — XBRL 숫자 추출

**Files:**
- Create: `src/tools/filing/dart_parser.py`
- Create: `tests/tools/filing/test_dart_parser.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/tools/filing/test_dart_parser.py
from decimal import Decimal
from unittest.mock import AsyncMock, patch

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
            {"account_nm": "매출액", "thstrm_amount": "333605938000000", "frmtrm_amount": "300870903000000", "sj_div": "IS"},
            {"account_nm": "영업이익", "thstrm_amount": "43601051000000", "frmtrm_amount": "32725961000000", "sj_div": "IS"},
            {"account_nm": "당기순이익", "thstrm_amount": "45206805000000", "frmtrm_amount": "34451351000000", "sj_div": "IS"},
            {"account_nm": "자산총계", "thstrm_amount": "566942110000000", "frmtrm_amount": "514531948000000", "sj_div": "BS"},
            {"account_nm": "자본총계", "thstrm_amount": "436320337000000", "frmtrm_amount": "402192070000000", "sj_div": "BS"},
            {"account_nm": "부채총계", "thstrm_amount": "130621773000000", "frmtrm_amount": "112339878000000", "sj_div": "BS"},
        ],
    }


@patch("src.tools.filing.dart_parser.httpx.AsyncClient")
async def test_parse_extracts_financials(mock_client_cls, parser, mock_dart_financials):
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_dart_financials
    mock_response.raise_for_status = lambda: None

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
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_dart_financials
    mock_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    facts = await parser.parse("005930", corp_code="00126380", bsns_year="2025")

    assert "revenue_yoy" in facts.comparisons
    assert abs(facts.comparisons["revenue_yoy"].change_pct - 10.88) < 0.1


@patch("src.tools.filing.dart_parser.httpx.AsyncClient")
async def test_parse_handles_api_failure(mock_client_cls, parser):
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("Connection timeout")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    facts = await parser.parse("005930", corp_code="00126380", bsns_year="2025")
    assert facts is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/tools/filing/test_dart_parser.py -v`
Expected: FAIL

- [ ] **Step 3: dart_parser.py 구현**

```python
# src/tools/filing/dart_parser.py
"""DART 공시 파싱: fnlttSinglAcntAll API (XBRL) + document.xml (텍스트)."""

import json
import logging
import re
import time
from decimal import Decimal
from pathlib import Path

import httpx
from langchain_core.language_models import BaseChatModel

from src.tools.filing.concepts import resolve_dart_metric
from src.tools.filing.models import (
    Comparison,
    FilingFacts,
    FinancialMetric,
)

logger = logging.getLogger(__name__)

_DART_API_BASE = "https://opendart.fss.or.kr/api"
_CACHE_DIR = Path("data/cache/filings")
_CACHE_TTL = 24 * 3600


class DARTFilingParser:
    """DART에서 사업보고서/분기보고서 재무 데이터를 추출한다."""

    def __init__(self, api_key: str, llm: BaseChatModel | None = None) -> None:
        self.api_key = api_key
        self.llm = llm

    async def parse(
        self,
        stock_code: str,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = "11011",
    ) -> FilingFacts | None:
        """DART XBRL 재무제표를 추출한다."""
        try:
            raw = await self._fetch_financials(corp_code, bsns_year, reprt_code)
            if raw is None:
                return None
            facts = self._build_filing_facts(stock_code, bsns_year, reprt_code, raw)
            if facts and self.llm:
                await self._enrich_with_text(corp_code, facts)
            return facts
        except Exception:
            logger.exception("DART filing parse failed for %s", stock_code)
            return None

    async def _fetch_financials(
        self, corp_code: str, bsns_year: str, reprt_code: str
    ) -> list[dict] | None:
        cache_path = _CACHE_DIR / f"dart_facts_{corp_code}_{bsns_year}_{reprt_code}.json"
        if cache_path.exists():
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime < _CACHE_TTL:
                return json.loads(cache_path.read_text(encoding="utf-8"))

        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": "CFS",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_DART_API_BASE}/fnlttSinglAcntAll.json", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "000":
            logger.warning("DART API error: %s", data.get("message"))
            return None

        items = data.get("list", [])
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return items

    def _build_filing_facts(
        self, stock_code: str, bsns_year: str, reprt_code: str, items: list[dict]
    ) -> FilingFacts | None:
        financials: dict[str, FinancialMetric] = {}
        comparisons: dict[str, Comparison] = {}
        seen_metrics: set[str] = set()

        for item in items:
            account_nm = item.get("account_nm", "")
            metric_key = resolve_dart_metric(account_nm)
            if not metric_key or metric_key in seen_metrics:
                continue
            seen_metrics.add(metric_key)

            current_str = item.get("thstrm_amount", "").replace(",", "")
            prev_str = item.get("frmtrm_amount", "").replace(",", "")

            if not current_str or not current_str.lstrip("-").isdigit():
                continue

            current = int(current_str)
            financials[metric_key] = FinancialMetric(
                value=Decimal(str(current)),
                unit="KRW",
                scale="billions" if abs(current) >= 1e12 else "millions",
                source="XBRL",
                confidence="high",
            )

            if prev_str and prev_str.lstrip("-").isdigit():
                prev = int(prev_str)
                if prev != 0:
                    change = (current - prev) / abs(prev) * 100
                    comparisons[f"{metric_key}_yoy"] = Comparison(
                        change_pct=round(change, 2),
                        previous=Decimal(str(prev)),
                        period=f"FY{int(bsns_year) - 1}",
                    )

        if not financials:
            return None

        rev = financials.get("revenue")
        if rev and float(rev.value) > 0:
            rev_val = float(rev.value)
            for margin_key, num_key in [
                ("gross_margin", "gross_profit"),
                ("operating_margin", "operating_income"),
                ("net_margin", "net_income"),
            ]:
                num = financials.get(num_key)
                if num:
                    margin_pct = float(num.value) / rev_val * 100
                    financials[margin_key] = FinancialMetric(
                        value=Decimal(str(round(margin_pct, 2))),
                        unit="percent",
                        scale="percent",
                        source="XBRL",
                        confidence="high",
                    )

        ocf = financials.get("operating_cash_flow")
        capex = financials.get("capex")
        if ocf and capex:
            fcf = float(ocf.value) - float(capex.value)
            financials["fcf"] = FinancialMetric(
                value=Decimal(str(int(fcf))),
                unit="KRW",
                scale="billions" if abs(fcf) >= 1e12 else "millions",
                source="XBRL",
                confidence="high",
            )

        report_type_map = {"11011": "사업보고서", "11014": "분기보고서", "11012": "반기보고서"}

        return FilingFacts(
            ticker=stock_code,
            market="KR",
            filing_type=report_type_map.get(reprt_code, "사업보고서"),
            filing_date="",
            fiscal_period=f"FY{bsns_year}",
            source_url=f"{_DART_API_BASE}/fnlttSinglAcntAll.json",
            financials=financials,
            comparisons=comparisons,
            text_insights=[],
        )

    async def _enrich_with_text(self, corp_code: str, facts: FilingFacts) -> None:
        """document.xml에서 4개 사업 섹션 텍스트 추출. Task 7에서 구현."""
        pass
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/tools/filing/test_dart_parser.py -v`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add src/tools/filing/dart_parser.py tests/tools/filing/test_dart_parser.py
git commit -m "feat(filing): implement DARTFilingParser XBRL number extraction"
```

---

### Task 6: SECFilingParser — 텍스트 추출 (Guidance + Risk)

**Files:**
- Modify: `src/tools/filing/sec_parser.py`
- Modify: `tests/tools/filing/test_sec_parser.py`

edgartools `markdown()`으로 Item 7 (Guidance) + Item 1A (Risk) 텍스트를 추출하고 LLM으로 구조화.

- [ ] **Step 1: 섹션 추출 유틸 테스트 추가**

`tests/tools/filing/test_sec_parser.py`에 추가:

```python
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
```

- [ ] **Step 2: _extract_section 함수 구현**

`src/tools/filing/sec_parser.py`에 모듈 레벨 함수 추가:

```python
def _extract_section(markdown: str, item_pattern: str) -> str:
    """마크다운에서 ## Item X. 으로 시작하는 섹션 텍스트를 추출한다."""
    pattern = rf"^##\s*{item_pattern}.*$"
    match = re.search(pattern, markdown, re.MULTILINE | re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^## ", markdown[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(markdown)
    return markdown[start:end].strip()
```

- [ ] **Step 3: _enrich_with_text 구현 (edgartools + LLM)**

`sec_parser.py`의 `_enrich_with_text` 메서드를 구현. edgartools로 마크다운 추출 → Item 7/1A 섹션 분리 → LLM Guidance/Risk 추출. LLM 실패 시 graceful 처리 (text_insights에 raw_section만 저장).

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/tools/filing/test_sec_parser.py -v`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add src/tools/filing/sec_parser.py tests/tools/filing/test_sec_parser.py
git commit -m "feat(filing): add SEC text extraction for Guidance and Risk"
```

---

### Task 7: DARTFilingParser — 텍스트 추출 (4개 사업 섹션)

**Files:**
- Modify: `src/tools/filing/dart_parser.py`
- Modify: `tests/tools/filing/test_dart_parser.py`

- [ ] **Step 1: XML 섹션 추출 테스트 추가**

`tests/tools/filing/test_dart_parser.py`에 추가:

```python
def test_extract_dart_section():
    from src.tools.filing.dart_parser import _extract_dart_section

    xml_content = """<BODY>
<TITLE>1. 사업의 개요</TITLE>
<P>개요 내용</P>
<TITLE>2. 주요 제품 및 서비스</TITLE>
<P>반도체 매출 비중 71%</P>
<TABLE><TD>DS</TD><TD>71%</TD></TABLE>
<TITLE>3. 원재료 및 생산설비</TITLE>
<P>평택 P4 라인</P>
</BODY>"""

    section = _extract_dart_section(xml_content, "주요 제품 및 서비스")
    assert "반도체 매출 비중 71%" in section
    assert "평택 P4" not in section


def test_extract_dart_section_not_found():
    from src.tools.filing.dart_parser import _extract_dart_section

    section = _extract_dart_section("<BODY><TITLE>1. 개요</TITLE></BODY>", "주요 제품")
    assert section == ""
```

- [ ] **Step 2: _extract_dart_section 함수 구현**

`src/tools/filing/dart_parser.py`에 모듈 레벨 함수 추가:

```python
def _extract_dart_section(xml_content: str, section_title: str) -> str:
    """DART XML에서 <TITLE> 태그 기반으로 섹션 텍스트를 추출한다."""
    pattern = rf"<TITLE[^>]*>[^<]*{re.escape(section_title)}[^<]*</TITLE>"
    match = re.search(pattern, xml_content, re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    next_title = re.search(r"<TITLE[^>]*>", xml_content[start:], re.IGNORECASE)
    end = start + next_title.start() if next_title else len(xml_content)
    raw = xml_content[start:end]
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text
```

- [ ] **Step 3: _enrich_with_text 구현 (document.xml + LLM)**

`dart_parser.py`의 `_enrich_with_text` 메서드를 구현. document.xml ZIP 다운로드 → 4개 사업 섹션 추출 → LLM 구조화 추출 (섹션별 필수 항목 체크리스트). LLM 실패 시 raw_section만 저장.

4개 섹션 프롬프트에 필수 추출 항목:
- 주요 제품 및 서비스 → 매출비중, 비중변화, 신규
- 원재료 및 생산설비 → 원재료가격, 가동률, 증설계획, CAPEX
- 매출 및 수주상황 → 수주잔고, 수주증감률, 수주추이, 주요고객
- 주요계약 및 연구개발활동 → 대형계약, R&D투자, 핵심테마

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/tools/filing/test_dart_parser.py -v`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add src/tools/filing/dart_parser.py tests/tools/filing/test_dart_parser.py
git commit -m "feat(filing): add DART text extraction for 4 business sections"
```

---

### Task 8: ImpactCalculator (4가지 유형)

**Files:**
- Create: `src/tools/filing/impact.py`
- Create: `tests/tools/filing/test_impact.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/tools/filing/test_impact.py
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
            "revenue_yoy": Comparison(change_pct=6.4, previous=Decimal("391000000000"), period="FY2024"),
            "operating_income_yoy": Comparison(change_pct=8.0, previous=Decimal("123200000000"), period="FY2024"),
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
            "operating_income_yoy": Comparison(change_pct=-25.0, previous=Decimal("50"), period="FY2024"),
        },
    )
    impact = calculator.calculate(facts)
    assert impact.direction == "부정"


def test_유상증자_impact(calculator):
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


def test_전환사채_impact(calculator):
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


def test_공급계약_impact(calculator):
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/tools/filing/test_impact.py -v`
Expected: FAIL

- [ ] **Step 3: impact.py 구현**

```python
# src/tools/filing/impact.py
"""공시 유형별 임팩트 정량 계산."""

import logging

from src.tools.filing.models import FilingFacts, FilingImpact

logger = logging.getLogger(__name__)


class ImpactCalculator:
    """FilingFacts에서 유형별 임팩트를 계산한다."""

    def calculate(self, facts: FilingFacts) -> FilingImpact:
        detail = facts.disclosure_detail

        if detail and detail.detail_type == "유상증자":
            return self._calc_유상증자(facts)
        if detail and detail.detail_type == "전환사채":
            return self._calc_전환사채(facts)
        if detail and detail.detail_type == "공급계약":
            return self._calc_공급계약(facts)
        return self._calc_실적발표(facts)

    def _calc_실적발표(self, facts: FilingFacts) -> FilingImpact:
        metrics: dict[str, float] = {}
        for key, comp in facts.comparisons.items():
            metrics[key.replace("_yoy", "_yoy_pct")] = comp.change_pct

        oi = facts.financials.get("operating_margin")
        if oi:
            metrics["operating_margin_pct"] = float(oi.value)

        direction = self._infer_direction(facts)
        severity = self._infer_severity(metrics)

        parts = []
        rev_yoy = metrics.get("revenue_yoy_pct")
        if rev_yoy is not None:
            parts.append(f"매출 YoY {rev_yoy:+.1f}%")
        oi_yoy = metrics.get("operating_income_yoy_pct")
        if oi_yoy is not None:
            parts.append(f"영업이익 YoY {oi_yoy:+.1f}%")

        return FilingImpact(
            facts=facts,
            impact_type="실적발표",
            metrics=metrics,
            severity=severity,
            direction=direction,
            summary=", ".join(parts) if parts else "비교 데이터 없음",
            confidence="high" if facts.comparisons else "low",
        )

    def _calc_유상증자(self, facts: FilingFacts) -> FilingImpact:
        detail = facts.disclosure_detail
        shares = facts.financials.get("shares_outstanding")
        equity = facts.financials.get("total_equity")

        metrics: dict[str, float] = {}
        if detail.new_shares and shares:
            total_after = float(shares.value) + detail.new_shares
            metrics["dilution_pct"] = round(detail.new_shares / total_after * 100, 2)
            metrics["new_shares"] = float(detail.new_shares)
        if detail.issue_price:
            metrics["issue_price"] = float(detail.issue_price)
        if detail.new_shares and detail.issue_price:
            proceeds = detail.new_shares * float(detail.issue_price)
            metrics["proceeds"] = proceeds
            if equity:
                metrics["proceeds_to_equity_pct"] = round(proceeds / float(equity.value) * 100, 2)

        return FilingImpact(
            facts=facts,
            impact_type="유상증자",
            metrics=metrics,
            severity="High" if metrics.get("dilution_pct", 0) > 10 else "Medium",
            direction="부정",
            summary=f"희석률 {metrics.get('dilution_pct', 0):.1f}%, 자금용도 {detail.purpose or '미공개'}",
            confidence="medium",
        )

    def _calc_전환사채(self, facts: FilingFacts) -> FilingImpact:
        detail = facts.disclosure_detail
        shares = facts.financials.get("shares_outstanding")

        metrics: dict[str, float] = {}
        if detail.conversion_shares and shares:
            metrics["overhang_pct"] = round(
                detail.conversion_shares / float(shares.value) * 100, 2
            )
            metrics["conversion_shares"] = float(detail.conversion_shares)
        if detail.conversion_price:
            metrics["conversion_price"] = float(detail.conversion_price)
        if detail.cb_amount:
            metrics["cb_amount"] = float(detail.cb_amount)

        return FilingImpact(
            facts=facts,
            impact_type="전환사채",
            metrics=metrics,
            severity="High" if metrics.get("overhang_pct", 0) > 10 else "Medium",
            direction="부정",
            summary=f"오버행 {metrics.get('overhang_pct', 0):.1f}%, 만기 {detail.maturity_date or '미공개'}",
            confidence="medium",
        )

    def _calc_공급계약(self, facts: FilingFacts) -> FilingImpact:
        detail = facts.disclosure_detail
        revenue = facts.financials.get("revenue")

        metrics: dict[str, float] = {}
        if detail.contract_amount:
            metrics["contract_amount"] = float(detail.contract_amount)
            if revenue and float(revenue.value) > 0:
                metrics["revenue_ratio_pct"] = round(
                    float(detail.contract_amount) / float(revenue.value) * 100, 2
                )

        return FilingImpact(
            facts=facts,
            impact_type="공급계약",
            metrics=metrics,
            severity="High" if metrics.get("revenue_ratio_pct", 0) > 10 else "Medium",
            direction="긍정",
            summary=f"매출 대비 {metrics.get('revenue_ratio_pct', 0):.1f}%, 상대방 {detail.counterparty or '미공개'}",
            confidence="medium",
        )

    def _infer_direction(self, facts: FilingFacts) -> str:
        if not facts.comparisons:
            return "중립"
        positive = sum(1 for c in facts.comparisons.values() if c.change_pct > 0)
        negative = sum(1 for c in facts.comparisons.values() if c.change_pct < 0)
        if positive > negative:
            return "긍정"
        if negative > positive:
            return "부정"
        return "중립"

    def _infer_severity(self, metrics: dict[str, float]) -> str:
        changes = [abs(v) for k, v in metrics.items() if "yoy_pct" in k]
        if not changes:
            return "Low"
        avg = sum(changes) / len(changes)
        if avg > 20:
            return "High"
        if avg > 5:
            return "Medium"
        return "Low"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/tools/filing/test_impact.py -v`
Expected: ALL PASS

- [ ] **Step 5: __init__.py에 ImpactCalculator export 추가**

`src/tools/filing/__init__.py`에 추가:
```python
from src.tools.filing.impact import ImpactCalculator
```

- [ ] **Step 6: 커밋**

```bash
git add src/tools/filing/impact.py src/tools/filing/__init__.py tests/tools/filing/test_impact.py
git commit -m "feat(filing): implement ImpactCalculator for 4 disclosure types"
```

---

### Task 9: DeepDivePipeline 통합

**Files:**
- Modify: `src/pipelines/deep_dive.py`
- Modify: `src/llm/models.py`
- Modify: `src/llm/analyzer.py`

- [ ] **Step 1: DeepDivePipeline에 filing_parser + impact_calculator 주입**

`src/pipelines/deep_dive.py`의 `__init__`에 선택적 파라미터 추가:

```python
from src.tools.filing.models import FilingFacts, FilingImpact
from src.tools.filing.impact import ImpactCalculator
from src.tools.filing.sec_parser import SECFilingParser
from src.tools.filing.dart_parser import DARTFilingParser
```

`__init__`에 `filing_parser` 및 `impact_calculator` 파라미터 추가. `run()`에서 기존 병렬 실행 블록에 `filing_parser.parse(ticker)` 추가. 결과를 `filing_facts`, `filing_impact`로 return dict에 포함.

- [ ] **Step 2: IntegratedAnalysisInput 확장**

`src/llm/models.py`의 `IntegratedAnalysisInput`에 3개 필드 추가:
```python
filing_financials: str | None = None
filing_impact: str | None = None
filing_text_insights: str | None = None
```

- [ ] **Step 3: 종합 분석 프롬프트에 filing 컨텍스트 추가**

`src/llm/analyzer.py`의 `generate_integrated_analysis` 함수에서 filing 데이터를 프롬프트 user 메시지에 추가. `ainvoke` 호출 시 새 필드를 변수로 전달.

- [ ] **Step 4: 기존 테스트 통과 확인**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add src/pipelines/deep_dive.py src/llm/models.py src/llm/analyzer.py
git commit -m "feat(filing): integrate FilingParser into DeepDivePipeline"
```

---

### Task 10: CLI 출력 + 초기화

**Files:**
- Modify: `src/cli/main.py`

- [ ] **Step 1: 재무 테이블 + 임팩트 패널 + 사업 인사이트 출력 함수 추가**

`src/cli/main.py`에 3개 함수 추가:
- `display_filing_financials(facts: FilingFacts) -> Table` — Rich Table
- `display_filing_impact(impact: FilingImpact) -> Panel` — 임팩트 Rich Panel
- `display_text_insights(facts: FilingFacts) -> Panel | None` — 인사이트 Panel

- [ ] **Step 2: analyze 커맨드에서 FilingParser 초기화**

analyze 함수에서 ticker 유형에 따라 SECFilingParser 또는 DARTFilingParser 생성, DeepDivePipeline에 주입.

- [ ] **Step 3: analyze 출력에 filing 섹션 추가**

결과에 `filing_facts`가 있으면 재무 테이블 + 임팩트 패널 + 사업 인사이트 순서로 출력.

- [ ] **Step 4: 기존 테스트 통과 확인**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add src/cli/main.py
git commit -m "feat(filing): add CLI output for filing financials, impact, and insights"
```

---

### Task 11: 문서 업데이트 + 최종 검증

**Files:**
- Modify: `docs/FEATURES.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/spec/disclosure-intelligence.md`

- [ ] **Step 1: docs/FEATURES.md 업데이트**

섹션 2 (Deep Dive Analysis)에 공시 재무 + 임팩트 + 사업 인사이트 설명 추가.

- [ ] **Step 2: docs/ARCHITECTURE.md 업데이트**

Tools 섹션에 `filing/` 모듈 추가. 캐싱 전략에 Filing JSON Cache 추가.

- [ ] **Step 3: Feature spec status 업데이트**

`docs/spec/disclosure-intelligence.md`: `Status: Draft` → `Status: Shipped`

- [ ] **Step 4: 전체 테스트 + 린트**

Run: `uv run pytest tests/ -v --cov=src/tools/filing`
Run: `uv run ruff check src/tools/filing/ tests/tools/filing/`
Expected: ALL PASS, 린트 에러 없음

- [ ] **Step 5: 커밋**

```bash
git add docs/FEATURES.md docs/ARCHITECTURE.md docs/spec/disclosure-intelligence.md
git commit -m "docs: update FEATURES.md and ARCHITECTURE.md for disclosure intelligence"
```

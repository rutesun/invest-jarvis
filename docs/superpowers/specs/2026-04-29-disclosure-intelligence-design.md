# Design: 공시 원문 파싱 + 정량 시뮬레이션 (Disclosure Intelligence)

Generated on 2026-04-29
Branch: main
Repo: invest-jarvis
Status: APPROVED
Tasks: ROADMAP Task 1 (공시 원문 파싱) + Task 6 (공시 정량 시뮬레이션)
Change record: `docs/changes/disclosure-intelligence.md`

---

## Problem Statement

`jarvis analyze AAPL` 실행 시 공시 **제목만** 출력됨 (예: "[8-K] Material Contract Agreement").
"계약 금액이 얼마인지", "가이던스 상향/하향인지", "희석 비율이 몇 %인지" 전혀 없음.
현재는 ChatGPT에 10-K 원문 수동 복붙해서 분석 중.

**Task 1**: 공시 원문에서 재무 숫자 + 텍스트 인사이트 자동 추출
**Task 6**: 추출된 데이터로 공시 유형별 임팩트 정량화

## Design Decisions

### 1. 하이브리드 접근 (규칙 + LLM)

숫자 추출은 XBRL/정규식 (규칙 기반), 임팩트 해석은 LLM.
핵심 원칙: **"숫자는 규칙이 뽑고, 의미는 LLM이 해석한다."**

**검토한 대안:**
- A) 규칙 기반만: 정확하지만 Guidance/Risk 같은 비정형 텍스트 처리 불가
- B) LLM 기반만: 유연하지만 숫자 환각 위험, 비용 높음
- **C) 하이브리드 (선택)**: 각각의 강점만 활용. 숫자는 정확, 해석은 유연

**Confidence 체계:**

| 출처 | Confidence | 이유 |
|------|-----------|------|
| XBRL 태그 | high | 표준화된 구조, 회계감사 완료 |
| 테이블/정규식 | medium | 구조 있지만 포맷 변동 가능 |
| LLM 추출 숫자 | low | 환각 가능성 |

### 2. 분리된 파서 + 공유 모델 (Approach B)

**검토한 대안:**
- A) 단일 FilingIntelligenceTool: DisclosureTool 확장. 비대해짐, 단일 책임 위반.
- **B) 분리된 파서 (선택)**: SECFilingParser / DARTFilingParser / ImpactCalculator 독립.
- C) 파이프라인 스테이지: daily_report처럼 스테이지 분리. 단일 종목 분석에 오버엔지니어링.

```
DisclosureTool (기존, 메타데이터만)
  ↓ filing URLs
SECFilingParser / DARTFilingParser (신규, 숫자+텍스트 추출)
  ↓ FilingFacts
ImpactCalculator (신규, 정량 시뮬레이션)
  ↓ FilingImpact (원본 FilingFacts 참조 보존)
DeepDivePipeline에서 조합
```

각 컴포넌트가 독립적 — DeepDive 외 파이프라인 (report daily, screen 등)에서도 재사용 가능.
의존 방향: `FilingParser → FilingFacts ← ImpactCalculator`

### 3. JSON 파일 캐시

`data/cache/filings/{ticker}_{filing_type}_{date}.json`

**검토한 대안:**
- A) SQLite: 구조적 쿼리 가능하지만, 프로젝트에 SQLite 의존성 없음
- **B) JSON 파일 (선택)**: 기존 캐시 패턴 (sec_cik_cache.json 등)과 일치
- C) 캐시 없음: SEC/DART API가 multi-year 반환하지만, 속도 느림

### 4. SEC/DART 도구 선정

| | SEC | DART |
|---|---|---|
| 숫자 추출 | companyfacts API (XBRL) | fnlttSinglAcntAll API (XBRL) |
| 텍스트 추출 | edgartools `markdown()` | document.xml ZIP→XML 파싱 |
| 섹션 분리 | `## Item X.` regex | `<TITLE>` 태그 |
| 외부 의존성 | edgartools (신규) | 없음 (httpx 기존) |

**검증 결과 (2026-04-29 실시):**

SEC:
- AAPL 10-K: Revenue $416.2B, OI $133.1B, NI $112.0B 추출 성공
- NVDA: Revenues 태그 사용 (AAPL과 다른 태그) → fallback 체인 필요 확인
- JPM (은행): OperatingIncomeLoss 없음 → 업종별 태그 차이 확인
- Item 7 (MD&A): ~5,400 토큰. Haiku로 ~$0.01
- 8-K Item 2.02 필터링: `filing.items`에 "2.02" 문자열로 확인 가능

DART:
- 삼성전자 사업보고서: 매출 333.6조, 영업이익 43.6조 + 전기 비교 데이터 추출 성공
- document.xml: 136개 섹션, `<TITLE>` 태그로 깔끔 분리
- fnlttSinglAcntAll API: 전기(frmtrm_amount) 데이터 포함 → YoY 별도 계산 불필요

### 5. KR 사업보고서: Guidance/Risk 대신 사업 섹션

한국 사업보고서에는 SEC Item 7 (Guidance), Item 1A (Risk Factors)에 해당하는 섹션이 없음.
"이사의 경영진단"은 과거 실적 해설 수준, 구체적 숫자 가이던스 없음.

대신 투자에 실질적으로 유용한 4개 섹션을 추출:

| 섹션 | 추출 내용 |
|------|----------|
| 주요 제품 및 서비스 | 제품별 매출 비중, 전기 대비 비중 변화, 신규 제품/서비스 |
| 원재료 및 생산설비 | 주요 원재료 가격 동향, 가동률, 증설/감축 계획, CAPEX 규모 |
| 매출 및 수주상황 | 수주잔고 금액, 수주 증감률, 제품별 수주 추이, 주요 고객 변화 |
| 주요계약 및 연구개발활동 | 대형 계약 금액/상대방, R&D 투자 금액 및 매출 대비 비율, 핵심 연구 테마 |

US/KR 공통 `TextInsight` 모델로 통합. 시장별 추출 섹션만 다름.

---

## Data Models

### FinancialMetric

```python
class FinancialMetric(BaseModel):
    value: Decimal
    unit: str           # "USD" | "KRW"
    scale: str          # "millions" | "billions"
    source: str         # "XBRL" | "regex" | "LLM"
    confidence: str     # "high" | "medium" | "low"
```

### TextInsight

```python
class TextInsight(BaseModel):
    section: str                        # "주요 제품 및 서비스" | "Guidance" | ...
    extracted: dict[str, str | None]    # 필수 항목별 추출 결과
    additional: list[str]               # 기타 주목할 사항
    raw_section: str                    # 원문 (검증용)
```

LLM 프롬프트에 섹션별 필수 추출 항목을 체크리스트로 포함.
해당 정보 없으면 "없음" 반환 → extracted에서 None 비율로 추출률 수치화.

### GuidanceInfo (US 전용)

```python
class GuidanceInfo(BaseModel):
    period: str              # "Q2 FY2026"
    metric: str              # "revenue"
    range_low: Decimal | None
    range_high: Decimal | None
    direction: str           # "상향" | "하향" | "유지"
    raw_text: str            # 원문 인용
```

### Comparison

```python
class Comparison(BaseModel):
    change_pct: float
    previous: Decimal
    period: str              # "FY2024" | "Q2 2025"
```

### DisclosureDetail (Task 6 입력 — 주요사항보고서용)

```python
class DisclosureDetail(BaseModel):
    detail_type: str         # "전환사채" | "유상증자" | "공급계약"
    # 전환사채
    conversion_price: Decimal | None
    conversion_shares: int | None
    maturity_date: str | None
    cb_amount: Decimal | None
    # 유상증자
    new_shares: int | None
    issue_price: Decimal | None
    purpose: str | None
    # 공급계약
    contract_amount: Decimal | None
    counterparty: str | None
    contract_period: str | None
```

### FilingFacts (Task 1 출력)

```python
class FilingFacts(BaseModel):
    ticker: str
    market: str              # "US" | "KR"
    filing_type: str         # "10-K" | "10-Q" | "8-K" | "사업보고서" | "분기보고서" | "주요사항보고서"
    filing_date: str         # YYYY-MM-DD
    fiscal_period: str       # "FY2025" | "Q3 2025"
    source_url: str

    financials: dict[str, FinancialMetric]
    # 19개 키:
    # 손익: revenue, cost_of_revenue, gross_profit, operating_income, ebitda, net_income, eps
    # 현금흐름: operating_cash_flow, capex, fcf
    # 재무상태: total_assets, total_liabilities, total_equity,
    #          cash_and_equivalents, total_debt, shares_outstanding
    # 마진: gross_margin, operating_margin, net_margin

    comparisons: dict[str, Comparison]
    # 키: {metric}_yoy, {metric}_qoq

    text_insights: list[TextInsight]
    guidance: GuidanceInfo | None           # US 전용
    disclosure_detail: DisclosureDetail | None  # 주요사항보고서일 때만
```

### FilingImpact (Task 6 출력)

```python
class FilingImpact(BaseModel):
    facts: FilingFacts           # 원 데이터 보존
    impact_type: str             # "실적발표" | "유상증자" | "전환사채" | "공급계약"
    metrics: dict[str, float]    # 유형별 계산 결과
    severity: str                # "High" | "Medium" | "Low"
    direction: str               # "긍정" | "부정" | "중립"
    summary: str                 # LLM 해석 (한 줄)
    confidence: str              # "high" | "medium" | "low"
```

**ImpactCalculator metrics 키 (유형별):**

| 유형 | metrics 키 |
|------|-----------|
| 실적발표 | revenue_yoy_pct, operating_income_yoy_pct, operating_margin_pct, operating_margin_change_pp, net_income_yoy_pct, eps_yoy_pct, debt_to_equity_pct, cash_ratio_pct |
| 유상증자 | dilution_pct, new_shares, issue_price, proceeds, proceeds_to_equity_pct |
| 전환사채 | overhang_pct, conversion_price, conversion_shares, cb_amount, premium_to_current_pct |
| 공급계약 | contract_amount, revenue_ratio_pct, contract_duration_months, annual_revenue_impact_pct |

---

## Components

### File Structure

```
src/tools/filing/
├── __init__.py
├── models.py          # FilingFacts, FilingImpact, FinancialMetric 등
├── sec_parser.py      # SECFilingParser
├── dart_parser.py     # DARTFilingParser
├── impact.py          # ImpactCalculator
└── concepts.py        # XBRL concept mapping (태그 fallback 체인)
```

### SECFilingParser

- 입력: ticker
- 동작:
  1. companyfacts API → 19개 재무 숫자 (XBRL, confidence=high)
  2. edgartools `markdown()` → Item 7 → LLM Guidance 추출
  3. edgartools `markdown()` → Item 1A → LLM Risk 추출
  4. 8-K Item 2.02 필터링 → 실적발표 감지
- 출력: FilingFacts

### DARTFilingParser

- 입력: stock_code (6자리)
- 동작:
  1. fnlttSinglAcntAll API → 재무 숫자 (XBRL, confidence=high)
  2. document.xml ZIP → 섹션별 텍스트 추출 (4개 사업 섹션)
  3. 주요사항보고서 감지 시 → DisclosureDetail 파싱
- 출력: FilingFacts

### ImpactCalculator

- 입력: FilingFacts
- 동작: filing_type + disclosure_detail 기반 분기
  - 실적발표 → comparisons에서 서프라이즈 계산 (규칙)
  - 유상증자 → `new_shares / (shares_outstanding + new_shares)` (규칙)
  - 전환사채 → `conversion_shares / shares_outstanding` (규칙)
  - 공급계약 → `contract_amount / revenue` (규칙)
  - 각 결과에 LLM 해석 한 줄 추가
- 출력: FilingImpact (facts 참조 보존)

### XBRL Concept Mapping (concepts.py)

**SEC 태그 fallback 체인:**

| Metric | Primary | Fallback 1 | Fallback 2 |
|--------|---------|-----------|-----------|
| revenue | RevenueFromContractWithCustomerExcludingAssessedTax | Revenues | SalesRevenueNet |
| operating_income | OperatingIncomeLoss | IncomeLossFromOperations | - |
| net_income | NetIncomeLoss | ProfitLoss | - |
| operating_cash_flow | NetCashProvidedByOperatingActivities | - | - |
| capex | PaymentsToAcquirePropertyPlantAndEquipment | - | - |
| total_debt | LongTermDebt | LongTermDebtNoncurrent | - |
| shares_outstanding | CommonStockSharesOutstanding | EntityCommonStockSharesOutstanding | - |

**DART 계정명 매핑:**

| API account_nm | Metric | 비고 |
|----------------|--------|------|
| 매출액 | revenue | |
| 매출원가 | cost_of_revenue | |
| 매출총이익 | gross_profit | |
| 영업이익 | operating_income | |
| 당기순이익 | net_income | |
| 기본주당이익 | eps | 원 단위 |
| 자산총계 | total_assets | |
| 부채총계 | total_liabilities | |
| 자본총계 | total_equity | |
| 현금및현금성자산 | cash_and_equivalents | 재무상태표에서 |
| 장단기차입금 합산 | total_debt | 차입금+사채 합산 필요 |
| 발행주식총수 | shares_outstanding | 사업보고서 "주식의 총수" 섹션 |
| ebitda | ebitda | 직접 계산: operating_income + 감가상각비 |
| 영업활동현금흐름 | operating_cash_flow | 현금흐름표 |
| 유형자산취득 | capex | 현금흐름표 |
| fcf | fcf | 계산: operating_cash_flow - capex |
| gross_margin 등 | 마진 3종 | 계산: gross_profit / revenue 등 |

DART fnlttSinglAcntAll API에서 직접 추출 불가한 항목 (ebitda, fcf, 마진)은 추출된 값으로 계산.

---

## Pipeline Integration

### DeepDivePipeline 변경

```
jarvis analyze AAPL
  │
  ├─ [기존, 병렬] ────────────────────────────
  │   technical_tool    → TechnicalResult
  │   news_tool         → list[NewsArticle]
  │   fundamental_tool  → FundamentalSnapshot
  │   disclosure_tool   → list[DisclosureItem]
  │   flow_tool         → InvestorFlow
  │
  ├─ [신규, 병렬] ────────────────────────────
  │   filing_parser.parse(ticker) → FilingFacts
  │
  ├─ [신규, 순차] ────────────────────────────
  │   impact_calculator.calculate(facts) → FilingImpact
  │
  ├─ [기존, 수정] ────────────────────────────
  │   LLM 종합 분석 (IntegratedAnalysisInput에 filing 데이터 추가)
  │
  └─ CLI 출력
      ├─ [기존] 기술적 분석, 뉴스, 펀더멘탈...
      ├─ [신규] 재무 테이블 (Rich Table)
      ├─ [신규] 임팩트 패널
      └─ [신규] 사업 인사이트
```

`DeepDivePipeline.__init__`에 `filing_parser`와 `impact_calculator` 선택적 주입.
없으면 기존처럼 메타데이터만 출력 (하위 호환).

### IntegratedAnalysisInput 확장

```python
class IntegratedAnalysisInput(BaseModel):
    # ...기존 필드
    filing_financials: str | None       # 재무 테이블 텍스트
    filing_impact: str | None           # 임팩트 요약 텍스트
    filing_text_insights: str | None    # 사업 인사이트 텍스트
```

### CLI 출력 예시

US (AAPL):
```
┌─────────── 📊 공시 재무 (10-K FY2025) ────────────┐
│ 지표          │ 현재         │ YoY 변화           │
│ 매출          │ $416.2B      │ +6.4%              │
│ 영업이익      │ $133.1B      │ +8.0%              │
│ 순이익        │ $112.0B      │ +19.5%             │
│ 영업이익률    │ 32.0%        │ +0.5pp             │
│ FCF           │ $101.2B      │ +12.3%             │
└────────────────────────────────────────────────────┘
┌─────────── 💡 Guidance (Item 7) ──────────────────┐
│ Q2 FY2026 매출: $100-105B (상향)                   │
└────────────────────────────────────────────────────┘
```

KR (삼성전자):
```
┌─────────── 📊 공시 재무 (사업보고서 2025.12) ─────┐
│ 매출          │ 333.6조      │ +10.9%             │
│ 영업이익      │ 43.6조       │ +33.2%             │
└────────────────────────────────────────────────────┘
┌─────────── 🏭 사업 인사이트 ──────────────────────┐
│ [주요 제품] 반도체 매출 비중 65%→71% (+6pp)        │
│ [수주상황] HBM 수주잔고 전기 대비 2.3배            │
│ [생산설비] 평택 P4 라인 2026 상반기 가동 예정      │
│ [R&D] 투자 28.9조 (매출 대비 8.7%)                 │
└────────────────────────────────────────────────────┘
```

---

## Text Insight Extraction

### 섹션별 필수 추출 항목

LLM 프롬프트에 체크리스트로 포함. 해당 정보 없으면 "없음" 반환.

**US 10-K:**

| 섹션 | 필수 추출 항목 |
|------|---------------|
| Item 7 (Guidance) | 구체적 수치 (매출/이익 범위), 기간, 상향/하향/유지 |
| Item 1A (Risk) | 신규 등장 리스크, 상위 5개 리스크 |

**KR 사업보고서:**

| 섹션 | 필수 추출 항목 |
|------|---------------|
| 주요 제품 및 서비스 | 제품/사업별 매출 비중, 전기 대비 비중 변화, 신규 제품/서비스 |
| 원재료 및 생산설비 | 주요 원재료 가격 동향, 가동률, 증설/감축 계획, CAPEX 규모 |
| 매출 및 수주상황 | 수주잔고 금액, 수주 증감률, 제품별 수주 추이, 주요 고객 변화 |
| 주요계약 및 연구개발활동 | 대형 계약 금액/상대방, R&D 투자 금액 및 매출 대비 비율, 핵심 연구 테마 |

### Golden Set 검증

- US 5종목 + KR 5종목 (업종 다양하게 선정)
- 각 종목 사업보고서를 수동 검토 → 핵심 포인트 작성
- LLM 추출 결과와 비교: **recall 80% 이상** 목표
- extracted에서 None이 아닌 비율 = 추출률로 프롬프트 품질 수치화

---

## ImpactCalculator 출력 예시

### 실적발표 (삼성전자 사업보고서 2025.12)

```python
FilingImpact(
    facts=<FilingFacts>,  # 원 데이터 보존
    impact_type="실적발표",
    metrics={
        "revenue_yoy_pct": 10.9,
        "operating_income_yoy_pct": 33.2,
        "operating_margin_pct": 13.1,
        "operating_margin_change_pp": 2.2,
        "net_income_yoy_pct": 31.2,
        "debt_to_equity_pct": 29.9,
        "cash_ratio_pct": 13.3,
    },
    severity="High",
    direction="긍정",
    summary="매출 YoY +10.9%, 영업이익 YoY +33.2%로 반도체 업황 회복. 영업이익률 13.1% (+2.2pp)",
    confidence="high",
)
```

### 유상증자

```python
FilingImpact(
    facts=<FilingFacts>,
    impact_type="유상증자",
    metrics={
        "dilution_pct": 9.09,
        "new_shares": 1_000_000,
        "issue_price": 50_000,
        "proceeds": 50_000_000_000,
        "proceeds_to_equity_pct": 3.2,
    },
    severity="Medium",
    direction="부정",
    summary="신주 100만주 발행, 희석률 9.09%. 자금용도 시설투자 (500억원, 자본총계 대비 3.2%)",
    confidence="medium",
)
```

### 전환사채

```python
FilingImpact(
    facts=<FilingFacts>,
    impact_type="전환사채",
    metrics={
        "overhang_pct": 12.3,
        "conversion_price": 45_000,
        "conversion_shares": 2_222_222,
        "cb_amount": 100_000_000_000,
        "premium_to_current_pct": -5.3,
    },
    severity="High",
    direction="부정",
    summary="CB 1,000억원, 전환가 45,000원 (현재가 대비 -5.3%). 오버행 12.3%, 만기 2028-06",
    confidence="medium",
)
```

### 공급계약

```python
FilingImpact(
    facts=<FilingFacts>,
    impact_type="공급계약",
    metrics={
        "contract_amount": 500_000_000_000,
        "revenue_ratio_pct": 16.7,
        "contract_duration_months": 24,
        "annual_revenue_impact_pct": 8.3,
    },
    severity="High",
    direction="긍정",
    summary="공급계약 5,000억원 (전년 매출 대비 16.7%). 2년 계약, 연간 매출 기여 ~8.3%",
    confidence="medium",
)
```

---

## Error Handling

| 상황 | 대응 |
|------|------|
| XBRL API 실패 | 3회 재시도 (exponential backoff). 실패 시 filing 섹션 생략, 나머지 분석 계속 |
| edgartools 파싱 실패 | text_insights = [], guidance = None. 숫자만 출력 |
| DART document.xml 실패 | text_insights = []. XBRL 숫자는 별도 API라 영향 없음 |
| LLM 구조화 출력 실패 | raw text fallback. extracted 전부 None, additional에 원문 요약 |
| XBRL 태그 없음 (은행 등) | fallback 체인 시도 → 전부 실패 시 해당 metric = None |
| 주요사항보고서 비정형 | 정규식 실패 시 LLM fallback (confidence=low) |
| 비교 데이터 없음 | comparisons = {}. 절대값만 표시 |
| 캐시 손상 | 무시하고 API 재호출 |

---

## Constraints

- edgartools 외부 의존성 추가 (SEC 텍스트 추출용)
- LLM 비용: 종목당 ~$0.02-0.05 (Haiku 기준)
- SEC API rate limit: 10 req/sec (User-Agent 필수)
- filing_parser 미설정 시 기존 동작 유지 (하위 호환)

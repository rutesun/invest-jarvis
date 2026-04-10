# 섹터별 펀더멘털 지표 우선순위 설계

**날짜:** 2026-04-11
**상태:** 초안
**작성자:** Claude Code

## 개요

CLI 출력과 LLM 분석에서 섹터별 펀더멘털 지표의 우선순위 지정 및 강조 표시 기능을 추가합니다. 섹터마다 중요한 지표가 다르므로(예: 기술주는 PEG/PSR, 금융주는 ROE/P/B 중시), 사용자가 가장 관련성 높은 지표를 먼저 볼 수 있도록 시각적 강조를 제공합니다.

## 목표

1. 펀더멘털 분석 출력에서 섹터에 적합한 지표를 상단에 표시
2. 핵심 지표를 ⭐ 이모지와 볼드 포맷으로 강조
3. LLM에게 각 섹터에서 어떤 지표가 중요한지 알려주기
4. 7-10개 주요 섹터를 커스텀 지표 우선순위로 지원
5. 기존 모든 지표를 출력에 유지 (순서만 변경, 제거 없음)

## 비목표 (Non-Goals)

- 섹터 평균/벤치마크 비교 (데이터 수집 복잡도)
- 임계값 기반 자동 밸류에이션 (LLM이 담당)
- YAML을 통한 런타임 설정 가능한 지표 (하드코딩으로 충분)
- 사용자 정의 커스텀 섹터

## 아키텍처

### 컴포넌트 개요

```
┌─────────────────────────────────────────────────────────┐
│  yfinance API → FundamentalSnapshot (모든 지표 수집)     │
└────────────────────┬────────────────────────────────────┘
                     ↓
         ┌───────────────────────────┐
         │   SectorMetrics 클래스    │
         │  (섹터 식별 및           │
         │   우선순위 지표)          │
         └───────────┬───────────────┘
                     ↓
        ┌────────────┴────────────┐
        ↓                         ↓
┌───────────────┐        ┌────────────────┐
│  CLI 출력     │        │  LLM 프롬프트  │
│ (⭐ 강조)     │        │ ([핵심] 태그)  │
└───────────────┘        └────────────────┘
```

### 신규 모듈: `src/utils/sector_metrics.py`

섹터-지표 매핑을 정의하고 다음 유틸리티 함수 제공:
- yfinance 섹터 문자열에서 섹터 식별
- 주어진 섹터의 우선순위 지표 조회
- 지표 정렬 (우선순위 먼저, 그 다음 알파벳순)

### 수정 모듈: `src/cli/main.py`

`format_deep_dive_output()` 함수 변경사항:
- `SectorMetrics`에서 우선순위 지표 조회
- 우선순위 지표를 ⭐ 이모지와 함께 먼저 렌더링
- 나머지 지표를 우선순위 섹션 다음에 렌더링

### 수정 모듈: `src/llm/analyzer.py`

`generate_fundamental_summary()` 함수 변경사항:
- 우선순위 지표에 [핵심] 접두사 표시
- 모든 지표 포함 (필터링 없음)
- LLM이 [핵심] 태그를 사용해 분석에 집중

## 데이터 모델

### 섹터별 지표 매핑

**지원 섹터 (10개):**

1. **Technology (기술주)**
   - 핵심 지표: PEG Ratio, PSR, 매출 성장률, 이익 성장률, 영업이익률, FCF Yield, Debt/Equity

2. **Financials (금융주)**
   - 핵심 지표: ROE, ROA, P/B Ratio, Debt/Equity, 이익 성장률

3. **Consumer Cyclical (경기소비재)**
   - 핵심 지표: P/E Ratio, 매출 성장률, 매출총이익률, Debt/Equity, Free Cash Flow

4. **Consumer Defensive (필수소비재)**
   - 핵심 지표: 배당 수익률, P/E Ratio, 매출총이익률, ROE, 배당 성향

5. **Healthcare (헬스케어)**
   - 핵심 지표: PEG Ratio, 매출 성장률, 영업이익률, ROE, FCF Yield

6. **Industrials (산업재)**
   - 핵심 지표: P/E Ratio, ROE, Debt/Equity, Free Cash Flow, 영업이익률

7. **Energy (에너지)**
   - 핵심 지표: P/B Ratio, Debt/Equity, FCF Yield, 영업이익률, 배당 수익률

8. **Real Estate (부동산)**
   - 핵심 지표: P/B Ratio, 배당 수익률, Debt/Equity, Free Cash Flow

9. **Utilities (유틸리티)**
   - 핵심 지표: 배당 수익률, P/E Ratio, Debt/Equity, 배당 성향

10. **Communication Services (통신)**
    - 핵심 지표: P/E Ratio, EV/EBITDA, 매출 성장률, FCF Yield, 영업이익률

**Default (기본값 - 섹터 매칭 실패 시):**
- 핵심 지표: P/E Ratio, ROE, 매출 성장률, Debt/Equity, Free Cash Flow

### 필드명 매핑

내부 지표명에서 표시명으로:
```python
{
    "pe_ratio": "P/E Ratio",
    "forward_pe": "Forward P/E",
    "peg_ratio": "PEG Ratio",
    "pb_ratio": "P/B Ratio",
    "ps_ratio": "PSR",
    "ev_ebitda": "EV/EBITDA",
    "roe": "ROE",
    "roa": "ROA",
    "revenue_growth": "매출 성장률",
    "earnings_growth": "이익 성장률",
    "gross_margin": "매출총이익률",
    "operating_margin": "영업이익률",
    "profit_margin": "순이익률",
    "debt_to_equity": "Debt/Equity",
    "free_cash_flow": "Free Cash Flow",
    "operating_cash_flow": "Operating Cash Flow",
    "fcf_yield": "FCF Yield",
    "dividend_yield": "배당 수익률",
    "payout_ratio": "배당 성향",
    "current_ratio": "유동비율",
    "quick_ratio": "당좌비율",
}
```

## 구현 상세

### 1. SectorMetrics 클래스

**파일:** `src/utils/sector_metrics.py`

```python
class SectorMetrics:
    """섹터별 우선순위 지표 정의"""
    
    TECHNOLOGY = [
        "peg_ratio", "ps_ratio", "revenue_growth", "earnings_growth",
        "operating_margin", "fcf_yield", "debt_to_equity"
    ]
    
    FINANCIALS = [
        "roe", "roa", "pb_ratio", "debt_to_equity", "earnings_growth"
    ]
    
    CONSUMER_CYCLICAL = [
        "pe_ratio", "revenue_growth", "gross_margin", "debt_to_equity", "free_cash_flow"
    ]
    
    CONSUMER_DEFENSIVE = [
        "dividend_yield", "pe_ratio", "gross_margin", "roe", "payout_ratio"
    ]
    
    HEALTHCARE = [
        "peg_ratio", "revenue_growth", "operating_margin", "roe", "fcf_yield"
    ]
    
    INDUSTRIALS = [
        "pe_ratio", "roe", "debt_to_equity", "free_cash_flow", "operating_margin"
    ]
    
    ENERGY = [
        "pb_ratio", "debt_to_equity", "fcf_yield", "operating_margin", "dividend_yield"
    ]
    
    REAL_ESTATE = [
        "pb_ratio", "dividend_yield", "debt_to_equity", "free_cash_flow"
    ]
    
    UTILITIES = [
        "dividend_yield", "pe_ratio", "debt_to_equity", "payout_ratio"
    ]
    
    COMMUNICATION_SERVICES = [
        "pe_ratio", "ev_ebitda", "revenue_growth", "fcf_yield", "operating_margin"
    ]
    
    DEFAULT = [
        "pe_ratio", "roe", "revenue_growth", "debt_to_equity", "free_cash_flow"
    ]
    
    @classmethod
    def get_priority_metrics(cls, sector: str | None) -> list[str]:
        """주어진 섹터의 우선순위 지표 반환.
        
        yfinance 섹터명 변형을 처리하기 위해 퍼지 매칭 사용.
        섹터가 None이거나 인식되지 않으면 DEFAULT 반환.
        """
        if not sector:
            return cls.DEFAULT
        
        sector_lower = sector.lower()
        
        if "technolog" in sector_lower:
            return cls.TECHNOLOGY
        elif "financial" in sector_lower:
            return cls.FINANCIALS
        elif "consumer cyclical" in sector_lower or "consumer discretionary" in sector_lower:
            return cls.CONSUMER_CYCLICAL
        elif "consumer defensive" in sector_lower or "consumer staples" in sector_lower:
            return cls.CONSUMER_DEFENSIVE
        elif "healthcare" in sector_lower or "health care" in sector_lower:
            return cls.HEALTHCARE
        elif "industrial" in sector_lower:
            return cls.INDUSTRIALS
        elif "energy" in sector_lower:
            return cls.ENERGY
        elif "real estate" in sector_lower:
            return cls.REAL_ESTATE
        elif "utilit" in sector_lower:
            return cls.UTILITIES
        elif "communication" in sector_lower:
            return cls.COMMUNICATION_SERVICES
        
        return cls.DEFAULT
```

### 2. CLI 렌더링 변경

**파일:** `src/cli/main.py`

**헬퍼 함수:**
```python
def _format_metric_value(metric_name: str, value: float) -> str:
    """지표 타입에 따라 값 포맷팅"""
    if metric_name in ["revenue_growth", "earnings_growth", "gross_margin", 
                       "operating_margin", "profit_margin", "fcf_yield", 
                       "dividend_yield", "roe", "roa"]:
        return f"{value*100:.1f}%"
    elif metric_name in ["free_cash_flow", "operating_cash_flow"]:
        return f"${value/1e9:.1f}B"
    elif metric_name == "payout_ratio":
        return f"{value*100:.1f}%"
    else:
        return f"{value:.1f}" if abs(value) > 10 else f"{value:.2f}"
```

**수정된 format_deep_dive_output():**
```python
from src.utils.sector_metrics import SectorMetrics

# 펀더멘털 섹션에서 (Sector/Industry 라인 다음):
priority_metrics = SectorMetrics.get_priority_metrics(fundamental.sector)

# 우선순위 지표를 ⭐와 함께 먼저 렌더링
for metric_name in priority_metrics:
    value = getattr(fundamental, metric_name, None)
    if value is not None:
        display_name = METRIC_DISPLAY_NAMES.get(metric_name, metric_name)
        formatted = _format_metric_value(metric_name, value)
        output += f"⭐ **{display_name}**: {formatted}\n"

output += "\n"  # 구분자

# 나머지 지표 렌더링
all_metric_names = [
    "market_cap", "pe_ratio", "forward_pe", "peg_ratio", "pb_ratio", 
    "ps_ratio", "ev_ebitda", "roe", "roa", "gross_margin", 
    "operating_margin", "profit_margin", "revenue_growth", 
    "earnings_growth", "debt_to_equity", "current_ratio", 
    "quick_ratio", "free_cash_flow", "operating_cash_flow", 
    "fcf_yield", "dividend_yield", "payout_ratio"
]

remaining_metrics = [m for m in all_metric_names if m not in priority_metrics]

for metric_name in remaining_metrics:
    value = getattr(fundamental, metric_name, None)
    if value is not None:
        display_name = METRIC_DISPLAY_NAMES.get(metric_name, metric_name)
        formatted = _format_metric_value(metric_name, value)
        output += f"- **{display_name}**: {formatted}\n"
```

### 3. LLM 프롬프트 변경

**파일:** `src/llm/analyzer.py`

**수정된 generate_fundamental_summary():**
```python
from src.utils.sector_metrics import SectorMetrics

async def generate_fundamental_summary(
    input_data: FundamentalSummaryInput,
    llm: BaseChatModel,
) -> FundamentalSummaryOutput:
    priority_metrics = SectorMetrics.get_priority_metrics(input_data.sector)
    
    # 우선순위 지표에 [핵심] 접두사를 붙여 지표 텍스트 생성
    metrics_text = []
    
    all_metrics = [
        ("pe_ratio", "P/E"),
        ("forward_pe", "Forward P/E"),
        ("peg_ratio", "PEG"),
        ("pb_ratio", "P/B"),
        ("ps_ratio", "PSR"),
        ("ev_ebitda", "EV/EBITDA"),
        ("roe", "ROE"),
        ("roa", "ROA"),
        ("revenue_growth", "매출 성장률"),
        ("earnings_growth", "이익 성장률"),
        ("gross_margin", "매출총이익률"),
        ("operating_margin", "영업이익률"),
        ("profit_margin", "순이익률"),
        ("debt_to_equity", "D/E"),
        ("free_cash_flow", "FCF"),
        ("fcf_yield", "FCF Yield"),
        ("dividend_yield", "배당 수익률"),
        ("payout_ratio", "배당 성향"),
    ]
    
    for metric_name, display_name in all_metrics:
        value = getattr(input_data, metric_name, None)
        if value is not None:
            prefix = "[핵심] " if metric_name in priority_metrics else ""
            formatted = _format_metric_value(metric_name, value)
            metrics_text.append(f"{prefix}{display_name}: {formatted}")
    
    if not metrics_text:
        metrics_text.append("No financial metrics available")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a fundamental analysis expert."),
        ("user", """Analyze the following fundamental data for {ticker}:

**Sector**: {sector} / {industry}

**Key Metrics** (핵심 지표는 [핵심]으로 표시):
{metrics_text}

Provide summary with:
- summary: overall fundamental assessment in Korean
- strengths: list of 2-3 key strengths (핵심 지표를 중심으로)
- weaknesses: list of 2-3 key weaknesses
- valuation_assessment: "저평가", "적정", or "고평가"
- confidence: 0.0-1.0""")
    ])
    
    chain = prompt | llm.with_structured_output(FundamentalSummaryOutput)
    
    result = await chain.ainvoke({
        "ticker": input_data.ticker,
        "sector": input_data.sector or "N/A",
        "industry": input_data.industry or "N/A",
        "metrics_text": "\n".join(f"- {m}" for m in metrics_text),
    })
    
    return result
```

## 출력 예시

### CLI 출력 (NVDA - Technology)

**변경 전:**
```
Sector/Industry: Technology / Semiconductors

- 시가총액: $4572.99B
- P/E Ratio: 38.5
- Forward P/E: 16.9
- EV/EBITDA: 33.2
- ROE: 101.5%
...
```

**변경 후:**
```
Sector/Industry: Technology / Semiconductors

⭐ **PEG Ratio**: 2.1
⭐ **PSR**: 8.5
⭐ **매출 성장률**: 73.2%
⭐ **이익 성장률**: 95.6%
⭐ **영업이익률**: 65.0%
⭐ **FCF Yield**: 1.3%
⭐ **Debt/Equity**: 7.3

- **시가총액**: $4572.99B
- **P/E Ratio**: 38.5
- **Forward P/E**: 16.9
- **EV/EBITDA**: 33.2
- **ROE**: 101.5%
- **ROA**: 51.2%
...
```

### LLM 프롬프트 (NVDA - Technology)

```
**Sector**: Technology / Semiconductors

**Key Metrics** (핵심 지표는 [핵심]으로 표시):
- [핵심] PEG: 2.1
- [핵심] PSR: 8.5
- [핵심] 매출 성장률: 73.2%
- [핵심] 이익 성장률: 95.6%
- [핵심] 영업이익률: 65.0%
- [핵심] FCF Yield: 1.3%
- [핵심] D/E: 7.3
- P/E: 38.5
- Forward P/E: 16.9
- ROE: 101.5%
- ROA: 51.2%
- 매출총이익률: 71.1%
- 순이익률: 55.6%
...
```

## 테스트 전략

### 단위 테스트

**파일:** `tests/utils/test_sector_metrics.py`

`SectorMetrics` 클래스 테스트:
1. `test_get_priority_metrics_technology()` - Technology 섹터 매핑 검증
2. `test_get_priority_metrics_financials()` - Financials 섹터 매핑 검증
3. `test_get_priority_metrics_fuzzy_match()` - "Technology" vs "Information Technology" 테스트
4. `test_get_priority_metrics_none()` - None일 때 DEFAULT 반환 검증
5. `test_get_priority_metrics_unknown()` - 인식되지 않는 섹터에 대해 DEFAULT 검증
6. `test_all_sectors_covered()` - 10개 섹터 모두 매핑되었는지 검증

**파일:** `tests/cli/test_main.py`

CLI 렌더링 테스트:
1. `test_format_metric_value_percent()` - 퍼센트 포맷팅 테스트
2. `test_format_metric_value_dollar()` - 달러 금액 포맷팅 테스트
3. `test_cli_priority_metrics_order()` - 우선순위 지표가 먼저 나오는지 검증
4. `test_cli_priority_metrics_emoji()` - ⭐ 이모지가 있는지 검증

### 통합 테스트

**파일:** `tests/integration/test_e2e_plan4.py`

통합 테스트:
```python
@pytest.mark.integration
def test_analyze_shows_sector_priority_metrics():
    """CLI에서 섹터별 우선순위 지표가 강조 표시되는지 검증"""
    result = runner.invoke(app, ["analyze", "NVDA", "--provider", "openai"])
    
    # Technology 섹터는 PEG와 PSR을 ⭐와 함께 표시해야 함
    assert "⭐ **PEG Ratio**" in result.stdout
    assert "⭐ **PSR**" in result.stdout
    
    # 우선순위가 아닌 지표는 ⭐가 없어야 함
    assert "⭐ **P/E Ratio**" not in result.stdout
```

### 수동 테스트

**테스트 케이스:**
1. 기술주: `uv run jarvis analyze NVDA --provider openai`
   - PEG, PSR이 ⭐와 함께 먼저 나오는지 확인
2. 금융주: `uv run jarvis analyze JPM --provider openai`
   - ROE, P/B가 ⭐와 함께 먼저 나오는지 확인
3. 알 수 없는 섹터: sector="Unknown"인 mock 티커
   - DEFAULT 지표가 사용되는지 확인
4. LLM 응답: strengths에서 [핵심] 지표를 언급하는지 확인

## 에러 처리

**시나리오:**

1. **섹터가 None**: DEFAULT 지표 사용
2. **인식되지 않는 섹터 문자열**: DEFAULT 지표 사용
3. **지표 값이 None**: 렌더링에서 스킵 (기존 동작)
4. **모든 우선순위 지표가 None**: 나머지 지표만 표시

## 의존성

- 신규 외부 의존성 없음
- 섹터 데이터는 기존 `yfinance` 사용
- 타입 안전성은 기존 `pydantic` 사용

## 리스크 및 완화 방안

**리스크 1: yfinance 섹터명이 다양함**
- 완화 방안: 부분 문자열 검사로 퍼지 매칭
- 영향도: 낮음 - DEFAULT 폴백으로 기능 보장

**리스크 2: 섹터 분류가 시간에 따라 변경됨**
- 완화 방안: 단일 파일에서 매핑 업데이트 용이
- 영향도: 낮음 - 변경 빈도 낮음

**리스크 3: 기존 CLI 출력 깨짐**
- 완화 방안: 순서만 변경, 지표 제거 없음
- 영향도: 낮음 - 사용자는 여전히 모든 정보 확인 가능

**리스크 4: LLM이 [핵심] 태그를 오해**
- 완화 방안: 명확한 프롬프트 지시 + LLM 능력 충분
- 영향도: 낮음 - 최악의 경우 LLM이 태그 무시 (현재보다 나쁘지 않음)

## 향후 개선 사항 (범위 외)

- 섹터 평균/벤치마크 비교
- config를 통한 사용자 커스터마이즈 가능한 지표 우선순위
- 섹터가 아닌 업종(industry) 단위의 세분화
- 섹터별 자동 밸류에이션 임계값
- 히스토리컬 섹터 로테이션 분석

## 구현 체크리스트

- [ ] `src/utils/sector_metrics.py`에 SectorMetrics 클래스 생성
- [ ] 10개 섹터 지표 매핑 + DEFAULT 추가
- [ ] 퍼지 매칭을 사용한 `get_priority_metrics()` 구현
- [ ] CLI에 METRIC_DISPLAY_NAMES 매핑 생성
- [ ] `_format_metric_value()` 헬퍼 함수 추가
- [ ] `format_deep_dive_output()` 수정하여 우선순위 지표 먼저 렌더링
- [ ] 우선순위 지표에 ⭐ 이모지 추가
- [ ] `generate_fundamental_summary()` 수정하여 [핵심] 태그 추가
- [ ] [핵심] 태그를 언급하도록 LLM 프롬프트 업데이트
- [ ] SectorMetrics에 대한 6개 단위 테스트 작성
- [ ] CLI 포맷팅에 대한 4개 단위 테스트 작성
- [ ] E2E 검증을 위한 1개 통합 테스트 작성
- [ ] NVDA (Technology)와 JPM (Financials)로 수동 테스트
- [ ] 필요시 문서 업데이트

# Advanced Technical Indicators + Fundamental Analysis Design

**생성일**: 2026-04-09
**버전**: 1.0
**상태**: 승인됨

---

## 1. 개요

invest-jarvis의 기술적 분석 품질을 대폭 향상하고, Fundamental 분석 도구를 추가한다.

### 1.1 목표
- 고급 기술 지표 8개 추가 (cRSI, 거래량, Gap, Swing, Minervini, Velocity, VCP, Breakout)
- 기존 5개 전략 고도화 (component 패턴으로 내부 분리)
- 가중치 기반 종합 스코어링 시스템 도입
- Fundamental 분석 도구 추가 (Deep Dive 파이프라인에 연결)

### 1.2 설계 원칙
- 플러그인은 전략 단위 (Registry + config.yaml)
- 내부 구조는 component로 분리 (코드 비대화 방지)
- component 선택은 전략 코드 내부에서 결정 (config로 관리 안 함)

---

## 2. 지표 계산 확장 (IndicatorCalculator)

### 2.1 신규 지표

| 지표 | 파라미터 | 용도 |
|------|----------|------|
| SMA_150 | length=150 | Minervini Stage 2 조건 |
| cRSI | dominant_cycle=20, vibration=10, torque=0.1818, lag=4 | 사이클 기반 과매수/과매도 |
| cRSI 동적 밴드 | lookback=40, low=10th percentile, high=90th percentile | cRSI 과매수/과매도 레벨 |
| Vol SMA 20/50/120 | 거래량 이동평균 | 거래량 분석, VCP |
| Swing High | 11봉 윈도우 (양쪽 5봉), High == rolling(11, center=True).max() | 구조적 고점 |
| Swing Low | 11봉 윈도우, Low == rolling(11, center=True).min() | 구조적 저점 |
| Gap Up | Low > 전일 High | 갭 감지, 지지 레벨 |
| Gap Down | High < 전일 Low | 갭 감지, 저항 레벨 |
| MACD (5/35/5) | fast=5, slow=35, signal=5 | 빠른 시그널 |

### 2.2 cRSI 계산 로직

```
1. raw_rsi = RSI(Close, length=10)  # 지배 주기 20의 절반
2. dominant_cycle = 20
3. vibration = 10
4. torque = 2.0 / (vibration + 1)  # = 0.1818
5. lag = int((vibration - 1) / 2)   # = 4

6. for i in range(lag, len(data)):
     crsi[i] = torque * (2 * rsi[i] - rsi[i-lag]) + (1 - torque) * crsi[i-1]

7. lookback = 2 * dominant_cycle  # = 40
8. low_band = rolling_percentile(crsi, lookback, 10)
9. high_band = rolling_percentile(crsi, lookback, 90)
```

### 2.3 IndicatorSnapshot 모델 확장

기존 필드에 추가:

```python
# Moving Averages
sma_150: float | None = None

# Cycle RSI
crsi: float | None = None
crsi_high_band: float | None = None
crsi_low_band: float | None = None

# Volume
vol_sma_20: float | None = None
vol_sma_50: float | None = None
vol_sma_120: float | None = None

# Swing Points
swing_high: float | None = None
swing_low: float | None = None

# Gap
is_gap_up: bool | None = None
is_gap_down: bool | None = None

# Fast MACD
macd_fast: float | None = None
macd_fast_signal: float | None = None
macd_fast_histogram: float | None = None
```

---

## 3. Component 구조

### 3.1 파일 구조

```
src/tools/technical/
├── base.py
├── indicators.py              # 확장
├── models.py                  # 확장
├── registry.py
├── scorer.py                  # 신규
├── tool.py                    # 수정
├── strategies/
│   ├── trend.py               # 수정
│   ├── oscillator.py          # 수정
│   ├── divergence.py          # 수정
│   ├── disparity.py           # 유지
│   └── risk.py                # 수정
└── components/
    ├── __init__.py
    ├── minervini.py           # 신규
    ├── velocity.py            # 신규
    ├── crsi.py                # 신규
    ├── volume.py              # 신규
    └── patterns.py            # 신규
```

### 3.2 ComponentResult 모델

모든 component가 반환하는 통일된 결과 모델:

```python
class ComponentResult(BaseModel):
    signals: list[str]         # 감지된 시그널
    evidence: list[str]        # LLM 해석용 근거
    metrics: dict[str, float]  # 수치 지표
    score: int                 # 이 component가 기여하는 점수
```

### 3.3 Component 상세

#### minervini.py — Minervini Stage 2 (5조건)

조건:
1. Price > SMA_150 > SMA_200 (MA 정배열)
2. SMA_200이 상승 중 (21일 전 대비)
3. Price > SMA_50
4. Price >= 52주 저점 × 1.30 (저점 대비 +30%)
5. Price >= 52주 고점 × 0.75 (고점 대비 -25% 이내)

결과:
- 5조건 모두 충족: "Stage 2 (강력한 상승 국면)", score +40
- above_50만 충족: "강세", score +25
- 미충족: "약세/보합", score -20

#### velocity.py — MA 기울기/가속도

SMA_20의 최근 15일 기반:
- 현재 구간 (최근 5일) 선형회귀 기울기
- 이전 구간 (6-10일) 선형회귀 기울기
- 정규화: norm_slope = (slope / SMA_20) × 100

상태 판별:
- SLOPE_THRESHOLD: 0.05%
- ACCEL_THRESHOLD: 0.02%
- accelerating_up, decelerating_up, exhaustion_up
- accelerating_down, decelerating_down
- turning_up, turning_down (방향 전환)

#### crsi.py — Cycle RSI 분석

시그널:
- Hook Down: prev cRSI > HighBand AND curr cRSI < HighBand → 매도 시그널
- Hook Up: prev cRSI < LowBand AND curr cRSI > LowBand → 매수 시그널
- Squeeze: band_width < 10 → 에너지 응축
- Overbought: cRSI > HighBand
- Oversold: cRSI < LowBand

#### volume.py — 거래량 분석

분석:
- vol_ratio = Volume / Vol_SMA_20
- 거래량 급증: vol_ratio > 2.0 → "거래량 급증"
- 거래량 감소: vol_ratio < 0.5 → "거래량 감소"
- 가격 상승 + 거래량 증가: 강세 확인
- 가격 하락 + 거래량 급증: 경고 시그널

#### patterns.py — 패턴 인식

**VCP (Volatility Contraction Pattern):**
- 4블록 × 10일 = 40일 분석
- 블록별 range% = (High_max - Low_min) / High_max
- 점진적 축소 감지 (최소 2회 축소)
- 마지막 블록 range < 10%
- 거래량 감소 동반 여부
- 신뢰도: 거래량 감소 동반 85%, 미동반 70%

**Breakout (Rolling + Pivot):**
- Rolling: N일(기본 50) 최고가 돌파
- Pivot: 최근 Swing High 돌파
- 크로스오버 확인: 전일 미달 → 오늘 돌파
- 거래량 확인: 1.2x 이상 +10% 신뢰도

**Candlestick:**
- Doji: pandas_ta cdl_doji
- Hammer: wick_down >= 2×body AND wick_up <= 0.5×body
- Bullish Engulfing: 전일 음봉 + 오늘 양봉이 감싼 형태

---

## 4. 전략별 Component 매핑

### 4.1 Trend Strategy (수정)

기존 로직 유지 + component 추가:
- `minervini` → Stage 2 판정이 전체 Trend 스코어의 핵심
- `velocity` → 추세 가속/감속/전환 감지
- `patterns` → VCP, Breakout 시그널 포함

### 4.2 Oscillator Strategy (수정)

기존 RSI/Stochastic/CCI 유지 + 추가:
- `crsi` → Hook Up/Down, Squeeze, 과매수/과매도
- `volume` → 거래량 기반 모멘텀 확인

### 4.3 Divergence Strategy (수정)

기존 RSI/MACD 다이버전스 유지 + 개선:
- cRSI 다이버전스 추가
- 피크 탐지 개선: scipy argrelextrema 사용 (order=3)
- RSI + cRSI 동시 다이버전스 시 "강력 다이버전스" 신뢰도 90%

### 4.4 Disparity Strategy (변경 없음)

현재 로직 충분. 수정하지 않음.

### 4.5 Risk Strategy (수정)

기존 ATR/BB/52주 유지 + 대폭 고도화:
- 다층 지지/저항 수집:
  - 동적: SMA_20, SMA_50, SMA_200
  - 정적: Swing High/Low (최근 100일)
  - 갭: Gap Up/Down 레벨
  - 공식: Pivot, S1, R1
- Confluence 감지: 현재가 2% 내 지지선 중첩 수
- 리스크 페널티: SMA_50 하회 시 +1단계, SuperTrend 하락 시 +1단계
- 손절가 계산: current_price - (2 × ATR)

---

## 5. 종합 스코어링 시스템 (TechnicalScorer)

### 5.1 위치

`src/tools/technical/scorer.py`

### 5.2 가중치

| 카테고리 | 배점 | 소스 |
|----------|------|------|
| Trend | 40 | TrendStrategy |
| Momentum | 30 | OscillatorStrategy |
| Pattern | 20 | patterns component |
| Risk | 10 | RiskStrategy |
| Divergence | 10 | DivergenceStrategy |

### 5.3 카테고리별 점수 변환

**Trend (40점 만점):**
- Stage 2: +40
- 강세: +25
- 약강세: +15
- 중립: 0
- 약약세: -10
- 약세: -20

**Momentum (30점 만점):**
- 과매도 (매수 기회): +20
- 약과매도: +10
- 중립: +5
- 약과매수: -10
- 과매수: -15

**Pattern (20점 만점):**
- 패턴당 +7점, 최대 20점

**Risk (10점 만점):**
- 저위험: +10
- 중위험: +5
- 고위험: 0

**Divergence (10점 만점):**
- 강세 다이버전스: +10
- 중립: 0
- 약세 다이버전스: -5

### 5.4 총점 → 평가

| 총점 | 평가 |
|------|------|
| >= 70 | 강력 매수 |
| >= 40 | 매수 |
| >= -10 | 중립 |
| >= -40 | 매도 |
| < -40 | 강력 매도 |

### 5.5 TechnicalResult 변경

기존 필드에 추가:
```python
total_score: int  # 종합 점수
```

기존 `overall_assessment`은 Scorer가 결정.

---

## 6. Fundamental 분석 도구

### 6.1 위치

`src/tools/fundamental.py`

### 6.2 FundamentalSnapshot 모델

```python
class FundamentalSnapshot(BaseModel):
    # 기본 정보
    market_cap: float | None = None
    sector: str | None = None
    industry: str | None = None

    # 밸류에이션 (가치주 핵심)
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_ebitda: float | None = None

    # 수익성
    eps: float | None = None
    ebitda: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    profit_margin: float | None = None
    roe: float | None = None
    roa: float | None = None

    # 성장성 (성장주 핵심)
    revenue_growth: float | None = None
    earnings_growth: float | None = None

    # 분기 실적 (최근 4분기)
    quarterly_revenue: list[dict] | None = None   # [{period, revenue}]
    quarterly_earnings: list[dict] | None = None  # [{period, earnings}]

    # 재무 건전성
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None

    # 현금흐름 (시크리컬주 핵심)
    free_cash_flow: float | None = None
    operating_cash_flow: float | None = None
    fcf_yield: float | None = None  # FCF / Market Cap

    # 배당
    dividend_yield: float | None = None
    payout_ratio: float | None = None

    # 주주환원
    shares_outstanding: float | None = None
    float_shares: float | None = None
```

### 6.3 FundamentalTool

- `BaseTool` 상속
- `execute(ticker)` → `ToolResult(data=FundamentalSnapshot)`
- YFinanceProvider의 `.info` + `.quarterly_financials` 사용

### 6.4 DeepDivePipeline 변경

- `__init__`에 `fundamental_tool: FundamentalTool` 추가
- `run()` 순서: 기술적 분석 → 펀더멘털 → 뉴스 → LLM 해석
- 결과 dict에 `fundamental: FundamentalSnapshot` 추가
- 결과 dict에 `fundamental_summary: FundamentalSummaryOutput` 추가

### 6.5 LLM Analyzer 확장

`src/llm/analyzer.py`에 추가:

```python
async def generate_fundamental_summary(
    input_data: FundamentalSummaryInput,
    llm: BaseChatModel,
) -> FundamentalSummaryOutput:
```

**FundamentalSummaryInput**: ticker, sector, 주요 지표들
**FundamentalSummaryOutput**:
- summary: str (한글)
- strengths: list[str] (강점)
- weaknesses: list[str] (약점)
- valuation_assessment: str ("저평가", "적정", "고평가")
- confidence: float (0-1)

---

## 7. 영향 범위

### 7.1 신규 파일

| 파일 | 내용 |
|------|------|
| `src/tools/technical/components/__init__.py` | component 패키지 |
| `src/tools/technical/components/minervini.py` | Minervini Stage 2 |
| `src/tools/technical/components/velocity.py` | MA 기울기/가속도 |
| `src/tools/technical/components/crsi.py` | Cycle RSI |
| `src/tools/technical/components/volume.py` | 거래량 분석 |
| `src/tools/technical/components/patterns.py` | VCP, Breakout, 캔들스틱 |
| `src/tools/technical/scorer.py` | 종합 스코어링 |
| `src/tools/fundamental.py` | Fundamental 분석 도구 |

### 7.2 수정 파일

| 파일 | 변경 |
|------|------|
| `src/tools/technical/indicators.py` | 신규 지표 추가 |
| `src/tools/technical/models.py` | IndicatorSnapshot 확장, ComponentResult, FundamentalSnapshot, TechnicalResult.total_score |
| `src/tools/technical/strategies/trend.py` | minervini, velocity, patterns 통합 |
| `src/tools/technical/strategies/oscillator.py` | crsi, volume 통합 |
| `src/tools/technical/strategies/divergence.py` | cRSI 다이버전스, 피크 탐지 개선 |
| `src/tools/technical/strategies/risk.py` | Swing/Gap 지지저항, confluence, 페널티, 손절가 |
| `src/tools/technical/tool.py` | Scorer 연동 |
| `src/pipelines/deep_dive.py` | FundamentalTool 추가 |
| `src/llm/analyzer.py` | generate_fundamental_summary() |
| `src/llm/models.py` | FundamentalSummaryInput/Output |
| `src/cli/main.py` | analyze 출력에 Fundamental 섹션 |

### 7.3 변경 없음

- `src/tools/technical/strategies/disparity.py`
- `src/pipelines/quick_check.py`
- `src/pipelines/daily_report.py`
- `src/pipelines/portfolio.py`
- `config.yaml`

---

## 8. 의존성

**추가 필요:**
- `scipy` — argrelextrema (다이버전스 피크 탐지)
- `numpy` — polyfit (velocity 선형회귀), 이미 pandas 의존성으로 설치됨

**기존 활용:**
- `pandas_ta` — 신규 지표 계산
- `yfinance` — Fundamental 데이터 (.info, .quarterly_financials)

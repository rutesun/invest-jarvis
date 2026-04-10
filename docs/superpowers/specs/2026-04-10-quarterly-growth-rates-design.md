# 분기별 성장률 기능 설계

**날짜:** 2026-04-10
**상태:** 초안
**작성자:** Claude Code

## 개요

펀더멘털 분석 기능에 YoY (전년 동기 대비) 및 QoQ (전분기 대비) 성장률 계산 기능을 추가하고, 분기별 추이를 표와 리스트 형식으로 시각화합니다.

## 목표

1. 매출과 이익의 YoY 및 QoQ 성장률 표시
2. 최근 4개 분기의 추이 표시
3. 표 형식(Key Metrics)과 리스트 형식(별도 섹션) 모두 제공
4. 표준 재무 보고 관행에 부합

## 비목표 (Non-Goals)

- 매출/이익 외 추가 분기별 지표 (EBITDA, 매출총이익 등)
- 히스토리컬 트렌드 차트나 그래프
- 2년 이상 오래된 분기별 데이터

## 아키텍처

### 데이터 수집 전략

**현재 상태:**
- `FundamentalTool._fetch_fundamentals()`가 4개 분기 데이터만 수집
- 단순 dict로 저장: `{"period": "2026-Q1", "revenue": 143756000000}`
- 성장률 계산 없음

**변경 후:**
- yfinance `quarterly_financials`에서 **8개 분기** 데이터 수집
- YoY 및 QoQ 성장률 계산
- **최근 4개 분기**만 계산된 성장률과 함께 구조화된 모델에 저장

### 데이터 모델 변경

#### 신규 모델: QuarterlyData

**파일:** `src/tools/fundamental.py`

```python
class QuarterlyData(BaseModel):
    """분기별 재무 데이터 및 성장률"""
    period: str                      # "2026-Q1"
    revenue: float | None = None     # 절대값 (USD)
    earnings: float | None = None    # 절대값 (USD)
    revenue_yoy: float | None = None # YoY 성장률 (0.1565 = 15.65%)
    revenue_qoq: float | None = None # QoQ 성장률 (0.4030 = 40.30%)
    earnings_yoy: float | None = None
    earnings_qoq: float | None = None
```

#### 수정 모델: FundamentalSnapshot

**파일:** `src/tools/fundamental.py`

```python
class FundamentalSnapshot(BaseModel):
    # ... 기존 필드 ...
    
    # 제거할 필드:
    # quarterly_revenue: list[dict] | None = None
    # quarterly_earnings: list[dict] | None = None
    
    # 추가할 필드:
    quarterly_data: list[QuarterlyData] | None = None
```

### 계산 로직

**위치:** `FundamentalTool._fetch_fundamentals()`

**단계:**

1. **8개 분기 파싱** from `yfinance.Ticker.quarterly_financials.columns[:8]`
   - 각 분기의 period, revenue, earnings 추출
   - 임시 리스트에 저장: `[(period, revenue, earnings), ...]`
   - 순서: 최신 우선 (Q1 2026, Q4 2025, Q3 2025, ...)

2. **YoY 성장률 계산** (최근 4개 분기에 대해):
   ```python
   # Q1 2026 vs Q1 2025 (4분기 전)
   if len(quarters) >= 5 and quarters[0].revenue and quarters[4].revenue:
       revenue_yoy = (quarters[0].revenue - quarters[4].revenue) / quarters[4].revenue
   ```

3. **QoQ 성장률 계산** (최근 4개 분기에 대해):
   ```python
   # Q1 2026 vs Q4 2025 (1분기 전)
   if len(quarters) >= 2 and quarters[0].revenue and quarters[1].revenue:
       revenue_qoq = (quarters[0].revenue - quarters[1].revenue) / quarters[1].revenue
   ```

4. **QuarterlyData 객체 생성** (최근 4개 분기)
   - 계산된 YoY/QoQ 성장률 포함
   - 누락 데이터는 None으로 graceful하게 처리

5. **FundamentalSnapshot의 일부로 반환**

### 에러 처리

**시나리오:**

1. **8개 분기 미만 데이터** (신규 상장사):
   - YoY 계산은 ≥5개 분기가 있을 때만
   - QoQ 계산은 ≥2개 분기만 있으면 항상 수행
   - 표시할 때 None 값은 "N/A"로 처리

2. **매출 또는 이익 데이터 누락**:
   - 해당 성장률을 None으로 설정
   - 경고 로그 출력하고 처리 계속

3. **분모가 0 또는 음수**:
   - 성장률을 None으로 설정 (0으로 나누기 방지 및 오해의 소지 방지)

4. **yfinance API 실패**:
   - 기존 에러 처리 그대로 (경고 로그, quarterly_data를 None으로 반환)
   - 변경 불필요

## CLI 출력 형식

### 섹션 1: Key Metrics 표

**위치:** 밸류에이션 지표 다음, 수익성 지표 이전

**형식:** Rich Table

```
분기별 추이 (최근 4분기)

Period          Q1 2026     Q4 2025     Q3 2025     Q2 2025
Revenue         $143.76B    $102.47B    $94.04B     $88.23B
YoY Growth %    15.65%      7.94%       9.63%       12.45%
QoQ Growth %    40.30%      8.96%       6.59%       5.23%
Earnings        $36.50B     $28.30B     $24.20B     $22.10B
YoY Growth %    18.30%      12.40%      14.20%      16.80%
QoQ Growth %    35.20%      16.94%      9.50%       7.20%
```

**구현 방법:**
- `rich.table.Table` 사용, 열 정렬
- 숫자 포맷: 십억 단위, 소수점 2자리 (`$143.76B`)
- 성장률 포맷: 퍼센트, 소수점 2자리 (`15.65%`)
- 색상 코딩: 양수는 녹색, 음수는 빨간색

### 섹션 2: 분기별 상세 리스트

**위치:** Key Metrics와 LLM Analysis 사이의 새 하위 섹션 "### 분기별 실적"

**형식:** 성장률이 포함된 불릿 리스트

```
### 분기별 실적

매출 추이:
• Q1 2026: $143.76B (YoY +15.65%, QoQ +40.30%)
• Q4 2025: $102.47B (YoY +7.94%, QoQ +8.96%)
• Q3 2025: $94.04B (YoY +9.63%, QoQ +6.59%)
• Q2 2025: $88.23B (YoY +12.45%, QoQ +5.23%)

이익 추이:
• Q1 2026: $36.50B (YoY +18.30%, QoQ +35.20%)
• Q4 2025: $28.30B (YoY +12.40%, QoQ +16.94%)
• Q3 2025: $24.20B (YoY +14.20%, QoQ +9.50%)
• Q2 2025: $22.10B (YoY +16.80%, QoQ +7.20%)
```

**구현 방법:**
- `quarterly_data` 리스트 반복
- 헬퍼 함수로 포맷: `_format_quarterly_growth()`
- None 값 처리: 퍼센트 대신 "N/A" 표시

## 테스트 전략

### 단위 테스트

**파일:** `tests/tools/test_fundamental.py`

**신규 테스트:**

1. `test_quarterly_data_model()` - QuarterlyData pydantic 모델 검증
2. `test_quarterly_yoy_calculation()` - 8개 분기 mock, YoY 계산 검증
3. `test_quarterly_qoq_calculation()` - 5개 분기 mock, QoQ 계산 검증
4. `test_quarterly_insufficient_data()` - 3개 분기 mock, graceful 처리 검증
5. `test_quarterly_zero_denominator()` - Q-4 매출 0 mock, None 결과 검증
6. `test_quarterly_missing_earnings()` - 매출만 있는 경우 mock, 부분 결과 검증

### 통합 테스트

**파일:** `tests/integration/test_e2e_plan4.py`

**신규 테스트:**

```python
@pytest.mark.integration
def test_analyze_shows_quarterly_trends():
    """CLI에서 분기별 표와 리스트가 표시되는지 검증"""
    result = runner.invoke(app, ["analyze", "AAPL"])
    assert "분기별 추이" in result.stdout
    assert "YoY Growth %" in result.stdout
    assert "매출 추이:" in result.stdout
```

### 수동 테스트

**명령어:**
```bash
# 전체 데이터가 있는 미국 주식
uv run jarvis analyze AAPL --provider openai

# 신규 상장사 (분기 수 적음)
uv run jarvis analyze COIN --provider openai

# 한국 주식
uv run jarvis analyze 005930.KS --provider openai
```

**검증 사항:**
- 표가 4개 분기를 올바르게 표시
- YoY/QoQ 퍼센트 정확도
- 누락 데이터는 "N/A"로 graceful하게 표시
- 엣지 케이스에서 크래시 없음

## 구현 체크리스트

- [ ] `src/tools/fundamental.py`에 QuarterlyData 모델 추가
- [ ] FundamentalSnapshot 모델 수정 (기존 필드 제거, quarterly_data 추가)
- [ ] `_fetch_fundamentals()`를 8개 분기 수집하도록 업데이트
- [ ] YoY 계산 로직 구현
- [ ] QoQ 계산 로직 구현
- [ ] `src/cli/main.py`에 분기별 표 렌더링 추가
- [ ] `src/cli/main.py`에 분기별 리스트 섹션 추가
- [ ] 6개 단위 테스트 작성
- [ ] 1개 통합 테스트 작성
- [ ] 기존 quarterly_revenue/quarterly_earnings 필드에 의존하는 테스트 업데이트
- [ ] 3개 다른 주식으로 수동 테스트
- [ ] 커밋 메시지: "feat(fundamental): add YoY/QoQ quarterly growth rates and trends"

## 의존성

**Python 패키지:**
- `rich` - CLI 표에 이미 사용 중
- `yfinance` - 데이터 수집에 이미 사용 중
- 신규 의존성 없음

**데이터 소스:**
- `yfinance.Ticker.quarterly_financials` - 분기를 컬럼으로 하는 DataFrame
- "Total Revenue"와 "Net Income" 행이 있을 것으로 예상
- `None` 체크로 누락 데이터 처리

## 리스크 및 완화 방안

**리스크 1: yfinance API가 8개 분기 미만 반환**
- **완화 방안:** `len(qf.columns)` 체크 후 ≥5개 분기가 있을 때만 YoY 계산
- **영향도:** 낮음 - QoQ만 표시하는 graceful degradation

**리스크 2: 8개 분기 파싱으로 인한 성능 영향**
- **완화 방안:** 파싱이 이미 빠름 (< 100ms), 2배로 늘어나도 체감 불가
- **영향도:** 무시 가능

**리스크 3: 기존 코드 breaking change**
- **완화 방안:** `quarterly_revenue`/`quarterly_earnings` 참조하는 모든 테스트 업데이트
- **영향도:** 중간 - 여러 파일의 테스트 업데이트 필요

## 향후 개선 사항 (범위 외)

- 분기별 EBITDA, 매출총이익, 영업이익 추이
- 다년간 히스토리컬 차트 (ASCII 또는 웹 기반)
- 업종 평균과의 비교
- 분기별 가이던스 vs 실제 실적

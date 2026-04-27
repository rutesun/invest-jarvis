# Phase 2 차트 패턴 강화 설계

**날짜:** 2026-04-25  
**목적:** 차트 패턴 감지 정확도 개선 및 새로운 패턴 추가

## 배경

### 현재 상태
- Phase 1: VCP, Pocket Pivot, Power Gap Up 등 구현 완료 (PR #20)
- Phase 2: Cup & Handle, Double Bottom, Head & Shoulders, Support/Resistance Test 구현됨 (PR #19)

### 문제점
1. **Double Bottom 미감지 사례 (NVTS)**
   - 실제 차트에서 명확한 Double Bottom 패턴 육안 확인
   - 알고리즘 미감지 원인: 두 저점 거리 10일 (현재 최소 40일 제약)
   - 짧은 기간 패턴도 유효함에도 놓치고 있음

2. **다른 패턴들의 엄격한 Threshold**
   - Cup & Handle: 최소 60일, handle 최대 10일 → 실무보다 제약적
   - Head & Shoulders: 최소 60일, head prominence >5% → 약한 패턴 놓침
   - Peak/Valley 감지: 평균 가격 기반 prominence → 변동성 미고려

3. **주요 패턴 누락**
   - Ascending/Descending Triangle (수렴 패턴)
   - Bullish/Bearish Flag (추세 지속 패턴)
   - 실무에서 자주 사용하는 패턴들

## 목표

### 1. 기존 패턴 Threshold 완화
- Double Bottom 거리 제약 완화 (40일 → 20일)
- Cup & Handle 기간 제약 완화 (60일 → 40일, handle 10일 → 20일)
- Head & Shoulders 제약 완화 (60일 → 40일, prominence 5% → 3%)

### 2. 새 패턴 추가
- Ascending Triangle (상승 돌파 예상)
- Descending Triangle (하락 돌파 예상)
- Bullish Flag (상승 추세 지속)
- Bearish Flag (하락 추세 지속)

### 3. (선택) Adaptive Threshold
- ATR 기반 동적 prominence/distance 조정
- 변동성에 따라 민감도 자동 조절

## 설계

### 아키텍처

**변경 파일:**
- `src/tools/technical/components/chart_patterns.py` (패턴 감지 로직)
- `src/tools/technical/models.py` (필요시 모델 확장)
- `tests/tools/technical/test_chart_patterns.py` (테스트 추가)
- `docs/FEATURES.md` (문서 업데이트)

**데이터 흐름:**
```
DataFrame (OHLCV) 
  → detect_chart_patterns()
    → detect_double_bottom() (수정)
    → detect_cup_and_handle() (수정)
    → detect_head_and_shoulders() (수정)
    → detect_ascending_triangle() (신규)
    → detect_descending_triangle() (신규)
    → detect_bullish_flag() (신규)
    → detect_bearish_flag() (신규)
    → test_support_resistance() (기존)
  → dict[str, ChartPatternResult]
```

### 컴포넌트별 상세 설계

#### 1. Double Bottom 개선

**변경사항:**
```python
# Before
if valley2_idx - valley1_idx < 40 or valley2_idx - valley1_idx > 80:
    continue

# After
if valley2_idx - valley1_idx < 20 or valley2_idx - valley1_idx > 80:
    continue

# Valley prominence 완화
valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean() * 0.02)  # 0.03 → 0.02
```

**Confidence 조정:**
```python
def calculate_double_bottom_confidence(height_diff, rebound, distance):
    confidence = 0.0
    
    # Valley similarity (0-0.4)
    similarity_score = 1.0 - (height_diff / 0.05)
    confidence += similarity_score * 0.4
    
    # Rebound strength (0-0.3)
    rebound_score = min(rebound / 0.20, 1.0)
    confidence += rebound_score * 0.3
    
    # Period fit (0-0.3)
    if 40 <= distance <= 60:
        period_score = 1.0
    elif 20 <= distance < 40:
        period_score = 0.85  # Short-term penalty
    elif 60 < distance <= 80:
        period_score = 0.95
    else:
        period_score = 0.5
    confidence += period_score * 0.3
    
    return min(confidence, 1.0)
```

**검증:**
- NVTS 데이터로 패턴 감지 확인
- False positive 모니터링 (다른 종목 테스트)

---

#### 2. Cup & Handle 개선

**변경사항:**
```python
# Before
최소 데이터: 70일
cup_length: 60-120일
handle_max: 10일

# After
최소 데이터: 50일
cup_length: 40-120일
handle_range: 2-20일

# 코드 변경
if len(df) < 50:  # 70 → 50
    return ChartPatternResult(...)

cup_range = prices[left_peak_idx : right_peak_idx + 1]
if len(cup_range) < 40 or len(cup_range) > 120:  # 60 → 40
    continue

handle_range = prices[right_peak_idx : min(right_peak_idx + 20, len(prices))]  # 10 → 20
if len(handle_range) < 2:
    continue
```

**Confidence 조정:**
```python
def calculate_cup_handle_confidence(cup_depth, handle_ret, cup_length, weights):
    # Period fit 조정
    if 60 <= cup_length <= 120:
        period_score = 1.0
    elif 40 <= cup_length < 60:
        period_score = 0.9  # Short cup penalty
    else:
        period_score = 0.7
    
    confidence += period_score * weights["period_weight"]
```

---

#### 3. Head & Shoulders 개선

**변경사항:**
```python
# Before
최소 데이터: 70일
pattern_width: 60-100일
head > shoulders: >5%
peak distance: 10일

# After
최소 데이터: 50일
pattern_width: 40-100일
head > shoulders: >3%
peak distance: 15일 (노이즈 필터링)

# 코드 변경
if len(df) < 50:  # 70 → 50
    return ChartPatternResult(...)

peaks, _ = find_peaks(prices, distance=15, prominence=prices.mean() * 0.05)  # distance 10→15

if (right_shoulder_idx - left_shoulder_idx < 40 or  # 60→40
    right_shoulder_idx - left_shoulder_idx > 100):
    continue

# Head must be higher (>3%)
if head <= left_shoulder * 1.03 or head <= right_shoulder * 1.03:  # 1.05→1.03
    continue
```

---

#### 4. Ascending Triangle (신규)

**패턴 정의:**
- 수평 저항선: 고점들이 비슷한 높이 (표준편차 <3%)
- 상승 지지선: 저점들이 점점 높아짐 (기울기 >0.1% per day)
- 기간: 30-90일
- 수렴: 마지막 고점-저점 간격이 첫 번째의 50% 이하

**감지 알고리즘:**
```python
def detect_ascending_triangle(df: pd.DataFrame) -> ChartPatternResult:
    if len(df) < 40:
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 40일 필요)",
        )
    
    prices = df["Close"].values
    
    # 고점/저점 추출
    peaks, _ = find_peaks(prices, distance=10, prominence=prices.mean() * 0.03)
    valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean() * 0.03)
    
    if len(peaks) < 3 or len(valleys) < 3:
        return ChartPatternResult(...)
    
    # 최근 3-4개 고점/저점만 사용
    recent_peaks = peaks[-4:] if len(peaks) >= 4 else peaks[-3:]
    recent_valleys = valleys[-4:] if len(valleys) >= 4 else valleys[-3:]
    
    # 패턴 기간 확인
    pattern_start = min(recent_peaks[0], recent_valleys[0])
    pattern_end = max(recent_peaks[-1], recent_valleys[-1])
    pattern_length = pattern_end - pattern_start
    
    if not (30 <= pattern_length <= 90):
        return ChartPatternResult(...)
    
    # 고점 수평성 확인
    peak_prices = prices[recent_peaks]
    peak_std = np.std(peak_prices) / np.mean(peak_prices)
    
    if peak_std > 0.03:  # 표준편차 >3%면 수평 아님
        return ChartPatternResult(...)
    
    # 저점 상승 추세 확인 (선형회귀)
    from scipy.stats import linregress
    valley_prices = prices[recent_valleys]
    slope, intercept, r_value, _, _ = linregress(recent_valleys, valley_prices)
    
    daily_slope = slope / pattern_length
    
    if daily_slope <= 0.001:  # 일일 0.1% 미만 상승이면 불충분
        return ChartPatternResult(...)
    
    # 수렴 확인
    first_gap = peak_prices[0] - valley_prices[0]
    last_gap = peak_prices[-1] - valley_prices[-1]
    
    if last_gap > first_gap * 0.5:  # 간격이 50% 이하로 좁아지지 않음
        return ChartPatternResult(...)
    
    # Confidence 계산
    resistance_level = np.mean(peak_prices)
    support_slope_percent = daily_slope * 100
    convergence_ratio = last_gap / first_gap
    
    confidence = calculate_triangle_confidence(
        peak_std, support_slope_percent, convergence_ratio, "ascending"
    )
    
    # Target price: resistance + (resistance - first valley)
    target = resistance_level + (resistance_level - valley_prices[0])
    
    return ChartPatternResult(
        pattern_name="Ascending Triangle",
        detected=True,
        confidence=confidence,
        completed_date=df.index[pattern_end].strftime("%Y-%m-%d"),
        days_ago=len(df) - pattern_end - 1,
        current_price=prices[-1],
        breakout_level=resistance_level,
        support_level=valley_prices[-1],
        description=f"고점 수평도 {peak_std:.2%}, 저점 기울기 +{support_slope_percent:.2%}/day, {pattern_length}일",
        key_levels={
            "resistance": float(resistance_level),
            "support_start": float(valley_prices[0]),
            "support_end": float(valley_prices[-1]),
            "target": float(target),
        },
    )
```

**Confidence Scoring:**
```python
def calculate_triangle_confidence(
    peak_std: float, 
    slope_percent: float, 
    convergence_ratio: float,
    triangle_type: str  # "ascending" or "descending"
) -> float:
    confidence = 0.0
    
    # 1. 수평선 품질 (0-0.4)
    horizontal_score = max(0, 1.0 - peak_std / 0.03)
    confidence += horizontal_score * 0.4
    
    # 2. 추세선 기울기 (0-0.3)
    ideal_slope = 0.15  # 0.15% per day
    slope_score = max(0, 1.0 - abs(abs(slope_percent) - ideal_slope) / 0.15)
    confidence += slope_score * 0.3
    
    # 3. 수렴도 (0-0.3)
    convergence_score = 1.0 - convergence_ratio  # 작을수록 좋음
    confidence += convergence_score * 0.3
    
    return min(confidence, 1.0)
```

---

#### 5. Descending Triangle (신규)

**패턴 정의:**
- 하락 저항선: 고점들이 점점 낮아짐 (기울기 <-0.1% per day)
- 수평 지지선: 저점들이 비슷한 높이 (표준편차 <3%)
- 기간: 30-90일

**감지 알고리즘:**
Ascending Triangle과 동일한 로직, 고점↔저점 역할 반전

```python
def detect_descending_triangle(df: pd.DataFrame) -> ChartPatternResult:
    # Ascending과 유사하지만 역방향
    # - 저점 수평성 확인 (valley_std < 0.03)
    # - 고점 하락 추세 확인 (slope < -0.001)
    # - 수렴 확인
    pass
```

---

#### 6. Bullish Flag (신규)

**패턴 정의:**
- **Pole (깃대):** 5-15일간 급등 (>15%)
- **Flag (깃발):** pole 직후 5-20일 하향 채널
- Flag 기울기: -5° ~ -20° (약 -0.5% ~ -2% per day)
- Flag 조정 깊이: pole 상승의 30-50%
- 거래량: pole에서 급증 → flag에서 감소

**감지 알고리즘:**
```python
def detect_bullish_flag(df: pd.DataFrame) -> ChartPatternResult:
    if len(df) < 30:
        return ChartPatternResult(
            pattern_name="Bullish Flag",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 30일 필요)",
        )
    
    prices = df["Close"].values
    volumes = df["Volume"].values
    
    # Pole 감지 (최근 25일 내에서)
    for pole_end in range(len(df) - 5, max(len(df) - 25, 5), -1):
        # Pole 길이 5-15일 시도
        for pole_length in range(5, 16):
            pole_start = pole_end - pole_length
            if pole_start < 0:
                continue
            
            pole_gain = (prices[pole_end] / prices[pole_start]) - 1
            
            # 급등 조건 (>15%)
            if pole_gain < 0.15:
                continue
            
            # Flag 영역 확인 (pole 직후 5-20일)
            flag_start = pole_end
            flag_max_end = min(pole_end + 20, len(prices) - 1)
            
            if flag_max_end - flag_start < 5:
                continue
            
            # Flag 내 가격 추세 확인 (하향 채널)
            flag_prices = prices[flag_start:flag_max_end]
            flag_indices = np.arange(len(flag_prices))
            
            from scipy.stats import linregress
            slope, intercept, r_value, _, _ = linregress(flag_indices, flag_prices)
            
            # 기울기 조건: 음수이면서 일일 -0.5% ~ -2%
            daily_slope_pct = (slope / prices[flag_start]) * 100
            
            if not (-2.0 <= daily_slope_pct <= -0.3):
                continue
            
            # Flag 조정 깊이 확인
            flag_low = min(flag_prices)
            retracement = (prices[pole_end] - flag_low) / (prices[pole_end] - prices[pole_start])
            
            if not (0.30 <= retracement <= 0.50):
                continue
            
            # 거래량 패턴 확인 (pole > flag)
            pole_vol_avg = np.mean(volumes[pole_start:pole_end])
            flag_vol_avg = np.mean(volumes[flag_start:flag_max_end])
            
            volume_decrease = flag_vol_avg / pole_vol_avg
            
            # Confidence 계산
            confidence = calculate_flag_confidence(
                pole_gain, abs(daily_slope_pct), retracement, volume_decrease, "bullish"
            )
            
            # Target price: pole_end + pole_height
            pole_height = prices[pole_end] - prices[pole_start]
            target = prices[-1] + pole_height
            
            return ChartPatternResult(
                pattern_name="Bullish Flag",
                detected=True,
                confidence=confidence,
                completed_date=df.index[flag_max_end - 1].strftime("%Y-%m-%d"),
                days_ago=len(df) - (flag_max_end - 1) - 1,
                current_price=prices[-1],
                breakout_level=prices[pole_end],
                support_level=flag_low,
                description=f"Pole {pole_gain:.1%} 상승, Flag {daily_slope_pct:.2%}/day, {pole_length+len(flag_prices)}일",
                key_levels={
                    "pole_start": float(prices[pole_start]),
                    "pole_end": float(prices[pole_end]),
                    "flag_low": float(flag_low),
                    "target": float(target),
                },
            )
    
    return ChartPatternResult(
        pattern_name="Bullish Flag",
        detected=False,
        confidence=0.0,
        current_price=prices[-1],
        description="패턴 미감지",
    )
```

**Confidence Scoring:**
```python
def calculate_flag_confidence(
    pole_gain: float,
    slope_abs: float,
    retracement: float,
    volume_decrease: float,
    flag_type: str  # "bullish" or "bearish"
) -> float:
    confidence = 0.0
    
    # 1. Pole 강도 (0-0.3)
    # 15% 이상 강함, 30% 이상 매우 강함
    pole_score = min(pole_gain / 0.30, 1.0)
    confidence += pole_score * 0.3
    
    # 2. Flag 기울기 적정성 (0-0.3)
    # Ideal: -1% per day (bullish) or +1% per day (bearish)
    ideal_slope = 1.0
    slope_score = max(0, 1.0 - abs(slope_abs - ideal_slope) / 1.0)
    confidence += slope_score * 0.3
    
    # 3. Retracement 적정성 (0-0.2)
    # Ideal: 38.2% (피보나치)
    retracement_score = max(0, 1.0 - abs(retracement - 0.382) / 0.15)
    confidence += retracement_score * 0.2
    
    # 4. 거래량 패턴 (0-0.2)
    # Ideal: flag 거래량이 pole의 50% 이하
    if volume_decrease <= 0.5:
        volume_score = 1.0
    elif volume_decrease <= 0.7:
        volume_score = 0.7
    else:
        volume_score = 0.3
    confidence += volume_score * 0.2
    
    return min(confidence, 1.0)
```

---

#### 7. Bearish Flag (신규)

**패턴 정의:**
- **Pole:** 5-15일간 급락 (<-15%)
- **Flag:** pole 직후 5-20일 상향 채널
- Flag 기울기: +5° ~ +20° (약 +0.5% ~ +2% per day)
- Flag 반등: pole 하락의 30-50%

**감지 알고리즘:**
Bullish Flag와 동일한 로직, 방향만 반전

```python
def detect_bearish_flag(df: pd.DataFrame) -> ChartPatternResult:
    # Bullish Flag와 유사하지만 역방향
    # - Pole: <-15% 하락
    # - Flag: 상향 기울기 +0.5% ~ +2%
    # - Retracement: pole 하락의 30-50% 반등
    pass
```

---

#### 8. Support/Resistance Test (개선 - 선택)

**현재 문제:**
- 고정 proximity (±2%)
- 변동성 높은 종목에선 너무 좁음
- 변동성 낮은 종목에선 너무 넓음

**ATR 기반 Adaptive Proximity (선택적):**
```python
def test_support_resistance(df: pd.DataFrame, snapshot: IndicatorSnapshot) -> ChartPatternResult:
    current_price = snapshot.price
    
    # ATR 계산
    if "ATR" in df.columns:
        atr = df["ATR"].iloc[-1]
        atr_percent = atr / current_price
        
        # 변동성 기반 proximity
        if atr_percent < 0.02:  # 변동성 낮음
            proximity = 0.015
        elif atr_percent < 0.05:  # 변동성 보통
            proximity = 0.020
        else:  # 변동성 높음
            proximity = 0.030
    else:
        proximity = 0.020  # Fallback
    
    # 기존 로직에 dynamic proximity 적용
    for level_type, level_price, level_name in levels:
        distance_pct = abs(current_price - level_price) / current_price
        
        if distance_pct <= proximity:
            return ChartPatternResult(...)
```

---

### 통합: detect_chart_patterns()

```python
def detect_chart_patterns(
    df: pd.DataFrame, snapshot: IndicatorSnapshot | None = None
) -> dict[str, ChartPatternResult]:
    """모든 차트 패턴 감지 통합 함수"""
    
    patterns = {
        "cup_and_handle": detect_cup_and_handle(df),
        "double_bottom": detect_double_bottom(df),
        "head_and_shoulders": detect_head_and_shoulders(df),
        "ascending_triangle": detect_ascending_triangle(df),
        "descending_triangle": detect_descending_triangle(df),
        "bullish_flag": detect_bullish_flag(df),
        "bearish_flag": detect_bearish_flag(df),
    }
    
    if snapshot:
        patterns["support_resistance_test"] = test_support_resistance(df, snapshot)
    
    return patterns
```

---

### 테스트 전략

#### Unit Tests

**기존 패턴 수정 검증:**
```python
def test_double_bottom_short_period():
    """20-40일 짧은 기간 Double Bottom 감지"""
    # 25일 간격 패턴 생성
    # 감지 확인
    pass

def test_cup_and_handle_short_cup():
    """40-60일 짧은 Cup 감지"""
    pass

def test_head_and_shoulders_weak_pattern():
    """Head가 3% 높은 약한 H&S"""
    pass
```

**신규 패턴 테스트:**
```python
def test_ascending_triangle_perfect():
    """이상적인 Ascending Triangle"""
    # 고점 수평, 저점 상승, 수렴
    pass

def test_descending_triangle_perfect():
    """이상적인 Descending Triangle"""
    pass

def test_bullish_flag_strong_pole():
    """강한 pole + 적절한 flag"""
    pass

def test_bearish_flag_strong_pole():
    """강한 하락 pole + 적절한 flag"""
    pass

def test_flags_insufficient_pole():
    """Pole이 15% 미만일 때 미감지"""
    pass

def test_triangles_insufficient_convergence():
    """수렴하지 않는 경우 미감지"""
    pass
```

#### Integration Tests

**Real-world 데이터:**
```python
def test_nvts_double_bottom():
    """NVTS 실제 데이터로 Double Bottom 감지 확인"""
    df = fetch_nvts_data()
    result = detect_double_bottom(df)
    assert result.detected == True
    assert result.confidence > 0.7
```

**다양한 종목:**
```python
@pytest.mark.parametrize("ticker", ["AAPL", "NVDA", "TSLA", "META"])
def test_patterns_on_real_stocks(ticker):
    """실제 종목에서 패턴 감지 (false positive 모니터링)"""
    df = fetch_data(ticker)
    patterns = detect_chart_patterns(df)
    # 감지된 패턴 로깅
    detected = [k for k, v in patterns.items() if v.detected]
    print(f"{ticker}: {detected}")
```

---

### 문서 업데이트

#### docs/FEATURES.md

**섹션 1. Technical Analysis Components > Patterns 항목:**

현재:
```markdown
### 8. Patterns (차트 패턴)
- **Cup & Handle**: 60-120일, confidence 0.85
- **Double Bottom**: 40-80일, confidence 0.80
- **Head & Shoulders**: 60-100일, confidence 0.75
- **Support/Resistance Test**: 최근 20일, confidence 0.70
```

업데이트:
```markdown
### 8. Patterns (차트 패턴)

**Phase 2 패턴 (반전/지속):**
- **Cup & Handle**: 40-120일 (handle 2-20일), confidence 0.85
  - Cup depth 15-40%, handle retracement ≤15%
- **Double Bottom**: 20-80일, confidence 0.80
  - Valley 높이 차이 <5%, rebound >10%
- **Head & Shoulders**: 40-100일, confidence 0.75
  - Head > shoulders >3%, shoulder 유사도 <10%
- **Ascending Triangle**: 30-90일, confidence 0.80
  - 수평 저항 + 상승 지지, 수렴 패턴
- **Descending Triangle**: 30-90일, confidence 0.75
  - 하락 저항 + 수평 지지, 수렴 패턴
- **Bullish Flag**: 10-35일 (pole 5-15일 + flag 5-20일), confidence 0.85
  - Pole >15% 상승 + 하향 flag
- **Bearish Flag**: 10-35일, confidence 0.85
  - Pole <-15% 하락 + 상향 flag
- **Support/Resistance Test**: 최근 20일, confidence 0.70
  - 주요 레벨 ±2% (또는 ATR 기반 동적)

**개선사항:**
- Threshold 완화로 짧은 기간 패턴 감지
- ATR 기반 동적 prominence/proximity (선택)
- 실무 표준에 맞춘 파라미터 조정
```

#### docs/CLI_USAGE.md

**analyze 명령어 섹션 업데이트:**

추가:
```markdown
- **실행 가능한 투자 시그널** (Phase 2 강화):
  - 패턴 분석: 차트 패턴 해석 (Cup & Handle, Double Bottom, Head & Shoulders, Triangles, Flags)
  - 목표가: 시나리오별 가격 목표 (돌파 시/조정 시)
  - 진입 구간: 구체적 매수/매도 타이밍
  - 주요 레벨: 지지선/저항선 요약
  - **총 8가지 패턴 감지** (반전형 + 지속형)
```

---

## 구현 순서

### Phase A: 기존 패턴 개선 (우선순위 High)
1. Double Bottom distance 완화 (20-80일)
2. Double Bottom prominence 완화 (3% → 2%)
3. Cup & Handle 기간 완화 (40-120일, handle 20일)
4. Head & Shoulders 기간/prominence 완화
5. NVTS 검증
6. 테스트 추가

### Phase B: Triangle 패턴 추가
1. Ascending Triangle 구현
2. Descending Triangle 구현
3. Confidence scoring
4. 테스트 추가
5. 실제 데이터 검증

### Phase C: Flag 패턴 추가
1. Bullish Flag 구현
2. Bearish Flag 구현
3. Confidence scoring
4. 테스트 추가
5. 실제 데이터 검증

### Phase D: 문서 및 통합
1. FEATURES.md 업데이트
2. CLI_USAGE.md 업데이트
3. 전체 regression test
4. Real-world 종목 테스트 (false positive 모니터링)

### Phase E (선택): Adaptive Threshold
1. ATR 계산 유틸리티
2. Dynamic prominence 적용
3. Dynamic proximity 적용
4. A/B 테스트 (고정 vs 동적)

---

## Trade-offs 및 리스크

### Trade-offs

**완화된 Threshold:**
- ✅ 짧은 기간 패턴 감지 (false negative ↓)
- ⚠️ False positive 증가 가능성
- ✅ Confidence scoring으로 구분

**새 패턴 추가:**
- ✅ 더 다양한 시장 상황 분석
- ⚠️ 코드 복잡도 증가
- ⚠️ 테스트 유지보수 부담
- ✅ 실무에서 실제로 사용하는 패턴들

**ATR 기반 Adaptive:**
- ✅ 변동성별 최적화
- ⚠️ 구현 복잡도
- ⚠️ ATR 계산 오버헤드
- ⚠️ 디버깅 어려움 (동적 파라미터)

### 리스크 완화

**False Positive 관리:**
- Confidence scoring으로 품질 구분
- 실제 데이터 대량 테스트
- 사용자 피드백 수집 메커니즘

**코드 품질:**
- 각 패턴 독립 함수
- 충분한 unit test coverage
- Real-world integration test

**성능:**
- 벡터화 연산 (numpy)
- 불필요한 반복 최소화
- 캐싱 (필요시)

---

## 성공 기준

### Functional
- ✅ NVTS Double Bottom 감지됨
- ✅ 모든 신규 패턴 unit test 통과
- ✅ 기존 5개 테스트 여전히 통과
- ✅ AAPL, NVDA, TSLA 등에서 합리적인 결과

### Non-functional
- ✅ False positive rate <20% (수동 검증)
- ✅ 패턴 감지 시간 <500ms per ticker
- ✅ Code coverage >85%

### Documentation
- ✅ FEATURES.md 업데이트
- ✅ CLI_USAGE.md 업데이트
- ✅ 테스트 케이스 문서화

---

## 참고 자료

### 책/논문
- "Technical Analysis of Stock Trends" by Edwards & Magee
- "Encyclopedia of Chart Patterns" by Thomas Bulkowski

### 코드 예제
- TA-Lib (Technical Analysis Library)
- TradingView Pine Script 패턴 감지 예제

### 실제 사례
- NVTS Double Bottom (2026-02-20 ~ 2026-03-06)
- TradingView 커뮤니티 패턴 사례

---

## 결론

이 설계는 실제 감지 실패 사례(NVTS)를 기반으로 기존 패턴의 threshold를 완화하고, 실무에서 자주 사용되는 Triangle/Flag 패턴을 추가합니다.

**핵심 개선:**
1. **짧은 기간 패턴 감지** (20일 Double Bottom 등)
2. **4가지 주요 패턴 추가** (Triangles, Flags)
3. **Confidence scoring** (품질 구분)
4. **(선택) ATR 기반 adaptive** (변동성 대응)

**검증 계획:**
- NVTS 실제 케이스 확인
- 다양한 종목 테스트
- False positive 모니터링

단계별로 구현하고 각 단계마다 검증하여 점진적으로 개선합니다.

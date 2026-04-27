# Phase 2 차트 패턴 강화 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 차트 패턴 감지 threshold 완화 및 4가지 신규 패턴 추가 (Triangles, Flags)

**Architecture:** 기존 chart_patterns.py 함수 수정 + 신규 패턴 감지 함수 추가, TDD 방식으로 각 변경마다 테스트 작성 후 구현

**Tech Stack:** Python, pandas, numpy, scipy.signal.find_peaks, scipy.stats.linregress, pytest, yfinance

---

## Task 1: Double Bottom Threshold 완화

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py:133-228`
- Modify: `tests/tools/technical/test_chart_patterns.py:80-140`

- [ ] **Step 1: Write failing test for 20-40일 Double Bottom**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def test_double_bottom_short_period():
    """20-40일 짧은 기간 Double Bottom 감지 테스트"""
    # 25일 간격 패턴 생성
    df = create_mock_double_bottom(valley1=100.0, valley2=101.0, days=35)
    result = detect_double_bottom(df)
    
    # 짧은 기간도 감지되어야 함
    assert result.detected is True
    assert result.confidence > 0.6  # 짧은 기간이므로 약간 낮은 confidence
    assert "Double Bottom" == result.pattern_name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_double_bottom_short_period -v`
Expected: FAIL (현재 40일 미만 패턴은 감지 안됨)

- [ ] **Step 3: Modify detect_double_bottom distance threshold**

`src/tools/technical/components/chart_patterns.py`의 `detect_double_bottom` 함수 수정:

```python
# Line 133-143 부근
def detect_double_bottom(df: pd.DataFrame) -> ChartPatternResult:
    """Double Bottom 패턴 감지 (일봉)"""

    if len(df) < 50:
        return ChartPatternResult(
            pattern_name="Double Bottom",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 50일 필요)",
        )

    prices = df["Close"].values

    # Valley 감지 (prominence 완화: 0.03 → 0.02)
    valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean() * 0.02)
```

```python
# Line 149-155 부근 (distance 제약 변경)
    for i in range(1, len(valleys)):
        valley1_idx = valleys[i - 1]
        valley2_idx = valleys[i]

        # Distance 제약 완화: 40-80일 → 20-80일
        if valley2_idx - valley1_idx < 20 or valley2_idx - valley1_idx > 80:
            continue
```

- [ ] **Step 4: Update calculate_double_bottom_confidence for period fit**

`src/tools/technical/components/chart_patterns.py`의 `calculate_double_bottom_confidence` 함수 수정:

```python
# Line 212-228 부근 (전체 함수 교체)
def calculate_double_bottom_confidence(height_diff: float, rebound: float, distance: int) -> float:
    """Double Bottom confidence scoring"""
    confidence = 0.0

    # 1. Valley similarity (0-0.4)
    similarity_score = 1.0 - (height_diff / 0.05)
    confidence += similarity_score * 0.4

    # 2. Rebound strength (0-0.3)
    rebound_score = min(rebound / 0.20, 1.0)
    confidence += rebound_score * 0.3

    # 3. Period fit (0-0.3) - 거리에 따라 차등 점수
    if 40 <= distance <= 60:
        period_score = 1.0
    elif 20 <= distance < 40:
        period_score = 0.85  # 짧은 기간 약간 감점
    elif 60 < distance <= 80:
        period_score = 0.95
    else:
        period_score = 0.5
    confidence += period_score * 0.3

    return min(confidence, 1.0)
```

그리고 `detect_double_bottom` 함수 내 confidence 계산 호출 부분 수정:

```python
# Line 175 부근
            # Calculate confidence (distance 파라미터 추가)
            confidence = calculate_double_bottom_confidence(
                height_diff, rebound, distance=valley2_idx - valley1_idx
            )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_double_bottom_short_period -v`
Expected: PASS

- [ ] **Step 6: Commit Double Bottom threshold changes**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): relax Double Bottom distance constraint to 20-80 days

- Change min distance from 40 to 20 days
- Update confidence scoring to penalize short periods slightly
- Add test for 20-40 day Double Bottom patterns
- Fixes NVTS detection issue (10-day distance case)"
```

---

## Task 2: Cup & Handle Threshold 완화

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py:20-102`
- Modify: `tests/tools/technical/test_chart_patterns.py:8-78`

- [ ] **Step 1: Write failing test for 40-60일 Cup**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def test_cup_and_handle_short_cup():
    """40-60일 짧은 Cup 감지 테스트"""
    df = create_mock_cup_and_handle(cup_depth=0.25, handle_ret=0.10, cup_days=50)
    
    result = detect_cup_and_handle(df)
    
    assert result.detected is True
    assert result.confidence > 0.7
    assert result.pattern_name == "Cup & Handle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_cup_and_handle_short_cup -v`
Expected: FAIL (현재 60일 미만 cup은 감지 안됨)

- [ ] **Step 3: Modify detect_cup_and_handle thresholds**

`src/tools/technical/components/chart_patterns.py`의 `detect_cup_and_handle` 함수 수정:

```python
# Line 20-30 부근
def detect_cup_and_handle(df: pd.DataFrame) -> ChartPatternResult:
    """Cup & Handle 패턴 감지 (일봉 기준)"""

    # 최소 데이터 요구사항 완화: 70일 → 50일
    if len(df) < 50:
        return ChartPatternResult(
            pattern_name="Cup & Handle",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 50일 필요)",
        )
```

```python
# Line 40-45 부근
        # Cup range
        cup_range = prices[left_peak_idx : right_peak_idx + 1]
        # Cup 길이 제약 완화: 60-120일 → 40-120일
        if len(cup_range) < 40 or len(cup_range) > 120:
            continue
```

```python
# Line 54-57 부근
        # Check handle
        # Handle 길이 확장: max 10일 → max 20일
        handle_range = prices[right_peak_idx : min(right_peak_idx + 20, len(prices))]
        if len(handle_range) < 2:
            continue
```

- [ ] **Step 4: Update calculate_cup_handle_confidence for period fit**

`src/tools/technical/components/chart_patterns.py`의 `calculate_cup_handle_confidence` 함수 수정:

```python
# Line 104-131 부근 (period fit 부분 수정)
def calculate_cup_handle_confidence(
    cup_depth: float, handle_ret: float, cup_length: int, weights: dict | None = None
) -> float:
    """Cup & Handle confidence scoring"""

    if weights is None:
        weights = PATTERN_CONFIDENCE_WEIGHTS["cup_and_handle"]

    confidence = 0.0

    # 1. Cup depth fit
    ideal_depth = 0.27
    depth_score = 1.0 - abs(cup_depth - ideal_depth) / 0.125
    confidence += depth_score * weights["depth_weight"]

    # 2. Handle retracement fit
    handle_score = 1.0 - (handle_ret / 0.15)
    confidence += handle_score * weights["handle_weight"]

    # 3. Period fit (거리에 따라 차등 점수)
    if 60 <= cup_length <= 120:
        period_score = 1.0
    elif 40 <= cup_length < 60:
        period_score = 0.9  # 짧은 cup 약간 감점
    else:
        period_score = 0.7
    confidence += period_score * weights["period_weight"]

    # 4. Volume (placeholder)
    confidence += 0.5 * weights["volume_weight"]

    return min(confidence, 1.0)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_cup_and_handle_short_cup -v`
Expected: PASS

- [ ] **Step 6: Commit Cup & Handle threshold changes**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): relax Cup & Handle period constraints

- Min data required: 70 → 50 days
- Cup length: 60-120 → 40-120 days
- Handle max length: 10 → 20 days
- Update confidence scoring for short cups (0.9 penalty)
- Add test for 40-60 day cup patterns"
```

---

## Task 3: Head & Shoulders Threshold 완화

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py:230-323`

- [ ] **Step 1: Write failing test for weak H&S (3% head prominence)**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def test_head_and_shoulders_weak_pattern():
    """약한 Head & Shoulders (3% prominence) 감지 테스트"""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq="D")
    prices = []
    
    # Left shoulder
    for i in range(15):
        prices.append(100 + i * 1.0)  # 100 → 115
    # Descending to valley
    for i in range(10):
        prices.append(115 - i * 1.0)  # 115 → 105
    # Head (3% higher than shoulder)
    for i in range(10):
        prices.append(105 + i * 1.18)  # 105 → 116.8 (약 3% higher)
    # Descending
    for i in range(10):
        prices.append(116.8 - i * 1.18)  # 116.8 → 105
    # Right shoulder
    for i in range(15):
        prices.append(105 + i * 0.67)  # 105 → 115
    
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )
    
    result = detect_head_and_shoulders(df)
    assert result.detected is True
    assert result.confidence > 0.6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_head_and_shoulders_weak_pattern -v`
Expected: FAIL (현재 5% prominence 필요)

- [ ] **Step 3: Modify detect_head_and_shoulders thresholds**

`src/tools/technical/components/chart_patterns.py`의 `detect_head_and_shoulders` 함수 수정:

```python
# Line 230-240 부근
def detect_head_and_shoulders(df: pd.DataFrame) -> ChartPatternResult:
    """Head & Shoulders 패턴 감지 (일봉)"""

    # 최소 데이터 요구사항 완화: 70일 → 50일
    if len(df) < 50:
        return ChartPatternResult(
            pattern_name="Head & Shoulders",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 50일 필요)",
        )

    prices = df["Close"].values

    # Find 3 peaks (distance 증가로 노이즈 필터링: 10 → 15)
    peaks, _ = find_peaks(prices, distance=15, prominence=prices.mean() * 0.05)
```

```python
# Line 256-263 부근
        if (
            # Pattern width 완화: 60-100일 → 40-100일
            right_shoulder_idx - left_shoulder_idx < 40
            or right_shoulder_idx - left_shoulder_idx > 100
        ):
            continue

        left_shoulder = prices[left_shoulder_idx]
        head = prices[head_idx]
        right_shoulder = prices[right_shoulder_idx]

        # Head must be higher (prominence 완화: >5% → >3%)
        if head <= left_shoulder * 1.03 or head <= right_shoulder * 1.03:
            continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_head_and_shoulders_weak_pattern -v`
Expected: PASS

- [ ] **Step 5: Commit Head & Shoulders threshold changes**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): relax Head & Shoulders constraints

- Min data required: 70 → 50 days
- Pattern width: 60-100 → 40-100 days
- Head prominence: >5% → >3%
- Peak distance: 10 → 15 days (noise filtering)
- Add test for weak H&S pattern (3% prominence)"
```

---

## Task 4: Ascending Triangle 신규 패턴 추가

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py` (새 함수 추가)
- Modify: `tests/tools/technical/test_chart_patterns.py` (새 테스트 추가)

- [ ] **Step 1: Write failing test for Ascending Triangle**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def create_mock_ascending_triangle(days: int = 60) -> pd.DataFrame:
    """Generate mock Ascending Triangle pattern
    
    - 수평 저항선 (고점들이 비슷)
    - 상승 지지선 (저점들이 점점 높아짐)
    """
    import numpy as np
    
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    prices = []
    
    resistance = 150.0
    support_start = 130.0
    support_end = 145.0
    
    # 3개의 고점-저점 사이클 생성
    for cycle in range(3):
        cycle_length = days // 3
        
        # 저점 (점점 높아짐)
        support_level = support_start + (support_end - support_start) * (cycle / 2)
        
        for i in range(cycle_length):
            progress = i / cycle_length
            
            # 저점에서 고점으로 상승
            price = support_level + (resistance - support_level) * progress
            
            # 약간의 노이즈 추가
            price += np.random.normal(0, 0.5)
            prices.append(price)
    
    return pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )


def test_ascending_triangle_perfect():
    """이상적인 Ascending Triangle 패턴 감지 테스트"""
    from src.tools.technical.components.chart_patterns import detect_ascending_triangle
    
    df = create_mock_ascending_triangle(days=60)
    result = detect_ascending_triangle(df)
    
    assert result.detected is True
    assert result.confidence > 0.7
    assert result.pattern_name == "Ascending Triangle"
    assert result.breakout_level is not None  # 저항선
    assert result.support_level is not None  # 지지선
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_ascending_triangle_perfect -v`
Expected: FAIL (함수 아직 없음)

- [ ] **Step 3: Implement detect_ascending_triangle function**

`src/tools/technical/components/chart_patterns.py`에 추가 (line 409 이후):

```python
def detect_ascending_triangle(df: pd.DataFrame) -> ChartPatternResult:
    """Ascending Triangle 패턴 감지
    
    수평 저항선 + 상승 지지선, 돌파 시 상승 기대
    """
    if len(df) < 40:
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 40일 필요)",
        )
    
    import numpy as np
    from scipy.stats import linregress
    
    prices = df["Close"].values
    
    # 고점/저점 추출
    peaks, _ = find_peaks(prices, distance=10, prominence=prices.mean() * 0.03)
    valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean() * 0.03)
    
    if len(peaks) < 3 or len(valleys) < 3:
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description="고점/저점 부족 (각 3개 필요)",
        )
    
    # 최근 3-4개 고점/저점만 사용
    recent_peaks = peaks[-4:] if len(peaks) >= 4 else peaks[-3:]
    recent_valleys = valleys[-4:] if len(valleys) >= 4 else valleys[-3:]
    
    # 패턴 기간 확인
    pattern_start = min(recent_peaks[0], recent_valleys[0])
    pattern_end = max(recent_peaks[-1], recent_valleys[-1])
    pattern_length = pattern_end - pattern_start
    
    if not (30 <= pattern_length <= 90):
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"패턴 기간 부적합 ({pattern_length}일, 30-90일 필요)",
        )
    
    # 고점 수평성 확인
    peak_prices = prices[recent_peaks]
    peak_std = np.std(peak_prices) / np.mean(peak_prices)
    
    if peak_std > 0.03:  # 표준편차 >3%면 수평 아님
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"고점 수평성 부족 (std: {peak_std:.2%} > 3%)",
        )
    
    # 저점 상승 추세 확인 (선형회귀)
    valley_prices = prices[recent_valleys]
    slope, intercept, r_value, _, _ = linregress(recent_valleys, valley_prices)
    
    daily_slope = slope / pattern_length
    
    if daily_slope <= 0.001:  # 일일 0.1% 미만 상승이면 불충분
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"저점 상승 추세 불충분 (기울기: {daily_slope*100:.3%}/day)",
        )
    
    # 수렴 확인
    first_gap = peak_prices[0] - valley_prices[0]
    last_gap = peak_prices[-1] - valley_prices[-1]
    
    if last_gap > first_gap * 0.5:  # 간격이 50% 이하로 좁아지지 않음
        return ChartPatternResult(
            pattern_name="Ascending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"수렴 부족 (gap: {last_gap/first_gap:.1%})",
        )
    
    # Confidence 계산
    resistance_level = np.mean(peak_prices)
    support_slope_percent = daily_slope * 100
    convergence_ratio = last_gap / first_gap
    
    confidence = calculate_triangle_confidence(
        peak_std, support_slope_percent, convergence_ratio, "ascending"
    )
    
    # Target price: resistance + (resistance - first valley)
    target = resistance_level + (resistance_level - valley_prices[0])
    
    # Timing
    completed_date = df.index[pattern_end].strftime("%Y-%m-%d")
    days_ago = len(df) - pattern_end - 1
    
    return ChartPatternResult(
        pattern_name="Ascending Triangle",
        detected=True,
        confidence=confidence,
        completed_date=completed_date,
        days_ago=days_ago,
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

- [ ] **Step 4: Implement calculate_triangle_confidence function**

`src/tools/technical/components/chart_patterns.py`에 추가 (detect_ascending_triangle 다음):

```python
def calculate_triangle_confidence(
    peak_std: float,
    slope_percent: float,
    convergence_ratio: float,
    triangle_type: str,  # "ascending" or "descending"
) -> float:
    """Triangle 패턴 confidence scoring
    
    Args:
        peak_std: 수평선 표준편차 (ascending은 고점, descending은 저점)
        slope_percent: 추세선 기울기 (일일 %)
        convergence_ratio: 마지막/첫 gap 비율 (작을수록 수렴)
        triangle_type: 패턴 타입
    """
    confidence = 0.0
    
    # 1. 수평선 품질 (0-0.4)
    horizontal_score = max(0, 1.0 - peak_std / 0.03)
    confidence += horizontal_score * 0.4
    
    # 2. 추세선 기울기 (0-0.3)
    # Ideal: 0.15% per day
    ideal_slope = 0.15
    slope_score = max(0, 1.0 - abs(abs(slope_percent) - ideal_slope) / 0.15)
    confidence += slope_score * 0.3
    
    # 3. 수렴도 (0-0.3)
    # 작을수록 좋음 (0이면 완전 수렴)
    convergence_score = 1.0 - convergence_ratio
    confidence += convergence_score * 0.3
    
    return min(confidence, 1.0)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_ascending_triangle_perfect -v`
Expected: PASS

- [ ] **Step 6: Add test for insufficient convergence (should not detect)**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def test_ascending_triangle_insufficient_convergence():
    """수렴하지 않는 경우 미감지 테스트"""
    from src.tools.technical.components.chart_patterns import detect_ascending_triangle
    import numpy as np
    
    # 평행선 패턴 생성 (수렴 없음)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=60, freq="D")
    prices = []
    
    resistance = 150.0
    support = 130.0
    
    for i in range(60):
        # 저점과 고점 사이 진동 (수렴 없음)
        progress = (i % 20) / 20
        price = support + (resistance - support) * progress
        prices.append(price + np.random.normal(0, 0.5))
    
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )
    
    result = detect_ascending_triangle(df)
    
    # 수렴하지 않으므로 감지되지 않아야 함
    assert result.detected is False
```

- [ ] **Step 7: Run convergence test**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_ascending_triangle_insufficient_convergence -v`
Expected: PASS

- [ ] **Step 8: Commit Ascending Triangle implementation**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): add Ascending Triangle pattern detection

- Detect horizontal resistance + rising support
- Require 30-90 day period with 3+ peaks/valleys
- Check convergence (last gap < 50% of first gap)
- Confidence scoring based on horizontal quality, slope, convergence
- Add helper function calculate_triangle_confidence
- Add tests for perfect pattern and insufficient convergence"
```

---

## Task 5: Descending Triangle 신규 패턴 추가

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py` (새 함수 추가)
- Modify: `tests/tools/technical/test_chart_patterns.py` (새 테스트 추가)

- [ ] **Step 1: Write failing test for Descending Triangle**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def create_mock_descending_triangle(days: int = 60) -> pd.DataFrame:
    """Generate mock Descending Triangle pattern
    
    - 하락 저항선 (고점들이 점점 낮아짐)
    - 수평 지지선 (저점들이 비슷)
    """
    import numpy as np
    
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq="D")
    prices = []
    
    resistance_start = 150.0
    resistance_end = 135.0
    support = 130.0
    
    # 3개의 고점-저점 사이클 생성
    for cycle in range(3):
        cycle_length = days // 3
        
        # 고점 (점점 낮아짐)
        resistance_level = resistance_start - (resistance_start - resistance_end) * (cycle / 2)
        
        for i in range(cycle_length):
            progress = i / cycle_length
            
            # 고점에서 저점으로 하락
            price = resistance_level - (resistance_level - support) * progress
            
            # 약간의 노이즈 추가
            price += np.random.normal(0, 0.5)
            prices.append(price)
    
    return pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
        },
        index=dates,
    )


def test_descending_triangle_perfect():
    """이상적인 Descending Triangle 패턴 감지 테스트"""
    from src.tools.technical.components.chart_patterns import detect_descending_triangle
    
    df = create_mock_descending_triangle(days=60)
    result = detect_descending_triangle(df)
    
    assert result.detected is True
    assert result.confidence > 0.7
    assert result.pattern_name == "Descending Triangle"
    assert result.support_level is not None  # 지지선
    assert result.breakout_level is not None  # 저항선 (하락 돌파 예상)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_descending_triangle_perfect -v`
Expected: FAIL (함수 아직 없음)

- [ ] **Step 3: Implement detect_descending_triangle function**

`src/tools/technical/components/chart_patterns.py`에 추가 (calculate_triangle_confidence 다음):

```python
def detect_descending_triangle(df: pd.DataFrame) -> ChartPatternResult:
    """Descending Triangle 패턴 감지
    
    하락 저항선 + 수평 지지선, 돌파 시 하락 기대
    """
    if len(df) < 40:
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 40일 필요)",
        )
    
    import numpy as np
    from scipy.stats import linregress
    
    prices = df["Close"].values
    
    # 고점/저점 추출
    peaks, _ = find_peaks(prices, distance=10, prominence=prices.mean() * 0.03)
    valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean() * 0.03)
    
    if len(peaks) < 3 or len(valleys) < 3:
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description="고점/저점 부족 (각 3개 필요)",
        )
    
    # 최근 3-4개 고점/저점만 사용
    recent_peaks = peaks[-4:] if len(peaks) >= 4 else peaks[-3:]
    recent_valleys = valleys[-4:] if len(valleys) >= 4 else valleys[-3:]
    
    # 패턴 기간 확인
    pattern_start = min(recent_peaks[0], recent_valleys[0])
    pattern_end = max(recent_peaks[-1], recent_valleys[-1])
    pattern_length = pattern_end - pattern_start
    
    if not (30 <= pattern_length <= 90):
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"패턴 기간 부적합 ({pattern_length}일, 30-90일 필요)",
        )
    
    # 저점 수평성 확인 (Ascending과 반대)
    valley_prices = prices[recent_valleys]
    valley_std = np.std(valley_prices) / np.mean(valley_prices)
    
    if valley_std > 0.03:  # 표준편차 >3%면 수평 아님
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"저점 수평성 부족 (std: {valley_std:.2%} > 3%)",
        )
    
    # 고점 하락 추세 확인 (선형회귀)
    peak_prices = prices[recent_peaks]
    slope, intercept, r_value, _, _ = linregress(recent_peaks, peak_prices)
    
    daily_slope = slope / pattern_length
    
    if daily_slope >= -0.001:  # 일일 -0.1% 초과 하락이면 불충분
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"고점 하락 추세 불충분 (기울기: {daily_slope*100:.3%}/day)",
        )
    
    # 수렴 확인
    first_gap = peak_prices[0] - valley_prices[0]
    last_gap = peak_prices[-1] - valley_prices[-1]
    
    if last_gap > first_gap * 0.5:  # 간격이 50% 이하로 좁아지지 않음
        return ChartPatternResult(
            pattern_name="Descending Triangle",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description=f"수렴 부족 (gap: {last_gap/first_gap:.1%})",
        )
    
    # Confidence 계산
    support_level = np.mean(valley_prices)
    resistance_slope_percent = daily_slope * 100
    convergence_ratio = last_gap / first_gap
    
    confidence = calculate_triangle_confidence(
        valley_std, abs(resistance_slope_percent), convergence_ratio, "descending"
    )
    
    # Target price: support - (first peak - support)
    target = support_level - (peak_prices[0] - support_level)
    
    # Timing
    completed_date = df.index[pattern_end].strftime("%Y-%m-%d")
    days_ago = len(df) - pattern_end - 1
    
    return ChartPatternResult(
        pattern_name="Descending Triangle",
        detected=True,
        confidence=confidence,
        completed_date=completed_date,
        days_ago=days_ago,
        current_price=prices[-1],
        breakout_level=peak_prices[-1],  # 마지막 저항선 (하락 돌파 예상)
        support_level=support_level,
        description=f"저점 수평도 {valley_std:.2%}, 고점 기울기 {resistance_slope_percent:.2%}/day, {pattern_length}일",
        key_levels={
            "support": float(support_level),
            "resistance_start": float(peak_prices[0]),
            "resistance_end": float(peak_prices[-1]),
            "target": float(target),
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_descending_triangle_perfect -v`
Expected: PASS

- [ ] **Step 5: Commit Descending Triangle implementation**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): add Descending Triangle pattern detection

- Detect falling resistance + horizontal support
- Require 30-90 day period with 3+ peaks/valleys
- Check convergence (last gap < 50% of first gap)
- Reuse calculate_triangle_confidence with valley std
- Add test for perfect descending pattern"
```

---

## Task 6: Bullish Flag 신규 패턴 추가

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py` (새 함수 추가)
- Modify: `tests/tools/technical/test_chart_patterns.py` (새 테스트 추가)

- [ ] **Step 1: Write failing test for Bullish Flag**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def create_mock_bullish_flag(pole_days: int = 10, flag_days: int = 15) -> pd.DataFrame:
    """Generate mock Bullish Flag pattern
    
    - Pole: 급등 (>15%)
    - Flag: 하향 채널
    """
    import numpy as np
    
    total_days = pole_days + flag_days + 5
    dates = pd.date_range(end=pd.Timestamp.now(), periods=total_days, freq="D")
    prices = []
    volumes = []
    
    # Pre-pole 안정기
    for i in range(5):
        prices.append(100.0 + np.random.normal(0, 0.5))
        volumes.append(1000000)
    
    # Pole: 급등 (100 → 120, 20%)
    pole_start = 100.0
    pole_end = 120.0
    for i in range(pole_days):
        progress = i / pole_days
        prices.append(pole_start + (pole_end - pole_start) * progress)
        volumes.append(2000000)  # 거래량 증가
    
    # Flag: 하향 채널 (120 → 115, 약 -0.6%/day)
    flag_start = pole_end
    flag_end = 115.0
    for i in range(flag_days):
        progress = i / flag_days
        prices.append(flag_start - (flag_start - flag_end) * progress)
        volumes.append(1200000)  # 거래량 감소
    
    return pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": volumes,
        },
        index=dates,
    )


def test_bullish_flag_strong_pole():
    """강한 pole + 적절한 flag 패턴 감지 테스트"""
    from src.tools.technical.components.chart_patterns import detect_bullish_flag
    
    df = create_mock_bullish_flag(pole_days=10, flag_days=15)
    result = detect_bullish_flag(df)
    
    assert result.detected is True
    assert result.confidence > 0.7
    assert result.pattern_name == "Bullish Flag"
    assert result.breakout_level is not None  # Pole 고점
    assert result.support_level is not None  # Flag 저점
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_bullish_flag_strong_pole -v`
Expected: FAIL (함수 아직 없음)

- [ ] **Step 3: Implement detect_bullish_flag function**

`src/tools/technical/components/chart_patterns.py`에 추가 (detect_descending_triangle 다음):

```python
def detect_bullish_flag(df: pd.DataFrame) -> ChartPatternResult:
    """Bullish Flag 패턴 감지
    
    Pole (급등) + Flag (하향 채널), 상승 추세 지속 기대
    """
    if len(df) < 30:
        return ChartPatternResult(
            pattern_name="Bullish Flag",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 30일 필요)",
        )
    
    import numpy as np
    from scipy.stats import linregress
    
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
            
            slope, intercept, r_value, _, _ = linregress(flag_indices, flag_prices)
            
            # 기울기 조건: 음수이면서 일일 -0.3% ~ -2%
            daily_slope_pct = (slope / prices[flag_start]) * 100
            
            if not (-2.0 <= daily_slope_pct <= -0.3):
                continue
            
            # Flag 조정 깊이 확인
            flag_low = min(flag_prices)
            pole_height = prices[pole_end] - prices[pole_start]
            retracement = (prices[pole_end] - flag_low) / pole_height
            
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
            
            # Target price: current + pole_height
            target = prices[-1] + pole_height
            
            # Timing
            completed_date = df.index[flag_max_end - 1].strftime("%Y-%m-%d")
            days_ago = len(df) - (flag_max_end - 1) - 1
            
            return ChartPatternResult(
                pattern_name="Bullish Flag",
                detected=True,
                confidence=confidence,
                completed_date=completed_date,
                days_ago=days_ago,
                current_price=prices[-1],
                breakout_level=prices[pole_end],
                support_level=flag_low,
                description=f"Pole {pole_gain:.1%} 상승, Flag {daily_slope_pct:.2%}/day, {pole_length + len(flag_prices)}일",
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

- [ ] **Step 4: Implement calculate_flag_confidence function**

`src/tools/technical/components/chart_patterns.py`에 추가 (detect_bullish_flag 다음):

```python
def calculate_flag_confidence(
    pole_gain: float,
    slope_abs: float,
    retracement: float,
    volume_decrease: float,
    flag_type: str,  # "bullish" or "bearish"
) -> float:
    """Flag 패턴 confidence scoring
    
    Args:
        pole_gain: Pole 상승/하락률 (절댓값)
        slope_abs: Flag 기울기 절댓값 (% per day)
        retracement: Flag 조정/반등 비율
        volume_decrease: Flag 거래량 / Pole 거래량
        flag_type: 패턴 타입
    """
    confidence = 0.0
    
    # 1. Pole 강도 (0-0.3)
    # 15% 이상 강함, 30% 이상 매우 강함
    pole_score = min(pole_gain / 0.30, 1.0)
    confidence += pole_score * 0.3
    
    # 2. Flag 기울기 적정성 (0-0.3)
    # Ideal: 1.0% per day
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

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_bullish_flag_strong_pole -v`
Expected: PASS

- [ ] **Step 6: Add test for insufficient pole (should not detect)**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def test_bullish_flag_insufficient_pole():
    """Pole이 15% 미만일 때 미감지 테스트"""
    from src.tools.technical.components.chart_patterns import detect_bullish_flag
    import numpy as np
    
    # 약한 pole (100 → 110, 10%)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=30, freq="D")
    prices = []
    volumes = []
    
    for i in range(5):
        prices.append(100.0)
        volumes.append(1000000)
    
    # Weak pole
    for i in range(10):
        progress = i / 10
        prices.append(100 + 10 * progress)
        volumes.append(2000000)
    
    # Flag
    for i in range(15):
        progress = i / 15
        prices.append(110 - 5 * progress)
        volumes.append(1200000)
    
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": volumes,
        },
        index=dates,
    )
    
    result = detect_bullish_flag(df)
    
    # Pole이 15% 미만이므로 감지되지 않아야 함
    assert result.detected is False
```

- [ ] **Step 7: Run insufficient pole test**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_bullish_flag_insufficient_pole -v`
Expected: PASS

- [ ] **Step 8: Commit Bullish Flag implementation**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): add Bullish Flag pattern detection

- Detect pole (>15% gain in 5-15 days) + flag (downward channel)
- Check flag slope (-0.3% to -2% per day), retracement (30-50%)
- Validate volume pattern (pole high, flag low)
- Confidence scoring based on pole strength, slope, retracement, volume
- Add helper function calculate_flag_confidence
- Add tests for strong pole and insufficient pole cases"
```

---

## Task 7: Bearish Flag 신규 패턴 추가

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py` (새 함수 추가)
- Modify: `tests/tools/technical/test_chart_patterns.py` (새 테스트 추가)

- [ ] **Step 1: Write failing test for Bearish Flag**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def create_mock_bearish_flag(pole_days: int = 10, flag_days: int = 15) -> pd.DataFrame:
    """Generate mock Bearish Flag pattern
    
    - Pole: 급락 (<-15%)
    - Flag: 상향 채널
    """
    import numpy as np
    
    total_days = pole_days + flag_days + 5
    dates = pd.date_range(end=pd.Timestamp.now(), periods=total_days, freq="D")
    prices = []
    volumes = []
    
    # Pre-pole 안정기
    for i in range(5):
        prices.append(120.0 + np.random.normal(0, 0.5))
        volumes.append(1000000)
    
    # Pole: 급락 (120 → 100, -16.7%)
    pole_start = 120.0
    pole_end = 100.0
    for i in range(pole_days):
        progress = i / pole_days
        prices.append(pole_start - (pole_start - pole_end) * progress)
        volumes.append(2000000)  # 거래량 증가
    
    # Flag: 상향 채널 (100 → 105, 약 +0.6%/day)
    flag_start = pole_end
    flag_end = 105.0
    for i in range(flag_days):
        progress = i / flag_days
        prices.append(flag_start + (flag_end - flag_start) * progress)
        volumes.append(1200000)  # 거래량 감소
    
    return pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": volumes,
        },
        index=dates,
    )


def test_bearish_flag_strong_pole():
    """강한 하락 pole + 적절한 flag 패턴 감지 테스트"""
    from src.tools.technical.components.chart_patterns import detect_bearish_flag
    
    df = create_mock_bearish_flag(pole_days=10, flag_days=15)
    result = detect_bearish_flag(df)
    
    assert result.detected is True
    assert result.confidence > 0.7
    assert result.pattern_name == "Bearish Flag"
    assert result.support_level is not None  # Pole 저점
    assert result.breakout_level is not None  # Flag 고점
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_bearish_flag_strong_pole -v`
Expected: FAIL (함수 아직 없음)

- [ ] **Step 3: Implement detect_bearish_flag function**

`src/tools/technical/components/chart_patterns.py`에 추가 (calculate_flag_confidence 다음):

```python
def detect_bearish_flag(df: pd.DataFrame) -> ChartPatternResult:
    """Bearish Flag 패턴 감지
    
    Pole (급락) + Flag (상향 채널), 하락 추세 지속 기대
    """
    if len(df) < 30:
        return ChartPatternResult(
            pattern_name="Bearish Flag",
            detected=False,
            confidence=0.0,
            current_price=df["Close"].iloc[-1],
            description="데이터 부족 (최소 30일 필요)",
        )
    
    import numpy as np
    from scipy.stats import linregress
    
    prices = df["Close"].values
    volumes = df["Volume"].values
    
    # Pole 감지 (최근 25일 내에서)
    for pole_end in range(len(df) - 5, max(len(df) - 25, 5), -1):
        # Pole 길이 5-15일 시도
        for pole_length in range(5, 16):
            pole_start = pole_end - pole_length
            if pole_start < 0:
                continue
            
            pole_loss = (prices[pole_end] / prices[pole_start]) - 1
            
            # 급락 조건 (<-15%)
            if pole_loss > -0.15:
                continue
            
            # Flag 영역 확인 (pole 직후 5-20일)
            flag_start = pole_end
            flag_max_end = min(pole_end + 20, len(prices) - 1)
            
            if flag_max_end - flag_start < 5:
                continue
            
            # Flag 내 가격 추세 확인 (상향 채널)
            flag_prices = prices[flag_start:flag_max_end]
            flag_indices = np.arange(len(flag_prices))
            
            slope, intercept, r_value, _, _ = linregress(flag_indices, flag_prices)
            
            # 기울기 조건: 양수이면서 일일 +0.3% ~ +2%
            daily_slope_pct = (slope / prices[flag_start]) * 100
            
            if not (0.3 <= daily_slope_pct <= 2.0):
                continue
            
            # Flag 반등 깊이 확인
            flag_high = max(flag_prices)
            pole_height = abs(prices[pole_end] - prices[pole_start])
            retracement = (flag_high - prices[pole_end]) / pole_height
            
            if not (0.30 <= retracement <= 0.50):
                continue
            
            # 거래량 패턴 확인 (pole > flag)
            pole_vol_avg = np.mean(volumes[pole_start:pole_end])
            flag_vol_avg = np.mean(volumes[flag_start:flag_max_end])
            
            volume_decrease = flag_vol_avg / pole_vol_avg
            
            # Confidence 계산
            confidence = calculate_flag_confidence(
                abs(pole_loss), abs(daily_slope_pct), retracement, volume_decrease, "bearish"
            )
            
            # Target price: current - pole_height
            target = prices[-1] - pole_height
            
            # Timing
            completed_date = df.index[flag_max_end - 1].strftime("%Y-%m-%d")
            days_ago = len(df) - (flag_max_end - 1) - 1
            
            return ChartPatternResult(
                pattern_name="Bearish Flag",
                detected=True,
                confidence=confidence,
                completed_date=completed_date,
                days_ago=days_ago,
                current_price=prices[-1],
                breakout_level=flag_high,  # 하락 돌파 예상 레벨
                support_level=prices[pole_end],
                description=f"Pole {pole_loss:.1%} 하락, Flag +{daily_slope_pct:.2%}/day, {pole_length + len(flag_prices)}일",
                key_levels={
                    "pole_start": float(prices[pole_start]),
                    "pole_end": float(prices[pole_end]),
                    "flag_high": float(flag_high),
                    "target": float(target),
                },
            )
    
    return ChartPatternResult(
        pattern_name="Bearish Flag",
        detected=False,
        confidence=0.0,
        current_price=prices[-1],
        description="패턴 미감지",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_bearish_flag_strong_pole -v`
Expected: PASS

- [ ] **Step 5: Commit Bearish Flag implementation**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): add Bearish Flag pattern detection

- Detect pole (<-15% loss in 5-15 days) + flag (upward channel)
- Check flag slope (+0.3% to +2% per day), retracement (30-50%)
- Validate volume pattern (pole high, flag low)
- Reuse calculate_flag_confidence for bearish patterns
- Add test for strong bearish pole"
```

---

## Task 8: detect_chart_patterns() 통합

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py:394-409`

- [ ] **Step 1: Write failing test for integrated detection**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
def test_detect_chart_patterns_integration():
    """detect_chart_patterns() 통합 함수 테스트"""
    from src.tools.technical.components.chart_patterns import detect_chart_patterns
    
    # Bullish Flag 패턴 생성
    df = create_mock_bullish_flag(pole_days=10, flag_days=15)
    
    patterns = detect_chart_patterns(df, snapshot=None)
    
    # 8개 패턴 키 확인
    assert "cup_and_handle" in patterns
    assert "double_bottom" in patterns
    assert "head_and_shoulders" in patterns
    assert "ascending_triangle" in patterns
    assert "descending_triangle" in patterns
    assert "bullish_flag" in patterns
    assert "bearish_flag" in patterns
    # support_resistance_test는 snapshot 없으면 제외
    
    # Bullish Flag는 감지되어야 함
    assert patterns["bullish_flag"].detected is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_detect_chart_patterns_integration -v`
Expected: FAIL (신규 패턴들이 아직 통합 안됨)

- [ ] **Step 3: Update detect_chart_patterns function**

`src/tools/technical/components/chart_patterns.py`의 `detect_chart_patterns` 함수 수정:

```python
# Line 394-409 부근 (전체 함수 교체)
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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_detect_chart_patterns_integration -v`
Expected: PASS

- [ ] **Step 5: Run all chart pattern tests to verify nothing broke**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit integration changes**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): integrate new patterns into detect_chart_patterns

- Add ascending_triangle, descending_triangle, bullish_flag, bearish_flag
- Total 8 patterns now detected (7 always + 1 conditional)
- Add integration test verifying all pattern keys present"
```

---

## Task 9: Real Data Integration Tests

**Files:**
- Modify: `tests/tools/technical/test_chart_patterns.py` (새 테스트 추가)

- [ ] **Step 1: Write NVTS Double Bottom integration test**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
import pytest


@pytest.mark.integration
def test_nvts_double_bottom_real_data():
    """NVTS 실제 데이터로 Double Bottom 감지 확인 (integration test)
    
    NVTS는 2026-02-20 ~ 2026-03-06 사이 약 10일 거리 Double Bottom 보유
    Threshold 완화 후 감지되어야 함
    """
    import yfinance as yf
    from src.tools.technical.components.chart_patterns import detect_double_bottom
    
    ticker = yf.Ticker("NVTS")
    df = ticker.history(period="6mo")
    
    if len(df) < 50:
        pytest.skip("NVTS 데이터 부족")
    
    result = detect_double_bottom(df)
    
    # Double Bottom이 감지되어야 함
    assert result.detected is True, f"NVTS Double Bottom 미감지: {result.description}"
    assert result.confidence > 0.6, f"Confidence 너무 낮음: {result.confidence}"
    
    # 감지된 날짜가 2026-02 또는 2026-03이어야 함
    if result.completed_date:
        assert (
            "2026-02" in result.completed_date or "2026-03" in result.completed_date
        ), f"예상 기간 밖 날짜: {result.completed_date}"
    
    print(f"\n✓ NVTS Double Bottom 감지됨:")
    print(f"  Confidence: {result.confidence:.2f}")
    print(f"  완성 날짜: {result.completed_date}")
    print(f"  설명: {result.description}")
```

- [ ] **Step 2: Write multi-stock pattern detection test**

`tests/tools/technical/test_chart_patterns.py`에 추가:

```python
@pytest.mark.integration
@pytest.mark.parametrize("ticker", ["AAPL", "NVDA", "TSLA", "META"])
def test_patterns_on_real_stocks(ticker):
    """실제 종목에서 패턴 감지 테스트 (false positive 모니터링)
    
    여러 종목에서 패턴 감지 실행하고 결과 로깅
    한 종목에서 너무 많은 패턴이 감지되면 threshold가 너무 느슨한 것
    """
    import yfinance as yf
    from src.tools.technical.components.chart_patterns import detect_chart_patterns
    
    ticker_obj = yf.Ticker(ticker)
    df = ticker_obj.history(period="6mo")
    
    if len(df) < 50:
        pytest.skip(f"{ticker} 데이터 부족")
    
    patterns = detect_chart_patterns(df, snapshot=None)
    
    # 감지된 패턴 목록
    detected = [
        (name, result.confidence)
        for name, result in patterns.items()
        if result.detected
    ]
    
    print(f"\n{ticker} 감지된 패턴:")
    if detected:
        for name, conf in detected:
            print(f"  - {name}: {conf:.2f}")
    else:
        print("  (없음)")
    
    # False positive 체크: 한 종목에서 4개 이상이면 의심
    assert len(detected) <= 4, (
        f"{ticker}에서 너무 많은 패턴 감지됨 ({len(detected)}개). "
        f"Threshold가 너무 느슨할 수 있음: {[name for name, _ in detected]}"
    )
```

- [ ] **Step 3: Add pytest markers configuration**

프로젝트 root의 `pyproject.toml` 또는 `pytest.ini`에 integration marker 추가 (이미 있으면 skip):

`pyproject.toml`에 추가:
```toml
[tool.pytest.ini_options]
markers = [
    "integration: marks tests as integration tests (require network, slower)",
]
```

또는 `pytest.ini` 파일 생성:
```ini
[pytest]
markers =
    integration: marks tests as integration tests (require network, slower)
```

- [ ] **Step 4: Run integration tests (requires network)**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_nvts_double_bottom_real_data -v`
Expected: PASS (NVTS Double Bottom 감지됨)

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_patterns_on_real_stocks -v`
Expected: PASS (각 종목에서 0-4개 패턴 감지, 로그 출력)

- [ ] **Step 5: Verify unit tests still pass (fast, no network)**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py -v -m "not integration"`
Expected: All unit tests PASS

- [ ] **Step 6: Commit integration tests**

```bash
git add tests/tools/technical/test_chart_patterns.py pyproject.toml
git commit -m "test(patterns): add real data integration tests

- Add NVTS Double Bottom verification (fixes issue detection)
- Add multi-stock pattern detection test (AAPL, NVDA, TSLA, META)
- Add pytest integration marker for network-dependent tests
- False positive check: fail if >4 patterns detected per stock
- Run with: pytest -m integration (requires network)"
```

---

## Task 10: FEATURES.md 문서 업데이트

**Files:**
- Modify: `docs/FEATURES.md`

- [ ] **Step 1: Read current FEATURES.md Patterns section**

Run: `cat docs/FEATURES.md | grep -A 10 "### 8. Patterns"`

Expected: 현재 4개 패턴 문서화되어 있음

- [ ] **Step 2: Update Patterns section**

`docs/FEATURES.md`의 "### 8. Patterns (차트 패턴)" 섹션 전체 교체:

```markdown
### 8. Patterns (차트 패턴)

**Phase 2 패턴 (반전/지속):**
- **Cup & Handle**: 40-120일 (handle 2-20일), confidence 0.85
  - Cup depth 15-40%, handle retracement ≤15%
  - scipy.signal.find_peaks 기반 고점 감지
- **Double Bottom**: 20-80일, confidence 0.80
  - Valley 높이 차이 <5%, rebound >10%
  - 짧은 기간 패턴 감지 가능 (20일부터)
- **Head & Shoulders**: 40-100일, confidence 0.75
  - Head > shoulders >3%, shoulder 유사도 <10%
  - 약한 패턴도 감지 가능 (3% prominence)
- **Ascending Triangle**: 30-90일, confidence 0.80
  - 수평 저항 + 상승 지지, 수렴 패턴
  - scipy.stats.linregress로 추세선 분석
- **Descending Triangle**: 30-90일, confidence 0.75
  - 하락 저항 + 수평 지지, 수렴 패턴
- **Bullish Flag**: 10-35일 (pole 5-15일 + flag 5-20일), confidence 0.85
  - Pole >15% 상승 + 하향 flag (-0.3% ~ -2%/day)
  - 거래량: pole 높음 → flag 낮음
- **Bearish Flag**: 10-35일, confidence 0.85
  - Pole <-15% 하락 + 상향 flag (+0.3% ~ +2%/day)
- **Support/Resistance Test**: 최근 20일, confidence 0.70
  - 주요 레벨 ±2% 근접 테스트

**개선사항 (Phase 2 enhancement):**
- Threshold 완화로 짧은 기간 패턴 감지 (NVTS 같은 실패 케이스 해결)
- 4가지 신규 패턴 추가 (Triangles, Flags)
- Real data integration tests로 검증
- 총 8가지 패턴 지원 (반전형 4개 + 지속형 2개 + 테스트 2개)
```

- [ ] **Step 3: Verify FEATURES.md syntax**

Run: `cat docs/FEATURES.md | grep -A 30 "### 8. Patterns"`

Expected: 새로운 내용 출력, 마크다운 문법 오류 없음

- [ ] **Step 4: Commit FEATURES.md update**

```bash
git add docs/FEATURES.md
git commit -m "docs: update FEATURES.md with Phase 2 pattern enhancements

- Document 4 new patterns (Triangles, Flags)
- Update thresholds for existing patterns (relaxed constraints)
- Add implementation details (scipy functions)
- Total 8 patterns now supported"
```

---

## Task 11: CLI_USAGE.md 문서 업데이트

**Files:**
- Modify: `docs/CLI_USAGE.md`

- [ ] **Step 1: Read current CLI_USAGE.md analyze section**

Run: `cat docs/CLI_USAGE.md | grep -A 20 "실행 가능한 투자 시그널"`

Expected: Phase 2 강화 내용 있지만 8가지 패턴 언급 없음

- [ ] **Step 2: Update analyze command output description**

`docs/CLI_USAGE.md`의 "실행 가능한 투자 시그널 (Phase 2 강화)" 섹션 업데이트:

```markdown
- **실행 가능한 투자 시그널** (Phase 2 강화):
  - 패턴 분석: 차트 패턴 해석 (Cup & Handle, Double Bottom, Head & Shoulders, Ascending Triangle, Descending Triangle, Bullish Flag, Bearish Flag)
  - 목표가: 시나리오별 가격 목표 (돌파 시/조정 시)
  - 진입 구간: 구체적 매수/매도 타이밍
  - 주요 레벨: 지지선/저항선 요약
  - **총 8가지 패턴 감지** (반전형 4개 + 지속형 4개)
  - **짧은 기간 패턴 감지 개선** (20일부터 감지 가능)
```

- [ ] **Step 3: Verify CLI_USAGE.md syntax**

Run: `cat docs/CLI_USAGE.md | grep -A 8 "실행 가능한 투자 시그널"`

Expected: 업데이트된 내용 출력

- [ ] **Step 4: Commit CLI_USAGE.md update**

```bash
git add docs/CLI_USAGE.md
git commit -m "docs: update CLI_USAGE.md with Phase 2 pattern details

- List all 8 pattern types in analyze command output
- Mention short-period detection improvement (20 days)
- Clarify reversal vs continuation patterns"
```

---

## Task 12: Final Verification and Cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py -v`
Expected: All tests PASS (unit + integration)

- [ ] **Step 2: Run only unit tests (fast)**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py -v -m "not integration"`
Expected: All unit tests PASS

- [ ] **Step 3: Verify debug script still works**

Run: `uv run python debug_nvts.py`
Expected: NVTS Double Bottom 감지됨 (Valley 5→6, 10일 거리, 통과 여부 True)

- [ ] **Step 4: Clean up debug script**

```bash
rm debug_nvts.py
git add -u
```

- [ ] **Step 5: Run linter and formatter**

Run:
```bash
uv run ruff check src/tools/technical/components/chart_patterns.py
uv run ruff format src/tools/technical/components/chart_patterns.py
uv run ruff check tests/tools/technical/test_chart_patterns.py
uv run ruff format tests/tools/technical/test_chart_patterns.py
```

Expected: No errors, files formatted

- [ ] **Step 6: Verify pre-commit hooks pass**

Run: `git diff --cached`
Expected: 변경사항 확인

Run: `git commit --dry-run`
Expected: pre-commit hooks 통과 (ruff, FEATURES.md check)

- [ ] **Step 7: Final commit for cleanup**

```bash
git add .
git commit -m "chore: cleanup debug files and run linter

- Remove debug_nvts.py (temporary debugging script)
- Format all modified files with ruff
- Verify all pre-commit hooks pass"
```

---

## Summary

**구현 완료:**
- ✅ Double Bottom threshold 완화 (40→20일)
- ✅ Cup & Handle threshold 완화 (60→40일, handle 20일)
- ✅ Head & Shoulders threshold 완화 (60→40일, prominence 3%)
- ✅ Ascending Triangle 신규 패턴 추가
- ✅ Descending Triangle 신규 패턴 추가
- ✅ Bullish Flag 신규 패턴 추가
- ✅ Bearish Flag 신규 패턴 추가
- ✅ detect_chart_patterns() 통합 (8개 패턴)
- ✅ Unit tests (synthetic data)
- ✅ Integration tests (NVTS, AAPL, NVDA, TSLA, META)
- ✅ 문서 업데이트 (FEATURES.md, CLI_USAGE.md)

**검증 방법:**
```bash
# Unit tests (빠름)
uv run pytest tests/tools/technical/test_chart_patterns.py -v -m "not integration"

# Integration tests (느림, 네트워크 필요)
uv run pytest tests/tools/technical/test_chart_patterns.py -v -m integration

# 전체 테스트
uv run pytest tests/tools/technical/test_chart_patterns.py -v

# NVTS 검증 (설계 목표)
uv run pytest tests/tools/technical/test_chart_patterns.py::test_nvts_double_bottom_real_data -v
```

**다음 단계:**
- `jarvis analyze NVTS` 실행하여 실제 패턴 감지 확인
- 다른 종목들에서 false positive 모니터링
- 필요시 threshold 미세 조정

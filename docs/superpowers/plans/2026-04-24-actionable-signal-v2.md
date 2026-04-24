# Actionable Signal v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add chart pattern detection (Cup & Handle, Double Bottom, H&S, S/R Test) and comprehensive price level analysis to provide specific entry zones, price targets, and pattern insights in investment signals.

**Architecture:** Extends existing 8-component technical analysis system with two new modules: `chart_patterns.py` (scipy-based pattern detection) and `price_levels.py` (Fibonacci/ATR/pivot calculations). Integrates into DeepDivePipeline via enhanced LLM prompts that receive structured pattern and level data. Maintains backward compatibility with Phase 1.

**Tech Stack:** scipy.signal.find_peaks, pandas, pydantic, existing technical analysis infrastructure

---

## File Structure

**New Files:**
- `src/tools/technical/utils.py` - Helper functions (find_last_occurrence, mock generators)
- `src/tools/technical/components/chart_patterns.py` - Pattern detection (4 patterns)
- `src/tools/technical/price_levels.py` - Price level calculation and deduplication
- `tests/fixtures/patterns/` - Test snapshot data
- `tests/tools/technical/test_utils.py` - Helper function tests
- `tests/tools/technical/test_chart_patterns.py` - Pattern detection tests
- `tests/tools/technical/test_price_levels.py` - Price level tests
- `tests/integration/test_known_patterns.py` - Historical pattern validation
- `tests/pipelines/test_deep_dive_v2.py` - E2E integration tests

**Modified Files:**
- `src/tools/technical/models.py` - Add ChartPatternResult, PriceLevel, PriceLevels
- `src/llm/models.py` - Extend ActionableSignalOutput with 4 new fields
- `src/llm/analyzer.py` - Enhance generate_actionable_signal prompt
- `src/pipelines/deep_dive.py` - Integrate pattern/level detection
- `src/cli/main.py` - Display new fields in Rich Panel

---

## Task 1: Add Data Models

**Files:**
- Modify: `src/tools/technical/models.py`
- Test: `tests/tools/technical/test_models.py`

- [ ] **Step 1: Write test for ChartPatternResult model**

```python
# tests/tools/technical/test_models.py

def test_chart_pattern_result_creation():
    """Test ChartPatternResult model with all fields"""
    result = ChartPatternResult(
        pattern_name="Cup & Handle",
        detected=True,
        confidence=0.85,
        completed_date="2026-04-15",
        days_ago=8,
        current_price=200.0,
        breakout_level=205.0,
        support_level=175.0,
        description="컵 깊이 28%, 핸들 조정 12%, 8일 전 완성",
        key_levels={"cup_bottom": 140.0, "right_peak": 200.0}
    )
    
    assert result.detected is True
    assert result.confidence == 0.85
    assert result.pattern_name == "Cup & Handle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_models.py::test_chart_pattern_result_creation -v`
Expected: FAIL with "NameError: name 'ChartPatternResult' is not defined"

- [ ] **Step 3: Add ChartPatternResult to models.py**

```python
# src/tools/technical/models.py

from pydantic import BaseModel, Field

class ChartPatternResult(BaseModel):
    """차트 패턴 감지 결과"""
    
    pattern_name: str
    detected: bool
    confidence: float = Field(ge=0.0, le=1.0)
    
    # 타이밍 정보
    completed_date: str | None = None
    days_ago: int | None = None
    
    # 가격 정보
    current_price: float
    breakout_level: float | None = None
    support_level: float | None = None
    
    # 상세 정보
    description: str
    key_levels: dict = Field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_models.py::test_chart_pattern_result_creation -v`
Expected: PASS

- [ ] **Step 5: Write test for PriceLevel model**

```python
def test_price_level_model():
    """Test PriceLevel with distance calculation"""
    level = PriceLevel(
        price=187.50,
        type="pivot_s1",
        distance_pct=-6.25,
        description="피봇 지지1"
    )
    
    assert level.price == 187.50
    assert level.type == "pivot_s1"
    assert level.distance_pct == -6.25
```

- [ ] **Step 6: Add PriceLevel to models.py**

```python
class PriceLevel(BaseModel):
    """개별 가격 레벨"""
    price: float
    type: str
    distance_pct: float
    description: str
```

- [ ] **Step 7: Write test for PriceLevels container**

```python
def test_price_levels_container():
    """Test PriceLevels with sorted supports/resistances"""
    levels = PriceLevels(
        current_price=200.0,
        support_levels=[
            PriceLevel(price=187.0, type="pivot_s1", distance_pct=-6.5, description="피봇 S1"),
            PriceLevel(price=175.0, type="sma_50", distance_pct=-12.5, description="50일선"),
        ],
        resistance_levels=[
            PriceLevel(price=210.0, type="pivot_r1", distance_pct=+5.0, description="피봇 R1"),
        ],
        targets={"cup_handle": 250.0, "fib_1.618": 235.0}
    )
    
    assert levels.current_price == 200.0
    assert len(levels.support_levels) == 2
    assert levels.support_levels[0].price == 187.0  # Closer support first
    assert levels.targets["cup_handle"] == 250.0
```

- [ ] **Step 8: Add PriceLevels to models.py**

```python
class PriceLevels(BaseModel):
    """통합 가격 레벨 정보"""
    current_price: float
    support_levels: list[PriceLevel] = Field(default_factory=list)
    resistance_levels: list[PriceLevel] = Field(default_factory=list)
    targets: dict[str, float] = Field(default_factory=dict)
```

- [ ] **Step 9: Run all model tests**

Run: `uv run pytest tests/tools/technical/test_models.py -v`
Expected: All PASS

- [ ] **Step 10: Commit models**

```bash
git add src/tools/technical/models.py tests/tools/technical/test_models.py
git commit -m "feat(models): add ChartPatternResult and PriceLevels data models

- ChartPatternResult: pattern detection result with timing and price info
- PriceLevel: individual support/resistance level
- PriceLevels: container for organized price levels and targets

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add Helper Functions

**Files:**
- Create: `src/tools/technical/utils.py`
- Test: `tests/tools/technical/test_utils.py`

- [ ] **Step 1: Write test for find_last_occurrence**

```python
# tests/tools/technical/test_utils.py

import pandas as pd
from src.tools.technical.utils import find_last_occurrence

def test_find_last_occurrence_exact_match():
    """Test finding exact value"""
    df = pd.DataFrame({
        'High': [100, 105, 110, 105, 100]
    })
    
    idx = find_last_occurrence(df, 'High', 110)
    assert idx == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_utils.py::test_find_last_occurrence_exact_match -v`
Expected: FAIL with "cannot import name 'find_last_occurrence'"

- [ ] **Step 3: Implement find_last_occurrence**

```python
# src/tools/technical/utils.py

import pandas as pd

def find_last_occurrence(
    df: pd.DataFrame,
    column: str,
    target_value: float,
    tolerance: float = 0.001
) -> int | None:
    """DataFrame에서 특정 값이 마지막으로 나타난 인덱스 찾기
    
    Args:
        df: 데이터프레임
        column: 검색할 컬럼명
        target_value: 찾을 값
        tolerance: 허용 오차 (±0.1% = 0.001)
    
    Returns:
        마지막 발생 인덱스 (없으면 None)
    """
    mask = (df[column] - target_value).abs() / target_value <= tolerance
    matches = df.index[mask]
    
    if len(matches) == 0:
        return None
    
    # Return integer index, not label
    return df.index.get_loc(matches[-1])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_utils.py::test_find_last_occurrence_exact_match -v`
Expected: PASS

- [ ] **Step 5: Write test for tolerance handling**

```python
def test_find_last_occurrence_with_tolerance():
    """Test tolerance for similar values (±0.1%)"""
    df = pd.DataFrame({
        'High': [100.0, 105.0, 110.0, 110.05, 100.0]  # 110.05 is within 0.1% of 110
    })
    
    idx = find_last_occurrence(df, 'High', 110.0, tolerance=0.001)
    assert idx == 3  # Should match 110.05
```

- [ ] **Step 6: Run tolerance test**

Run: `uv run pytest tests/tools/technical/test_utils.py::test_find_last_occurrence_with_tolerance -v`
Expected: PASS

- [ ] **Step 7: Write test for mock data generators**

```python
from src.tools.technical.utils import create_flat_price_series, create_noisy_series, create_random_walk

def test_create_flat_price_series():
    """Test flat price series generator"""
    df = create_flat_price_series(days=120, price=100.0)
    
    assert len(df) == 120
    assert 'Close' in df.columns
    assert df['Close'].mean() == 100.0
    assert df['Close'].std() < 0.5  # Very flat
```

- [ ] **Step 8: Implement mock data generators**

```python
def create_flat_price_series(days: int, price: float) -> pd.DataFrame:
    """평평한 가격 시계열 생성 (횡보)"""
    import numpy as np
    
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
    noise = np.random.normal(0, price * 0.001, days)
    
    return pd.DataFrame({
        'Open': price + noise,
        'High': price + abs(noise),
        'Low': price - abs(noise),
        'Close': price + noise * 0.5,
    }, index=dates)

def create_noisy_series(days: int, base: float, noise: float = 0.02) -> pd.DataFrame:
    """노이즈가 있는 시계열 생성"""
    import numpy as np
    
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
    noise_values = np.random.normal(0, base * noise, days)
    
    return pd.DataFrame({
        'Open': base + noise_values,
        'High': base + abs(noise_values) * 1.2,
        'Low': base - abs(noise_values) * 1.2,
        'Close': base + noise_values * 0.8,
    }, index=dates)

def create_random_walk(days: int, start: float) -> pd.DataFrame:
    """랜덤워크 시계열 생성"""
    import numpy as np
    
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
    returns = np.random.normal(0.001, 0.02, days)
    prices = start * np.exp(np.cumsum(returns))
    
    return pd.DataFrame({
        'Open': prices,
        'High': prices * 1.01,
        'Low': prices * 0.99,
        'Close': prices,
    }, index=dates)
```

- [ ] **Step 9: Run all util tests**

Run: `uv run pytest tests/tools/technical/test_utils.py -v`
Expected: All PASS

- [ ] **Step 10: Commit utils**

```bash
git add src/tools/technical/utils.py tests/tools/technical/test_utils.py
git commit -m "feat(utils): add helper functions for pattern detection

- find_last_occurrence: locate value in DataFrame with tolerance
- Mock data generators: flat, noisy, random walk series for testing

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Implement Cup & Handle Pattern Detection

**Files:**
- Create: `src/tools/technical/components/chart_patterns.py`
- Test: `tests/tools/technical/test_chart_patterns.py`

- [ ] **Step 1: Write test for Cup & Handle detection**

```python
# tests/tools/technical/test_chart_patterns.py

import pandas as pd
import numpy as np
from src.tools.technical.components.chart_patterns import detect_cup_and_handle
from src.tools.technical.models import ChartPatternResult

def create_mock_cup_and_handle(
    cup_depth: float = 0.25,
    handle_ret: float = 0.10,
    cup_days: int = 60
) -> pd.DataFrame:
    """Generate mock Cup & Handle pattern"""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=cup_days + 20, freq='D')
    
    # Left peak
    left_peak = 200.0
    # Cup bottom
    cup_bottom = left_peak * (1 - cup_depth)
    # Right peak
    right_peak = left_peak * 0.98
    # Handle bottom
    handle_bottom = right_peak * (1 - handle_ret)
    
    prices = []
    for i in range(len(dates)):
        if i < 10:
            prices.append(left_peak)
        elif i < 10 + cup_days // 2:
            # Descending to cup bottom
            progress = (i - 10) / (cup_days // 2)
            prices.append(left_peak - (left_peak - cup_bottom) * progress)
        elif i < 10 + cup_days:
            # Ascending to right peak
            progress = (i - 10 - cup_days // 2) / (cup_days // 2)
            prices.append(cup_bottom + (right_peak - cup_bottom) * progress)
        else:
            # Handle
            progress = (i - 10 - cup_days) / 10
            prices.append(right_peak - (right_peak - handle_bottom) * progress)
    
    return pd.DataFrame({
        'Open': prices,
        'High': [p * 1.01 for p in prices],
        'Low': [p * 0.99 for p in prices],
        'Close': prices,
    }, index=dates)

def test_cup_and_handle_perfect_pattern():
    """Test Cup & Handle detection with ideal parameters"""
    df = create_mock_cup_and_handle(cup_depth=0.25, handle_ret=0.10, cup_days=60)
    
    result = detect_cup_and_handle(df)
    
    assert result.detected is True
    assert result.confidence > 0.7
    assert result.pattern_name == "Cup & Handle"
    assert result.breakout_level is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_cup_and_handle_perfect_pattern -v`
Expected: FAIL with "cannot import name 'detect_cup_and_handle'"

- [ ] **Step 3: Implement Cup & Handle detection skeleton**

```python
# src/tools/technical/components/chart_patterns.py

import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from src.tools.technical.models import ChartPatternResult

# Pattern confidence weights (externalized config)
PATTERN_CONFIDENCE_WEIGHTS = {
    "cup_and_handle": {
        "depth_weight": 0.3,
        "handle_weight": 0.3,
        "period_weight": 0.2,
        "volume_weight": 0.2,
    },
}

def detect_cup_and_handle(df: pd.DataFrame) -> ChartPatternResult:
    """Cup & Handle 패턴 감지 (일봉 기준)"""
    
    if len(df) < 70:
        return ChartPatternResult(
            pattern_name="Cup & Handle",
            detected=False,
            confidence=0.0,
            current_price=df['Close'].iloc[-1],
            description="데이터 부족 (최소 70일 필요)"
        )
    
    prices = df['Close'].values
    
    # Find peaks
    peaks, _ = find_peaks(prices, distance=5, prominence=prices.mean()*0.05)
    
    for i in range(1, len(peaks)):
        left_peak_idx = peaks[i-1]
        right_peak_idx = peaks[i]
        
        # Cup range
        cup_range = prices[left_peak_idx : right_peak_idx+1]
        if len(cup_range) < 60 or len(cup_range) > 120:
            continue
        
        cup_max = max(prices[left_peak_idx], prices[right_peak_idx])
        cup_min = min(cup_range)
        cup_depth = (cup_max - cup_min) / cup_max
        
        # Validate cup depth (15-40%)
        if not (0.15 <= cup_depth <= 0.40):
            continue
        
        # Check handle
        handle_range = prices[right_peak_idx : min(right_peak_idx + 10, len(prices))]
        if len(handle_range) < 2:
            continue
        
        handle_max = handle_range[0]
        handle_min = min(handle_range)
        handle_retracement = (handle_max - handle_min) / handle_max
        
        # Validate handle (<15%, above cup bottom)
        if handle_retracement <= 0.15 and handle_min > cup_min:
            
            # Calculate confidence
            confidence = calculate_cup_handle_confidence(
                cup_depth, handle_retracement, len(cup_range)
            )
            
            # Timing
            completed_idx = right_peak_idx
            completed_date = df.index[completed_idx].strftime("%Y-%m-%d")
            days_ago = len(df) - completed_idx - 1
            
            # Target price
            target = cup_max + (cup_max - cup_min)
            
            return ChartPatternResult(
                pattern_name="Cup & Handle",
                detected=True,
                confidence=confidence,
                completed_date=completed_date,
                days_ago=days_ago,
                current_price=prices[-1],
                breakout_level=cup_max,
                support_level=cup_min,
                description=f"컵 깊이 {cup_depth:.1%}, 핸들 조정 {handle_retracement:.1%}, {days_ago}일 전 완성",
                key_levels={"cup_bottom": float(cup_min), "right_peak": float(cup_max), "target": float(target)},
            )
    
    return ChartPatternResult(
        pattern_name="Cup & Handle",
        detected=False,
        confidence=0.0,
        current_price=prices[-1],
        description="패턴 미감지"
    )

def calculate_cup_handle_confidence(
    cup_depth: float,
    handle_ret: float,
    cup_length: int,
    weights: dict | None = None
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
    
    # 3. Period fit
    if 60 <= cup_length <= 120:
        confidence += weights["period_weight"]
    
    # 4. Volume (placeholder)
    confidence += 0.5 * weights["volume_weight"]
    
    return min(confidence, 1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_cup_and_handle_perfect_pattern -v`
Expected: PASS

- [ ] **Step 5: Write test for edge case (too shallow)**

```python
def test_cup_and_handle_too_shallow():
    """Cup too shallow (10%) should not detect"""
    df = create_mock_cup_and_handle(cup_depth=0.10)
    
    result = detect_cup_and_handle(df)
    
    assert result.detected is False
```

- [ ] **Step 6: Run edge case test**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_cup_and_handle_too_shallow -v`
Expected: PASS

- [ ] **Step 7: Commit Cup & Handle detection**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): implement Cup & Handle pattern detection

- scipy.find_peaks based peak detection
- Validate cup depth (15-40%), handle retracement (<15%)
- Confidence scoring with externalized weights
- Returns target price and key levels

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Implement Double Bottom Pattern

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py`
- Test: `tests/tools/technical/test_chart_patterns.py`

- [ ] **Step 1: Write test for Double Bottom**

```python
def create_mock_double_bottom(
    valley1: float = 100.0,
    valley2: float = 101.0,
    neckline: float = 120.0,
    days: int = 60
) -> pd.DataFrame:
    """Generate mock Double Bottom pattern"""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='D')
    
    prices = []
    for i in range(days):
        if i < days // 3:
            # Descending to first valley
            progress = i / (days // 3)
            prices.append(neckline - (neckline - valley1) * progress)
        elif i < 2 * days // 3:
            # Ascending to neckline
            progress = (i - days // 3) / (days // 3)
            prices.append(valley1 + (neckline - valley1) * progress)
        else:
            # Descending to second valley then up
            progress = (i - 2 * days // 3) / (days // 3)
            if progress < 0.5:
                prices.append(neckline - (neckline - valley2) * (progress * 2))
            else:
                prices.append(valley2 + (neckline - valley2) * ((progress - 0.5) * 2))
    
    return pd.DataFrame({
        'Open': prices,
        'High': [p * 1.01 for p in prices],
        'Low': [p * 0.99 for p in prices],
        'Close': prices,
    }, index=dates)

def test_double_bottom_similar_valleys():
    """Test Double Bottom with similar valley heights"""
    df = create_mock_double_bottom(valley1=100.0, valley2=101.0)
    
    result = detect_double_bottom(df)
    
    assert result.detected is True
    assert result.confidence > 0.6
    assert result.pattern_name == "Double Bottom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_double_bottom_similar_valleys -v`
Expected: FAIL with "cannot import name 'detect_double_bottom'"

- [ ] **Step 3: Implement Double Bottom detection**

```python
# Add to src/tools/technical/components/chart_patterns.py

def detect_double_bottom(df: pd.DataFrame) -> ChartPatternResult:
    """Double Bottom 패턴 감지 (일봉)"""
    
    if len(df) < 50:
        return ChartPatternResult(
            pattern_name="Double Bottom",
            detected=False,
            confidence=0.0,
            current_price=df['Close'].iloc[-1],
            description="데이터 부족 (최소 50일 필요)"
        )
    
    prices = df['Close'].values
    
    # Find valleys (inverted peaks)
    valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean()*0.03)
    
    for i in range(1, len(valleys)):
        valley1_idx = valleys[i-1]
        valley2_idx = valleys[i]
        
        if valley2_idx - valley1_idx < 40 or valley2_idx - valley1_idx > 80:
            continue
        
        bottom1 = prices[valley1_idx]
        bottom2 = prices[valley2_idx]
        
        # Check valley height similarity (<5%)
        height_diff = abs(bottom1 - bottom2) / min(bottom1, bottom2)
        if height_diff > 0.05:
            continue
        
        # Find neckline (middle peak)
        middle_range = prices[valley1_idx : valley2_idx]
        neckline = max(middle_range)
        
        # Validate rebound (>10%)
        rebound = (neckline - min(bottom1, bottom2)) / min(bottom1, bottom2)
        if rebound < 0.10:
            continue
        
        # Confidence
        confidence = calculate_double_bottom_confidence(height_diff, rebound)
        
        # Timing
        completed_idx = valley2_idx
        completed_date = df.index[completed_idx].strftime("%Y-%m-%d")
        days_ago = len(df) - completed_idx - 1
        
        # Target
        target = neckline + (neckline - min(bottom1, bottom2))
        
        return ChartPatternResult(
            pattern_name="Double Bottom",
            detected=True,
            confidence=confidence,
            completed_date=completed_date,
            days_ago=days_ago,
            current_price=prices[-1],
            breakout_level=neckline,
            support_level=min(bottom1, bottom2),
            description=f"두 저점 높이 차이 {height_diff:.1%}, {days_ago}일 전 완성",
            key_levels={"bottom1": float(bottom1), "bottom2": float(bottom2), "neckline": float(neckline), "target": float(target)},
        )
    
    return ChartPatternResult(
        pattern_name="Double Bottom",
        detected=False,
        confidence=0.0,
        current_price=prices[-1],
        description="패턴 미감지"
    )

def calculate_double_bottom_confidence(height_diff: float, rebound: float) -> float:
    """Double Bottom confidence scoring"""
    confidence = 0.0
    
    # 1. Valley similarity (0-0.4)
    similarity_score = 1.0 - (height_diff / 0.05)
    confidence += similarity_score * 0.4
    
    # 2. Rebound strength (0-0.3)
    rebound_score = min(rebound / 0.20, 1.0)
    confidence += rebound_score * 0.3
    
    # 3. Period fit (0-0.3)
    confidence += 0.3
    
    return min(confidence, 1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_double_bottom_similar_valleys -v`
Expected: PASS

- [ ] **Step 5: Commit Double Bottom**

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): add Double Bottom pattern detection

- Detects two valleys with similar heights (<5% difference)
- Validates neckline rebound (>10%)
- Confidence based on valley similarity and rebound strength

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Implement Head & Shoulders Pattern

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py`
- Test: `tests/tools/technical/test_chart_patterns.py`

- [ ] **Step 1: Write test for Head & Shoulders**

```python
def test_head_and_shoulders_detection():
    """Test H&S pattern with 3 peaks"""
    # Create mock H&S pattern
    dates = pd.date_range(end=pd.Timestamp.now(), periods=80, freq='D')
    prices = []
    
    for i in range(80):
        if i < 20:
            prices.append(100 + i * 2)  # Left shoulder ascend
        elif i < 40:
            prices.append(140 - (i - 20) * 2)  # Descend
        elif i < 50:
            prices.append(100 + (i - 40) * 3)  # Head ascend
        elif i < 60:
            prices.append(130 - (i - 50) * 3)  # Descend
        elif i < 70:
            prices.append(100 + (i - 60) * 2)  # Right shoulder ascend
        else:
            prices.append(120 - (i - 70) * 2)  # Final descend
    
    df = pd.DataFrame({
        'Open': prices,
        'High': [p * 1.01 for p in prices],
        'Low': [p * 0.99 for p in prices],
        'Close': prices,
    }, index=dates)
    
    result = detect_head_and_shoulders(df)
    
    assert result.detected is True
    assert result.pattern_name == "Head & Shoulders"
```

- [ ] **Step 2: Implement Head & Shoulders detection**

```python
# Add to chart_patterns.py

def detect_head_and_shoulders(df: pd.DataFrame) -> ChartPatternResult:
    """Head & Shoulders 패턴 감지 (일봉)"""
    
    if len(df) < 70:
        return ChartPatternResult(
            pattern_name="Head & Shoulders",
            detected=False,
            confidence=0.0,
            current_price=df['Close'].iloc[-1],
            description="데이터 부족 (최소 70일 필요)"
        )
    
    prices = df['Close'].values
    
    # Find 3 peaks
    peaks, _ = find_peaks(prices, distance=10, prominence=prices.mean()*0.05)
    
    if len(peaks) < 3:
        return ChartPatternResult(
            pattern_name="Head & Shoulders",
            detected=False,
            confidence=0.0,
            current_price=prices[-1],
            description="고점 부족 (3개 필요)"
        )
    
    for i in range(len(peaks) - 2):
        left_shoulder_idx = peaks[i]
        head_idx = peaks[i+1]
        right_shoulder_idx = peaks[i+2]
        
        if right_shoulder_idx - left_shoulder_idx < 60 or right_shoulder_idx - left_shoulder_idx > 100:
            continue
        
        left_shoulder = prices[left_shoulder_idx]
        head = prices[head_idx]
        right_shoulder = prices[right_shoulder_idx]
        
        # Head must be higher (>5%)
        if head <= left_shoulder * 1.05 or head <= right_shoulder * 1.05:
            continue
        
        # Shoulders similar height (<10%)
        shoulder_diff = abs(left_shoulder - right_shoulder) / max(left_shoulder, right_shoulder)
        if shoulder_diff > 0.10:
            continue
        
        # Neckline
        left_valley = prices[left_shoulder_idx : head_idx].min()
        right_valley = prices[head_idx : right_shoulder_idx].min()
        neckline = (left_valley + right_valley) / 2
        
        # Confidence
        head_prominence = (head - max(left_shoulder, right_shoulder)) / head
        confidence = calculate_head_shoulders_confidence(head_prominence, shoulder_diff)
        
        # Timing
        completed_idx = right_shoulder_idx
        completed_date = df.index[completed_idx].strftime("%Y-%m-%d")
        days_ago = len(df) - completed_idx - 1
        
        # Target (downward)
        target = neckline - (head - neckline)
        
        return ChartPatternResult(
            pattern_name="Head & Shoulders",
            detected=True,
            confidence=confidence,
            completed_date=completed_date,
            days_ago=days_ago,
            current_price=prices[-1],
            breakout_level=neckline,
            support_level=target,
            description=f"헤드-어깨 높이 차이 {head_prominence:.1%}, {days_ago}일 전 완성",
            key_levels={
                "left_shoulder": float(left_shoulder),
                "head": float(head),
                "right_shoulder": float(right_shoulder),
                "neckline": float(neckline),
                "target": float(target)
            },
        )
    
    return ChartPatternResult(
        pattern_name="Head & Shoulders",
        detected=False,
        confidence=0.0,
        current_price=prices[-1],
        description="패턴 미감지"
    )

def calculate_head_shoulders_confidence(head_prominence: float, shoulder_diff: float) -> float:
    """H&S confidence scoring"""
    confidence = 0.0
    
    # Head prominence
    prominence_score = min(head_prominence / 0.10, 1.0)
    confidence += prominence_score * 0.4
    
    # Shoulder similarity
    similarity_score = 1.0 - (shoulder_diff / 0.10)
    confidence += similarity_score * 0.3
    
    # Period fit
    confidence += 0.3
    
    return min(confidence, 1.0)
```

- [ ] **Step 3: Run test and commit**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_head_and_shoulders_detection -v`
Expected: PASS

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): add Head & Shoulders detection

- Identifies 3 peaks with head higher than shoulders
- Validates shoulder height similarity (<10%)
- Bearish pattern with downward target

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Implement Support/Resistance Test

**Files:**
- Modify: `src/tools/technical/components/chart_patterns.py`
- Test: `tests/tools/technical/test_chart_patterns.py`

- [ ] **Step 1: Write test for S/R Test**

```python
from src.tools.technical.models import IndicatorSnapshot

def test_support_resistance_test_near_level():
    """Test detection when price near support/resistance"""
    df = pd.DataFrame({
        'Close': [200.0] * 30
    }, index=pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D'))
    
    snapshot = IndicatorSnapshot(
        price=200.5,  # Within 2% of pivot
        support_s1=200.0,
        resistance_r1=210.0,
        sma_50=185.0,
        sma_200=170.0,
    )
    
    result = test_support_resistance(df, snapshot)
    
    assert result.detected is True
    assert "테스트 중" in result.description
```

- [ ] **Step 2: Implement S/R Test**

```python
# Add to chart_patterns.py

from src.tools.technical.models import IndicatorSnapshot

def test_support_resistance(
    df: pd.DataFrame,
    snapshot: IndicatorSnapshot
) -> ChartPatternResult:
    """현재가가 주요 레벨 근처(±2%)에 있는지 테스트"""
    
    current_price = snapshot.price
    levels = []
    
    # Collect levels
    if snapshot.support_s1:
        levels.append(("support", snapshot.support_s1, "피봇 S1"))
    if snapshot.resistance_r1:
        levels.append(("resistance", snapshot.resistance_r1, "피봇 R1"))
    if snapshot.sma_50:
        levels.append(("support", snapshot.sma_50, "50일선"))
    if snapshot.sma_200:
        levels.append(("support", snapshot.sma_200, "200일선"))
    if snapshot.swing_high:
        levels.append(("resistance", snapshot.swing_high, "스윙 고점"))
    if snapshot.swing_low:
        levels.append(("support", snapshot.swing_low, "스윙 저점"))
    
    # Check ±2% proximity
    for level_type, level_price, level_name in levels:
        distance_pct = abs(current_price - level_price) / current_price
        
        if distance_pct <= 0.02:
            return ChartPatternResult(
                pattern_name="Support/Resistance Test",
                detected=True,
                confidence=1.0 - distance_pct / 0.02,
                completed_date=df.index[-1].strftime("%Y-%m-%d"),
                days_ago=0,
                current_price=current_price,
                breakout_level=level_price if level_type == "resistance" else None,
                support_level=level_price if level_type == "support" else None,
                description=f"{level_name} 테스트 중 (거리 {distance_pct:.1%})",
                key_levels={"test_level": float(level_price), "type": level_type, "name": level_name},
            )
    
    return ChartPatternResult(
        pattern_name="Support/Resistance Test",
        detected=False,
        confidence=0.0,
        current_price=current_price,
        description="레벨 근처 아님"
    )
```

- [ ] **Step 3: Add pattern detection wrapper**

```python
# Add to chart_patterns.py

def detect_chart_patterns(
    df: pd.DataFrame,
    snapshot: IndicatorSnapshot | None = None
) -> dict[str, ChartPatternResult]:
    """모든 차트 패턴 감지 통합 함수"""
    
    patterns = {
        "cup_and_handle": detect_cup_and_handle(df),
        "double_bottom": detect_double_bottom(df),
        "head_and_shoulders": detect_head_and_shoulders(df),
    }
    
    if snapshot:
        patterns["support_resistance_test"] = test_support_resistance(df, snapshot)
    
    return patterns
```

- [ ] **Step 4: Run test and commit**

Run: `uv run pytest tests/tools/technical/test_chart_patterns.py::test_support_resistance_test_near_level -v`
Expected: PASS

```bash
git add src/tools/technical/components/chart_patterns.py tests/tools/technical/test_chart_patterns.py
git commit -m "feat(patterns): add S/R Test and pattern detection wrapper

- Support/Resistance Test: detects price near key levels (±2%)
- detect_chart_patterns: unified function for all 4 patterns
- Complete pattern detection module

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Implement Price Level Calculation

**Files:**
- Create: `src/tools/technical/price_levels.py`
- Test: `tests/tools/technical/test_price_levels.py`

- [ ] **Step 1: Write test for Fibonacci calculation**

```python
# tests/tools/technical/test_price_levels.py

from src.tools.technical.price_levels import calculate_fibonacci_levels

def test_fibonacci_levels_calculation():
    """Test Fibonacci retracement and extension"""
    fib = calculate_fibonacci_levels(high=200.0, low=100.0)
    
    # Retracements
    assert fib["fib_0.382"] == pytest.approx(161.8, rel=0.01)
    assert fib["fib_0.618"] == pytest.approx(138.2, rel=0.01)
    
    # Extensions
    assert fib["fib_1.618"] == pytest.approx(261.8, rel=0.01)
```

- [ ] **Step 2: Implement Fibonacci calculation**

```python
# src/tools/technical/price_levels.py

def calculate_fibonacci_levels(high: float, low: float) -> dict[str, float]:
    """피보나치 되돌림 및 확장 레벨"""
    
    diff = high - low
    
    return {
        # Retracements
        "fib_0.236": high - diff * 0.236,
        "fib_0.382": high - diff * 0.382,
        "fib_0.500": high - diff * 0.500,
        "fib_0.618": high - diff * 0.618,
        "fib_0.786": high - diff * 0.786,
        "fib_1.000": low,
        
        # Extensions
        "fib_1.272": high + diff * 0.272,
        "fib_1.618": high + diff * 0.618,
        "fib_2.000": high + diff * 1.000,
    }
```

- [ ] **Step 3: Test Fibonacci base point selection**

```python
from src.tools.technical.price_levels import get_fibonacci_base_points
from src.tools.technical.models import IndicatorSnapshot

def test_fibonacci_base_points_swing_priority():
    """Test swing points used if within 6 months"""
    df = pd.DataFrame({
        'High': [100, 110, 105, 115, 100],
        'Low': [90, 95, 90, 95, 85],
    }, index=pd.date_range(end=pd.Timestamp.now(), periods=5, freq='D'))
    
    snapshot = IndicatorSnapshot(
        price=100.0,
        swing_high=115.0,
        swing_low=85.0,
    )
    
    high, low = get_fibonacci_base_points(df, snapshot)
    
    assert high == 115.0  # Swing high
    assert low == 85.0    # Swing low
```

- [ ] **Step 4: Implement Fibonacci base point selection**

```python
# Add to price_levels.py

import pandas as pd
from src.tools.technical.models import IndicatorSnapshot
from src.tools.technical.utils import find_last_occurrence

def get_fibonacci_base_points(
    df: pd.DataFrame,
    snapshot: IndicatorSnapshot
) -> tuple[float, float]:
    """피보나치 계산 기준 고점/저점 선택
    
    우선순위:
    1. Swing High/Low (6개월 이내)
    2. 6개월 High/Low (Fallback)
    """
    
    # Try swing points
    if snapshot.swing_high and snapshot.swing_low:
        swing_high_idx = find_last_occurrence(df, 'High', snapshot.swing_high, tolerance=0.001)
        
        if swing_high_idx is not None:
            days_since_swing = len(df) - swing_high_idx - 1
            if days_since_swing <= 126:  # 6 months ≈ 126 trading days
                return snapshot.swing_high, snapshot.swing_low
    
    # Fallback: 6-month high/low
    high_6m = df['High'].tail(126).max()
    low_6m = df['Low'].tail(126).min()
    
    return high_6m, low_6m
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/tools/technical/test_price_levels.py -v`
Expected: All PASS

```bash
git add src/tools/technical/price_levels.py tests/tools/technical/test_price_levels.py
git commit -m "feat(price-levels): add Fibonacci calculation and base point selection

- calculate_fibonacci_levels: 9 retracement/extension levels
- get_fibonacci_base_points: prioritize swing points over 6M high/low
- Foundation for comprehensive price level analysis

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Implement Level Deduplication

**Files:**
- Modify: `src/tools/technical/price_levels.py`
- Test: `tests/tools/technical/test_price_levels.py`

- [ ] **Step 1: Write test for level deduplication**

```python
from src.tools.technical.models import PriceLevel
from src.tools.technical.price_levels import deduplicate_levels

def test_deduplicate_levels_basic():
    """Test deduplication with ±1% threshold"""
    levels = [
        PriceLevel(price=100.0, type="sma_50", distance_pct=-5.0, description="50일선"),
        PriceLevel(price=100.5, type="pivot_s1", distance_pct=-4.9, description="피봇"),
        PriceLevel(price=110.0, type="sma_20", distance_pct=+5.0, description="20일선"),
    ]
    
    unique = deduplicate_levels(levels, current_price=105.0, base_threshold=0.01)
    
    assert len(unique) == 2  # 100.0 and 100.5 merged
    assert unique[0].type == "sma_50"  # Higher priority

def test_deduplicate_levels_dynamic_threshold():
    """Test stricter threshold near current price"""
    levels = [
        PriceLevel(price=200.0, type="pivot_r1", distance_pct=+0.5, description="피봇"),
        PriceLevel(price=201.0, type="fib_0.618", distance_pct=+1.0, description="피보나치"),
    ]
    
    # Near current price (±5%) -> threshold reduced to 0.5%
    unique = deduplicate_levels(levels, current_price=199.0, base_threshold=0.01)
    
    assert len(unique) == 2  # Both kept due to stricter threshold
```

- [ ] **Step 2: Implement deduplication**

```python
# Add to price_levels.py

def deduplicate_levels(
    levels: list[PriceLevel],
    current_price: float,
    base_threshold: float = 0.01
) -> list[PriceLevel]:
    """중복 레벨 제거 (현재가 대비 dynamic threshold)"""
    
    if not levels:
        return []
    
    levels_sorted = sorted(levels, key=lambda x: x.price)
    unique = [levels_sorted[0]]
    
    for level in levels_sorted[1:]:
        last_price = unique[-1].price
        
        # Dynamic threshold: stricter near current price
        distance_from_current = abs(level.price - current_price) / current_price
        threshold = base_threshold * (0.5 if distance_from_current < 0.05 else 1.0)
        
        if abs(level.price - last_price) / last_price > threshold:
            unique.append(level)
        else:
            # Priority: sma/swing > pivot > fib > atr
            priority_map = {"sma_": 3, "swing_": 3, "pivot_": 2, "fib_": 1, "atr_": 0}
            
            current_priority = max(
                (priority_map.get(k, 0) for k in priority_map if level.type.startswith(k)),
                default=0
            )
            last_priority = max(
                (priority_map.get(k, 0) for k in priority_map if unique[-1].type.startswith(k)),
                default=0
            )
            
            if current_priority > last_priority:
                unique[-1] = level
    
    return unique
```

- [ ] **Step 3: Run tests and commit**

Run: `uv run pytest tests/tools/technical/test_price_levels.py -k deduplicate -v`
Expected: All PASS

```bash
git add src/tools/technical/price_levels.py tests/tools/technical/test_price_levels.py
git commit -m "feat(price-levels): add dynamic level deduplication

- Base threshold 1%, reduced to 0.5% near current price (±5%)
- Priority: SMA/swing > pivot > fibonacci > ATR
- Prevents level clustering while keeping important nearby levels

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Integrate Price Levels

**Files:**
- Modify: `src/tools/technical/price_levels.py`
- Test: `tests/tools/technical/test_price_levels.py`

- [ ] **Step 1: Write integration test**

```python
from src.tools.technical.price_levels import identify_key_levels
from src.tools.technical.models import IndicatorSnapshot

def test_identify_key_levels_integration():
    """Test full price level identification"""
    snapshot = IndicatorSnapshot(
        price=200.0,
        sma_20=205.0,
        sma_50=175.0,
        sma_200=150.0,
        support_s1=187.0,
        resistance_r1=210.0,
        swing_high=215.0,
        swing_low=182.0,
        atr=8.0,
    )
    
    pattern_results = {}  # Empty for this test
    
    levels = identify_key_levels(
        snapshot=snapshot,
        pattern_results=pattern_results,
        lookback_high=220.0,
        lookback_low=140.0,
    )
    
    assert levels.current_price == 200.0
    assert len(levels.support_levels) > 0
    assert len(levels.resistance_levels) > 0
    # Supports sorted by price descending (closest first)
    assert levels.support_levels[0].price > levels.support_levels[-1].price
```

- [ ] **Step 2: Implement identify_key_levels**

```python
# Add to price_levels.py

def identify_key_levels(
    snapshot: IndicatorSnapshot,
    pattern_results: dict[str, ChartPatternResult],
    lookback_high: float,
    lookback_low: float,
) -> PriceLevels:
    """모든 레벨 수집 → 중복 제거 → 가까운 순 정렬"""
    
    from src.tools.technical.models import PriceLevel, PriceLevels, ChartPatternResult
    
    all_levels: list[PriceLevel] = []
    
    # 1. Moving averages
    for ma in [20, 50, 200]:
        ma_val = getattr(snapshot, f"sma_{ma}", None)
        if ma_val:
            all_levels.append(PriceLevel(
                price=ma_val,
                type=f"sma_{ma}",
                distance_pct=(ma_val - snapshot.price) / snapshot.price * 100,
                description=f"{ma}일 이평선",
            ))
    
    # 2. Pivot points
    if snapshot.support_s1:
        all_levels.append(PriceLevel(
            price=snapshot.support_s1,
            type="pivot_s1",
            distance_pct=(snapshot.support_s1 - snapshot.price) / snapshot.price * 100,
            description="피봇 지지1",
        ))
    if snapshot.resistance_r1:
        all_levels.append(PriceLevel(
            price=snapshot.resistance_r1,
            type="pivot_r1",
            distance_pct=(snapshot.resistance_r1 - snapshot.price) / snapshot.price * 100,
            description="피봇 저항1",
        ))
    
    # 3. Swing points
    if snapshot.swing_high:
        all_levels.append(PriceLevel(
            price=snapshot.swing_high,
            type="swing_high",
            distance_pct=(snapshot.swing_high - snapshot.price) / snapshot.price * 100,
            description="스윙 고점",
        ))
    if snapshot.swing_low:
        all_levels.append(PriceLevel(
            price=snapshot.swing_low,
            type="swing_low",
            distance_pct=(snapshot.swing_low - snapshot.price) / snapshot.price * 100,
            description="스윙 저점",
        ))
    
    # 4. Fibonacci levels
    fib_levels = calculate_fibonacci_levels(lookback_high, lookback_low)
    for fib_name, fib_price in fib_levels.items():
        all_levels.append(PriceLevel(
            price=fib_price,
            type=fib_name,
            distance_pct=(fib_price - snapshot.price) / snapshot.price * 100,
            description=f"피보나치 {fib_name.replace('fib_', '')}",
        ))
    
    # 5. ATR levels (if available)
    if snapshot.atr:
        atr_levels = calculate_atr_levels(snapshot.price, snapshot.atr)
        for atr_name, atr_price in atr_levels.items():
            all_levels.append(PriceLevel(
                price=atr_price,
                type=atr_name,
                distance_pct=(atr_price - snapshot.price) / snapshot.price * 100,
                description=f"ATR {atr_name.replace('atr_', '').replace('_', ' ')}",
            ))
    
    # 6. Pattern breakout levels
    for pattern_name, result in pattern_results.items():
        if result.detected and result.breakout_level:
            all_levels.append(PriceLevel(
                price=result.breakout_level,
                type=f"pattern_{pattern_name}_breakout",
                distance_pct=(result.breakout_level - snapshot.price) / snapshot.price * 100,
                description=f"{result.pattern_name} 돌파",
            ))
    
    # Deduplicate
    unique_levels = deduplicate_levels(all_levels, snapshot.price, base_threshold=0.01)
    
    # Split into supports/resistances
    supports = [lv for lv in unique_levels if lv.price < snapshot.price]
    resistances = [lv for lv in unique_levels if lv.price > snapshot.price]
    
    # Sort: supports high to low, resistances low to high
    supports.sort(key=lambda x: x.price, reverse=True)
    resistances.sort(key=lambda x: x.price)
    
    # Extract targets from patterns
    targets = {}
    for pattern_name, result in pattern_results.items():
        if result.detected and "target" in result.key_levels:
            targets[f"{pattern_name}_target"] = result.key_levels["target"]
    
    # Add Fibonacci extension as target
    if "fib_1.618" in fib_levels:
        targets["fibonacci_extension_1.618"] = fib_levels["fib_1.618"]
    
    return PriceLevels(
        current_price=snapshot.price,
        support_levels=supports[:5],  # Top 5
        resistance_levels=resistances[:5],
        targets=targets,
    )

def calculate_atr_levels(current_price: float, atr: float) -> dict[str, float]:
    """ATR 기반 지지/저항"""
    return {
        "atr_support_1x": current_price - atr,
        "atr_support_2x": current_price - 2 * atr,
        "atr_resistance_1x": current_price + atr,
        "atr_resistance_2x": current_price + 2 * atr,
    }
```

- [ ] **Step 3: Run tests and commit**

Run: `uv run pytest tests/tools/technical/test_price_levels.py -v`
Expected: All PASS

```bash
git add src/tools/technical/price_levels.py tests/tools/technical/test_price_levels.py
git commit -m "feat(price-levels): complete integrated level identification

- identify_key_levels: collects all support/resistance from 6 sources
- Sorts by proximity (closest first)
- Returns top 5 supports/resistances + targets
- Price level analysis module complete

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Extend ActionableSignalOutput Model

**Files:**
- Modify: `src/llm/models.py`
- Test: `tests/llm/test_models.py`

- [ ] **Step 1: Write test for extended model**

```python
# tests/llm/test_models.py

def test_actionable_signal_output_with_new_fields():
    """Test ActionableSignalOutput with 4 new fields"""
    signal = ActionableSignalOutput(
        action="매수",
        timing="조정_대기",
        signal_strength=7,
        headline="매수. 조정_대기. 이유: Cup & Handle 형성",
        primary_reason="Cup & Handle 8일 전 완성 (신뢰도 85%)",
        supporting_reasons=["50일선 지지 근접", "거래량 증가"],
        risks=["저항선 $210 돌파 실패 시 조정"],
        invalidation_point="$175 (50일선)",
        confidence=0.75,
        # New fields
        pattern_insight="Cup & Handle 8일 전 완성, 현재 핸들 구간",
        target_price="돌파 시 $250 (Cup & Handle 목표), 중간 저항 $210",
        entry_zone="조정 시 $175-180 (50일선) 분할 매수",
        key_levels="지지: $187/$175/$160, 저항: $200/$210/$250",
    )
    
    assert signal.pattern_insight is not None
    assert "$250" in signal.target_price
    assert "조정 시" in signal.entry_zone
    assert "지지:" in signal.key_levels
```

- [ ] **Step 2: Extend ActionableSignalOutput**

```python
# src/llm/models.py

from pydantic import BaseModel, Field

class ActionableSignalOutput(BaseModel):
    """Actionable investment signal with pattern and price insights"""
    
    # Phase 1 fields
    action: Literal["매수", "매도", "관망"]
    timing: Literal["지금", "조정_대기", "보류"]
    signal_strength: int = Field(ge=1, le=10)
    headline: str
    primary_reason: str
    supporting_reasons: list[str]
    risks: list[str]
    invalidation_point: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    
    # Phase 2 fields
    pattern_insight: str | None = Field(
        None,
        description="차트 패턴 해석. 예: 'Cup & Handle 8일 전 완성, 돌파 준비'"
    )
    target_price: str | None = Field(
        None,
        description="가격 목표 (자유 서술). 예: '돌파 시 $250, 조정 시 $175 지지'"
    )
    entry_zone: str | None = Field(
        None,
        description="진입 구간 (자유 서술). 예: '현재 $200 횡보, 조정 시 $175-180 매수'"
    )
    key_levels: str | None = Field(
        None,
        description="주요 레벨 요약. 예: '지지: $187/$175, 저항: $200/$250'"
    )
    
    @field_validator('pattern_insight', 'target_price', 'entry_zone', 'key_levels')
    @classmethod
    def validate_non_empty(cls, v):
        """Ensure Phase 2 fields are not empty strings"""
        if v is not None and v.strip() == "":
            return None
        return v
```

- [ ] **Step 3: Run test and commit**

Run: `uv run pytest tests/llm/test_models.py::test_actionable_signal_output_with_new_fields -v`
Expected: PASS

```bash
git add src/llm/models.py tests/llm/test_models.py
git commit -m "feat(llm): extend ActionableSignalOutput with 4 pattern/price fields

- pattern_insight: chart pattern interpretation
- target_price: scenario-based price targets
- entry_zone: specific entry recommendations
- key_levels: concise support/resistance summary
- Validators ensure non-empty strings

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Enhance LLM Prompt

**Files:**
- Modify: `src/llm/analyzer.py`
- Test: `tests/llm/test_analyzer.py`

- [ ] **Step 1: Write formatters test**

```python
# tests/llm/test_analyzer.py

from src.llm.analyzer import format_patterns_for_llm, format_levels_for_llm
from src.tools.technical.models import ChartPatternResult, PriceLevels, PriceLevel

def test_format_patterns_for_llm():
    """Test pattern formatting for LLM"""
    patterns = {
        "cup_and_handle": ChartPatternResult(
            pattern_name="Cup & Handle",
            detected=True,
            confidence=0.85,
            completed_date="2026-04-15",
            days_ago=8,
            current_price=200.0,
            breakout_level=205.0,
            description="컵 깊이 28%, 8일 전 완성",
            key_levels={}
        ),
        "double_bottom": ChartPatternResult(
            pattern_name="Double Bottom",
            detected=False,
            confidence=0.0,
            current_price=200.0,
            description="미감지",
            key_levels={}
        ),
    }
    
    text = format_patterns_for_llm(patterns)
    
    assert "Cup & Handle: 감지됨" in text
    assert "신뢰도 85%" in text
    assert "8일 전 완성" in text
    assert "Double Bottom: 미감지" in text
```

- [ ] **Step 2: Implement formatters**

```python
# Add to src/llm/analyzer.py

def format_patterns_for_llm(patterns: dict[str, ChartPatternResult]) -> str:
    """패턴 결과를 LLM용 텍스트로 변환"""
    
    lines = []
    
    for pattern_name, result in patterns.items():
        if result.detected:
            lines.append(
                f"- {result.pattern_name}: 감지됨 "
                f"(신뢰도 {result.confidence:.0%}, {result.days_ago}일 전 완성)"
            )
            lines.append(f"  {result.description}")
            if result.breakout_level:
                lines.append(f"  돌파 레벨: ${result.breakout_level:.2f}")
        else:
            lines.append(f"- {result.pattern_name}: 미감지")
    
    return "\n".join(lines) if lines else "패턴 감지 없음"

def format_levels_for_llm(levels: PriceLevels) -> str:
    """가격 레벨을 LLM용 텍스트로 변환"""
    
    lines = [f"현재가: ${levels.current_price:.2f}\n"]
    
    # Supports
    if levels.support_levels:
        lines.append("지지선 (가까운 순):")
        for i, support in enumerate(levels.support_levels, 1):
            lines.append(
                f"  {i}. ${support.price:.2f} "
                f"({support.description}, {support.distance_pct:+.1f}%)"
            )
        lines.append("")
    
    # Resistances
    if levels.resistance_levels:
        lines.append("저항선 (가까운 순):")
        for i, resistance in enumerate(levels.resistance_levels, 1):
            lines.append(
                f"  {i}. ${resistance.price:.2f} "
                f"({resistance.description}, {resistance.distance_pct:+.1f}%)"
            )
        lines.append("")
    
    # Targets
    if levels.targets:
        lines.append("타겟 (상승 시나리오):")
        for target_name, target_price in levels.targets.items():
            readable_name = target_name.replace("_", " ").title()
            lines.append(f"  - {readable_name}: ${target_price:.2f}")
    
    return "\n".join(lines)
```

- [ ] **Step 3: Test prompt enhancement**

```python
def test_generate_actionable_signal_prompt_structure():
    """Test that prompt includes pattern and level sections"""
    # This is a partial test - full integration test in Task 12
    patterns_text = format_patterns_for_llm({})
    levels_text = format_levels_for_llm(PriceLevels(
        current_price=200.0,
        support_levels=[],
        resistance_levels=[],
        targets={}
    ))
    
    assert "현재가:" in levels_text
    assert "패턴 감지 없음" in patterns_text
```

- [ ] **Step 4: Update generate_actionable_signal signature**

```python
# Modify src/llm/analyzer.py

async def generate_actionable_signal(
    ticker: str,
    technical_data: TechnicalResult,
    technical_summary: TechnicalSummaryOutput,
    chart_patterns: dict[str, ChartPatternResult],  # NEW
    price_levels: PriceLevels,  # NEW
    news_analysis: str | None = None,
    fundamental_summary: str | None = None,
    disclosure_text: str | None = None,
    flow_text: str | None = None,
    llm: BaseChatModel | None = None,
) -> ActionableSignalOutput:
    """Generate actionable signal with pattern and price insights"""
    
    if llm is None:
        from src.llm.provider import get_llm_instance
        llm = get_llm_instance()
    
    # Format pattern and level data
    patterns_text = format_patterns_for_llm(chart_patterns)
    levels_text = format_levels_for_llm(price_levels)
    
    # Enhanced prompt (see design spec for full prompt)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """당신은 프로 트레이더입니다. 구체적인 가격과 패턴으로 명확한 투자 신호를 제공하세요.

**신규 필드 작성 가이드:**

1. **pattern_insight**: 감지된 패턴을 자연스럽게 해석
   - 패턴이 있으면: "Cup & Handle 형성 완료 (8일 전), 돌파 준비 중"
   - 패턴이 없으면: "명확한 차트 패턴 없음, 지지/저항선 중심 분석"

2. **target_price**: 시나리오별 목표가 (자유 서술)
   - 상승 시: "돌파 시 Cup & Handle 목표 $250, 중간 저항 $210"
   - 하락 시: "이탈 시 50일선 $175까지 조정 가능"

3. **entry_zone**: 진입 타이밍과 구간
   - "조정 시 $175-180 (50일선) 분할 매수, 돌파 확인 후 $205 추격 가능"

4. **key_levels**: 핵심 가격 레벨 간결 요약
   - "지지: $187/$175/$160, 저항: $200/$210/$250"

**기존 필드 작성 규칙:**
- primary_reason: 반드시 구체적 숫자 포함
- signal_strength: 1-10, 패턴 신뢰도 포함"""),
        ("user", """종목: {ticker}

**기술적 분석** (8 components):
{technical_summary}

**차트 패턴**:
{patterns_text}

**가격 레벨**:
{levels_text}

**뉴스**: {news_analysis}
**펀더멘탈**: {fundamental_summary}

위 정보를 종합해서 명확한 투자 신호를 생성하세요."""),
    ])
    
    messages = prompt.format_messages(
        ticker=ticker,
        technical_summary=technical_summary.model_dump_json(),
        patterns_text=patterns_text,
        levels_text=levels_text,
        news_analysis=news_analysis or "없음",
        fundamental_summary=fundamental_summary or "없음",
    )
    
    from src.llm.retry import invoke_llm_with_retry
    
    return await invoke_llm_with_retry(
        llm=llm,
        output_model=ActionableSignalOutput,
        messages=messages,
        config={},
        max_retries=3,
        timeout_seconds=60.0,
    )
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/llm/test_analyzer.py -v`
Expected: All PASS

```bash
git add src/llm/analyzer.py tests/llm/test_analyzer.py
git commit -m "feat(llm): enhance prompt with pattern and price level data

- format_patterns_for_llm: converts pattern results to readable text
- format_levels_for_llm: formats support/resistance/targets
- Updated generate_actionable_signal with new parameters
- Comprehensive prompt guides LLM to use pattern and level data

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Integrate into DeepDivePipeline

**Files:**
- Modify: `src/pipelines/deep_dive.py`
- Modify: `src/tools/technical/models.py` (TechnicalResult)
- Test: `tests/pipelines/test_deep_dive_v2.py`

- [ ] **Step 1: Extend TechnicalResult with raw_dataframe**

```python
# src/tools/technical/models.py

class TechnicalResult(BaseModel):
    """Complete technical analysis result"""
    
    ticker: str | None
    timestamp: datetime
    snapshot: IndicatorSnapshot
    components: dict[str, dict]
    total_score: int = 0
    
    # NEW: Pattern detection requires OHLC data
    raw_dataframe: pd.DataFrame | None = None
    
    # Legacy fields
    indicators: IndicatorSnapshot | None = None
    strategies: list[StrategyResult] | None = None
    overall_assessment: str | None = None
    confidence_score: float | None = None
    key_insights: list[str] | None = None
    warnings: list[str] | None = None
    
    class Config:
        arbitrary_types_allowed = True
    
    @classmethod
    def from_analysis(cls, df: pd.DataFrame, **kwargs):
        """메모리 최적화: OHLC 컬럼만 저장"""
        slim_df = df[['Open', 'High', 'Low', 'Close']].copy()
        return cls(raw_dataframe=slim_df, **kwargs)
```

- [ ] **Step 2: Write integration test**

```python
# tests/pipelines/test_deep_dive_v2.py

@pytest.mark.asyncio
async def test_deep_dive_with_patterns_and_levels(mock_llm):
    """Test DeepDivePipeline with pattern/level integration"""
    
    # Mock LLM to return signal with new fields
    mock_signal = ActionableSignalOutput(
        action="매수",
        timing="조정_대기",
        signal_strength=7,
        headline="매수. 조정_대기. 이유: Cup & Handle 형성",
        primary_reason="Cup & Handle 8일 전 완성 (신뢰도 85%)",
        supporting_reasons=["50일선 지지", "거래량 증가"],
        risks=["$210 돌파 실패 시 조정"],
        invalidation_point="$175",
        confidence=0.75,
        pattern_insight="Cup & Handle 8일 전 완성, 핸들 구간",
        target_price="돌파 시 $250, 조정 시 $175 지지",
        entry_zone="조정 시 $175-180 분할 매수",
        key_levels="지지: $187/$175, 저항: $200/$250",
    )
    
    with patch("src.llm.analyzer.generate_actionable_signal", return_value=mock_signal):
        pipeline = DeepDivePipeline(...)
        result = await pipeline.run("AAPL")
        
        signal = result["actionable_signal"]
        
        # Verify new fields exist and non-empty
        assert signal.pattern_insight is not None
        assert "Cup" in signal.pattern_insight or "컵" in signal.pattern_insight
        assert signal.target_price is not None
        assert "$250" in signal.target_price
        assert signal.entry_zone is not None
        assert signal.key_levels is not None
```

- [ ] **Step 3: Modify DeepDivePipeline to detect patterns and levels**

```python
# src/pipelines/deep_dive.py

from src.tools.technical.components.chart_patterns import detect_chart_patterns
from src.tools.technical.price_levels import get_fibonacci_base_points, identify_key_levels

class DeepDivePipeline:
    
    async def _generate_actionable_signal(
        self,
        ticker: str,
        technical_data: TechnicalResult,
        technical_summary: TechnicalSummaryOutput,
        news_analysis: str | None = None,
        fundamental_summary: str | None = None,
    ) -> ActionableSignalOutput:
        """Generate signal with pattern and price level analysis"""
        
        # Extract raw dataframe
        df = technical_data.raw_dataframe
        if df is None:
            raise ValueError("raw_dataframe required for pattern detection")
        
        # Detect patterns
        chart_patterns = detect_chart_patterns(df, technical_data.snapshot)
        
        # Calculate Fibonacci base points
        lookback_high, lookback_low = get_fibonacci_base_points(df, technical_data.snapshot)
        
        # Identify all price levels
        price_levels = identify_key_levels(
            snapshot=technical_data.snapshot,
            pattern_results=chart_patterns,
            lookback_high=lookback_high,
            lookback_low=lookback_low,
        )
        
        # Generate signal with enhanced data
        from src.llm.analyzer import generate_actionable_signal
        
        return await generate_actionable_signal(
            ticker=ticker,
            technical_data=technical_data,
            technical_summary=technical_summary,
            chart_patterns=chart_patterns,
            price_levels=price_levels,
            news_analysis=news_analysis,
            fundamental_summary=fundamental_summary,
        )
```

- [ ] **Step 4: Update TechnicalTool to include raw_dataframe**

```python
# src/tools/technical/tool.py

class TechnicalTool(BaseTool):
    
    def execute(self, ticker: str) -> TechnicalResult:
        """Execute technical analysis and return result with raw data"""
        
        # Download data
        df = download_data(ticker)
        
        # Calculate indicators
        snapshot = calculate_indicators(df)
        
        # Analyze components
        components = analyze_components(df, snapshot)
        
        # Return with slim raw_dataframe
        return TechnicalResult.from_analysis(
            df=df,
            ticker=ticker,
            timestamp=datetime.now(),
            snapshot=snapshot,
            components=components,
            total_score=calculate_total_score(components),
        )
```

- [ ] **Step 5: Run integration test**

Run: `uv run pytest tests/pipelines/test_deep_dive_v2.py -v`
Expected: PASS

- [ ] **Step 6: Commit integration**

```bash
git add src/pipelines/deep_dive.py src/tools/technical/models.py src/tools/technical/tool.py tests/pipelines/test_deep_dive_v2.py
git commit -m "feat(pipeline): integrate pattern detection and price levels

- TechnicalResult.from_analysis: stores slim OHLC dataframe
- DeepDivePipeline: detects patterns and calculates levels
- Passes structured data to enhanced LLM prompt
- E2E integration complete

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Update CLI Display

**Files:**
- Modify: `src/cli/main.py`

- [ ] **Step 1: Add new fields to Rich Panel output**

```python
# src/cli/main.py

def display_actionable_signal(signal: ActionableSignalOutput):
    """Display actionable signal with pattern and price insights"""
    
    # Existing fields
    console.print(Panel(
        f"[bold]{signal.headline}[/bold]\n\n"
        f"[yellow]Signal Strength:[/yellow] {signal.signal_strength}/10\n"
        f"[yellow]Confidence:[/yellow] {signal.confidence:.0%}\n\n"
        f"[green]Primary Reason:[/green] {signal.primary_reason}\n\n"
        f"[cyan]Supporting Reasons:[/cyan]\n" +
        "\n".join(f"  • {r}" for r in signal.supporting_reasons) + "\n\n"
        f"[red]Risks:[/red]\n" +
        "\n".join(f"  • {r}" for r in signal.risks) +
        (f"\n\n[yellow]Invalidation:[/yellow] {signal.invalidation_point}" if signal.invalidation_point else ""),
        title="🎯 투자 신호",
        border_style="bold"
    ))
    
    # NEW: Pattern and Price Level Insights
    if signal.pattern_insight or signal.target_price or signal.entry_zone or signal.key_levels:
        insight_parts = []
        
        if signal.pattern_insight:
            insight_parts.append(f"[magenta]📊 패턴:[/magenta] {signal.pattern_insight}")
        
        if signal.target_price:
            insight_parts.append(f"[green]🎯 목표가:[/green] {signal.target_price}")
        
        if signal.entry_zone:
            insight_parts.append(f"[cyan]📍 진입 구간:[/cyan] {signal.entry_zone}")
        
        if signal.key_levels:
            insight_parts.append(f"[yellow]📏 주요 레벨:[/yellow] {signal.key_levels}")
        
        console.print(Panel(
            "\n\n".join(insight_parts),
            title="💡 패턴 & 가격 분석",
            border_style="blue"
        ))
```

- [ ] **Step 2: Test CLI output manually**

Run: `uv run jarvis analyze AAPL`
Expected: New panel "💡 패턴 & 가격 분석" displays with 4 fields

- [ ] **Step 3: Commit CLI updates**

```bash
git add src/cli/main.py
git commit -m "feat(cli): display pattern insights and price levels

- New Rich Panel for pattern/price analysis
- Shows pattern_insight, target_price, entry_zone, key_levels
- Enhanced user experience with specific entry/exit guidance

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 14: Create Test Snapshots

**Files:**
- Create: `tests/fixtures/patterns/*.csv`
- Create: `tests/fixtures/patterns/README.md`

- [ ] **Step 1: Download historical data for known patterns**

```python
# Script to create snapshots (one-time)
import yfinance as yf
import pandas as pd

patterns = [
    ("NVDA", "2023-01-01", "2023-12-31", "nvda_2023.csv"),
    ("AAPL", "2019-01-01", "2019-12-31", "aapl_2019.csv"),
    ("TSLA", "2021-01-01", "2021-12-31", "tsla_2021.csv"),
]

for ticker, start, end, filename in patterns:
    df = yf.download(ticker, start=start, end=end)
    df.to_csv(f"tests/fixtures/patterns/{filename}")
    print(f"Saved {filename}")
```

- [ ] **Step 2: Run snapshot creation**

Run: `uv run python -c "$(cat snapshot_script.py)"`
Expected: 3 CSV files created in `tests/fixtures/patterns/`

- [ ] **Step 3: Create README for snapshots**

```markdown
# Test Pattern Snapshots

Historical price data snapshots for pattern detection validation.

## Files

- `nvda_2023.csv` - NVDA Cup & Handle (June 2023)
- `aapl_2019.csv` - AAPL Double Bottom (March 2019)
- `tsla_2021.csv` - TSLA Head & Shoulders (November 2021)

## Usage

```python
df = pd.read_csv("tests/fixtures/patterns/nvda_2023.csv", index_col=0, parse_dates=True)
result = detect_cup_and_handle(df)
assert result.detected is True
```

## Regeneration

If snapshots become outdated or corrupted:

```bash
python scripts/generate_test_snapshots.py
```

## Notes

- Snapshots ensure reproducible tests (yfinance data can change)
- Do NOT use live data in CI tests
- Mock data (create_flat_price_series, etc.) preferred for unit tests
```

- [ ] **Step 4: Commit snapshots**

```bash
git add tests/fixtures/patterns/
git commit -m "test: add historical pattern snapshots for reproducible tests

- NVDA 2023: Cup & Handle pattern
- AAPL 2019: Double Bottom pattern
- TSLA 2021: Head & Shoulders pattern
- Ensures stable CI test results

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 15: Write Historical Pattern Tests

**Files:**
- Create: `tests/integration/test_known_patterns.py`

- [ ] **Step 1: Write historical pattern tests**

```python
# tests/integration/test_known_patterns.py

import pytest
import pandas as pd
from src.tools.technical.components.chart_patterns import (
    detect_cup_and_handle,
    detect_double_bottom,
    detect_head_and_shoulders,
)

@pytest.mark.integration
@pytest.mark.parametrize("ticker,expected_pattern,year,month", [
    ("nvda", "cup_and_handle", "2023", "06"),
    ("aapl", "double_bottom", "2019", "03"),
    ("tsla", "head_and_shoulders", "2021", "11"),
])
def test_historical_pattern_detection(ticker, expected_pattern, year, month):
    """Validate pattern detection on known historical patterns"""
    
    # Load snapshot
    snapshot_path = f"tests/fixtures/patterns/{ticker}_{year}.csv"
    df = pd.read_csv(snapshot_path, index_col=0, parse_dates=True)
    
    # Detect pattern
    if expected_pattern == "cup_and_handle":
        result = detect_cup_and_handle(df)
    elif expected_pattern == "double_bottom":
        result = detect_double_bottom(df)
    elif expected_pattern == "head_and_shoulders":
        result = detect_head_and_shoulders(df)
    else:
        raise ValueError(f"Unknown pattern: {expected_pattern}")
    
    # Assertions
    assert result.detected is True, f"{ticker} {year}년 {expected_pattern} 미감지"
    assert result.confidence > 0.6, f"신뢰도 너무 낮음: {result.confidence}"
    assert result.completed_date.startswith(f"{year}-{month}"), \
        f"완성 시점 불일치: {result.completed_date}"
```

- [ ] **Step 2: Write false positive test**

```python
@pytest.mark.integration
def test_false_positive_rate_with_mock_data():
    """Ensure patterns don't trigger on flat/noisy/random data"""
    
    from src.tools.technical.utils import (
        create_flat_price_series,
        create_noisy_series,
        create_random_walk,
    )
    
    test_cases = [
        ("flat", create_flat_price_series(days=120, price=100)),
        ("noisy", create_noisy_series(days=120, base=100, noise=0.02)),
        ("random_walk", create_random_walk(days=120, start=100)),
    ]
    
    false_positives = 0
    
    for name, df in test_cases:
        cup_result = detect_cup_and_handle(df)
        double_result = detect_double_bottom(df)
        hs_result = detect_head_and_shoulders(df)
        
        if cup_result.detected or double_result.detected or hs_result.detected:
            false_positives += 1
            print(f"False positive in {name}")
    
    # All 3 should be clean (no false positives)
    assert false_positives == 0, f"False positives: {false_positives}/3"
```

- [ ] **Step 3: Run integration tests**

Run: `uv run pytest tests/integration/test_known_patterns.py -v`
Expected: All PASS (3 historical + 1 false positive)

- [ ] **Step 4: Commit integration tests**

```bash
git add tests/integration/test_known_patterns.py
git commit -m "test: add historical pattern validation tests

- Validates 3 known historical patterns (NVDA, AAPL, TSLA)
- False positive test with flat/noisy/random data
- Uses snapshot data for reproducibility

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 16: Run Full Test Suite

**Files:**
- All test files

- [ ] **Step 1: Run all unit tests**

Run: `uv run pytest tests/tools/ tests/llm/ -v`
Expected: All PASS

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/pipelines/ tests/integration/ -v`
Expected: All PASS

- [ ] **Step 3: Run with coverage**

Run: `uv run pytest --cov=src --cov-report=term-missing`
Expected: Coverage > 80% for new modules

- [ ] **Step 4: Check existing tests still pass**

Run: `uv run pytest tests/ -v`
Expected: ALL tests pass (Phase 1 + Phase 2)

---

## Task 17: Manual E2E Testing

**Files:**
- N/A (manual CLI testing)

- [ ] **Step 1: Test with real ticker**

Run: `uv run jarvis analyze AAPL`
Expected: 
- Signal generated successfully
- New panel "💡 패턴 & 가격 분석" displayed
- All 4 new fields populated (or N/A if no patterns)

- [ ] **Step 2: Test with known pattern ticker**

Run: `uv run jarvis analyze NVDA`
Expected:
- Pattern detected (if recent Cup & Handle exists)
- Target price includes pattern target
- Entry zone specifies levels

- [ ] **Step 3: Test with different providers**

Run: `uv run jarvis analyze AAPL --provider anthropic`
Expected: Works with Anthropic LLM

- [ ] **Step 4: Document any issues**

If any issues found, fix and re-test before final commit.

---

## Task 18: Final Documentation Update

**Files:**
- `docs/FEATURES.md`
- `docs/CLI_USAGE.md`

- [ ] **Step 1: Update FEATURES.md**

```markdown
# Add to docs/FEATURES.md

## Phase 2: Pattern Detection & Price Levels (2026-04-24)

### Chart Pattern Detection

**4개 패턴 감지:**
- Cup & Handle (60-120일)
- Double Bottom (40-80일)
- Head & Shoulders (60-100일)
- Support/Resistance Test (현재)

**구현:**
- scipy.signal.find_peaks 기반
- Confidence scoring (0.0-1.0)
- 타이밍 정보 (completed_date, days_ago)

### Price Level Analysis

**6개 소스 통합:**
- 피보나치 (9 레벨: 되돌림 + 확장)
- 이동평균선 (20/50/200일)
- 피봇 포인트 (S1, R1)
- 스윙 고점/저점
- ATR 기반 레벨
- 패턴 돌파 레벨

**기능:**
- Dynamic threshold (현재가 근처 민감)
- 중복 제거 (±1% 기본)
- 가까운 순 정렬 (상위 5개)

### ActionableSignalOutput 확장

**4개 필드 추가:**
- `pattern_insight`: 패턴 해석
- `target_price`: 시나리오별 목표가
- `entry_zone`: 진입 구간
- `key_levels`: 주요 레벨 요약
```

- [ ] **Step 2: Update CLI_USAGE.md**

```markdown
# Add to docs/CLI_USAGE.md (analyze section)

**출력 내용 (Phase 2 추가):**
- 가격 및 변동률
- 기술적 분석 요약
- **💡 패턴 & 가격 분석 (NEW)**
  - 📊 패턴: Cup & Handle 8일 전 완성
  - 🎯 목표가: 돌파 시 $250, 조정 시 $175 지지
  - 📍 진입 구간: 조정 시 $175-180 분할 매수
  - 📏 주요 레벨: 지지 $187/$175, 저항 $200/$250
- 투자 추천 및 근거
- 뉴스 감성 분석
```

- [ ] **Step 3: Commit documentation**

```bash
git add docs/FEATURES.md docs/CLI_USAGE.md
git commit -m "docs: document Phase 2 pattern detection and price levels

- Updated FEATURES.md with pattern/level implementation details
- Updated CLI_USAGE.md with new output fields
- Reflects Phase 2 completion

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Self-Review Checklist

- [ ] All 18 tasks have implementation code (no placeholders)
- [ ] Type signatures consistent across all tasks
- [ ] Test commands include expected output
- [ ] File paths are exact and match existing structure
- [ ] Commits follow conventional commit format
- [ ] TDD flow maintained (test → fail → implement → pass → commit)

---

## Success Criteria

✅ `jarvis analyze AAPL` displays 4 new fields  
✅ Pattern detection works on 7/10 historical cases  
✅ False positive rate < 20%  
✅ All existing tests still pass  
✅ New test coverage > 80%  
✅ Response time < 5 seconds (< 3 second overhead)

---

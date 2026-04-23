# Design: Actionable Signal Enhancement v2 - Pattern & Price Levels

생성일: 2026-04-23  
상태: APPROVED  
Branch: feature/actionable-signal  
Repo: invest-jarvis

---

## Problem Statement

Phase 1에서 `ActionableSignalOutput` 모델을 추가했지만, **인사이트가 여전히 약합니다**.

**사용자 피드백:**
> "조정이 오면 어디까지 빠질 수 있다, 이전 고점을 돌파했으니 더 오를 가능성이 있다, 컵앤핸들 패턴이 보이니까 더 사도 된다 - 이 정도 인사이트는 줘야하는 거 아냐?"

**Phase 1의 한계:**
- 패턴 감지 없음 (기존 VCP/Breakout만)
- 구체적 가격 타겟 없음 (support/resistance 숫자만 나열)
- 진입 구간 모호함 ("조정 대기" → 어디서?)
- LLM이 해석할 데이터 부족 (52w high/low 활용 안 함)

---

## Solution Overview

**Phase 2: Pattern Detection & Price Level Analysis**

기존 8-component 시스템을 유지하면서, **차트 패턴 감지**와 **가격 레벨 분석**을 추가합니다.

**핵심 변경:**
1. 새 모듈: `chart_patterns.py` (4개 패턴 감지)
2. 새 모듈: `price_levels.py` (타겟/지지/저항 계산)
3. `ActionableSignalOutput` 확장 (4개 필드 추가)
4. LLM 프롬프트 강화 (패턴 + 레벨 정보 전달)

**유지 사항:**
- 기존 8-component 구조 그대로
- TechnicalResult 호환성 유지
- 기존 테스트 통과

---

## Architecture

### 모듈 구조

```
src/tools/technical/
  ├─ components/
  │   ├─ patterns.py (기존 - VCP, Breakout, Candlestick)
  │   ├─ chart_patterns.py (신규 - Cup & Handle, Double Bottom, H&S, S/R Test)
  │   └─ ... (기존 8개 컴포넌트)
  │
  ├─ price_levels.py (신규 - Fibonacci, ATR, Key Levels 통합)
  └─ models.py (확장 - ChartPatternResult, PriceLevels 추가)

src/llm/
  ├─ models.py (확장 - ActionableSignalOutput에 필드 4개 추가)
  └─ analyzer.py (수정 - generate_actionable_signal 프롬프트 강화)

src/pipelines/
  └─ deep_dive.py (수정 - chart_patterns + price_levels 호출)
```

### 새 데이터 모델

**1. ChartPatternResult**

```python
class ChartPatternResult(BaseModel):
    """차트 패턴 감지 결과"""
    
    pattern_name: str  # "Cup & Handle", "Double Bottom", etc.
    detected: bool
    confidence: float  # 0.0-1.0 (룰 기반 스코어링)
    
    # 타이밍 정보
    completed_date: str | None  # "2026-04-15"
    days_ago: int | None  # 8 (며칠 전 완성)
    
    # 가격 정보
    current_price: float
    breakout_level: float | None  # 돌파 레벨
    support_level: float | None   # 지지 레벨
    
    # 상세 정보
    description: str  # "컵 깊이 28%, 핸들 조정 12%, 8일 전 완성"
    key_levels: dict  # {"cup_bottom": 140, "right_peak": 200}
```

**2. PriceLevel & PriceLevels**

```python
class PriceLevel(BaseModel):
    """개별 가격 레벨"""
    price: float
    type: str  # "sma_50", "pivot_s1", "swing_high", "fib_0.618"
    distance_pct: float  # 현재가 대비 거리 (%)
    description: str  # "50일 이평선", "스윙 고점"

class PriceLevels(BaseModel):
    """통합 가격 레벨 정보"""
    current_price: float
    support_levels: list[PriceLevel]  # 가까운 순 정렬
    resistance_levels: list[PriceLevel]
    targets: dict[str, float]  # {"cup_handle": 250, "fib_1.618": 235}
```

**3. ActionableSignalOutput 확장**

```python
class ActionableSignalOutput(BaseModel):
    # 기존 필드 (Phase 1)
    action: Literal["매수", "매도", "관망"]
    timing: Literal["지금", "조정_대기", "보류"]
    signal_strength: int = Field(ge=1, le=10)
    headline: str
    primary_reason: str
    supporting_reasons: list[str]
    risks: list[str]
    invalidation_point: str | None
    confidence: float
    
    # 신규 필드 (Phase 2)
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
```

---

## Component 1: Chart Pattern Detection

### 구현할 패턴 (4개)

1. **Cup & Handle** (일봉 60-120일)
2. **Double Bottom** (일봉 40-80일)
3. **Head & Shoulders** (일봉 60-100일)
4. **Support/Resistance Test** (현재가 기준)

### 공통 인프라

```python
# src/tools/technical/components/chart_patterns.py

from scipy.signal import find_peaks
import pandas as pd
import numpy as np

def detect_chart_patterns(df: pd.DataFrame) -> dict[str, ChartPatternResult]:
    """모든 차트 패턴 감지 통합 함수 (일봉 데이터)"""
    return {
        "cup_and_handle": detect_cup_and_handle(df),
        "double_bottom": detect_double_bottom(df),
        "head_and_shoulders": detect_head_and_shoulders(df),
        "support_resistance_test": test_support_resistance(df),
    }
```

### 패턴 1: Cup & Handle

**감지 로직:**

```python
def detect_cup_and_handle(df: pd.DataFrame) -> ChartPatternResult:
    """Cup & Handle 패턴 감지 (일봉 기준)"""
    
    if len(df) < 70:  # 최소 60일 컵 + 10일 여유
        return ChartPatternResult(detected=False, ...)
    
    prices = df['Close'].values
    
    # 1. scipy.find_peaks로 고점 2개 찾기
    peaks, _ = find_peaks(prices, distance=5, prominence=prices.mean()*0.05)
    
    for i in range(1, len(peaks)):
        left_peak_idx = peaks[i-1]
        right_peak_idx = peaks[i]
        
        # 컵 구간 데이터
        cup_range = prices[left_peak_idx : right_peak_idx+1]
        if len(cup_range) < 60 or len(cup_range) > 120:
            continue
        
        cup_max = max(prices[left_peak_idx], prices[right_peak_idx])
        cup_min = min(cup_range)
        cup_depth = (cup_max - cup_min) / cup_max
        
        # 2. 컵 깊이 검증 (15-40%)
        if not (0.15 <= cup_depth <= 0.40):
            continue
        
        # 3. 핸들 구간 확인
        handle_range = prices[right_peak_idx : right_peak_idx + 10]
        if len(handle_range) < 2:
            continue
        
        handle_max = handle_range[0]
        handle_min = min(handle_range)
        handle_retracement = (handle_max - handle_min) / handle_max
        
        # 4. 핸들 검증 (되돌림 <15%, 위치 > 컵 바닥)
        if handle_retracement <= 0.15 and handle_min > cup_min:
            
            # 5. Confidence 계산 (0.0-1.0)
            confidence = calculate_cup_handle_confidence(
                cup_depth, handle_retracement, len(cup_range)
            )
            
            # 6. 발생 시점 계산
            completed_idx = right_peak_idx
            completed_date = df.index[completed_idx].strftime("%Y-%m-%d")
            days_ago = len(df) - completed_idx - 1
            
            # 7. 목표가 계산 (컵 깊이만큼 상승)
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
                key_levels={"cup_bottom": cup_min, "right_peak": cup_max, "target": target},
            )
    
    return ChartPatternResult(detected=False, ...)
```

**Confidence 계산:**

```python
# src/tools/technical/components/chart_patterns.py

# 패턴별 Confidence 가중치 (config로 외부화)
PATTERN_CONFIDENCE_WEIGHTS = {
    "cup_and_handle": {
        "depth_weight": 0.3,
        "handle_weight": 0.3,
        "period_weight": 0.2,
        "volume_weight": 0.2,
    },
    "double_bottom": {
        "height_similarity_weight": 0.4,
        "rebound_weight": 0.3,
        "period_weight": 0.3,
    },
    # 다른 패턴도 동일하게
}

def calculate_cup_handle_confidence(
    cup_depth: float, 
    handle_ret: float, 
    cup_length: int,
    weights: dict | None = None
) -> float:
    """룰 기반 신뢰도 스코어링 (가중치 외부화)"""
    
    if weights is None:
        weights = PATTERN_CONFIDENCE_WEIGHTS["cup_and_handle"]
    
    confidence = 0.0
    
    # 1. 컵 깊이 적합도
    ideal_depth = 0.27  # 15-40% 중간값
    depth_score = 1.0 - abs(cup_depth - ideal_depth) / 0.125
    confidence += depth_score * weights["depth_weight"]
    
    # 2. 핸들 되돌림 적합도
    handle_score = 1.0 - (handle_ret / 0.15)
    confidence += handle_score * weights["handle_weight"]
    
    # 3. 기간 적합도
    if 60 <= cup_length <= 120:
        confidence += weights["period_weight"]
    
    # 4. 볼륨 패턴 (선택적)
    confidence += 0.5 * weights["volume_weight"]  # 기본 점수
    
    return min(confidence, 1.0)
```

### 패턴 2: Double Bottom

**감지 로직:**

```python
def detect_double_bottom(df: pd.DataFrame) -> ChartPatternResult:
    """Double Bottom 패턴 감지 (일봉)"""
    
    if len(df) < 50:
        return ChartPatternResult(detected=False, ...)
    
    prices = df['Close'].values
    
    # 1. 골짜기(저점) 찾기 (가격 반전)
    valleys, _ = find_peaks(-prices, distance=10, prominence=prices.mean()*0.03)
    
    for i in range(1, len(valleys)):
        valley1_idx = valleys[i-1]
        valley2_idx = valleys[i]
        
        if valley2_idx - valley1_idx < 40 or valley2_idx - valley1_idx > 80:
            continue
        
        bottom1 = prices[valley1_idx]
        bottom2 = prices[valley2_idx]
        
        # 2. 두 저점 높이 유사도 (<5% 차이)
        height_diff = abs(bottom1 - bottom2) / min(bottom1, bottom2)
        if height_diff > 0.05:
            continue
        
        # 3. 중간 반등 고점 (목선)
        middle_range = prices[valley1_idx : valley2_idx]
        neckline = max(middle_range)
        
        # 4. 목선이 저점보다 충분히 높은지 (>10%)
        rebound = (neckline - min(bottom1, bottom2)) / min(bottom1, bottom2)
        if rebound < 0.10:
            continue
        
        # 5. Confidence 계산
        confidence = calculate_double_bottom_confidence(height_diff, rebound)
        
        # 6. 발생 시점
        completed_idx = valley2_idx
        completed_date = df.index[completed_idx].strftime("%Y-%m-%d")
        days_ago = len(df) - completed_idx - 1
        
        # 7. 목표가 (목선 + 바닥~목선 거리)
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
            key_levels={"bottom1": bottom1, "bottom2": bottom2, "neckline": neckline, "target": target},
        )
    
    return ChartPatternResult(detected=False, ...)
```

### 패턴 3: Head & Shoulders

**감지 로직:**

```python
def detect_head_and_shoulders(df: pd.DataFrame) -> ChartPatternResult:
    """Head & Shoulders 패턴 감지 (일봉)"""
    
    if len(df) < 70:
        return ChartPatternResult(detected=False, ...)
    
    prices = df['Close'].values
    
    # 1. 고점 3개 찾기
    peaks, _ = find_peaks(prices, distance=10, prominence=prices.mean()*0.05)
    
    if len(peaks) < 3:
        return ChartPatternResult(detected=False, ...)
    
    for i in range(len(peaks) - 2):
        left_shoulder_idx = peaks[i]
        head_idx = peaks[i+1]
        right_shoulder_idx = peaks[i+2]
        
        if right_shoulder_idx - left_shoulder_idx < 60 or right_shoulder_idx - left_shoulder_idx > 100:
            continue
        
        left_shoulder = prices[left_shoulder_idx]
        head = prices[head_idx]
        right_shoulder = prices[right_shoulder_idx]
        
        # 2. 헤드가 어깨들보다 높은지 (>5%)
        if head <= left_shoulder * 1.05 or head <= right_shoulder * 1.05:
            continue
        
        # 3. 두 어깨 높이 유사 (<10% 차이)
        shoulder_diff = abs(left_shoulder - right_shoulder) / max(left_shoulder, right_shoulder)
        if shoulder_diff > 0.10:
            continue
        
        # 4. 목선 (어깨 사이 저점들 연결)
        left_valley = prices[left_shoulder_idx : head_idx].min()
        right_valley = prices[head_idx : right_shoulder_idx].min()
        neckline = (left_valley + right_valley) / 2
        
        # 5. Confidence 계산
        head_prominence = (head - max(left_shoulder, right_shoulder)) / head
        confidence = calculate_head_shoulders_confidence(head_prominence, shoulder_diff)
        
        # 6. 발생 시점
        completed_idx = right_shoulder_idx
        completed_date = df.index[completed_idx].strftime("%Y-%m-%d")
        days_ago = len(df) - completed_idx - 1
        
        # 7. 목표가 (하방, 헤드-목선 거리만큼)
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
            key_levels={"left_shoulder": left_shoulder, "head": head, "right_shoulder": right_shoulder, "neckline": neckline, "target": target},
        )
    
    return ChartPatternResult(detected=False, ...)
```

### 패턴 4: Support/Resistance Test

**감지 로직:**

```python
def test_support_resistance(
    df: pd.DataFrame,
    snapshot: IndicatorSnapshot
) -> ChartPatternResult:
    """현재가가 주요 레벨 근처(±2%)에 있는지 테스트"""
    
    current_price = snapshot.price
    levels = []
    
    # 1. 수집할 레벨들
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
    
    # 2. ±2% 이내 레벨 찾기
    for level_type, level_price, level_name in levels:
        distance_pct = abs(current_price - level_price) / current_price
        
        if distance_pct <= 0.02:  # 2% 이내
            return ChartPatternResult(
                pattern_name="Support/Resistance Test",
                detected=True,
                confidence=1.0 - distance_pct / 0.02,  # 가까울수록 높음
                completed_date=df.index[-1].strftime("%Y-%m-%d"),
                days_ago=0,
                current_price=current_price,
                breakout_level=level_price if level_type == "resistance" else None,
                support_level=level_price if level_type == "support" else None,
                description=f"{level_name} 테스트 중 (거리 {distance_pct:.1%})",
                key_levels={"test_level": level_price, "type": level_type, "name": level_name},
            )
    
    return ChartPatternResult(detected=False, ...)
```

---

## Helper Functions

### find_last_occurrence (유틸리티)

```python
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
    
    Note:
        같은 가격대의 여러 봉을 같은 swing으로 간주하기 위해 tolerance 사용
    """
    mask = (df[column] - target_value).abs() / target_value <= tolerance
    matches = df.index[mask]
    
    return len(df) - len(matches) + matches[-1] if len(matches) > 0 else None
```

---

## Component 2: Price Level Analysis

### 계산 항목

1. **피보나치 되돌림** (Swing or 6개월 high/low 기준)
2. **이동평균선** (20/50/200일)
3. **피봇 포인트** (support_s1, resistance_r1)
4. **스윙 고점/저점**
5. **ATR 기반 레벨** (선택적)
6. **패턴 목표가** (패턴 감지 결과에서)

### 피보나치 베이스 포인트 선택

```python
def get_fibonacci_base_points(
    df: pd.DataFrame, 
    snapshot: IndicatorSnapshot
) -> tuple[float, float]:
    """피보나치 계산 기준 고점/저점 선택
    
    우선순위:
    1. Swing High/Low (최근 6개월 이내)
    2. 6개월 High/Low (Fallback)
    """
    
    # 1순위: Swing Points
    if snapshot.swing_high and snapshot.swing_low:
        # Swing 발생 시점이 6개월 이내인지 확인
        # tolerance: 같은 가격대(±0.1%)의 여러 봉을 같은 swing으로 간주
        swing_high_idx = find_last_occurrence(
            df, 'High', snapshot.swing_high, tolerance=0.001
        )
        
        if swing_high_idx is not None:
            days_since_swing = len(df) - swing_high_idx - 1
            if days_since_swing <= 126:  # 6개월 ≈ 126 거래일
                return snapshot.swing_high, snapshot.swing_low
    
    # 2순위: 6개월 High/Low
    high_6m = df['High'].tail(126).max()
    low_6m = df['Low'].tail(126).min()
    
    return high_6m, low_6m
```

### 피보나치 레벨 계산

```python
def calculate_fibonacci_levels(high: float, low: float) -> dict[str, float]:
    """피보나치 되돌림 및 확장 레벨"""
    
    diff = high - low
    
    return {
        # 되돌림 레벨 (하락 후 반등)
        "fib_0.236": high - diff * 0.236,
        "fib_0.382": high - diff * 0.382,
        "fib_0.500": high - diff * 0.500,
        "fib_0.618": high - diff * 0.618,  # 황금비율
        "fib_0.786": high - diff * 0.786,
        "fib_1.000": low,  # 100% 되돌림
        
        # 확장 레벨 (상승 목표)
        "fib_1.272": high + diff * 0.272,
        "fib_1.618": high + diff * 0.618,
        "fib_2.000": high + diff * 1.000,
    }
```

### ATR 기반 레벨

```python
def calculate_atr_levels(
    current_price: float, 
    atr: float
) -> dict[str, float]:
    """변동성 기반 지지/저항"""
    
    return {
        "atr_support_1x": current_price - atr,
        "atr_support_2x": current_price - 2 * atr,
        "atr_support_3x": current_price - 3 * atr,
        "atr_resistance_1x": current_price + atr,
        "atr_resistance_2x": current_price + 2 * atr,
        "atr_resistance_3x": current_price + 3 * atr,
    }
```

### 통합 및 필터링

```python
def identify_key_levels(
    snapshot: IndicatorSnapshot,
    pattern_results: dict[str, ChartPatternResult],
    lookback_high: float,
    lookback_low: float,
) -> PriceLevels:
    """모든 레벨 수집 → 중복 제거 → 가까운 순 정렬"""
    
    all_levels: list[PriceLevel] = []
    
    # 1. 이동평균선
    for ma in [20, 50, 200]:
        if ma_val := getattr(snapshot, f"sma_{ma}", None):
            all_levels.append(PriceLevel(
                price=ma_val,
                type=f"sma_{ma}",
                distance_pct=(ma_val - snapshot.price) / snapshot.price * 100,
                description=f"{ma}일 이평선",
            ))
    
    # 2. 피봇 포인트
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
    
    # 3. 스윙 포인트
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
    
    # 4. 피보나치 레벨
    fib_levels = calculate_fibonacci_levels(lookback_high, lookback_low)
    for fib_name, fib_price in fib_levels.items():
        all_levels.append(PriceLevel(
            price=fib_price,
            type=fib_name,
            distance_pct=(fib_price - snapshot.price) / snapshot.price * 100,
            description=f"피보나치 {fib_name.replace('fib_', '')}",
        ))
    
    # 5. ATR 레벨 (선택적)
    if snapshot.atr:
        atr_levels = calculate_atr_levels(snapshot.price, snapshot.atr)
        for atr_name, atr_price in atr_levels.items():
            all_levels.append(PriceLevel(
                price=atr_price,
                type=atr_name,
                distance_pct=(atr_price - snapshot.price) / snapshot.price * 100,
                description=f"ATR {atr_name.replace('atr_', '').replace('_', ' ')}",
            ))
    
    # 6. 패턴 돌파 레벨
    for pattern_name, result in pattern_results.items():
        if result.detected and result.breakout_level:
            all_levels.append(PriceLevel(
                price=result.breakout_level,
                type=f"pattern_{pattern_name}_breakout",
                distance_pct=(result.breakout_level - snapshot.price) / snapshot.price * 100,
                description=f"{result.pattern_name} 돌파",
            ))
    
    # 중복 제거 (현재가 대비 dynamic threshold)
    unique_levels = deduplicate_levels(all_levels, snapshot.price, base_threshold=0.01)
    
    # 현재가 기준 분류
    supports = [lv for lv in unique_levels if lv.price < snapshot.price]
    resistances = [lv for lv in unique_levels if lv.price > snapshot.price]
    
    # 가까운 순 정렬
    supports.sort(key=lambda x: x.price, reverse=True)  # 높은 지지부터
    resistances.sort(key=lambda x: x.price)  # 낮은 저항부터
    
    # 패턴 목표가 추출
    targets = {}
    for pattern_name, result in pattern_results.items():
        if result.detected:
            target_key = result.key_levels.get("target")
            if target_key:
                targets[f"{pattern_name}_target"] = target_key
    
    # 피보나치 확장도 타겟에 추가
    if "fib_1.618" in fib_levels:
        targets["fibonacci_extension_1.618"] = fib_levels["fib_1.618"]
    
    return PriceLevels(
        current_price=snapshot.price,
        support_levels=supports[:5],  # 상위 5개만
        resistance_levels=resistances[:5],
        targets=targets,
    )

def deduplicate_levels(
    levels: list[PriceLevel],
    current_price: float,
    base_threshold: float = 0.01
) -> list[PriceLevel]:
    """중복 레벨 제거 (현재가 대비 dynamic threshold)
    
    Args:
        levels: 모든 가격 레벨
        current_price: 현재가 (threshold 기준)
        base_threshold: 기본 threshold (1% = 0.01)
    
    현재가 근처(±5% 이내)는 더 민감하게 (threshold 50% 감소)
    """
    
    if not levels:
        return []
    
    levels_sorted = sorted(levels, key=lambda x: x.price)
    unique = [levels_sorted[0]]
    
    for level in levels_sorted[1:]:
        last_price = unique[-1].price
        
        # Dynamic threshold: 현재가 근처는 더 민감하게
        distance_from_current = abs(level.price - current_price) / current_price
        threshold = base_threshold * (0.5 if distance_from_current < 0.05 else 1.0)
        
        if abs(level.price - last_price) / last_price > threshold:
            unique.append(level)
        else:
            # 더 의미 있는 타입 우선 (이평선 > 피보나치 > ATR)
            priority = {"sma_": 3, "swing_": 3, "pivot_": 2, "fib_": 1, "atr_": 0}
            current_priority = max((priority.get(k, 0) for k in priority if level.type.startswith(k)), default=0)
            last_priority = max((priority.get(k, 0) for k in priority if unique[-1].type.startswith(k)), default=0)
            
            if current_priority > last_priority:
                unique[-1] = level
    
    return unique
```

---

## Component 3: LLM Integration

### 프롬프트 강화

```python
async def generate_actionable_signal(
    ticker: str,
    technical_data: TechnicalResult,
    technical_summary: TechnicalSummaryOutput,
    chart_patterns: dict[str, ChartPatternResult],  # 신규
    price_levels: PriceLevels,  # 신규
    llm: BaseChatModel,
) -> ActionableSignalOutput:
    """Generate actionable investment signal with patterns and price levels."""
    
    # 패턴 요약 문장 생성
    patterns_text = format_patterns_for_llm(chart_patterns)
    
    # 가격 레벨 요약 문장 생성
    levels_text = format_levels_for_llm(price_levels)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """당신은 프로 트레이더입니다. 구체적인 가격과 패턴으로 명확한 투자 신호를 제공하세요.

**신규 필드 작성 가이드:**

1. **pattern_insight**: 감지된 패턴을 자연스럽게 해석
   - 패턴이 있으면: "Cup & Handle 형성 완료 (8일 전), 돌파 준비 중"
   - 패턴이 없으면: "명확한 차트 패턴 없음, 지지/저항선 중심 분석"
   - 여러 패턴: 가장 신뢰도 높은 것 중심으로
   - 발생 시점 언급 (예: "3일 전 완성", "방금 형성")

2. **target_price**: 시나리오별 목표가 (자유 서술)
   - 상승 시: "돌파 시 Cup & Handle 목표 $250, 중간 저항 $210"
   - 하락 시: "이탈 시 50일선 $175까지 조정 가능, 지지 붕괴 시 $160"
   - 모든 레벨 활용 (패턴 목표, 피보나치, 이평선, ATR, 스윙 포인트)
   - 구체적 가격 + 근거 명시

3. **entry_zone**: 진입 타이밍과 구간 (자유 서술)
   - 현재 위치 설명: "현재 $200 저항 테스트 중"
   - 매수: "조정 시 $175-180 (50일선) 분할 매수, 돌파 확인 후 $205 추격 가능"
   - 매도/관망: "반등 시 $210 (피보나치 61.8%) 근처 매도 고려"
   - 구간은 지지/저항 레벨 활용

4. **key_levels**: 핵심 가격 레벨 간결 요약
   - "지지: $187/$175/$160, 저항: $200/$210/$250"
   - 괄호로 타입 설명 가능: "지지: $175(50일선)/$160(스윙저점)"
   - 최대 3-4개씩만 (가장 가까운 것 우선)

**기존 필드 작성 규칙:**
- primary_reason: 반드시 구체적 숫자 포함 (RSI 28, 거래량 2.3배 등)
- headline: "{action}. {timing}. 이유: {핵심}"
- invalidation_point: 손절 가격 명시 (가장 가까운 support 활용)
- signal_strength: 1-10, 5개 팩터 종합 (패턴 포함)
"""),
        ("user", """종목: {ticker}

**기술적 분석** (8 components):
{technical_summary}

**차트 패턴**:
{patterns_text}

**가격 레벨**:
{levels_text}

**뉴스**: {news_analysis}
**펀더멘탈**: {fundamental_summary}
**공시**: {disclosure_text}
**수급**: {flow_text}

위 정보를 종합해서 명확한 투자 신호를 생성하세요."""),
    ])
    
    messages = prompt.format_messages(
        ticker=ticker,
        technical_summary=technical_summary.model_dump_json(),
        patterns_text=patterns_text,
        levels_text=levels_text,
        news_analysis=...,
        fundamental_summary=...,
        disclosure_text=...,
        flow_text=...,
    )
    
    return await invoke_llm_with_retry(
        llm=llm,
        output_model=ActionableSignalOutput,
        messages=messages,
        config={},
        max_retries=3,
        timeout_seconds=60.0,
    )
```

### 포매터 함수

```python
def format_patterns_for_llm(
    patterns: dict[str, ChartPatternResult]
) -> str:
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
    
    # 지지선
    if levels.support_levels:
        lines.append("지지선 (가까운 순):")
        for i, support in enumerate(levels.support_levels[:5], 1):
            lines.append(
                f"  {i}. ${support.price:.2f} "
                f"({support.description}, {support.distance_pct:+.1f}%)"
            )
        lines.append("")
    
    # 저항선
    if levels.resistance_levels:
        lines.append("저항선 (가까운 순):")
        for i, resistance in enumerate(levels.resistance_levels[:5], 1):
            lines.append(
                f"  {i}. ${resistance.price:.2f} "
                f"({resistance.description}, {resistance.distance_pct:+.1f}%)"
            )
        lines.append("")
    
    # 타겟
    if levels.targets:
        lines.append("타겟 (상승 시나리오):")
        for target_name, target_price in levels.targets.items():
            readable_name = target_name.replace("_", " ").title()
            lines.append(f"  - {readable_name}: ${target_price:.2f}")
    
    return "\n".join(lines)
```

### LLM 출력 예시

```
**차트 패턴**:
- Cup & Handle: 감지됨 (신뢰도 85%, 8일 전 완성)
  컵 깊이 28%, 핸들 조정 12%, 8일 전 완성
  돌파 레벨: $200.50
- Double Bottom: 미감지
- Head & Shoulders: 미감지
- Support/Resistance Test: 저항선 테스트 중 (피봇 R1, +0.2%)

**가격 레벨**:
현재가: $200.00

지지선 (가까운 순):
  1. $187.46 (피봇 지지1, -6.3%)
  2. $182.00 (스윙 저점, -9.0%)
  3. $175.00 (50일 이평선, -12.5%)
  4. $160.25 (Supertrend, -19.9%)

저항선 (가까운 순):
  1. $205.00 (스윙 고점, +2.5%)
  2. $210.00 (피보나치 61.8%, +5.0%)
  3. $250.00 (패턴 목표, +25.0%)

타겟 (상승 시나리오):
  - Cup And Handle Target: $250.00
  - Fibonacci Extension 1.618: $235.00
```

---

## Data Flow

### 전체 흐름

```
1. CLI: jarvis analyze AAPL
   └─ DeepDivePipeline.run("AAPL")

2. TechnicalTool.execute("AAPL")
   ├─ Download OHLCV data (yfinance)
   ├─ Calculate indicators
   └─ Return TechnicalResult(raw_dataframe=df, snapshot=...)

3. DeepDivePipeline._generate_actionable_signal()
   ├─ detect_chart_patterns(df)
   │   └─ {cup_handle: ChartPatternResult(...), ...}
   │
   ├─ get_fibonacci_base_points(df, snapshot)
   │   └─ (swing_high, swing_low) or (6m_high, 6m_low)
   │
   ├─ identify_key_levels(snapshot, patterns, high, low)
   │   └─ PriceLevels(support=[...], resistance=[...], targets={...})
   │
   └─ analyzer.generate_actionable_signal(...)
       ├─ format_patterns_for_llm(patterns)
       ├─ format_levels_for_llm(levels)
       ├─ LLM 호출
       └─ ActionableSignalOutput(
             pattern_insight="Cup & Handle 8일 전 완성",
             target_price="돌파 시 $250 목표",
             entry_zone="조정 시 $175-180 매수",
             key_levels="지지: $187/$175, 저항: $205/$250",
             ...
         )

4. CLI: display_actionable_signal(signal)
   └─ Rich Panel 출력 (기존 + 신규 4개 필드)
```

### TechnicalResult 확장

```python
# src/tools/technical/models.py

class TechnicalResult(BaseModel):
    """Complete technical analysis result."""
    
    ticker: str | None
    timestamp: datetime
    snapshot: IndicatorSnapshot
    components: dict[str, dict]
    total_score: int = 0
    
    # 신규: 패턴 감지용 원본 데이터 (메모리 최적화)
    # 옵션 1: 필요한 컬럼만 (Open, High, Low, Close)
    # 옵션 2: 참조로 유지 (deep copy 피함)
    raw_dataframe: pd.DataFrame | None = None
    
    # Legacy fields (호환성)
    indicators: IndicatorSnapshot | None = None
    strategies: list[StrategyResult] | None = None
    overall_assessment: str | None = None
    confidence_score: float | None = None
    key_insights: list[str] | None = None
    warnings: list[str] | None = None
    
    class Config:
        arbitrary_types_allowed = True  # pandas.DataFrame 허용
    
    @classmethod
    def from_analysis(cls, df: pd.DataFrame, **kwargs):
        """메모리 최적화: 필요한 컬럼만 저장"""
        slim_df = df[['Open', 'High', 'Low', 'Close']].copy()
        return cls(raw_dataframe=slim_df, **kwargs)
```

---

## Testing Strategy

### 1. 단위 테스트 (Fast)

**패턴 감지:**

```python
# tests/tools/technical/test_chart_patterns.py

def test_cup_and_handle_perfect_pattern():
    """완벽한 Cup & Handle 패턴"""
    df = create_mock_cup_and_handle(
        cup_depth=0.25, 
        handle_ret=0.10, 
        cup_days=60
    )
    
    result = detect_cup_and_handle(df)
    
    assert result.detected is True
    assert result.confidence > 0.85
    assert result.days_ago == 0
    assert "Cup & Handle" in result.pattern_name

def test_cup_and_handle_too_shallow():
    """컵이 너무 얕음 (10%) - 미감지"""
    df = create_mock_cup_and_handle(cup_depth=0.10)
    result = detect_cup_and_handle(df)
    assert result.detected is False

def test_double_bottom_similar_valleys():
    """Double Bottom 두 저점 유사"""
    df = create_mock_double_bottom(valley1=100, valley2=101)
    result = detect_double_bottom(df)
    assert result.detected is True
    assert result.confidence > 0.7
```

**가격 레벨:**

```python
# tests/tools/technical/test_price_levels.py

def test_fibonacci_levels_calculation():
    """피보나치 계산 정확도"""
    fib = calculate_fibonacci_levels(high=200, low=100)
    
    assert fib["fib_0.382"] == pytest.approx(161.8, rel=0.01)
    assert fib["fib_0.618"] == pytest.approx(138.2, rel=0.01)
    assert fib["fib_1.618"] == pytest.approx(261.8, rel=0.01)

def test_deduplicate_levels():
    """중복 레벨 제거 (±1% 이내)"""
    levels = [
        PriceLevel(price=100.0, type="sma_50", distance_pct=-5.0, description="50일선"),
        PriceLevel(price=100.5, type="pivot_s1", distance_pct=-4.9, description="피봇"),
        PriceLevel(price=110.0, type="sma_20", distance_pct=+5.0, description="20일선"),
    ]
    
    unique = deduplicate_levels(levels, threshold=0.01)
    
    assert len(unique) == 2  # 100.0과 100.5는 중복 제거
    assert unique[0].type == "sma_50"  # 우선순위 높은 것 선택

def test_identify_key_levels_sorting():
    """지지/저항 가까운 순 정렬"""
    snapshot = IndicatorSnapshot(
        price=200.0,
        sma_50=175.0,
        sma_200=150.0,
        support_s1=187.0,
        resistance_r1=210.0,
    )
    
    levels = identify_key_levels(snapshot, {}, 250.0, 140.0)
    
    # 지지선: 가까운 순 (높은 가격부터)
    assert levels.support_levels[0].price > levels.support_levels[1].price
    # 저항선: 가까운 순 (낮은 가격부터)
    assert levels.resistance_levels[0].price < levels.resistance_levels[1].price
```

### 2. 통합 테스트 (Medium)

```python
# tests/pipelines/test_deep_dive_v2.py

@pytest.mark.asyncio
async def test_actionable_signal_with_patterns_and_levels(mock_llm):
    """패턴 + 가격 레벨 통합 테스트"""
    
    # Mock LLM output
    mock_llm_output = ActionableSignalOutput(
        action="매수",
        timing="조정_대기",
        signal_strength=7,
        headline="매수. 조정_대기. 이유: Cup & Handle 형성",
        primary_reason="Cup & Handle 8일 전 완성 (신뢰도 85%)",
        supporting_reasons=["50일선 지지 근접", "거래량 증가"],
        risks=["저항선 $210 돌파 실패 시 조정"],
        invalidation_point="$175 (50일선)",
        confidence=0.75,
        # 신규 필드
        pattern_insight="Cup & Handle 8일 전 완성, 현재 핸들 구간",
        target_price="돌파 시 $250 (Cup & Handle 목표), 중간 저항 $210",
        entry_zone="조정 시 $175-180 (50일선) 분할 매수",
        key_levels="지지: $187/$175/$160, 저항: $200/$210/$250",
    )
    
    with patch("src.llm.analyzer.generate_actionable_signal") as mock_gen:
        mock_gen.return_value = mock_llm_output
        
        pipeline = DeepDivePipeline(...)
        result = await pipeline.run("AAPL")
        
        signal = result["actionable_signal"]
        
        # 신규 필드 존재 확인
        assert signal.pattern_insight is not None
        assert "Cup" in signal.pattern_insight or "컵" in signal.pattern_insight
        assert signal.target_price is not None
        assert "$250" in signal.target_price
        assert signal.entry_zone is not None
        assert signal.key_levels is not None

@pytest.mark.asyncio
async def test_actionable_signal_no_patterns(mock_llm):
    """패턴 없을 때도 정상 동작"""
    
    # 패턴 미감지 상황
    with patch("src.tools.technical.components.chart_patterns.detect_chart_patterns") as mock_detect:
        mock_detect.return_value = {
            "cup_and_handle": ChartPatternResult(detected=False, ...),
            "double_bottom": ChartPatternResult(detected=False, ...),
            "head_and_shoulders": ChartPatternResult(detected=False, ...),
            "support_resistance_test": ChartPatternResult(detected=False, ...),
        }
        
        pipeline = DeepDivePipeline(...)
        result = await pipeline.run("AAPL")
        
        signal = result["actionable_signal"]
        
        # 패턴이 없어도 가격 레벨 기반 분석은 가능
        assert signal.target_price is not None
        assert signal.key_levels is not None
        # pattern_insight는 "명확한 패턴 없음" 같은 문구 가능
```

### 3. 실제 데이터 검증 (Slow, CI skip)

```python
# tests/integration/test_known_patterns.py

@pytest.mark.integration
@pytest.mark.parametrize("ticker,expected_pattern,year,month", [
    ("NVDA", "cup_and_handle", "2023", "06"),
    ("AAPL", "double_bottom", "2019", "03"),
    ("TSLA", "head_and_shoulders", "2021", "11"),
])
def test_historical_pattern_detection(ticker, expected_pattern, year, month):
    """유명한 역사적 패턴 감지 검증 (snapshot 데이터 사용)"""
    
    # Snapshot 파일에서 데이터 로드 (재현 가능한 테스트)
    snapshot_path = f"tests/fixtures/patterns/{ticker}_{year}.csv"
    df = pd.read_csv(snapshot_path, index_col=0, parse_dates=True)
    
    patterns = detect_chart_patterns(df)
    
    result = patterns[expected_pattern]
    
    assert result.detected is True, f"{ticker} {year}년 {expected_pattern} 미감지"
    assert result.confidence > 0.6
    assert result.completed_date.startswith(f"{year}-{month}")

@pytest.mark.integration
def test_false_positive_rate():
    """False Positive 체크 (Mock 데이터 사용)"""
    
    # Mock 데이터 생성 (확정적 테스트)
    test_cases = [
        create_flat_price_series(days=120, price=100),  # 횡보
        create_noisy_series(days=120, base=100, noise=0.02),  # 노이즈
        create_random_walk(days=120, start=100),  # 랜덤워크
    ]
    
    false_positives = 0
    
    for df in test_cases:
        patterns = detect_chart_patterns(df)
        
        # 패턴이 감지되면 False Positive
        detected_count = sum(1 for p in patterns.values() if p.detected)
        if detected_count > 0:
            false_positives += 1
    
    # False Positive < 20% (3개 중 0개 예상)
    assert false_positives / len(test_cases) < 0.2
```

### 4. CLI E2E 테스트

```python
# tests/cli/test_analyze_v2.py

def test_analyze_displays_new_fields():
    """CLI 출력에 새 필드 표시 확인"""
    
    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "--provider", "openai"])
    
    assert result.exit_code == 0
    assert "🎯 투자 신호" in result.output
    
    # 새 필드 키워드 체크 (LLM 생성 문구는 가변적이므로)
    output_lower = result.output.lower()
    
    # pattern_insight 관련
    assert any(kw in output_lower for kw in ["패턴", "pattern", "형성", "완성"])
    
    # target_price 관련
    assert any(kw in output_lower for kw in ["목표", "target", "돌파"])
    
    # entry_zone 관련
    assert any(kw in output_lower for kw in ["진입", "매수", "구간"])
    
    # key_levels 관련
    assert "지지" in output_lower or "저항" in output_lower
```

---

## Success Criteria

### Phase 2 목표

| 항목 | 기준 | 측정 방법 |
|------|------|-----------|
| **패턴 감지 정확도** | ≥ 70% | 10개 유명 패턴 테스트 (NVDA 2023 Cup & Handle 등) |
| **False Positive** | ≤ 20% | 패턴 없는 횡보 종목 테스트 |
| **Confidence 스코어링** | ≥ 0.7 (완벽한 패턴) | 단위 테스트 검증 |
| **가격 레벨 개수** | 3-5개 (지지/저항 각각) | 중복 제거 후 개수 확인 |
| **LLM 필드 채움률** | 100% | 4개 필드 모두 non-null |
| **응답 속도** | < 5초 (기존 대비 +2초) | 패턴/레벨 계산 오버헤드 |
| **기존 테스트 통과** | 100% | Phase 1 테스트 그린 유지 |

### 품질 게이트

**출시 전 체크리스트:**

- [ ] 4개 패턴 모두 단위 테스트 통과
- [ ] 10개 역사적 패턴 감지 성공 (≥7개)
- [ ] False Positive < 20% (횡보 종목 테스트)
- [ ] 가격 레벨 중복 제거 검증
- [ ] LLM 프롬프트 10개 종목 테스트 (4개 필드 채움 확인)
- [ ] 기존 deep_dive 테스트 모두 통과
- [ ] CLI 출력 매뉴얼 확인 (예쁘게 나오는지)

---

## Implementation Plan

### 작업 항목 (Phase 2)

| # | 작업 | 파일 | 예상 시간 |
|---|------|------|-----------|
| 2.1 | ChartPatternResult, PriceLevel 모델 추가 | `src/tools/technical/models.py` | 15분 |
| 2.1b | Helper 함수 구현 (find_last_occurrence, mock generators) | `src/tools/technical/utils.py` (신규) | 20분 |
| 2.2 | Cup & Handle 패턴 감지 구현 | `src/tools/technical/components/chart_patterns.py` | 45분 |
| 2.3 | Double Bottom 패턴 감지 구현 | 위 파일 | 30분 |
| 2.4 | Head & Shoulders 패턴 감지 구현 | 위 파일 | 30분 |
| 2.5 | Support/Resistance Test 구현 | 위 파일 | 15분 |
| 2.6 | 피보나치 레벨 계산 | `src/tools/technical/price_levels.py` (신규) | 20분 |
| 2.7 | 가격 레벨 통합 및 중복 제거 | 위 파일 | 30분 |
| 2.8 | ActionableSignalOutput 4개 필드 추가 | `src/llm/models.py` | 10분 |
| 2.9 | 프롬프트 강화 및 포매터 함수 | `src/llm/analyzer.py` | 30분 |
| 2.10 | DeepDivePipeline 통합 | `src/pipelines/deep_dive.py` | 20분 |
| 2.11 | TechnicalResult에 raw_dataframe 추가 | `src/tools/technical/models.py`, `tool.py` | 15분 |
| 2.12 | CLI 출력 수정 (4개 필드 표시) | `src/cli/main.py` | 15분 |
| 2.13 | 단위 테스트 작성 (패턴 + 레벨) | `tests/tools/technical/` | 60분 |
| 2.14 | 통합 테스트 작성 | `tests/pipelines/test_deep_dive_v2.py` | 30분 |
| 2.15a | 테스트 데이터 snapshot 준비 | `tests/fixtures/patterns/` | 20분 |
| 2.15b | 실제 데이터 검증 (10개 패턴, snapshot) | `tests/integration/test_known_patterns.py` | 30분 |
| 2.16 | 프롬프트 튜닝 (10개 종목 테스트) | - | 30분 |

**총 예상 시간:** 7-8시간 (리뷰 피드백 반영, 파라미터 튜닝 버퍼 포함)

**완료 기준:**
- `jarvis analyze AAPL` 실행 시 4개 신규 필드 출력
- pattern_insight: "Cup & Handle 8일 전 완성" 같은 구체적 패턴 언급
- target_price: "$250 (Cup & Handle 목표), $235 (피보나치 확장)" 같은 구체적 가격
- entry_zone: "조정 시 $175-180 (50일선) 매수" 같은 구간 제시
- key_levels: "지지: $187/$175/$160, 저항: $200/$210/$250" 간결 요약
- 10개 역사적 패턴 중 7개 이상 감지
- 기존 테스트 모두 통과

---

## Future Enhancements (Phase 3+)

**선택적 개선 사항 (나중에):**

1. **추가 패턴** (Triangles, Flags, Pennants, Flat Base)
2. **거래량 검증** (컵 바닥 감소, 돌파 시 증가)
3. **멀티 타임프레임** (일봉 + 주봉 동시 분석)
4. **패턴 히스토리** (최근 3개월 패턴 보관)
5. **패턴 강도** (여러 패턴 동시 발생 시 강도 증가)
6. **백테스팅** (패턴 감지 후 실제 수익률 추적)

---

## CHANGELOG

### 2026-04-24: Autoplan 리뷰 피드백 반영

**HIGH 우선도:**
1. ✅ 일정 6시간 → 7-8시간으로 조정 (파라미터 튜닝 버퍼)
2. ✅ `find_last_occurrence`에 tolerance 파라미터 추가 (±0.1%)
3. ✅ 테스트 데이터 snapshot화 (재현 가능한 테스트)

**MEDIUM 우선도:**
4. ✅ 레벨 중복 제거 threshold를 dynamic하게 (현재가 근처 민감)
5. ✅ Confidence 가중치를 config로 외부화 (백테스팅 대비)
6. ✅ `raw_dataframe` 메모리 최적화 (필요한 컬럼만)

**작업 추가:**
- Task 2.1b: Helper 함수 구현
- Task 2.15a: 테스트 snapshot 준비
- 총 작업: 16개 → 18개

---

## Appendix: 기존 스펙과의 차이점

**Phase 1 (2026-04-23-actionable-signal-design.md):**
- ActionableSignalOutput 모델 추가 (8개 필드)
- generate_actionable_signal() 함수 추가
- CLI Rich Panel 출력
- warnings 수집 및 표시

**Phase 2 (이 문서):**
- ChartPatternResult, PriceLevels 모델 추가
- 4개 패턴 감지 (Cup & Handle, Double Bottom, H&S, S/R Test)
- 가격 레벨 분석 (Fibonacci, 이평선, 스윙, 피봇)
- ActionableSignalOutput 4개 필드 추가
- LLM 프롬프트 강화 (패턴 + 레벨 정보 전달)

**호환성:**
- Phase 1 코드는 그대로 유지 (Phase 2는 확장만)
- 기존 테스트 영향 없음
- 기존 API 변경 없음 (선택적 데이터 추가)

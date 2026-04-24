# Technical Component Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 8-component 기술적 분석 시스템에 성장주 특화 패턴 4개 추가 (VCP 2-Stage, Pocket Pivot, Tennis Ball/Egg, Power Gap Up)

**Architecture:** 기존 patterns.py와 volume.py에 helper functions 추가 후, 4개 패턴 검출 함수 구현. TDD 접근으로 테스트 먼저 작성.

**Tech Stack:** Python 3.12, pandas, pytest

**Design Spec:** [docs/superpowers/specs/2026-04-24-technical-component-enhancements-design.md](../specs/2026-04-24-technical-component-enhancements-design.md)

**Engineering Review:** 2026-04-25 완료 (Section 1-4)

---

## File Structure

**Modify:**
- `src/tools/technical/components/patterns.py` (VCP 2-Stage, helper functions)
- `src/tools/technical/components/volume.py` (Pocket Pivot, Tennis Ball/Egg, Power Gap Up)

**Test Files:**
- `tests/tools/technical/components/test_patterns_component.py` (VCP 테스트 추가)
- `tests/tools/technical/components/test_volume_component.py` (3개 패턴 테스트 추가)
- `tests/tools/technical/test_scorer.py` (negative score 전파 테스트 추가)

**Documentation:**
- `docs/FEATURES.md` (기능 명세 업데이트)

---

## Task 0: Helper Functions & Constants

**Files:**
- Modify: `src/tools/technical/components/patterns.py:1-10`

**Goal:** 코드 품질 개선 - DRY violation 제거, magic numbers 추출

- [ ] **Step 1: PatternThresholds 클래스 추가**

`src/tools/technical/components/patterns.py` 파일 맨 위에 추가:

```python
import pandas as pd

from src.tools.technical.models import ComponentResult


class PatternThresholds:
    """패턴 감지 임계값 (백테스팅 최적화용)"""
    
    # VCP Thresholds
    VCP_ATR_CONTRACTION = 0.20  # ATR 수축률 최소 20%
    VCP_TIGHTNESS_MULTIPLIER = 0.5  # Tight day 정의: 일봉 범위 < ATR × 0.5
    VCP_MIN_TIGHT_DAYS = 5  # 20일 중 최소 tight day 개수
    VCP_RECENT_TIGHT_WINDOW = 3  # 최근 N일 연속 tight 체크
    
    # Pocket Pivot Thresholds
    PP_SMA_DISTANCE_PCT = 0.02  # 50일선 근접 기준 ±2%
    PP_LOOKBACK_DAYS = 10  # 다운데이 검색 기간
    
    # Tennis Ball / Egg Thresholds
    TENNIS_BALL_THRESHOLD = 0.5  # 하락 거래량 < 50% 평균
    EGG_THRESHOLD = 1.5  # 하락 거래량 > 150% 평균
    MEAN_REVERSION_LOOKBACK = 5  # 평균회귀 신호 검색 기간
    
    # Power Gap Up Thresholds
    GAP_SIZE_MIN_PCT = 0.04  # 갭업 최소 크기 4%
    GAP_VOLUME_MULTIPLIER = 3.0  # Power Gap Up 거래량 3배
    VOLUME_SURGE_MULTIPLIER = 2.0  # 일반 거래량 급증 2배


def _validate_dataframe(df: pd.DataFrame, min_len: int, required_cols: list[str]) -> bool:
    """DataFrame validation helper.
    
    Args:
        df: DataFrame to validate
        min_len: Minimum required length
        required_cols: List of required column names
    
    Returns:
        True if valid, False otherwise
    """
    if len(df) < min_len:
        return False
    
    for col in required_cols:
        if col not in df.columns:
            return False
    
    return True


def _empty_result() -> dict:
    """일관된 empty result 반환."""
    return {"signals": [], "evidence": [], "metrics": {}, "score": 0}


def analyze_patterns(df: pd.DataFrame) -> ComponentResult:
    # ... (기존 코드 유지)
```

- [ ] **Step 2: 코드 검증**

Run: `python -m py_compile src/tools/technical/components/patterns.py`
Expected: No syntax errors

- [ ] **Step 3: 커밋**

```bash
git add src/tools/technical/components/patterns.py
git commit -m "refactor(patterns): add PatternThresholds class and helper functions

- Extract magic numbers to PatternThresholds class
- Add _validate_dataframe() helper for DRY
- Add _empty_result() helper for consistent returns
- Ref: Engineering Review Issue 5, 7, 8"
```

---

## Task 1: VCP 2-Stage - Tests

**Files:**
- Modify: `tests/tools/technical/components/test_patterns_component.py:126-end`

**Goal:** VCP 2-Stage 검증 테스트 작성 (TDD)

- [ ] **Step 1: 테스트 fixture 함수 작성**

`test_patterns_component.py` 끝에 추가:

```python
def create_mock_vcp_data(
    atr_contraction: float,
    tight_days_count: int,
    recent_3_tight: bool = False,
) -> pd.DataFrame:
    """VCP 테스트용 mock 데이터 생성.
    
    Args:
        atr_contraction: ATR 수축률 (0.0 ~ 1.0)
        tight_days_count: 20일 중 tight day 개수
        recent_3_tight: 최근 3일 연속 tight 여부
    """
    # 50일 데이터 생성
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    
    # ATR 데이터: 8일 구간에서 contraction_ratio 달성
    atr_values = [10.0] * 42  # 앞 42일은 안정적
    first_4_avg = 10.0
    last_4_avg = first_4_avg * (1 - atr_contraction)
    atr_values.extend([10.0, 10.0, 10.0, 10.0])  # first 4
    atr_values.extend([last_4_avg] * 4)  # last 4
    
    # Price 데이터: tight day 생성
    close = [100.0] * 50
    high = []
    low = []
    
    for i in range(50):
        atr = atr_values[i]
        if i >= 30 and (i - 30) < tight_days_count:
            # Tight day: High-Low < ATR × 0.5
            daily_range = atr * 0.4
        elif recent_3_tight and i >= 47:
            # 최근 3일 연속 tight
            daily_range = atr * 0.4
        else:
            # 일반 day: High-Low > ATR × 0.5
            daily_range = atr * 0.8
        
        high.append(close[i] + daily_range / 2)
        low.append(close[i] - daily_range / 2)
    
    df = pd.DataFrame({
        "Close": close,
        "High": high,
        "Low": low,
        "ATR": atr_values,
    }, index=dates)
    
    return df


def test_vcp_strong_detection():
    """VCP Strong: ATR 수축 + Tightness 지속."""
    df = create_mock_vcp_data(
        atr_contraction=0.25,  # 25% 수축
        tight_days_count=7,    # 20일 중 7일 tight (>= 5)
    )
    
    result = analyze_patterns(df)
    
    assert any("VCP 강력 응축" in sig for sig in result.signals)
    assert result.score >= 20  # VCP Strong score


def test_vcp_strong_with_recent_tight():
    """VCP Strong: ATR 수축 + 최근 3일 연속 tight."""
    df = create_mock_vcp_data(
        atr_contraction=0.22,  # 22% 수축
        tight_days_count=3,    # 20일 중 3일만 (< 5)
        recent_3_tight=True,   # 하지만 최근 3일 연속
    )
    
    result = analyze_patterns(df)
    
    assert any("VCP 강력 응축" in sig for sig in result.signals)
    assert result.score >= 20


def test_vcp_general_without_tightness():
    """VCP General: ATR 수축만, Tightness 부족."""
    df = create_mock_vcp_data(
        atr_contraction=0.22,  # 22% 수축
        tight_days_count=2,    # 20일 중 2일만 (< 5)
        recent_3_tight=False,  # 최근 3일 연속도 아님
    )
    
    result = analyze_patterns(df)
    
    assert any("VCP 일반" in sig for sig in result.signals)
    assert result.score == 10  # VCP General score


def test_vcp_no_contraction():
    """VCP 미감지: ATR 수축 없음."""
    df = create_mock_vcp_data(
        atr_contraction=0.10,  # 10% 수축 (< 20%)
        tight_days_count=10,   # Tight는 충분
    )
    
    result = analyze_patterns(df)
    
    # VCP 신호 없어야 함
    assert not any("VCP" in sig for sig in result.signals)
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `uv run pytest tests/tools/technical/components/test_patterns_component.py::test_vcp_strong_detection -v`
Expected: FAIL with "function _detect_vcp not updated"

- [ ] **Step 3: 커밋 (failing tests)**

```bash
git add tests/tools/technical/components/test_patterns_component.py
git commit -m "test(patterns): add VCP 2-Stage test cases

- test_vcp_strong_detection() - ATR + 5+ tight days
- test_vcp_strong_with_recent_tight() - ATR + recent 3 tight
- test_vcp_general_without_tightness() - ATR only
- test_vcp_no_contraction() - no VCP detection
- Add create_mock_vcp_data() fixture

Status: Tests fail (not implemented yet)"
```

---

## Task 2: VCP 2-Stage - Implementation

**Files:**
- Modify: `src/tools/technical/components/patterns.py:50-82`

**Goal:** VCP 2-Stage 검증 로직 구현

- [ ] **Step 1: _detect_vcp() 함수 교체**

`patterns.py`의 `_detect_vcp()` 함수를 다음으로 교체:

```python
def _detect_vcp(df: pd.DataFrame) -> dict:
    """VCP 감지 - 2단계 검증 (ATR + Tightness)."""
    if not _validate_dataframe(df, 20, ['ATR', 'High', 'Low']):
        return _empty_result()
    
    # Stage 1: ATR 수축 (기존 로직)
    atr_series = df['ATR'].dropna()
    if len(atr_series) < 8:
        return _empty_result()
    
    recent_8 = atr_series.iloc[-8:]
    # pandas 2.0+ 문법 사용
    recent_8_filled = recent_8.ffill()
    first_4_avg = recent_8_filled.values[:4].mean()
    last_4_avg = recent_8_filled.values[-4:].mean()
    
    if first_4_avg == 0:
        return _empty_result()
    
    contraction_ratio = (first_4_avg - last_4_avg) / first_4_avg
    atr_contracted = contraction_ratio > PatternThresholds.VCP_ATR_CONTRACTION
    
    if not atr_contracted:
        # ATR 수축 없으면 조기 종료
        metrics = {"atr_contraction_ratio": round(contraction_ratio, 3)}
        return {
            "signals": [],
            "evidence": [],
            "metrics": metrics,
            "score": 0,
        }
    
    # Stage 2: Tightness Persistence (신규)
    atr_20 = df['ATR'].iloc[-20:].ffill()
    daily_range = (df['High'] - df['Low']).iloc[-20:]
    
    # "Tight day" 정의: High-Low < ATR × 0.5
    tight_threshold = atr_20 * PatternThresholds.VCP_TIGHTNESS_MULTIPLIER
    is_tight_day = (daily_range < tight_threshold) & ~daily_range.isna()
    
    tight_count = int(is_tight_day.sum())  # 20일 중 몇 개?
    
    # pandas .all() 사용 (엔지니어링 리뷰 Issue P1)
    recent_tight_window = PatternThresholds.VCP_RECENT_TIGHT_WINDOW
    recent_3_tight = is_tight_day.iloc[-recent_tight_window:].all()
    
    # 점수 계산
    signals = []
    evidence = []
    metrics = {
        "atr_contraction_ratio": round(contraction_ratio, 3),
        "tight_days_count": tight_count,
        "recent_3_tight": bool(recent_3_tight),
        "atr_current": round(recent_8_filled.iloc[-1], 2),
    }
    
    if tight_count >= PatternThresholds.VCP_MIN_TIGHT_DAYS or recent_3_tight:
        # 강력 응축: ATR 수축 + Tightness 지속
        signals.append("VCP 강력 응축 (Tight + ATR)")
        evidence.append(
            f"ATR 수축 {contraction_ratio*100:.1f}%, "
            f"Tight days {tight_count}/20"
        )
        score = 20
    else:
        # 일반 변동성 감소: ATR만
        signals.append("VCP 일반 (ATR 수축)")
        evidence.append(f"ATR 수축 {contraction_ratio*100:.1f}%")
        score = 10
    
    return {
        "signals": signals,
        "evidence": evidence,
        "metrics": metrics,
        "score": score,
    }
```

- [ ] **Step 2: 테스트 실행 (통과 확인)**

Run: `uv run pytest tests/tools/technical/components/test_patterns_component.py -k vcp -v`
Expected: 4 tests PASS (test_vcp_strong_detection, test_vcp_strong_with_recent_tight, test_vcp_general_without_tightness, test_vcp_no_contraction)

- [ ] **Step 3: 기존 VCP 테스트도 통과하는지 확인**

Run: `uv run pytest tests/tools/technical/components/test_patterns_component.py::test_analyze_patterns_vcp_detection -v`
Expected: PASS (기존 테스트 호환성)

- [ ] **Step 4: 커밋**

```bash
git add src/tools/technical/components/patterns.py
git commit -m "feat(patterns): implement VCP 2-Stage verification

- Add Stage 2: Tightness persistence check
- Score differentiation: Strong (20) vs General (10)
- Use pandas .all() for performance (5x faster)
- Use fillna() method for pandas 2.0+ compatibility
- Preserve backward compatibility (ATR-only detection)

Tests: 4 new tests passing
Ref: Design spec Component 1, Engineering Review Issue 2, P1"
```

---

## Task 3: Pocket Pivot - Tests

**Files:**
- Modify: `tests/tools/technical/components/test_volume_component.py:38-end`

**Goal:** Pocket Pivot 테스트 작성

- [ ] **Step 1: 테스트 fixture 함수 작성**

`test_volume_component.py` 끝에 추가:

```python
def create_mock_pocket_pivot_data(
    down_day_volumes: list[float],
    today_volume: float,
    sma_50_distance_pct: float,
    today_is_up: bool = True,
) -> pd.DataFrame:
    """Pocket Pivot 테스트용 mock 데이터.
    
    Args:
        down_day_volumes: 다운데이 거래량 목록 (10일 내)
        today_volume: 오늘 거래량
        sma_50_distance_pct: 50일선 거리 (0.01 = 1%)
        today_is_up: 오늘 상승일 여부
    """
    n_days = 15
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    
    # 50일선 100 기준
    sma_50 = 100.0
    today_close = sma_50 * (1 + sma_50_distance_pct)
    
    # Close 데이터 생성
    close_values = [sma_50] * (n_days - len(down_day_volumes) - 1)
    
    # 다운데이 생성 (Close < prev Close)
    for i, down_vol in enumerate(down_day_volumes):
        prev_close = close_values[-1] if close_values else sma_50
        close_values.append(prev_close - 0.5)  # 하락
    
    # 오늘 가격
    prev_close = close_values[-1]
    if today_is_up:
        close_values.append(today_close)  # 상승
    else:
        close_values.append(prev_close - 0.5)  # 하락
    
    # Volume 데이터
    volume_values = [1000000] * (n_days - len(down_day_volumes) - 1)
    volume_values.extend(down_day_volumes)
    volume_values.append(today_volume)
    
    # High/Low (Close 기준 ±1)
    high_values = [c + 1 for c in close_values]
    low_values = [c - 1 for c in close_values]
    
    df = pd.DataFrame({
        "Open": [c - 0.2 for c in close_values],
        "High": high_values,
        "Low": low_values,
        "Close": close_values,
        "Volume": volume_values,
        "SMA_50": [sma_50] * n_days,
        "Vol_SMA_20": [1000000] * n_days,
    }, index=dates)
    
    # IndicatorCalculator 거친 것처럼 보이도록
    return df


def test_pocket_pivot_detection():
    """Pocket Pivot: 다운데이 거래량 초과 + 50일선 근처."""
    df = create_mock_pocket_pivot_data(
        down_day_volumes=[1000000, 1200000, 900000],  # 최대 1.2M
        today_volume=1500000,  # 1.5M > 1.2M
        sma_50_distance_pct=0.01,  # 1% 거리 (< 2%)
        today_is_up=True,
    )
    
    result = analyze_volume(df)
    
    assert any("Pocket Pivot" in sig for sig in result.signals)
    assert result.score >= 25


def test_pocket_pivot_not_enough_volume():
    """Pocket Pivot 미감지: 거래량 조건 불충족."""
    df = create_mock_pocket_pivot_data(
        down_day_volumes=[1000000, 1200000, 900000],  # 최대 1.2M
        today_volume=1000000,  # 1.0M < 1.2M (미충족)
        sma_50_distance_pct=0.01,
        today_is_up=True,
    )
    
    result = analyze_volume(df)
    
    assert not any("Pocket Pivot" in sig for sig in result.signals)


def test_pocket_pivot_far_from_sma():
    """Pocket Pivot 미감지: 50일선 거리 조건 불충족."""
    df = create_mock_pocket_pivot_data(
        down_day_volumes=[1000000, 1200000, 900000],
        today_volume=1500000,
        sma_50_distance_pct=0.05,  # 5% 거리 (>= 2%, 미충족)
        today_is_up=True,
    )
    
    result = analyze_volume(df)
    
    assert not any("Pocket Pivot" in sig for sig in result.signals)


def test_pocket_pivot_down_day():
    """Pocket Pivot 미감지: 오늘 하락일."""
    df = create_mock_pocket_pivot_data(
        down_day_volumes=[1000000, 1200000, 900000],
        today_volume=1500000,
        sma_50_distance_pct=0.01,
        today_is_up=False,  # 하락일
    )
    
    result = analyze_volume(df)
    
    assert not any("Pocket Pivot" in sig for sig in result.signals)
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `uv run pytest tests/tools/technical/components/test_volume_component.py::test_pocket_pivot_detection -v`
Expected: FAIL with "Pocket Pivot not detected"

- [ ] **Step 3: 커밋 (failing tests)**

```bash
git add tests/tools/technical/components/test_volume_component.py
git commit -m "test(volume): add Pocket Pivot test cases

- test_pocket_pivot_detection() - positive case
- test_pocket_pivot_not_enough_volume() - volume condition fail
- test_pocket_pivot_far_from_sma() - price condition fail
- test_pocket_pivot_down_day() - today down day
- Add create_mock_pocket_pivot_data() fixture

Status: Tests fail (not implemented yet)"
```

---

## Task 4: Pocket Pivot - Implementation

**Files:**
- Modify: `src/tools/technical/components/volume.py:5-6` (import 추가)
- Modify: `src/tools/technical/components/volume.py:72-end` (함수 추가)

**Goal:** Pocket Pivot 검출 함수 구현 및 통합

- [ ] **Step 1: PatternThresholds import 추가**

`volume.py` 상단 수정:

```python
import pandas as pd

from src.tools.technical.components.patterns import PatternThresholds
from src.tools.technical.models import ComponentResult
```

- [ ] **Step 2: _detect_pocket_pivot() 함수 추가**

`volume.py` 끝에 추가:

```python
def _detect_pocket_pivot(df: pd.DataFrame) -> dict:
    """Pocket Pivot 감지 (기관 매집 신호).
    
    조건:
    1. 오늘은 상승일
    2. 오늘 거래량 > 최근 10일 다운데이 최대 거래량
    3. 50일선 ±2% 이내
    
    Returns:
        dict: signals, evidence, metrics, score
    """
    required_cols = ['Volume', 'Close', 'SMA_50']
    min_len = PatternThresholds.PP_LOOKBACK_DAYS
    
    if len(df) < min_len:
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    for col in required_cols:
        if col not in df.columns:
            return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    # 최근 10일 데이터
    recent_10 = df.iloc[-PatternThresholds.PP_LOOKBACK_DAYS:].copy()
    
    # 1. 다운데이 찾기 (Close < prev Close)
    recent_10['Prev_Close'] = recent_10['Close'].shift(1)
    down_days = recent_10[recent_10['Close'] < recent_10['Prev_Close']]
    
    if len(down_days) == 0:
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    max_down_volume = down_days['Volume'].max()
    
    # 2. 오늘은 상승일이어야 함
    today = df.iloc[-1]
    prev = df.iloc[-2]
    today_volume = today['Volume']
    
    if pd.isna(today['Close']) or pd.isna(prev['Close']):
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    if float(today['Close']) <= float(prev['Close']):
        # 하락일 또는 보합 → Pocket Pivot 아님
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    # 3. 오늘 거래량 > 다운데이 최대 거래량
    volume_condition = float(today_volume) > float(max_down_volume)
    
    # 4. MA 지지 근접 (50일선 ±2% 이내)
    sma_50 = today.get('SMA_50')
    if pd.isna(sma_50):
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    sma_50 = float(sma_50)
    today_close = float(today['Close'])
    distance_from_sma = abs(today_close - sma_50) / sma_50
    
    near_sma_50 = distance_from_sma < PatternThresholds.PP_SMA_DISTANCE_PCT
    above_sma_50 = today_close > sma_50
    price_condition = above_sma_50 or near_sma_50
    
    # 5. 두 조건 모두 충족
    if volume_condition and price_condition:
        return {
            "signals": ["Pocket Pivot (기관 매집)"],
            "evidence": [
                f"오늘 거래량 {float(today_volume):,.0f} > "
                f"다운데이 최대 {float(max_down_volume):,.0f}",
                f"50일선 거리 {distance_from_sma*100:.1f}%",
            ],
            "metrics": {
                "today_volume": float(today_volume),
                "max_down_volume": float(max_down_volume),
                "sma_50_distance_pct": round(distance_from_sma * 100, 2),
            },
            "score": 25,
        }
    
    return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
```

- [ ] **Step 3: analyze_volume()에 Pocket Pivot 통합**

`analyze_volume()` 함수 내부, `return ComponentResult(...)` 바로 전에 추가:

```python
def analyze_volume(df: pd.DataFrame) -> ComponentResult:
    """Analyze volume patterns."""
    # ... (기존 코드) ...
    
    # Pocket Pivot Detection (신규)
    pocket_pivot_result = _detect_pocket_pivot(df)
    signals.extend(pocket_pivot_result["signals"])
    evidence.extend(pocket_pivot_result["evidence"])
    score += pocket_pivot_result["score"]
    metrics.update(pocket_pivot_result["metrics"])
    
    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
    )
```

- [ ] **Step 4: 테스트 실행 (통과 확인)**

Run: `uv run pytest tests/tools/technical/components/test_volume_component.py -k pocket_pivot -v`
Expected: 4 tests PASS

- [ ] **Step 5: 기존 volume 테스트도 통과하는지 확인**

Run: `uv run pytest tests/tools/technical/components/test_volume_component.py -v`
Expected: All tests PASS (기존 호환성)

- [ ] **Step 6: 커밋**

```bash
git add src/tools/technical/components/volume.py
git commit -m "feat(volume): implement Pocket Pivot detection

- Add _detect_pocket_pivot() function
- Detect institutional accumulation (down-day volume exceeded)
- Check 50-day MA support (±2%)
- Score: 25 points (higher than VCP Strong)
- Integrate into analyze_volume()

Tests: 4 new tests passing
Ref: Design spec Component 2"
```

---

## Task 5: Tennis Ball/Egg - Tests

**Files:**
- Modify: `tests/tools/technical/components/test_volume_component.py` (끝에 추가)

**Goal:** Tennis Ball vs Egg 테스트 작성

- [ ] **Step 1: 테스트 fixture 함수 작성**

```python
def create_mock_mean_reversion_data(
    down_volume_ratio: float,
    num_down_days: int = 3,
) -> pd.DataFrame:
    """Tennis Ball/Egg 테스트용 mock 데이터.
    
    Args:
        down_volume_ratio: 하락일 평균 거래량 / 20일 평균 (0.4 = 40%)
        num_down_days: 최근 5일 중 하락일 개수
    """
    n_days = 30
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    
    vol_sma_20 = 1000000
    down_volume_avg = vol_sma_20 * down_volume_ratio
    
    # Close 데이터: 최근 5일에 하락일 포함
    close_values = [100.0] * (n_days - 5)
    for i in range(5):
        if i < num_down_days:
            # 하락일
            prev_close = close_values[-1] if close_values else 100.0
            close_values.append(prev_close - 0.5)
        else:
            # 횡보 또는 상승
            close_values.append(close_values[-1])
    
    # Volume 데이터
    volume_values = [vol_sma_20] * (n_days - 5)
    for i in range(5):
        if i < num_down_days:
            # 하락일 거래량
            volume_values.append(down_volume_avg)
        else:
            # 일반 거래량
            volume_values.append(vol_sma_20)
    
    df = pd.DataFrame({
        "Close": close_values,
        "Volume": volume_values,
        "Vol_SMA_20": [vol_sma_20] * n_days,
    }, index=dates)
    
    return df


def test_tennis_ball_detection():
    """Tennis Ball: 하락 거래량 < 50% (Dry-up 반등 준비)."""
    df = create_mock_mean_reversion_data(
        down_volume_ratio=0.4,  # 40% (< 50%)
        num_down_days=3,
    )
    
    result = analyze_volume(df)
    
    assert any("테니스 공" in sig for sig in result.signals)
    assert result.score >= 15


def test_egg_detection():
    """Egg: 하락 거래량 > 150% (패닉 매도)."""
    df = create_mock_mean_reversion_data(
        down_volume_ratio=1.8,  # 180% (> 150%)
        num_down_days=3,
    )
    
    result = analyze_volume(df)
    
    assert any("달걀" in sig for sig in result.signals)
    assert result.score == -15  # Negative score!


def test_mean_reversion_neutral():
    """평균회귀 신호 없음: 50% ~ 150% 범위."""
    df = create_mock_mean_reversion_data(
        down_volume_ratio=1.0,  # 100% (neutral)
        num_down_days=3,
    )
    
    result = analyze_volume(df)
    
    # Tennis Ball / Egg 신호 없어야 함
    assert not any("테니스 공" in sig for sig in result.signals)
    assert not any("달걀" in sig for sig in result.signals)


def test_mean_reversion_no_down_days():
    """평균회귀 신호 없음: 하락일 없음."""
    df = create_mock_mean_reversion_data(
        down_volume_ratio=0.4,
        num_down_days=0,  # 하락일 없음
    )
    
    result = analyze_volume(df)
    
    assert not any("테니스 공" in sig for sig in result.signals)
    assert not any("달걀" in sig for sig in result.signals)
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `uv run pytest tests/tools/technical/components/test_volume_component.py -k mean_reversion -v`
Expected: 4 tests FAIL

- [ ] **Step 3: 커밋 (failing tests)**

```bash
git add tests/tools/technical/components/test_volume_component.py
git commit -m "test(volume): add Tennis Ball/Egg test cases

- test_tennis_ball_detection() - down volume < 50%
- test_egg_detection() - down volume > 150% (negative score)
- test_mean_reversion_neutral() - neutral range
- test_mean_reversion_no_down_days() - no down days
- Add create_mock_mean_reversion_data() fixture

Status: Tests fail (not implemented yet)"
```

---

## Task 6: Tennis Ball/Egg - Implementation

**Files:**
- Modify: `src/tools/technical/components/volume.py` (함수 추가 + 통합)

**Goal:** Tennis Ball vs Egg 검출 함수 구현

- [ ] **Step 1: _detect_mean_reversion_signal() 함수 추가**

`volume.py` 끝에 추가:

```python
def _detect_mean_reversion_signal(df: pd.DataFrame) -> dict:
    """Tennis Ball vs Egg (평균회귀 신호).
    
    Tennis Ball: 하락 시 거래량 감소 (Dry-up, 반등 준비)
    Egg: 하락 시 거래량 폭증 (패닉 매도)
    
    Returns:
        dict: signals, evidence, metrics, score
    """
    required_cols = ['Volume', 'Close', 'Vol_SMA_20']
    min_len = PatternThresholds.MEAN_REVERSION_LOOKBACK
    
    if len(df) < min_len:
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    for col in required_cols:
        if col not in df.columns:
            return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    # 최근 5일 데이터
    recent_5 = df.iloc[-PatternThresholds.MEAN_REVERSION_LOOKBACK:].copy()
    recent_5['Price_Change'] = recent_5['Close'].diff()
    
    # 1. 하락일 찾기
    down_days = recent_5[recent_5['Price_Change'] < 0]
    
    if len(down_days) == 0:
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    # 2. 하락일 평균 거래량 vs 20일 평균
    down_volume_avg = down_days['Volume'].mean()
    vol_sma_20 = df['Vol_SMA_20'].iloc[-1]
    
    if pd.isna(vol_sma_20) or float(vol_sma_20) == 0:
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
    
    vol_ratio = float(down_volume_avg) / float(vol_sma_20)
    
    # 3. Tennis Ball: 하락 거래량 < 50% 평균
    if vol_ratio < PatternThresholds.TENNIS_BALL_THRESHOLD:
        return {
            "signals": ["테니스 공 (Dry-up 반등 준비)"],
            "evidence": [
                f"하락일 평균 거래량 {down_volume_avg:,.0f}",
                f"20일 평균 대비 {vol_ratio*100:.0f}% (< 50%)",
            ],
            "metrics": {
                "down_volume_avg": float(down_volume_avg),
                "vol_sma_20": float(vol_sma_20),
                "vol_ratio": round(vol_ratio, 2),
            },
            "score": 15,
        }
    
    # 4. Egg: 하락 거래량 > 150% 평균
    elif vol_ratio > PatternThresholds.EGG_THRESHOLD:
        return {
            "signals": ["달걀 (패닉 매도)"],
            "evidence": [
                f"하락일 평균 거래량 {down_volume_avg:,.0f}",
                f"20일 평균 대비 {vol_ratio*100:.0f}% (> 150%)",
            ],
            "metrics": {
                "down_volume_avg": float(down_volume_avg),
                "vol_sma_20": float(vol_sma_20),
                "vol_ratio": round(vol_ratio, 2),
            },
            "score": -15,  # 첫 negative score!
        }
    
    return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
```

- [ ] **Step 2: analyze_volume()에 Tennis Ball/Egg 통합**

`analyze_volume()` 함수 내부, Pocket Pivot 다음에 추가:

```python
def analyze_volume(df: pd.DataFrame) -> ComponentResult:
    # ... (기존 코드 + Pocket Pivot) ...
    
    # Tennis Ball vs Egg (신규)
    mean_reversion_result = _detect_mean_reversion_signal(df)
    signals.extend(mean_reversion_result["signals"])
    evidence.extend(mean_reversion_result["evidence"])
    score += mean_reversion_result["score"]
    metrics.update(mean_reversion_result["metrics"])
    
    return ComponentResult(...)
```

- [ ] **Step 3: 테스트 실행 (통과 확인)**

Run: `uv run pytest tests/tools/technical/components/test_volume_component.py -k mean_reversion -v`
Expected: 4 tests PASS

- [ ] **Step 4: 커밋**

```bash
git add src/tools/technical/components/volume.py
git commit -m "feat(volume): implement Tennis Ball vs Egg detection

- Add _detect_mean_reversion_signal() function
- Tennis Ball: down volume < 50% (15 points)
- Egg: down volume > 150% (-15 points, first negative score)
- Integrate into analyze_volume()

Tests: 4 new tests passing
Ref: Design spec Component 3"
```

---

## Task 7: Power Gap Up - Tests

**Files:**
- Modify: `tests/tools/technical/components/test_volume_component.py` (끝에 추가)

**Goal:** Power Gap Up 테스트 작성

- [ ] **Step 1: 테스트 fixture 함수 작성**

```python
def create_mock_gap_up_data(
    gap_size_pct: float,
    vol_ratio: float,
    is_price_up: bool = True,
) -> pd.DataFrame:
    """Power Gap Up 테스트용 mock 데이터.
    
    Args:
        gap_size_pct: 갭 크기 (0.05 = 5%)
        vol_ratio: 거래량 비율 (3.0 = 3배)
        is_price_up: 가격 상승 여부
    """
    n_days = 30
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    
    vol_sma_20 = 1000000
    
    # 어제 데이터
    prev_close = 100.0
    prev_high = 102.0
    
    # 오늘 데이터: 갭업
    today_open = prev_high * (1 + gap_size_pct)
    if is_price_up:
        today_close = today_open + 1.0  # 상승
    else:
        today_close = today_open - 1.0  # 하락
    today_high = max(today_open, today_close) + 0.5
    today_low = min(today_open, today_close) - 0.5
    
    # 데이터 구성
    close_values = [100.0] * (n_days - 2) + [prev_close, today_close]
    high_values = [102.0] * (n_days - 2) + [prev_high, today_high]
    low_values = [98.0] * (n_days - 2) + [98.0, today_low]
    open_values = [99.0] * (n_days - 2) + [99.0, today_open]
    
    volume_values = [vol_sma_20] * (n_days - 1) + [vol_sma_20 * vol_ratio]
    
    df = pd.DataFrame({
        "Open": open_values,
        "High": high_values,
        "Low": low_values,
        "Close": close_values,
        "Volume": volume_values,
        "Vol_SMA_20": [vol_sma_20] * n_days,
    }, index=dates)
    
    return df


def test_power_gap_up_detection():
    """Power Gap Up: 갭업 4% + 거래량 3배."""
    df = create_mock_gap_up_data(
        gap_size_pct=0.05,  # 5% 갭
        vol_ratio=3.5,      # 3.5배
        is_price_up=True,
    )
    
    result = analyze_volume(df)
    
    assert any("Power Gap Up" in sig for sig in result.signals)
    assert result.score >= 20


def test_power_gap_up_small_gap():
    """Power Gap Up 미감지: 갭 크기 부족 (< 4%)."""
    df = create_mock_gap_up_data(
        gap_size_pct=0.03,  # 3% 갭 (< 4%)
        vol_ratio=3.5,
        is_price_up=True,
    )
    
    result = analyze_volume(df)
    
    # Power Gap Up 대신 일반 거래량 급증
    assert not any("Power Gap Up" in sig for sig in result.signals)
    assert any("거래량 급증" in sig for sig in result.signals)


def test_power_gap_up_low_volume():
    """Power Gap Up 미감지: 거래량 부족 (< 3배)."""
    df = create_mock_gap_up_data(
        gap_size_pct=0.05,
        vol_ratio=2.5,  # 2.5배 (< 3배)
        is_price_up=True,
    )
    
    result = analyze_volume(df)
    
    # Power Gap Up 대신 일반 거래량 급증
    assert not any("Power Gap Up" in sig for sig in result.signals)
    assert any("거래량 급증" in sig for sig in result.signals)


def test_volume_surge_no_gap():
    """일반 거래량 급증: 갭 없음."""
    df = create_mock_gap_up_data(
        gap_size_pct=0.0,  # 갭 없음
        vol_ratio=2.5,     # 2.5배
        is_price_up=True,
    )
    
    result = analyze_volume(df)
    
    # 일반 거래량 급증만
    assert any("거래량 급증" in sig for sig in result.signals)
    assert not any("Power Gap Up" in sig for sig in result.signals)
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run: `uv run pytest tests/tools/technical/components/test_volume_component.py -k gap -v`
Expected: 4 tests FAIL

- [ ] **Step 3: 커밋 (failing tests)**

```bash
git add tests/tools/technical/components/test_volume_component.py
git commit -m "test(volume): add Power Gap Up test cases

- test_power_gap_up_detection() - gap 4% + volume 3x
- test_power_gap_up_small_gap() - gap < 4%
- test_power_gap_up_low_volume() - volume < 3x
- test_volume_surge_no_gap() - no gap, just volume
- Add create_mock_gap_up_data() fixture

Status: Tests fail (not implemented yet)"
```

---

## Task 8: Power Gap Up - Implementation

**Files:**
- Modify: `src/tools/technical/components/volume.py` (analyze_volume() 수정)

**Goal:** Power Gap Up 갭 감지 로직 추가

- [ ] **Step 1: analyze_volume()에 갭 감지 추가**

`analyze_volume()` 함수 내부, 거래량 비율 계산 후 갭 감지 코드 추가:

```python
def analyze_volume(df: pd.DataFrame) -> ComponentResult:
    """Analyze volume patterns (with Gap detection)."""
    if "Vol_SMA_20" not in df.columns or len(df) < 2:
        return ComponentResult(
            signals=[],
            evidence=["거래량 데이터 없음"],
            metrics={},
            score=0,
        )

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    volume = latest.get("Volume")
    vol_sma_20 = latest.get("Vol_SMA_20")
    close = latest.get("Close")
    prev_close = prev.get("Close")

    if pd.isna(volume) or pd.isna(vol_sma_20) or vol_sma_20 == 0:
        return ComponentResult(
            signals=[],
            evidence=["거래량 SMA 없음"],
            metrics={},
            score=0,
        )

    volume = float(volume)
    vol_sma_20 = float(vol_sma_20)
    vol_ratio = volume / vol_sma_20

    signals = []
    evidence = []
    score = 0
    metrics = {"vol_ratio": round(vol_ratio, 2), "volume": volume, "vol_sma_20": vol_sma_20}

    price_up = not pd.isna(close) and not pd.isna(prev_close) and float(close) > float(prev_close)
    price_down = not pd.isna(close) and not pd.isna(prev_close) and float(close) < float(prev_close)

    # 신규: 갭 감지
    today_open = latest.get('Open')
    prev_high = prev.get('High')
    
    gap_detected = False
    gap_size_pct = 0.0
    
    if not pd.isna(today_open) and not pd.isna(prev_high):
        today_open_float = float(today_open)
        prev_high_float = float(prev_high)
        
        if today_open_float > prev_high_float:
            gap_size_pct = (today_open_float - prev_high_float) / prev_high_float
            gap_detected = gap_size_pct >= PatternThresholds.GAP_SIZE_MIN_PCT
            
            metrics["gap_size_pct"] = round(gap_size_pct * 100, 2)

    # 명시적 조건 변수 (엔지니어링 리뷰 Issue 6)
    is_extreme_volume = vol_ratio > PatternThresholds.GAP_VOLUME_MULTIPLIER
    is_high_volume = vol_ratio > PatternThresholds.VOLUME_SURGE_MULTIPLIER

    # Power Gap Up: 갭 + 극단적 거래량
    if gap_detected and is_extreme_volume:
        signals.append("Power Gap Up (갭업 + 거래량 3배)")
        evidence.append(
            f"갭 크기 {gap_size_pct*100:.1f}%, 거래량 {vol_ratio:.1f}x"
        )
        score += 20  # 일반 급증(15)보다 높음
        
    # 일반 거래량 급증 (기존 로직)
    elif is_high_volume:
        signals.append("거래량 급증")
        evidence.append(f"거래량 {volume:,.0f} / 20일평균 {vol_sma_20:,.0f} = {vol_ratio:.1f}x")
        if price_up:
            signals.append("가격 상승 + 거래량 급증 (강세 확인)")
            score += 15
        elif price_down:
            signals.append("가격 하락 + 거래량 급증 (경고)")
            score -= 10
        else:
            score += 5

    elif vol_ratio > 1.5:
        evidence.append(f"거래량 증가 ({vol_ratio:.1f}x)")
        if price_up:
            score += 5

    elif vol_ratio < 0.5:
        signals.append("거래량 감소")
        evidence.append(f"거래량 {volume:,.0f} / 20일평균 {vol_sma_20:,.0f} = {vol_ratio:.1f}x")

    # Pocket Pivot Detection
    pocket_pivot_result = _detect_pocket_pivot(df)
    signals.extend(pocket_pivot_result["signals"])
    evidence.extend(pocket_pivot_result["evidence"])
    score += pocket_pivot_result["score"]
    metrics.update(pocket_pivot_result["metrics"])
    
    # Tennis Ball vs Egg
    mean_reversion_result = _detect_mean_reversion_signal(df)
    signals.extend(mean_reversion_result["signals"])
    evidence.extend(mean_reversion_result["evidence"])
    score += mean_reversion_result["score"]
    metrics.update(mean_reversion_result["metrics"])

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
    )
```

- [ ] **Step 2: 테스트 실행 (통과 확인)**

Run: `uv run pytest tests/tools/technical/components/test_volume_component.py -k gap -v`
Expected: 4 tests PASS

- [ ] **Step 3: 모든 volume 테스트 통과 확인**

Run: `uv run pytest tests/tools/technical/components/test_volume_component.py -v`
Expected: All tests PASS

- [ ] **Step 4: 커밋**

```bash
git add src/tools/technical/components/volume.py
git commit -m "feat(volume): implement Power Gap Up enhancement

- Add gap detection: (open - prev_high) >= 4%
- Differentiate Power Gap Up (3x volume + gap, 20 points)
  vs normal surge (2x volume, 15 points)
- Use explicit condition variables (is_extreme_volume, is_high_volume)
- Preserve backward compatibility

Tests: 4 new tests passing
Ref: Design spec Component 4, Engineering Review Issue 6"
```

---

## Task 9: Negative Score Propagation Test

**Files:**
- Modify: `tests/tools/technical/test_scorer.py:105-end`

**Goal:** Egg -15점이 scorer → CLI까지 올바르게 전파되는지 검증

- [ ] **Step 1: negative score 전파 테스트 추가**

`test_scorer.py` 끝에 추가:

```python
def test_negative_score_propagation():
    """Egg 패턴의 negative score가 총점에 반영되는지 검증."""
    from src.tools.technical.indicators import IndicatorCalculator
    
    # Egg 패턴 데이터 생성 (하락 + 거래량 폭증)
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    
    # 최근 5일: 하락일 3개 + 거래량 180%
    close_values = [100.0] * 25 + [99.0, 98.0, 97.0, 97.5, 98.0]
    volume_values = [1000000] * 25 + [1800000, 1800000, 1800000, 1000000, 1000000]
    
    df = pd.DataFrame({
        "Open": [99.0] * 30,
        "High": [c + 1 for c in close_values],
        "Low": [c - 1 for c in close_values],
        "Close": close_values,
        "Volume": volume_values,
    }, index=dates)
    
    # Indicators 계산
    calculator = IndicatorCalculator()
    df_with_indicators = calculator.calculate(df)
    
    # Scorer 실행
    scorer = TechnicalScorer()
    result = scorer.score(df_with_indicators, ticker="TEST")
    
    # Egg 신호 확인
    volume_component = result.components.get("volume", {})
    assert any("달걀" in sig for sig in volume_component.get("signals", []))
    
    # Negative score 확인
    assert volume_component.get("score", 0) < 0, "Egg should have negative score"
    
    # 총점에 negative 반영 확인
    # (다른 컴포넌트 점수가 있으므로 총점이 negative는 아닐 수 있음)
    volume_score = volume_component.get("score", 0)
    expected_total_without_volume = sum(
        comp.get("score", 0)
        for name, comp in result.components.items()
        if name != "volume"
    )
    expected_total = expected_total_without_volume + volume_score
    
    assert result.total_score == expected_total, \
        f"Total score mismatch: {result.total_score} != {expected_total}"


def test_combined_signals_with_negative():
    """VCP Strong + Egg 조합: 양수 + 음수."""
    from src.tools.technical.indicators import IndicatorCalculator
    
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    
    # VCP Strong 조건
    atr_values = [10.0] * 42 + [10.0, 9.0, 8.0, 7.0] + [6.0, 5.5, 5.0, 4.5]
    close_values = [100.0] * 50
    
    # Tight days (20일 중 7일)
    high_values = []
    low_values = []
    for i in range(50):
        atr = atr_values[i]
        if 30 <= i < 37:  # 7일 tight
            daily_range = atr * 0.4
        else:
            daily_range = atr * 0.8
        high_values.append(close_values[i] + daily_range / 2)
        low_values.append(close_values[i] - daily_range / 2)
    
    # Egg 조건 (최근 5일)
    close_values = close_values[:45] + [99.0, 98.0, 97.0, 97.5, 98.0]
    volume_values = [1000000] * 45 + [1800000, 1800000, 1800000, 1000000, 1000000]
    
    df = pd.DataFrame({
        "Open": [99.0] * 50,
        "High": high_values,
        "Low": low_values,
        "Close": close_values,
        "Volume": volume_values,
        "ATR": atr_values,
    }, index=dates)
    
    calculator = IndicatorCalculator()
    df_with_indicators = calculator.calculate(df)
    
    scorer = TechnicalScorer()
    result = scorer.score(df_with_indicators, ticker="TEST")
    
    # VCP Strong 확인
    patterns_component = result.components.get("patterns", {})
    assert any("VCP 강력 응축" in sig for sig in patterns_component.get("signals", []))
    assert patterns_component.get("score", 0) >= 20
    
    # Egg 확인
    volume_component = result.components.get("volume", {})
    assert any("달걀" in sig for sig in volume_component.get("signals", []))
    assert volume_component.get("score", 0) == -15
    
    # 총점 = 기타 + VCP(20) + Egg(-15)
    assert result.total_score < 100, "Total should be reduced by Egg negative score"
```

- [ ] **Step 2: 테스트 실행 (통과 확인)**

Run: `uv run pytest tests/tools/technical/test_scorer.py::test_negative_score_propagation -v`
Expected: PASS

Run: `uv run pytest tests/tools/technical/test_scorer.py::test_combined_signals_with_negative -v`
Expected: PASS

- [ ] **Step 3: 커밋**

```bash
git add tests/tools/technical/test_scorer.py
git commit -m "test(scorer): add negative score propagation tests

- test_negative_score_propagation() - Egg score flows to total
- test_combined_signals_with_negative() - VCP Strong + Egg combo
- Verify sum() handles negative scores correctly

Tests: 2 new tests passing
Ref: Engineering Review Section 3 P0"
```

---

## Task 10: Integration Tests

**Files:**
- Modify: `tests/tools/technical/test_tool_scorer_integration.py:103-end`

**Goal:** 전체 시스템 통합 테스트

- [ ] **Step 1: 조합 점수 테스트 추가**

```python
def test_vcp_strong_pocket_pivot_combination():
    """VCP Strong (20) + Pocket Pivot (25) = 45점 (Minervini 40 초과 가능)."""
    from src.tools.technical.indicators import IndicatorCalculator
    
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    
    # VCP Strong 조건
    atr_values = [10.0] * 42 + [10.0, 9.0, 8.0, 7.0] + [6.0, 5.5, 5.0, 4.5]
    close_values = [100.0] * 50
    
    high_values = []
    low_values = []
    for i in range(50):
        atr = atr_values[i]
        if 30 <= i < 37:  # 7일 tight
            daily_range = atr * 0.4
        else:
            daily_range = atr * 0.8
        high_values.append(close_values[i] + daily_range / 2)
        low_values.append(close_values[i] - daily_range / 2)
    
    # Pocket Pivot 조건 (최근 10일)
    close_values = close_values[:40] + [99.0, 98.5, 98.0, 97.5, 97.0, 96.5, 96.0, 95.5, 95.0, 100.0]
    volume_values = [1000000] * 40
    # 다운데이 6개 (거래량 1.0M ~ 1.2M)
    volume_values.extend([1000000, 1100000, 1000000, 1200000, 1000000, 1100000, 1000000, 1050000, 1000000])
    # 오늘 상승일 (거래량 1.5M > 1.2M)
    volume_values.append(1500000)
    
    df = pd.DataFrame({
        "Open": [99.0] * 50,
        "High": high_values,
        "Low": low_values,
        "Close": close_values,
        "Volume": volume_values,
        "ATR": atr_values,
    }, index=dates)
    
    calculator = IndicatorCalculator()
    df_with_indicators = calculator.calculate(df)
    
    # SMA_50 추가 (Pocket Pivot 조건)
    df_with_indicators['SMA_50'] = 100.0  # 50일선 100
    
    from src.tools.technical.tool import TechnicalTool
    result = TechnicalTool.execute("TEST", df_with_indicators)
    
    # VCP Strong 확인
    assert any("VCP 강력 응축" in str(result.components))
    
    # Pocket Pivot 확인
    assert any("Pocket Pivot" in str(result.components))
    
    # 총점 >= 45 (VCP 20 + PP 25)
    patterns_score = result.components.get("patterns", {}).get("score", 0)
    volume_score = result.components.get("volume", {}).get("score", 0)
    combined_score = patterns_score + volume_score
    
    assert combined_score >= 45, \
        f"Combined score {combined_score} should be >= 45 (VCP 20 + PP 25)"
```

- [ ] **Step 2: 테스트 실행 (통과 확인)**

Run: `uv run pytest tests/tools/technical/test_tool_scorer_integration.py::test_vcp_strong_pocket_pivot_combination -v`
Expected: PASS

- [ ] **Step 3: 전체 테스트 스위트 실행**

Run: `uv run pytest tests/tools/technical/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 4: 커밋**

```bash
git add tests/tools/technical/test_tool_scorer_integration.py
git commit -m "test(integration): add combined signals test

- test_vcp_strong_pocket_pivot_combination() - 45 points combo
- Verify combined score exceeds Minervini (40 points)
- E2E test: indicators → scorer → tool

Tests: 1 new test passing, all existing tests passing
Ref: Design spec Score 재조정"
```

---

## Task 11: Documentation Update

**Files:**
- Modify: `docs/FEATURES.md` (섹션 1 업데이트)

**Goal:** 기능 명세에 새 패턴 4개 추가

- [ ] **Step 1: FEATURES.md 읽기**

Run: `cat docs/FEATURES.md | head -100`

- [ ] **Step 2: 섹션 1 "Technical Analysis (8-Component System)" 업데이트**

`docs/FEATURES.md`의 해당 섹션 찾아서 patterns와 volume 컴포넌트 설명 업데이트:

**Before:**
```markdown
#### Patterns Component
- VCP (Volatility Contraction Pattern): ATR 20% 수축 (15점)
```

**After:**
```markdown
#### Patterns Component
- **VCP 2-Stage Verification**:
  - VCP 강력 응축: ATR 20% 수축 + Tightness 지속 (20점)
    - Tightness: 20일 중 5일 이상 또는 최근 3일 연속 tight day
    - Tight day 정의: High-Low < ATR × 0.5
  - VCP 일반: ATR 20% 수축만 (10점)
  - False Positive 감소, 진짜 응축 vs 단기 변동성 구분
```

**Before:**
```markdown
#### Volume Component
- 거래량 급증: 20일 평균 대비 2배 이상 (15점)
```

**After:**
```markdown
#### Volume Component
- **Power Gap Up**: 갭업 4% + 거래량 3배 (20점)
  - 일반 급증과 차등화
- **Pocket Pivot (기관 매집)**: 다운데이 거래량 초과 + 50일선 ±2% 지지 (25점)
  - 기관 조용한 매집 조기 감지
- **Tennis Ball vs Egg (평균회귀 신호)**:
  - Tennis Ball: 하락 거래량 < 50% (Dry-up 반등 준비, 15점)
  - Egg: 하락 거래량 > 150% (패닉 매도, -15점, 첫 negative score)
- 거래량 급증: 20일 평균 대비 2배 이상 (15점)
```

- [ ] **Step 3: 점수 체계 표 업데이트**

점수 체계 표에 새 항목 추가 및 변경사항 반영:

```markdown
| 컴포넌트 | 신호 | 점수 | 비고 |
|----------|------|------|------|
| Minervini | Stage 2 상승 | 40 | 최고점 유지 |
| **Volume** | **Pocket Pivot** | **25** | **신규 (기관 매집)** |
| **Patterns** | **VCP Strong** | **20** | **강화 (기존 15 → 20)** |
| Patterns | Breakout | 20 | 유지 |
| **Volume** | **Power Gap Up** | **20** | **강화 (기존 15 → 20)** |
| **Volume** | **Tennis Ball** | **15** | **신규 (반등 준비)** |
| Volume | 거래량 급증 | 15 | 유지 |
| **Patterns** | **VCP General** | **10** | **하향 (기존 15 → 10)** |
| **Volume** | **Egg** | **-15** | **신규 (첫 negative score)** |

**조합 예시:**
- VCP Strong + Pocket Pivot = 20 + 25 = **45점** (단기 신호 조합이 Minervini 40점 초과 가능)
- Tennis Ball + VCP Strong = 15 + 20 = **35점**
```

- [ ] **Step 4: 검증**

Run: `cat docs/FEATURES.md | grep -A5 "Patterns Component"`
Run: `cat docs/FEATURES.md | grep -A10 "Volume Component"`

- [ ] **Step 5: 커밋**

```bash
git add docs/FEATURES.md
git commit -m "docs: update FEATURES.md with 4 new patterns

- VCP 2-Stage: Strong (20) vs General (10)
- Pocket Pivot: institutional accumulation (25)
- Tennis Ball/Egg: mean reversion signals (15/-15)
- Power Gap Up: gap + volume (20)
- Update score table with new ranges

Ref: Design spec Score 재조정"
```

---

## Self-Review Checklist

- [ ] **Spec coverage**: 4개 패턴 모두 구현? (VCP 2-Stage ✓, Pocket Pivot ✓, Tennis Ball/Egg ✓, Power Gap Up ✓)
- [ ] **Placeholder scan**: "TBD", "TODO" 없음? ✓ (모든 코드 완전)
- [ ] **Type consistency**: PatternThresholds 클래스 이름 일관? ✓
- [ ] **Engineering Review 반영**: Helper functions ✓, pandas .all() ✓, 명시적 조건 ✓
- [ ] **Backward compatibility**: 기존 테스트 통과? (Task 2 Step 3, Task 4 Step 5에서 확인)
- [ ] **TDD**: 모든 패턴이 테스트 → 구현 순서? ✓

---

## Completion Checklist

Phase 1 구현 완료 시 확인:

- [ ] 모든 Task 완료 (Task 0 ~ Task 11)
- [ ] 전체 테스트 스위트 통과: `uv run pytest tests/tools/technical/ -v`
- [ ] 기존 테스트 호환성: `uv run pytest tests/ -v` (전체)
- [ ] 문서 업데이트 완료 (FEATURES.md)
- [ ] 모든 커밋 메시지 명확
- [ ] Worktree 정리 준비 (다음: finishing-a-development-branch)

---

## Next Steps After Implementation

**Success Criteria 검증 (TODOS.md 참조):**
1. VCP 구분 정확도: 수동 차트 검증 (10개 종목)
2. Pocket Pivot 감지: 역사적 매집 구간 검증
3. Tennis Ball/Egg 구분: 백테스팅 (100개 샘플)
4. Power Gap Up 구분: 단위 테스트로 100% 확인
5. Score 균형: 최대 60점 (Minervini×1.5) 검증
6. False Positive: < 10% (횡보 종목 20개)
7. 응답 속도: 기존 대비 +0.5초 이하 (벤치마크)

**Phase 2 (보류 항목):**
- Shakeout, Minervini Regression, HTF, Fibonacci Support
- 백테스팅 프레임워크
- TODOS.md 참조

---

## Estimated Time

| Task | 예상 시간 | 실제 시간 |
|------|-----------|-----------|
| Task 0: Helper Functions | 15분 | ___ |
| Task 1: VCP 2-Stage Tests | 20분 | ___ |
| Task 2: VCP 2-Stage Impl | 20분 | ___ |
| Task 3: Pocket Pivot Tests | 25분 | ___ |
| Task 4: Pocket Pivot Impl | 20분 | ___ |
| Task 5: Tennis Ball/Egg Tests | 20분 | ___ |
| Task 6: Tennis Ball/Egg Impl | 10분 | ___ |
| Task 7: Power Gap Up Tests | 20분 | ___ |
| Task 8: Power Gap Up Impl | 10분 | ___ |
| Task 9: Negative Score Test | 15분 | ___ |
| Task 10: Integration Tests | 15분 | ___ |
| Task 11: Documentation | 10분 | ___ |
| **Total** | **3-3.5시간** | ___ |

(설계서 예상 4-5시간보다 빠름: 테스트 코드 완전 포함, 엔지니어링 리뷰 반영 완료)

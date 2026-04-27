# Design: Technical Component Enhancements (8-Component System v2)

생성일: 2026-04-24  
상태: APPROVED  
Branch: feature/actionable-signal  
Repo: invest-jarvis

---

## Problem Statement

현재 8-component 기술적 분석 시스템은 기본적인 지표 조합으로 작동하지만, **성장주 투자에 최적화된 고급 패턴**을 감지하지 못합니다.

**사용자 피드백:**
> "VCP는 ATR 수축만 보는데, 실제로 중요한 건 가격 응축(tightness)이야. Pocket Pivot이나 Tennis Ball 같은 기관 매집 신호도 없어. 이런 걸 놓치면 진입 타이밍을 잃는다."

**현재 시스템의 한계:**

| 컴포넌트 | 현재 로직 | 문제점 |
|----------|-----------|--------|
| **Patterns (VCP)** | ATR 20% 수축 검증 | 단기 변동성 감소를 진짜 응축과 구분 못함 |
| **Minervini (Stage 2)** | SMA_200 단일 포인트 비교 (21일 전) | 단기 노이즈에 취약, 변동 섹터에서 오판 |
| **Volume** | 거래량 비율만 (2배 = 급증) | 기관 매집(Pocket Pivot) vs 패닉 감지 못함 |
| **Risk** | 지지/저항 레벨 수집 | 시간 패턴(Shakeout) 감지 못함 |

**놓치는 고급 시그널:**
- **Pocket Pivot**: 기관 조용히 매집 중 (다운데이 거래량 초과 + MA 지지)
- **Tennis Ball vs Egg**: 평균회귀 준비 vs 패닉 매도
- **VCP Tightness**: 진짜 응축 (High-Low < ATR×0.5 for 5+ days)
- **Shakeout**: 스윙 저점 언더컷 → 1-3일 내 재탈환

---

## Solution Overview

**기존 8-component 시스템을 유지하면서**, 4개 컴포넌트에 **성장주 특화 로직**을 추가합니다.

### 최종 선정 개선사항 (4개)

1. **VCP 2-Stage Verification** (patterns.py)
   - 기존: ATR 20% 수축만 체크
   - 추가: Tightness persistence (High-Low < ATR×0.5)
   - 효과: False Positive 감소, 진짜 응축 구분

2. **Pocket Pivot Detection** (volume.py)
   - 신규: 다운데이 최대 거래량 초과 + MA 지지 근접
   - 효과: 기관 매집 조기 감지

3. **Tennis Ball vs Egg** (volume.py)
   - 신규: 하락 거래량 비율 분석 (평균 대비)
   - 효과: 반등 준비 vs 패닉 구분, **첫 negative score**

4. **Power Gap Up Enhancement** (volume.py)
   - 기존: 거래량 2배 + 가격 상승
   - 추가: 갭업 감지 (오늘 시가 vs 어제 고가 ≥4%)
   - 효과: 일반 급증 vs 갭업 구분

### 코드 확인 결과

**Shakeout 중복 여부 (risk.py 확인):**
- risk.py는 **정적 레벨 수집**만 (Swing Low를 현재가와 비교)
- **시간 패턴 감지 없음**: 언더컷 → 재탈환 시퀀스 추적 안 함
- **결론**: Shakeout은 **중복 아님**, 구현 가치 있음 (단, 우선순위 낮음)

**Power Gap Up 중복 여부 (volume.py 확인):**
- volume.py는 거래량 비율(`vol_ratio > 2.0`)만 체크
- **갭 감지 로직 없음**: `(open - prev_high) / prev_high` 계산 없음
- **결론**: **부분 중복**, 갭 감지만 추가하면 됨 (새 패턴 불필요)

### 보류된 개선사항 (3개)

5. **Minervini Regression**: 30-45일 선형 회귀 (단일 포인트 대신)
   - 보류 이유: 백테스팅 필요, 섹터별 효과 불확실
   
6. **High Tight Flag (HTF)**: 8주 100% 상승 + 25% 조정
   - 보류 이유: 희귀 패턴, 실용성 낮음
   
7. **Fibonacci Support**: 피보나치 되돌림 근접
   - 보류 이유: 기존 레벨과 독립성 미검증

---

## Architecture

### 변경 파일 (4개)

```
src/tools/technical/components/
  ├─ patterns.py         [수정] VCP 2-stage 추가
  ├─ volume.py           [수정] Pocket Pivot, Tennis Ball/Egg, Gap 감지 추가
  ├─ risk.py             [유지] 변경 없음
  └─ minervini.py        [유지] 변경 없음
```

### Score 재조정

**기존 최고점 (Minervini Stage 2): 40점**

**새 점수 체계:**

| 컴포넌트 | 신호 | 점수 | 변경 |
|----------|------|------|------|
| Minervini | Stage 2 상승 | 40 | 유지 |
| Volume | **Pocket Pivot** | 25 | 신규 |
| Patterns | **VCP Strong (ATR+Tight)** | 20 | 신규 |
| Patterns | Breakout | 20 | 유지 |
| Volume | **Power Gap Up (갭+거래량)** | 20 | 강화 (기존 15) |
| Volume | **Tennis Ball (반등 준비)** | 15 | 신규 |
| Patterns | **VCP General (ATR만)** | 10 | 하향 (기존 15) |
| Volume | 거래량 급증 (일반) | 15 | 유지 |
| Volume | **Egg (패닉 매도)** | -15 | 신규 (첫 마이너스) |

**조합 예시:**
- VCP Strong + Pocket Pivot = 20 + 25 = **45점** (단기 신호가 Minervini 초과 가능)
- Tennis Ball + VCP Strong = 15 + 20 = **35점** (반등 준비)

**설계 원칙:**
- 장기 추세 (Minervini) > 단기 패턴 (조합)
- 단일 단기 신호가 Minervini를 초과하지 않음
- 조합 신호는 초과 가능 (여러 증거 동시 발생)

---

## Component 1: VCP 2-Stage Verification

### 현재 구현 (patterns.py:50-82)

```python
def _detect_vcp(df: pd.DataFrame) -> dict:
    recent_8 = atr_series.iloc[-8:].values
    first_4_avg = recent_8[:4].mean()
    last_4_avg = recent_8[-4:].mean()
    contraction_ratio = (first_4_avg - last_4_avg) / first_4_avg
    
    if contraction_ratio > 0.20:  # 20% ATR 수축
        return {"signals": ["VCP (에너지 응축)"], "score": 15, ...}
```

**문제:**
- 단기 ATR 감소를 진짜 응축으로 오인
- Tightness (일일 변동폭) 검증 없음

### 개선 구현

**2단계 검증 추가:**

```python
def _detect_vcp(df: pd.DataFrame) -> dict:
    """VCP 감지 - 2단계 검증 (ATR + Tightness)"""
    
    if len(df) < 20 or 'ATR' not in df.columns:
        return {"detected": False, ...}
    
    # Stage 1: ATR 수축 (기존 로직)
    recent_8 = df['ATR'].iloc[-8:].fillna(method='ffill').values
    first_4_avg = recent_8[:4].mean()
    last_4_avg = recent_8[-4:].mean()
    contraction_ratio = (first_4_avg - last_4_avg) / first_4_avg
    atr_contracted = contraction_ratio > 0.20
    
    # Stage 2: Tightness Persistence (신규)
    atr_20 = df['ATR'].iloc[-20:].fillna(method='ffill')
    daily_range = (df['High'] - df['Low']).iloc[-20:]
    
    # "Tight day" 정의: High-Low < ATR × 0.5
    is_tight_day = (daily_range < (atr_20 * 0.5)) & ~daily_range.isna()
    
    tight_count = is_tight_day.sum()  # 20일 중 몇 개?
    recent_3_tight = all(is_tight_day.iloc[-3:])  # 최근 3일 연속?
    
    # 점수 계산
    signals = []
    evidence = []
    score = 0
    
    if atr_contracted and (tight_count >= 5 or recent_3_tight):
        # 강력 응축: ATR 수축 + Tightness 지속
        signals.append("VCP 강력 응축 (Tight + ATR)")
        evidence.append(f"ATR 수축 {contraction_ratio*100:.1f}%, Tight days {tight_count}/20")
        score = 20
        
    elif atr_contracted:
        # 일반 변동성 감소: ATR만
        signals.append("VCP 일반 (ATR 수축)")
        evidence.append(f"ATR 수축 {contraction_ratio*100:.1f}%")
        score = 10
        
    else:
        return {"detected": False, ...}
    
    return {
        "signals": signals,
        "evidence": evidence,
        "metrics": {
            "atr_contraction_ratio": round(contraction_ratio, 2),
            "tight_days_count": tight_count,
            "recent_3_tight": recent_3_tight,
        },
        "score": score,
    }
```

**효과:**
- False Positive 감소 (단기 ATR 감소 vs 진짜 응축 구분)
- 점수 차등화 (강력 20점 vs 일반 10점)
- 기존 로직 보존 (ATR만으로도 10점)

---

## Component 2: Pocket Pivot Detection

### 신규 추가 (volume.py)

**개념 (Gil Morales, O'Neil 제자):**
- **다운데이 거래량 < 투데이 거래량** (기관이 조용히 매집)
- **MA 지지 근접** (50일선 ±2% 이내)

**구현:**

```python
def _detect_pocket_pivot(df: pd.DataFrame) -> dict:
    """Pocket Pivot 감지 (기관 매집 신호)"""
    
    if len(df) < 10 or 'Volume' not in df.columns:
        return {"detected": False}
    
    # 최근 10일 데이터
    recent_10 = df.iloc[-10:]
    
    # 1. 다운데이 찾기 (Close < prev Close)
    recent_10_with_prev = recent_10.copy()
    recent_10_with_prev['Prev_Close'] = recent_10['Close'].shift(1)
    down_days = recent_10_with_prev[
        recent_10_with_prev['Close'] < recent_10_with_prev['Prev_Close']
    ]
    
    if len(down_days) == 0:
        return {"detected": False}
    
    max_down_volume = down_days['Volume'].max()
    
    # 2. 오늘은 상승일이어야 함
    today = df.iloc[-1]
    prev = df.iloc[-2]
    today_volume = today['Volume']
    
    if today['Close'] <= prev['Close']:
        return {"detected": False}
    
    # 3. 오늘 거래량 > 다운데이 최대 거래량
    volume_condition = today_volume > max_down_volume
    
    # 4. MA 지지 근접 (50일선 ±2% 이내)
    sma_50 = today.get('SMA_50')
    if pd.isna(sma_50):
        return {"detected": False}
    
    sma_50 = float(sma_50)
    today_close = float(today['Close'])
    distance_from_sma = abs(today_close - sma_50) / sma_50
    
    near_sma_50 = distance_from_sma < 0.02
    above_sma_50 = today_close > sma_50
    price_condition = above_sma_50 or near_sma_50
    
    # 5. 두 조건 모두 충족
    if volume_condition and price_condition:
        return {
            "signals": ["Pocket Pivot (기관 매집)"],
            "evidence": [
                f"오늘 거래량 {today_volume:,.0f} > 다운데이 최대 {max_down_volume:,.0f}",
                f"50일선 거리 {distance_from_sma*100:.1f}%",
            ],
            "metrics": {
                "today_volume": today_volume,
                "max_down_volume": max_down_volume,
                "sma_50_distance_pct": round(distance_from_sma * 100, 2),
            },
            "score": 25,
        }
    
    return {"detected": False}
```

**점수 근거:**
- 25점 = Minervini 40점의 62.5% (기관 매집은 강한 신호)
- VCP Strong 20점보다 높음 (매집 > 응축)

---

## Component 3: Tennis Ball vs Egg

### 신규 추가 (volume.py)

**개념:**
- **Tennis Ball**: 하락 시 거래량 감소 (Dry-up, 반등 준비)
- **Egg**: 하락 시 거래량 폭증 (패닉 매도, 더 빠질 위험)

**구현:**

```python
def _detect_mean_reversion_signal(df: pd.DataFrame) -> dict:
    """Tennis Ball vs Egg (평균회귀 신호)"""
    
    if len(df) < 5 or 'Volume' not in df.columns or 'Vol_SMA_20' not in df.columns:
        return {"detected": False}
    
    # 최근 5일 데이터
    recent_5 = df.iloc[-5:].copy()
    recent_5['Price_Change'] = recent_5['Close'].diff()
    
    # 1. 하락일 찾기
    down_days = recent_5[recent_5['Price_Change'] < 0]
    
    if len(down_days) == 0:
        return {"detected": False}
    
    # 2. 하락일 평균 거래량 vs 20일 평균
    down_volume_avg = down_days['Volume'].mean()
    vol_sma_20 = df['Vol_SMA_20'].iloc[-1]
    
    if pd.isna(vol_sma_20) or vol_sma_20 == 0:
        return {"detected": False}
    
    vol_ratio = down_volume_avg / vol_sma_20
    
    # 3. Tennis Ball: 하락 거래량 < 50% 평균
    if vol_ratio < 0.5:
        return {
            "signals": ["테니스 공 (Dry-up 반등 준비)"],
            "evidence": [
                f"하락일 평균 거래량 {down_volume_avg:,.0f}",
                f"20일 평균 대비 {vol_ratio*100:.0f}% (< 50%)",
            ],
            "metrics": {
                "down_volume_avg": down_volume_avg,
                "vol_sma_20": vol_sma_20,
                "vol_ratio": round(vol_ratio, 2),
            },
            "score": 15,
        }
    
    # 4. Egg: 하락 거래량 > 150% 평균
    elif vol_ratio > 1.5:
        return {
            "signals": ["달걀 (패닉 매도)"],
            "evidence": [
                f"하락일 평균 거래량 {down_volume_avg:,.0f}",
                f"20일 평균 대비 {vol_ratio*100:.0f}% (> 150%)",
            ],
            "metrics": {
                "down_volume_avg": down_volume_avg,
                "vol_sma_20": vol_sma_20,
                "vol_ratio": round(vol_ratio, 2),
            },
            "score": -15,  # 첫 negative score!
        }
    
    return {"detected": False}
```

**첫 Negative Score:**
- 기존 시스템: 0점 = 중립, 양수 = 긍정
- Egg: -15점 = 명시적 경고
- 총점 계산에 반영되어 위험 신호 강화

**점수 근거:**
- Tennis Ball 15점 = 반등 가능성 (조심스러운 긍정)
- Egg -15점 = 패닉 매도 경고 (명시적 부정)

---

## Component 4: Power Gap Up Enhancement

### 기존 구현 (volume.py:44-55)

```python
if vol_ratio > 2.0:
    signals.append("거래량 급증")
    if price_up:
        signals.append("가격 상승 + 거래량 급증 (강세 확인)")
        score += 15
```

**문제:**
- 갭업과 일반 상승 구분 못함
- Gap size 계산 없음

### 개선 구현

**갭 감지 추가:**

```python
def analyze_volume(df: pd.DataFrame) -> ComponentResult:
    """Analyze volume patterns (with Gap detection)."""
    
    # ... (기존 코드) ...
    
    volume = float(latest['Volume'])
    vol_sma_20 = float(latest['Vol_SMA_20'])
    vol_ratio = volume / vol_sma_20
    
    # 신규: 갭 감지
    today_open = latest.get('Open')
    prev_high = prev.get('High')
    
    gap_detected = False
    gap_size_pct = 0.0
    
    if not pd.isna(today_open) and not pd.isna(prev_high):
        today_open = float(today_open)
        prev_high = float(prev_high)
        
        if today_open > prev_high:
            gap_size_pct = (today_open - prev_high) / prev_high
            gap_detected = gap_size_pct >= 0.04  # 4% 이상
    
    signals = []
    evidence = []
    score = 0
    
    # 거래량 급증 + 갭업 (Power Gap Up)
    if vol_ratio > 3.0 and gap_detected:
        signals.append("Power Gap Up (갭업 + 거래량 3배)")
        evidence.append(f"갭 크기 {gap_size_pct*100:.1f}%, 거래량 {vol_ratio:.1f}x")
        score += 20  # 일반 급증(15)보다 높음
        
    # 거래량 급증 (일반)
    elif vol_ratio > 2.0:
        signals.append("거래량 급증")
        evidence.append(f"거래량 {vol_ratio:.1f}x")
        if price_up:
            signals.append("가격 상승 + 거래량 급증 (강세 확인)")
            score += 15
        elif price_down:
            signals.append("가격 하락 + 거래량 급증 (경고)")
            score -= 10
    
    # ... (나머지 기존 로직) ...
    
    return ComponentResult(signals=signals, evidence=evidence, score=score, ...)
```

**변경사항:**
- 갭 감지 추가: `(open - prev_high) / prev_high >= 4%`
- 거래량 기준 상향: 2배 → 3배 (Power Gap Up은 더 강한 신호)
- 점수 차등화: 갭업 20점 vs 일반 15점

---

## Component 5: Shakeout (보류)

### 구현 로직 (참고용)

**감지 로직:**

```python
def _detect_shakeout(df: pd.DataFrame) -> dict:
    """Shakeout 패턴 감지 (스윙 저점 언더컷 + 재탈환)"""
    
    if len(df) < 10 or 'Swing_Low' not in df.columns:
        return {"detected": False}
    
    # 최근 스윙 저점 찾기
    swing_lows = df['Swing_Low'].dropna().tail(3)
    if len(swing_lows) == 0:
        return {"detected": False}
    
    last_swing_low = swing_lows.iloc[-1]
    
    # 최근 5일 데이터
    recent_5 = df.iloc[-5:]
    
    # 1. 언더컷 찾기 (Low < Swing Low)
    undercut_days = recent_5[recent_5['Low'] < last_swing_low]
    
    if len(undercut_days) == 0:
        return {"detected": False}
    
    undercut_idx = undercut_days.index[-1]  # 가장 최근 언더컷
    undercut_day_position = len(df) - df.index.get_loc(undercut_idx) - 1
    
    # 2. 재탈환 확인 (언더컷 이후 Close > Swing Low)
    days_after = recent_5.loc[undercut_idx:].iloc[1:]  # 언더컷 다음날부터
    
    if len(days_after) == 0:
        return {"detected": False}
    
    reclaimed = any(days_after['Close'] > last_swing_low)
    reclaim_within_3_days = len(days_after) <= 3
    
    if reclaimed and reclaim_within_3_days:
        return {
            "signals": ["Shakeout (가짜 하락)"],
            "evidence": [
                f"스윙 저점 ${last_swing_low:.2f} 언더컷",
                f"{len(days_after)}일 만에 재탈환",
            ],
            "metrics": {
                "swing_low": last_swing_low,
                "undercut_days_ago": undercut_day_position,
                "reclaim_days": len(days_after),
            },
            "score": 20,
        }
    
    return {"detected": False}
```

**보류 이유:**
- 구현 복잡도 높음 (시간 시퀀스 추적)
- 우선순위: Pocket Pivot, Tennis Ball이 더 실용적
- 향후 Phase 2에서 추가 고려

---

## Testing Strategy

### 1. 단위 테스트

**VCP 2-Stage:**

```python
# tests/tools/technical/components/test_patterns_v2.py

def test_vcp_strong_detection():
    """VCP Strong: ATR 수축 + Tightness"""
    df = create_mock_vcp(
        atr_contraction=0.25,  # 25% 수축
        tight_days_count=7,    # 20일 중 7일 tight
    )
    
    result = _detect_vcp(df)
    
    assert "VCP 강력 응축" in result["signals"][0]
    assert result["score"] == 20

def test_vcp_general_detection():
    """VCP General: ATR 수축만"""
    df = create_mock_vcp(
        atr_contraction=0.22,  # 22% 수축
        tight_days_count=2,    # tight 부족
    )
    
    result = _detect_vcp(df)
    
    assert "VCP 일반" in result["signals"][0]
    assert result["score"] == 10
```

**Pocket Pivot:**

```python
def test_pocket_pivot_detection():
    """Pocket Pivot: 다운데이 거래량 초과 + MA 지지"""
    df = create_mock_pocket_pivot(
        down_day_volumes=[100, 120, 90],
        today_volume=150,
        sma_50_distance=0.01,  # 1% 거리
    )
    
    result = _detect_pocket_pivot(df)
    
    assert result["signals"][0] == "Pocket Pivot (기관 매집)"
    assert result["score"] == 25
```

**Tennis Ball vs Egg:**

```python
def test_tennis_ball_detection():
    """Tennis Ball: 하락 거래량 감소"""
    df = create_mock_mean_reversion(
        down_volume_ratio=0.4,  # 40% (< 50%)
    )
    
    result = _detect_mean_reversion_signal(df)
    
    assert "테니스 공" in result["signals"][0]
    assert result["score"] == 15

def test_egg_detection():
    """Egg: 하락 거래량 폭증"""
    df = create_mock_mean_reversion(
        down_volume_ratio=1.8,  # 180% (> 150%)
    )
    
    result = _detect_mean_reversion_signal(df)
    
    assert "달걀" in result["signals"][0]
    assert result["score"] == -15
```

**Power Gap Up:**

```python
def test_power_gap_up():
    """Power Gap Up: 갭업 + 거래량 3배"""
    df = create_mock_gap_up(
        gap_size_pct=0.05,  # 5% 갭
        vol_ratio=3.5,      # 3.5배
    )
    
    result = analyze_volume(df)
    
    assert "Power Gap Up" in result.signals[0]
    assert result.score == 20
```

### 2. 통합 테스트

```python
# tests/tools/technical/test_integration_v2.py

def test_combined_signals_scoring():
    """조합 신호 점수 검증"""
    
    # VCP Strong + Pocket Pivot
    df = create_combined_pattern(
        vcp_strong=True,
        pocket_pivot=True,
    )
    
    result = TechnicalTool.execute("MOCK", df)
    
    # 20 + 25 = 45 (Minervini 40 초과 가능)
    assert result.total_score >= 45
    assert "VCP 강력 응축" in str(result.components)
    assert "Pocket Pivot" in str(result.components)
```

### 3. 실제 데이터 검증 (Slow)

```python
# tests/integration/test_real_patterns.py

@pytest.mark.integration
@pytest.mark.parametrize("ticker,date,expected", [
    ("NVDA", "2023-05-15", "Pocket Pivot"),
    ("AAPL", "2024-01-10", "VCP 강력 응축"),
    ("TSLA", "2023-11-20", "테니스 공"),
])
def test_known_historical_patterns(ticker, date, expected):
    """유명한 역사적 패턴 검증"""
    
    # Snapshot 데이터 사용 (재현 가능)
    df = load_snapshot(ticker, date)
    
    result = TechnicalTool.execute(ticker, df)
    signals_text = str(result.components)
    
    assert expected in signals_text
```

---

## Success Criteria

| 항목 | 기준 | 측정 방법 |
|------|------|-----------|
| **VCP 구분 정확도** | ATR vs Strong 80% 구분 | 수동 차트 검증 (10개 종목) |
| **Pocket Pivot 감지** | 역사적 매집 구간 70% 감지 | NVDA 2023, TSLA 2024 등 |
| **Tennis Ball/Egg 구분** | 반등 vs 패닉 75% 정확 | 백테스팅 (100개 샘플) |
| **Power Gap Up 구분** | 갭 vs 일반 100% 정확 | 단위 테스트 (갭 계산) |
| **Score 균형** | 조합 신호 ≤ Minervini×1.5 | 최대 60점 (40×1.5) 이하 |
| **False Positive** | < 10% | 횡보 종목 테스트 (20개) |
| **응답 속도** | 기존 대비 +0.5초 이하 | 벤치마크 (AAPL) |
| **기존 테스트 통과** | 100% | CI 그린 유지 |

---

## Implementation Plan

### Phase 1: Core Enhancements (우선)

| # | 작업 | 파일 | 예상 시간 |
|---|------|------|-----------|
| 1.1 | VCP 2-Stage 구현 | `src/tools/technical/components/patterns.py` | 40분 |
| 1.2 | Pocket Pivot 구현 | `src/tools/technical/components/volume.py` | 45분 |
| 1.3 | Tennis Ball/Egg 구현 | 위 파일 | 30분 |
| 1.4 | Power Gap Up 강화 | 위 파일 | 20분 |
| 1.5 | Score 재조정 | 모든 컴포넌트 | 15분 |
| 1.6 | 단위 테스트 작성 | `tests/tools/technical/components/` | 60분 |
| 1.7 | 통합 테스트 | `tests/tools/technical/test_integration_v2.py` | 30분 |
| 1.8 | 실제 데이터 검증 (Snapshot) | `tests/integration/test_real_patterns.py` | 40분 |
| 1.9 | 문서 업데이트 | `docs/FEATURES.md` | 20분 |

**Phase 1 총 시간:** 4-5시간

### Phase 2: Additional Patterns (나중)

| # | 작업 | 파일 | 예상 시간 |
|---|------|------|-----------|
| 2.1 | Shakeout 구현 | `src/tools/technical/components/patterns.py` | 60분 |
| 2.2 | Minervini Regression | `src/tools/technical/components/minervini.py` | 45분 |
| 2.3 | HTF 구현 | `src/tools/technical/components/patterns.py` | 45분 |
| 2.4 | Fibonacci Support | `src/tools/technical/components/risk.py` | 30분 |
| 2.5 | 백테스팅 프레임워크 | `tests/backtesting/` | 120분 |

**Phase 2 총 시간:** 5-6시간

---

## Migration Strategy

### Backward Compatibility

**기존 시스템과 호환:**
- VCP 일반 (10점)은 기존 로직 유지
- 거래량 급증 (15점)은 그대로 작동
- 새 패턴은 추가만, 기존 삭제 없음

**점수 변화 영향:**
- VCP 15→10점: 단독 신호 약화 (의도적)
- Power Gap Up 15→20점: 갭 감지 시만 상승

### Rollout Plan

1. **Feature Flag (선택적)**
   ```python
   USE_ADVANCED_PATTERNS = os.getenv("ADVANCED_PATTERNS", "true") == "true"
   
   if USE_ADVANCED_PATTERNS:
       pocket_pivot_result = _detect_pocket_pivot(df)
   ```

2. **점진적 활성화**
   - Week 1: VCP 2-Stage만
   - Week 2: Pocket Pivot, Tennis Ball 추가
   - Week 3: Power Gap Up 강화
   - Week 4: 전체 활성화

3. **모니터링**
   - 총점 분포 변화 (히스토그램)
   - False Positive 비율
   - 사용자 피드백

---

## Future Enhancements (Phase 3+)

**백테스팅 기반 최적화:**
1. VCP Tightness threshold 튜닝 (0.5 → 0.4?)
2. Pocket Pivot MA 기준 변경 (50일선 → 21일선?)
3. Tennis Ball threshold 조정 (50% → 40%?)
4. Gap size threshold (4% → 3%?)

**추가 패턴:**
5. **U-Turn**: Supertrend 방향 전환 + 거래량
6. **Climax Run**: 급등 후 과매수 경고
7. **Accumulation**: 횡보 구간 거래량 분석

---

## CHANGELOG

### 2026-04-24: 초안 작성
- 코드 확인 완료: Shakeout 중복 아님, Power Gap Up 부분 중복
- 4개 개선사항 최종 선정
- Score 재조정 (첫 negative score -15점)
- 2-Phase 구현 계획 (Phase 1 우선, Phase 2 보류)

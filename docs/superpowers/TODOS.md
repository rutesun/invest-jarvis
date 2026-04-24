# TODO: Technical Component Enhancements

생성일: 2026-04-25  
원본 설계: [docs/superpowers/specs/2026-04-24-technical-component-enhancements-design.md](specs/2026-04-24-technical-component-enhancements-design.md)  
엔지니어링 리뷰: 2026-04-25 완료

---

## Phase 1: Core Enhancements ✅ (진행 중)

### 구현 작업

- [ ] **1.1 VCP 2-Stage 구현** (`patterns.py`) - 40분
  - Branch: `feature/vcp-2stage-20260425`
  - Worktree: `.worktrees/feature/vcp-2stage-20260425` ✅ 준비 완료
  - 2단계 검증: ATR 수축 + Tightness persistence
  - 점수: Strong 20점 / General 10점

- [ ] **1.2 Pocket Pivot 구현** (`volume.py`) - 45분
  - 다운데이 최대 거래량 초과 + 50일선 ±2% 지지
  - 점수: 25점

- [ ] **1.3 Tennis Ball/Egg 구현** (`volume.py`) - 30분
  - 의존성: 1.2 완료 후 시작
  - Tennis Ball: 하락 거래량 < 50% (15점)
  - Egg: 하락 거래량 > 150% (-15점, 첫 negative score)

- [ ] **1.4 Power Gap Up 강화** (`volume.py`) - 20분
  - 갭 감지 추가: (open - prev_high) ≥ 4%
  - 점수: 20점 (vs 일반 급증 15점)

- [ ] **1.5 Score 재조정** (모든 파일) - 15분
  - 의존성: 1.1~1.4 완료 필요
  - VCP 일반 15→10점, Power Gap Up 15→20점

### 테스트 작업

- [ ] **1.6 단위 테스트 작성** (`tests/tools/technical/components/`) - 60분
  - 의존성: 1.1~1.4 완료 필요
  - `test_vcp_strong_with_tightness()` - VCP Strong 20점
  - `test_vcp_general_without_tightness()` - VCP 일반 10점
  - `test_pocket_pivot_detection()` - Pocket Pivot 25점
  - `test_tennis_ball_detection()` - Tennis Ball 15점
  - `test_egg_negative_score()` - Egg -15점
  - `test_power_gap_up_with_gap_and_volume()` - Power Gap Up 20점

- [ ] **1.7 통합 테스트** (`test_tool_scorer_integration.py`) - 30분
  - 의존성: 1.6 완료 필요
  - `test_negative_score_propagation()` - Egg -15점 scorer → CLI 전파
  - `test_combined_signals_scoring()` - VCP Strong + Pocket Pivot = 45점

- [ ] **1.8 실제 데이터 검증** (`tests/integration/`) - 40분
  - 의존성: 1.7 완료 필요
  - 역사적 패턴 검증 (NVDA 2023, AAPL 2024 등)

### 문서화

- [ ] **1.9 문서 업데이트** - 20분
  - 의존성: 1.5 완료 필요
  - `docs/FEATURES.md`: 새 패턴 4개 설명
  - `docs/adr/`: 아키텍처 결정 기록 (필요시)

### 예상 총 시간
**Phase 1 총 시간:** 4-5시간

---

## Phase 2: Additional Patterns (보류)

### 1. Pocket Pivot 21일선 지원
**우선순위:** Medium  
**예상 시간:** 20분  
**현재 상태:** 백테스팅 효과 검증 필요

**배경:**
- 현재: 50일선 ±2% 지지만 체크
- 문제: 21일선 지지 반등 패턴 놓침 (Failure Mode 2)
- 해결책: `near_sma_21` 조건 추가

**구현:**
```python
# volume.py::_detect_pocket_pivot()
sma_21 = today.get('SMA_21')
distance_from_sma_21 = abs(today_close - sma_21) / sma_21
near_sma_21 = distance_from_sma_21 < 0.02

# 기존 조건 OR 추가
price_condition = above_sma_50 or near_sma_50 or near_sma_21
```

**테스트:**
- `test_pocket_pivot_near_sma_21()`

**참고:**
- 설계서: Failure Modes 섹션

---

### 2. Shakeout Pattern
**우선순위:** Medium  
**예상 시간:** 60분  
**현재 상태:** 구현 복잡도 높음, 우선순위 낮음

**정의:**
- 스윙 저점 언더컷 → 1-3일 내 재탈환
- 점수: 20점

**구현 위치:**
- `src/tools/technical/components/patterns.py`

**복잡도:**
- 시간 시퀀스 추적 필요 (recent_5 내 언더컷 날짜 + 재탈환 날짜)
- 기존 risk.py는 정적 레벨 수집만 (중복 아님)

**참고:**
- 설계서 Component 5 (라인 451-508)
- 리뷰: "NOT in Scope" 섹션

---

### 3. Minervini Regression
**우선순위:** High (백테스팅 후)  
**예상 시간:** 45분  
**현재 상태:** 백테스팅 필요, 섹터별 효과 불확실

**정의:**
- 200일선 30-45일 선형 회귀 (단일 포인트 비교 대신)
- 현재: 21일 전 단일 포인트 비교 → 단기 노이즈 취약

**구현 위치:**
- `src/tools/technical/components/minervini.py`

**불확실성:**
- 섹터별 효과 미검증
- Threshold 튜닝 필요 (회귀 기울기 임계값)

**참고:**
- 설계서 보류 항목 2 (라인 72-73)

---

### 4. High Tight Flag (HTF)
**우선순위:** Low  
**예상 시간:** 45분  
**현재 상태:** 희귀 패턴, 실용성 낮음

**정의:**
- 8주 100% 상승 + 3-5주 25% 조정
- 점수: 미정 (~20-25점)

**구현 위치:**
- `src/tools/technical/components/patterns.py`

**실용성:**
- 발생 빈도 낮아 ROI 낮음
- 극단적 모멘텀 상황에서만 감지

**참고:**
- 설계서 보류 항목 6 (라인 75-76)

---

### 5. Fibonacci Support
**우선순위:** Low  
**예상 시간:** 30분  
**현재 상태:** 기존 레벨과 독립성 미검증

**정의:**
- 38.2%, 50%, 61.8% 되돌림 근접
- 점수: 미정 (~10점)

**구현 위치:**
- `src/tools/technical/components/risk.py`

**의존성:**
- 기존 레벨(Swing Low, Pivot)과 중복 가능성
- 독립적 신호인지 검증 필요

**참고:**
- 설계서 보류 항목 7 (라인 78-79)

---

### 6. 백테스팅 프레임워크
**우선순위:** High (Phase 2 선행 작업)  
**예상 시간:** 120분  
**현재 상태:** Phase 2 구현 전 필수

**목적:**
- 패턴별 승률/샤프 검증
- Threshold 튜닝 (VCP Tightness 0.5 → 0.4?)
- Phase 2 패턴 효과 검증

**구현 위치:**
- `tests/backtesting/` (신규)

**참고:**
- 설계서 Phase 2 (라인 692-700)

---

## 리뷰 발견 사항 (2026-04-25)

### 코드 품질 개선 (Phase 1 반영 완료)

#### Issue 5: DRY Violation
**해결책:** Helper functions 추가
- `_validate_dataframe(df, min_len, required_cols)` - 공통 validation
- `_empty_result()` - 일관된 empty return

#### Issue 6: Power Gap Up 중복 임계값
**해결책:** 명시적 조건 변수
```python
is_extreme_volume = vol_ratio > 3.0
is_high_volume = vol_ratio > 2.0
```

#### Issue 7: Return 일관성
**해결책:** `_empty_result()` 활용
```python
return {"signals": [], "evidence": [], "metrics": {}, "score": 0}
```

#### Issue 8: Magic Numbers
**해결책:** `PatternThresholds` 클래스 추출
```python
class PatternThresholds:
    """패턴 감지 임계값 (백테스팅 최적화용)"""
    VCP_ATR_CONTRACTION = 0.20
    VCP_TIGHTNESS_MULTIPLIER = 0.5
    VCP_MIN_TIGHT_DAYS = 5
    PP_SMA_DISTANCE_PCT = 0.02
    TENNIS_BALL_THRESHOLD = 0.5
    EGG_THRESHOLD = 1.5
    GAP_SIZE_MIN_PCT = 0.04
    GAP_VOLUME_MULTIPLIER = 3.0
```

### 성능 최적화 (Phase 1 반영 완료)

#### Issue P1: Python all() → pandas .all()
**위치:** `patterns.py::_detect_vcp()` 라인 169  
**변경:**
```python
# Before
recent_3_tight = all(is_tight_day.iloc[-3:])

# After
recent_3_tight = is_tight_day.iloc[-3:].all()
```
**효과:** ~5배 고속화 (10μs → 2μs)

---

## Success Criteria (Phase 1 검증 항목)

| 항목 | 기준 | 측정 방법 | 상태 |
|------|------|-----------|------|
| VCP 구분 정확도 | ATR vs Strong 80% 구분 | 수동 차트 검증 (10개 종목) | ⏳ 대기 |
| Pocket Pivot 감지 | 역사적 매집 구간 70% 감지 | NVDA 2023, TSLA 2024 등 | ⏳ 대기 |
| Tennis Ball/Egg 구분 | 반등 vs 패닉 75% 정확 | 백테스팅 (100개 샘플) | ⏳ 대기 |
| Power Gap Up 구분 | 갭 vs 일반 100% 정확 | 단위 테스트 (갭 계산) | ⏳ 대기 |
| Score 균형 | 조합 신호 ≤ Minervini×1.5 | 최대 60점 (40×1.5) 이하 | ⏳ 대기 |
| False Positive | < 10% | 횡보 종목 테스트 (20개) | ⏳ 대기 |
| 응답 속도 | 기존 대비 +0.5초 이하 | 벤치마크 (AAPL) | ✅ 예상 0.5초 |
| 기존 테스트 통과 | 100% | CI 그린 유지 | ✅ 87/87 passed |

---

## 참고 문서

- **원본 설계:** [docs/superpowers/specs/2026-04-24-technical-component-enhancements-design.md](specs/2026-04-24-technical-component-enhancements-design.md)
- **엔지니어링 리뷰:** 2026-04-25 (Section 1-4 완료)
- **아키텍처:** [docs/ARCHITECTURE.md](../ARCHITECTURE.md)
- **기능 명세:** [docs/FEATURES.md](../FEATURES.md)
- **개발 가이드:** [docs/DEVELOPMENT.md](../DEVELOPMENT.md)

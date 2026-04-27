# Current Tasks

> 📍 **Navigation:** [ROADMAP](ROADMAP.md) ↔ [TODOS](TODOS.md) (You are here)
> 
> 최종 업데이트: 2026-04-27

---

## Technical Component Enhancements (Phase 1)

**진행률:** 60% (3/5 core tasks done)  
**예상 남은 시간:** 3-4시간  
**참고 문서:** [설계 스펙](docs/superpowers/specs/2026-04-24-technical-component-enhancements-design.md)

### ✅ Recently Completed

- [x] **Chart Enhancement** (2026-04-27) - PR #21 ✅
  - 6 MA lines, Supertrend, cRSI, MACD panels
  - 19 commits, 94 tests passing
  - → Moved to ROADMAP.md

- [x] **VCP 2-Stage** (2026-04-25) - PR #20 ✅
  - Strong/General 구분
  - → Moved to ROADMAP.md

---

### 🚧 In Progress

**없음** - 다음 작업 선택 필요

---

### 📋 Next Up (우선순위 순)

#### 1. Pocket Pivot 구현
**파일:** `src/tools/technical/components/volume.py`  
**예상 시간:** 45분  
**점수:** 25점

**설명:**
- 다운데이 최대 거래량 초과
- 50일선 ±2% 지지 조건

**구현 포인트:**
```python
# volume.py::_detect_pocket_pivot()
down_days_volume = df[df['Close'] < df['Open']]['Volume'].tail(10)
max_down_volume = down_days_volume.max()
today_volume = today['Volume']

is_pocket_pivot = today_volume > max_down_volume and near_sma_50
```

**테스트:**
- `test_pocket_pivot_detection()`
- `test_pocket_pivot_near_sma_50()`

---

#### 2. Tennis Ball/Egg 패턴
**파일:** `src/tools/technical/components/volume.py`  
**예상 시간:** 30분  
**점수:** Tennis Ball +15점, Egg -15점 (첫 negative score)

**설명:**
- Tennis Ball: 하락 거래량 < 50% (반등 가능성)
- Egg: 하락 거래량 > 150% (패닉)

**구현 포인트:**
```python
down_avg_volume = down_days_volume.mean()
up_avg_volume = up_days_volume.mean()
ratio = down_avg_volume / up_avg_volume

if ratio < 0.5:
    # Tennis Ball: 15점
elif ratio > 1.5:
    # Egg: -15점
```

**테스트:**
- `test_tennis_ball_detection()`
- `test_egg_negative_score()`

---

#### 3. Power Gap Up 강화
**파일:** `src/tools/technical/components/volume.py`  
**예상 시간:** 20분  
**점수:** 20점 (vs 일반 급증 15점)

**설명:**
- 갭 감지: `(open - prev_high) >= 4%`
- 기존 거래량 급증에 갭 조건 추가

**구현 포인트:**
```python
prev_high = df['High'].iloc[-2]
gap_size = (today['Open'] - prev_high) / prev_high

is_gap_up = gap_size >= 0.04
is_extreme_volume = vol_ratio > 3.0

if is_gap_up and is_extreme_volume:
    score = 20  # Power Gap Up
elif is_extreme_volume:
    score = 15  # 일반 급증
```

**테스트:**
- `test_power_gap_up_with_gap_and_volume()`
- `test_regular_surge_without_gap()`

---

#### 4. Score 재조정
**파일:** 모든 컴포넌트 파일  
**예상 시간:** 15분  
**의존성:** 1-3 완료 필요

**변경 사항:**
- VCP 일반: 15점 → 10점
- Power Gap Up: 15점 → 20점
- 기타 점수는 유지

**파일 리스트:**
- `src/tools/technical/components/patterns.py`
- `src/tools/technical/components/volume.py`

---

#### 5. 테스트 작성
**파일:** `tests/tools/technical/components/`  
**예상 시간:** 60분  
**의존성:** 1-4 완료 필요

**테스트 케이스:**
- `test_vcp_strong_with_tightness()` - VCP Strong 20점
- `test_vcp_general_without_tightness()` - VCP 일반 10점
- `test_pocket_pivot_detection()` - Pocket Pivot 25점
- `test_tennis_ball_detection()` - Tennis Ball 15점
- `test_egg_negative_score()` - Egg -15점
- `test_power_gap_up_with_gap_and_volume()` - Power Gap Up 20점

**통합 테스트:**
- `test_negative_score_propagation()` - Egg -15점 전파
- `test_combined_signals_scoring()` - VCP Strong + Pocket Pivot = 45점

---

#### 6. 문서 업데이트
**파일:** `docs/FEATURES.md`  
**예상 시간:** 20분  
**의존성:** 5 완료 필요

**업데이트 내용:**
- 새 패턴 4개 설명 (Pocket Pivot, Tennis Ball, Egg, Power Gap Up)
- Score 재조정 내역
- 예시 차트 (선택)

---

## Phase 2: Additional Patterns (백로그)

> **참고:** Phase 1 완료 후 백테스팅 결과에 따라 우선순위 재평가

### 후보 항목:
1. **Pocket Pivot 21일선 지원** (Medium, 20분)
2. **Shakeout Pattern** (Medium, 60분)
3. **Minervini Regression** (High after backtesting, 45분)
4. **High Tight Flag** (Low, 45분)
5. **Fibonacci Support** (Low, 30분)
6. **Backtesting Framework** (High, 120분) - Phase 2 선행 작업

---

## 코드 품질 체크리스트 (구현 시 확인)

구현할 때 다음 항목 확인:

- [ ] DRY: Helper functions 활용 (`_validate_dataframe`, `_empty_result`)
- [ ] 명시적 조건 변수 (`is_extreme_volume`, `is_high_volume`)
- [ ] Return 일관성 (`_empty_result()` 사용)
- [ ] Magic numbers → 상수 추출 (`PatternThresholds` 클래스)
- [ ] pandas vectorization (Python `all()` 대신 `.all()`)
- [ ] 테스트 작성 (구현과 함께)

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
| 기존 테스트 통과 | 100% | CI 그린 유지 | ✅ 94/94 passed |

---

## 참고 문서

- **ROADMAP:** [ROADMAP.md](ROADMAP.md) - 전체 로드맵 및 완료 히스토리
- **설계 스펙:** [docs/superpowers/specs/2026-04-24-technical-component-enhancements-design.md](docs/superpowers/specs/2026-04-24-technical-component-enhancements-design.md)
- **아키텍처:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **기능 명세:** [docs/FEATURES.md](docs/FEATURES.md)
- **개발 가이드:** [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)

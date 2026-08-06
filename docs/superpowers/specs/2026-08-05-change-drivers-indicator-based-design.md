# 지표값 기반 change_drivers 재설계

작성일: 2026-08-05
대상 브랜치: feature/change-drivers-indicator-based

## 배경 / 문제

`jarvis check`의 "최근 점수 추이"는 각 거래일마다 `change_drivers`("변화:" 줄)로
전일 대비 무엇이 바뀌었는지 서술한다. 현재 구현은 컴포넌트별 **점수 델타**를
그대로 보여준다(`scorer.py:_top_component_changes`).

이 방식은 **일회성 이벤트 점수의 롤오프(roll-off)를 유령 신호로 오표기**한다.

실측 사례 (ALAB, point-in-time 재현):

| 날짜 | close | cRSI(전일→당일) | crsi 컴포넌트 점수 | 현재 표기 |
|------|-------|-----------------|--------------------|-----------|
| 7/31 | 311.23 | 32.7 → 38.1 | +20 (Hook Up, 하단밴드 상향돌파) | crsi +20 개선 |
| 8/03 | 321.05 | 38.1 → **44.1** | 0 (중립 복귀) | **crsi -20 악화** |

- crsi Hook Up(+20)은 밴드 돌파가 일어난 7/31 **하루만** 붙는 일회성 이벤트다
  (`crsi.py:66`, `prev < low AND now > low`).
- 8/3에는 cRSI가 38→44로 **계속 상승**했지만 Hook Up 이벤트가 끝나 점수가 0으로 복귀.
- Δ 엔진이 `0 - 20 = -20`을 계산하고 음수면 무조건 "악화"로 라벨(`scorer.py:233`).
- 결과: 지표는 상승 중인데 "crsi 악화"로 표기 — 사용자 차트 판단과 정반대.

이 결함은 crsi에 국한되지 않는다. 일회성 이벤트를 가진 모든 컴포넌트(supertrend
매수/매도 전환, velocity 전환점 등)에서 이벤트 발생 다음 날 반드시 반대 방향
유령 신호가 발생한다. 예: Supertrend 매수 전환(+15) 다음 날 −15 "악화".

## 목표

`change_drivers`를 **점수 델타 서술에서 지표값·이벤트 기반 서술로 전환**해
유령 신호를 제거한다. 동시에 각 날짜에 실제 발생한 이벤트를 숨김 없이 노출한다.

**비목표(Non-goals):** 점수·adjusted_score·technical_verdict·컴포넌트 스코어링
로직은 일절 변경하지 않는다. 이 변경은 **서술(narration) 레이어에만 국한**된다.
`change_drivers`는 오직 quick_check 포맷터에서 텍스트로만 소비되며(확인:
`grep change_drivers` → models.py 정의 + quick_check.py 2곳), 점수/판정에 관여하지 않는다.

## 설계

각 히스토리 포인트(날짜) 서술을 3개 트랙으로 구성한다.

### 트랙 1 — 당일 발생 이벤트 (신규)

그날 실제로 켜진 일회성 신호를 **전부** 표시한다.

- **정의:** 전일 `signals`에 없다가 당일 `signals`에 새로 등장한 항목(온셋).
- Hook Up/Down, Supertrend 매수/매도 전환, Pocket Pivot, Power Gap, 전환점 등이 잡힌다.
- 지속 신호(매일 반복되는 "Supertrend 하락" 등)는 온셋이 아니므로 제외되나,
  그 신호가 **처음 켜진 날**은 이벤트로 표시된다(유용).
- 히스토리 첫 포인트(전일 컴포넌트 없음)는 이벤트 계산을 생략한다(빈 리스트).
- `ScoreHistoryPoint`에 `events: list[str]` 필드를 추가하고 포맷터에서 `이벤트:` 라인으로 출력.

### 트랙 2 — 연속 지표 변화 (crsi, velocity)

점수 델타 대신 **실제 지표값 변화**로 서술한다. 두 컴포넌트 모두 이미 `metrics`에
필요한 값을 노출하므로 추가 배관이 없다. 전일 값은 `previous_components[name]["metrics"]`에 존재.

| 컴포넌트 | metric 키 | 임계값 | 서술 예시 |
|----------|-----------|--------|-----------|
| crsi | `crsi` (0–100) | \|Δ\| ≥ 3 | `cRSI 38.1→44.1 상승` |
| velocity | `norm_slope` (%) | \|Δ\| ≥ 0.02(ACCEL_THRESHOLD) 또는 부호 전환 | `SMA20 기울기 -0.10%→+0.05% 상승전환` |

- 임계값 미만의 미세 변동은 노이즈로 보고 생략한다.
- 이 방식은 velocity 전환점(일회성 ±15) 유령도 자동 흡수한다 — 전환점은 곧 기울기
  부호 변화라, 값 변화 서술이 그 자체로 담아낸다.
- 연속 컴포넌트 정의는 레지스트리(컴포넌트명 → metric 키·임계값·라벨 포맷)로 관리한다.

### 트랙 3 — 이산 상태/점수 변화 (나머지 6개)

supertrend, minervini, volume, patterns, divergence, risk는 점수 델타 서술을 유지하되
**순수 롤오프를 억제**한다.

- **억제 규칙:** 컴포넌트 점수 델타를 driver로 내보내는 조건은 —
  (a) 당일 새 signal이 발생(이벤트 온셋)했거나, (b) 지속 상태 변화가 있는 경우.
  어제 있던 signal이 오늘 사라지고 새 signal이 없는 **순수 롤오프**(델타가 이벤트
  소멸만으로 발생)는 억제한다.
- 억제해도 정보 손실이 없다: 지속 상태는 `driver_components`(그날 상위 기여 컴포넌트)에,
  당일 이벤트는 트랙 1에 나온다.

## 출력 예시 (ALAB 실측 기준)

```
- 7/31: close 311.23, raw -55, adjusted -55 (Δ +25), avoid — …
    | 이벤트: cRSI Hook Up | 변화: cRSI 32.7→38.1 상승 | 신규진입: no
- 8/03: close 321.05, raw -75, adjusted -75 (Δ -20), avoid — …
    | 변화: cRSI 38.1→44.1 상승 | 신규진입: no
- 8/04: close 361.67, raw 85, adjusted 70 (Δ +145), hold — …
    | 이벤트: Supertrend 매수 전환 | 변화: supertrend +65 개선, minervini +45 개선 | 신규진입: no
```

- 7/31: Hook Up 발생이 이벤트로 명시(숨기지 않음).
- 8/03: Hook Up 롤오프(−20) 억제 → 실제 지표 상승(38.1→44.1)만 표시. 유령 "악화" 제거.
- 8/04: Supertrend 매수 전환이 이벤트로 명시.
- `이벤트:` 세그먼트는 `변화:` 앞에 두고, 이벤트가 없는 날은 세그먼트를 생략한다.

## 변경 범위

| 파일 | 변경 |
|------|------|
| `src/tools/technical/models.py` | `ScoreHistoryPoint.events: list[str]` 필드 추가 |
| `src/tools/technical/scorer.py` | `_top_component_changes` 재작성(트랙 2·3), 당일 이벤트 추출 헬퍼 추가, 연속 컴포넌트 레지스트리 추가, `_build_score_history`에서 events 채우기 |
| `src/pipelines/quick_check.py` | compact/detailed 포맷터에 `이벤트:` 라인 추가 |

점수/verdict/컴포넌트 스코어링 파일(aggregator.py, context.py, components/*.py)은 변경 없음.

## 테스트

- 단위: 당일 이벤트 추출(온셋 판정, 첫 포인트 처리), 연속 지표 서술(임계값 경계),
  롤오프 억제(이벤트 소멸 vs 실제 상태 변화 구분).
- 골든: ALAB 7/29–8/04 시나리오를 fixture로 고정해 트랙 1·2·3 출력 전체를 검증.
  특히 8/3에 crsi "악화"가 없고 `cRSI 38.1→44.1 상승`이 나오는지, 7/31·8/4에
  이벤트가 노출되는지 고정.

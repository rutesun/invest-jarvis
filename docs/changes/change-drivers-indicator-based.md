# Change Record: 지표값 기반 change_drivers + 당일 이벤트 노출

**Status**: Draft
**Date**: 2026-08-06
**PRs**: #{PR 번호}
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

`jarvis check`의 "최근 점수 추이" 서술이 컴포넌트별 **점수 델타**를 그대로 보여줘, 일회성 이벤트 점수의 롤오프를 유령 신호로 오표기했다. 예: cRSI Hook Up(+20)은 밴드 돌파일 하루만 붙는데, 다음 날 점수가 0으로 복귀하면 Δ 엔진이 `0-20=-20`을 계산하고 "crsi 악화"로 라벨링한다 — 실제 cRSI는 계속 상승 중인데도(ALAB 8/3: cRSI 38.1→44.1) 지표 방향과 정반대 서술이 나왔다. 이 결함은 일회성 이벤트를 가진 모든 컴포넌트(supertrend 매수/매도 전환 등)에서 이벤트 발생 다음 날 반복 발생했다.

## What

1. **change_drivers를 지표값 기반으로 재작성** (`scorer.py:_top_component_changes`): 컴포넌트를 두 부류로 나눠 서술한다. 연속 지표 컴포넌트(crsi·velocity)는 점수 델타 대신 실제 지표값 변화로 서술하고, 이산 컴포넌트는 점수 델타를 유지하되 순수 롤오프를 억제한다. 컴포넌트마다 "실제값"의 성격이 이질적이라(crsi는 연속 오실레이터, supertrend는 방향 전환) 전면 통일 대신 연속 지표만 지표값화하는 범위를 선택했다.
2. **연속 컴포넌트 레지스트리** (`_CONTINUOUS_COMPONENTS`): crsi(metric `crsi`, 임계값 3.0, 라벨 `cRSI`, 무부호 소수1), velocity(metric `norm_slope`, 임계값 0.02, 라벨 `SMA20 기울기`, 부호표기 소수2, 접미사 `%`)를 표로 관리. 두 컴포넌트 모두 이미 `metrics`에 값을 노출해 추가 배관이 없다. 임계값 미만 미세 변동은 노이즈로 생략, 부호 전환 시엔 임계값과 무관하게 "상승전환/하락전환"으로 표기.
3. **순수 롤오프 억제** (`_is_pure_rolloff`): 이산 컴포넌트 델타는 `disappeared(전일−당일 signals)`가 있고 `appeared(당일−전일)`가 비어있는 경우만 억제. 새 signal 발생이나 signal 변화 없는 조용한 점수 이동은 유지한다. 억제해도 지속 상태는 `driver_components`에, 당일 이벤트는 아래 events에 남아 정보 손실이 없다.
4. **당일 발생 이벤트(events) 노출** (`ScoreHistoryPoint.events`, `_daily_events`): 롤오프는 억제하되, 그날 새로 켜진 신호(전일 signals에 없던 온셋)를 `이벤트:` 세그먼트로 숨김 없이 표시한다. Hook Up/Down, Supertrend 전환, Pocket Pivot 등이 잡히며, 히스토리 첫 포인트는 빈 리스트.
5. **fallback으로 회귀 안전성 확보**: 연속 컴포넌트라도 `metrics`가 없으면 이산 델타 경로로 진입하게 해, 기존 점수-델타 서술 테스트를 무변경으로 통과시킨다.
6. **점수 추이 멀티라인 출력** (`quick_check.py:_format_compact_history_point`): `check` 기본 출력이 한 줄에 모두 담겨 길어지던 것을, 헤더(날짜·close·raw·adjusted·Δ·신규진입) 아래에 `action — reason`·`이벤트`·`변화`를 하위 라인으로 분리했다. `신규진입`을 헤더로 올리고, 진입 여부가 불명(`new_entry_allowed=None`)이면 헤더에서 생략.

## Before / After

```
Before (ALAB 8/3, cRSI 38.1→44.1 상승 중):
- 8/03: ... adjusted -75 (Δ -20), avoid | 변화: crsi -20 악화 | 신규진입: no

After:
- 7/31: ... adjusted -55 (Δ +25), avoid | 이벤트: cRSI Hook Up | 변화: cRSI 32.7→38.1 상승 | 신규진입: no
- 8/03: ... adjusted -75 (Δ -20), avoid | 변화: cRSI 38.1→44.1 상승 | 신규진입: no
- 8/04: ... adjusted  70 (Δ +145), hold | 이벤트: Supertrend 매수 전환 | 변화: supertrend +65 개선, minervini +45 개선 | 신규진입: no
```

## Impact

- `jarvis check`의 "최근 점수 추이" 출력에 `이벤트:` 세그먼트가 추가되고, crsi·velocity 변화가 점수 대신 지표값으로 표기된다. 이벤트 없는 날은 세그먼트 생략.
- 각 날짜가 헤더 1줄 + 하위 라인(action/reason·이벤트·변화)의 멀티라인으로 출력된다(기존 단일 라인 → 멀티라인).
- **점수·adjusted_score·technical_verdict·컴포넌트 스코어링 로직은 불변**이다. 서술(narration) 레이어만 변경 — 액션 판정과 진입 허용 여부는 그대로다.
- `ScoreHistoryPoint.events`는 `default_factory=list`라 기존 직렬화 소비자(deep_dive `model_dump`, LLM 프롬프트)를 깨지 않는다. LLM에는 새 키가 추가로 흘러가지만 파싱을 깨지 않는다.
- 마이그레이션·환경변수 변경 없음.

## Constraints

- **연속 지표만 지표값화**: supertrend 방향 전환·minervini stage·volume·patterns 등 이산 이벤트는 점수 델타를 유지(롤오프만 억제)한다. 이산 신호는 "발생/소멸"이 본질이라 지표값 델타로 바꾸면 억지스럽다는 판단.
- **롤오프 서술 처리는 "억제" 채택**: "신호 종료"로 재라벨하는 대안은 기각. 종료된 일회성 이벤트는 노이즈에 가깝고 지속 상태는 이미 `driver_components`에 나오기 때문. 단, 당일 발생 이벤트는 `이벤트:`로 별도 노출해 이력을 보존한다.
- **표시 캡**: 이산 드라이버는 상위 2개 + `기타`로 캡, 연속 드라이버는 crsi·velocity 2개로 상한이 고정돼 한 날짜 최대 5줄로 유한.
- `_format_continuous`의 `prev_val==0` 정확 일치 엣지는 threshold 기준만 적용되며 별도 테스트 없음(실무 빈도 극히 낮음) — 후속에서 필요 시 처리.

## Related

- 설계: `docs/superpowers/specs/2026-08-05-change-drivers-indicator-based-design.md`
- 계획: `docs/superpowers/plans/2026-08-05-change-drivers-indicator-based.md`
- ADR: 없음
- FEATURES.md: 해당 없음 (기존 "Unified Technical Analysis Contract" 기능의 서술 개선)
- 후속: 없음

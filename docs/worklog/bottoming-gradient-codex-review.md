# Codex 독립 리뷰 — 바닥 그라데이션 (2026-09-14)

도구: `codex exec --sandbox read-only` (GPT 계열, 코드 직접 열람). 판정: **FAIL (High 4, Medium 2)**.
아래는 codex 지적 + 우리 측 재검증(동의/이견).

## 지적과 재검증

1. **[High] 하락 추세 삼중 카운팅** — **동의(핵심).**
   minervini(이평위치, -20 고정) + velocity(SMA20 기울기, 최대 -35) + supertrend(방향, -25) +
   risk(SMA50·ST 중복 -5씩)가 같은 "하락 추세"를 독립 점수처럼 합산. 9/2는 종가 217.3이
   SMA150(216.2)을 탈환했는데도 minervini 점수는 binary(Stage2=40/above50=25/else −20)라
   150선 탈환이 전혀 반영 안 됨 → RAW −80. 사용자 지적의 근원.

2. **[High] 그라데이션이 아니라 또 다른 hard threshold** — **부분 동의.**
   신호 2→3개 순간 bonus 0→~30 급증. 게다가 8/20(적격,−30 accumulate)→8/21(비적격,−90 avoid)은
   raw 변화(−30)보다 adjusted 변화(−60)가 더 커서 **경계에서 오히려 변동성 증폭**. 이건 실제 결함.
   단 "9/3→9/4 급점프 미해결"은 의도된 것(SMA50 위=확인 구간, 불blunt 원칙).

3. **[High] 가점이 기존 신호 재카운팅(double count)** — **동의.**
   momentum_improving = velocity의 slope_change 재사용(velocity가 이미 채점). bullish_divergence =
   divergence 컴포넌트가 이미 raw에 +10~15 반영한 신호를 bottoming이 다시 +10. higher_low도
   실제 swing low 비교가 아니라 고정창 최솟값 비교 → dead-cat 취약(10/30·MIN3로 완화했으나 근본은 아님).

4. **[High] new_entry_allowed 경계 미보장** — **부분 동의.**
   aggregator 내부는 막지만 Brief/CLI는 action만 노출, 금지 상태 미표시. analyze_decision factor=5는
   bias=neutral이라 "매수 leader"까지 간다는 건 과장이나, 경계 케이스 기여 가능성은 존재.
   "accumulate(매집)"라는 명칭이 "관찰 전용" 의미와 충돌 — 명칭 재고 타당(예: watch_bottoming).

5. **[Medium] SMA50 미계산 vs 아래 미구분** — **동의(경미).**
   SMA50=None이어도 close_above_sma50=False → "아래"로 간주. 40~49bar면 higher_low/volume_dry는
   계산돼 SMA50 없는데 가점 가능. 실사용은 200bar+라 영향 작지만 가드 공백.

6. **[Medium] 튜닝셋=검증셋(홀드아웃 없음)** — **동의(방법론).**
   BE/LULU/NVDA로 튜닝하고 같은 데이터로 회귀 검증. out-of-sample 일반화 미검증. NVDA는 SMA50
   위라 자동 제외돼 변별력 낮음.

## codex 우선순위 제안
- P0: aggregator에서 trend family(minervini/velocity/supertrend) 정규화·합산 상한, risk 중복 벌점 제거.
- P0: velocity 상태(기울기 음수)와 이벤트(하락 전환점 −15) 분리 — 반등일 stale 이벤트 처리.
- P1: bottoming을 additive 점수 대신 `watch_bottoming` 상태로 분리(진짜 swing low, 지속일, hysteresis).
- P1: 모든 consumer에서 new_entry_allowed 강제, 명칭 재고.
- P2: 홀드아웃 종목·국면으로 검증, 일일 최대 delta·지속성 테스트 추가.

## 우리 종합 판단
- 근본 원인은 **원본 점수의 추세 중복 카운팅 + velocity lag 아티팩트**. 현재 바닥 가점은 그 위의
  band-aid. 사용자 비판("점수가 도움이 안 된다")은 원본 레이어에서 타당.
- 가장 레버리지 큰 수정: velocity 상태/이벤트 분리 + trend family 중복 제거(9/2 −80 같은 착시 해소).
  이건 밴드 전체 재보정을 수반하는 큰 작업 → 별도 결정 필요.

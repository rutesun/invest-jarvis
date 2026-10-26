# Strategy 누적 구현 커밋 독립 리뷰

## 판정

원 리뷰: **수정 필요 — Critical 0 / Important 2 / Minor 0.**

현재 후속 상태(2026-10-22): 두 지적사항 모두 수정·검증했다. 각 수정의 독립 리뷰는 Spec PASS / Quality 승인(C0/I0/M0), 최신 전체 테스트는 2,193개 통과다. 원 리뷰와 수정 범위의 재검토를 구분하며, 전체 branch의 새로운 merge 승인을 뜻하지 않는다.

검토 대상은 `8c604029cae774f5bdd802a1cb98dc6aba0783f4..67d96416138d24bbbfdfd88ad8868f42154d2687`의 누적 구현 전체다. 이전 -1 ATR 부분 리뷰와 별도로 새 에이전트가 read-only로 수행했다. 리뷰 당시 두 지적사항은 미수정이었다. 후속 수정 상태는 아래에서 구분하며 push/merge는 하지 않았다.

## Important 1 — 복수 Entry의 대표 source 선택 불일치

같은 날 여러 Entry가 발생하면 detector는 높은 우선순위부터 정렬하지만 EntryOpportunity는 마지막 Entry를 선택한다. PositionPlanner는 높은 우선순위 Signal을 선택하고 source 일치를 요구하므로, `ALLOW`가 표시돼도 매수 제안이 누락된다.

- 근거: `src/strategies/entry_opportunity.py:264`, `src/strategies/swing_w150/signals.py:967`, `src/position/policy.py:37`.
- 재현: 저장 실제 `tests/fixtures/swing_w150/COIN.csv`의 2022-07-22~2024-07-22 502봉과 명시적 synthetic bull benchmark를 실제 adapter·Planner로 평가했다. 충분한 계좌·risk·현재가 입력도 제공했다.
- 실제: current Signal은 `PULLBACK_REVERSAL_ENTRY`, `TREND_BREAKOUT_ENTRY`; Opportunity는 돌파 source의 `ALLOW`, Planner는 `KEEP_CURRENT / buy=0 / AVAILABLE`.
- 기대: 같은 날 우선 Entry를 대표 source로 평가하고, 그 source가 ALLOW이면 매수 후보로 연결한다.
- 수정 방향: Planner의 exact source guard를 유지하고 대표 Entry 선택 규칙을 일치시킨다. adapter→Opportunity→Planner 통합 회귀가 필요하다.

## Important 2 — 새 돌파선 지지 Signal의 Backtest 소비 누락

명시 V2 연구용 support ladder는 `PRIOR_BREAKOUT_LEVEL`을 근거로 정상 눌림목 진입 Signal을 생성하지만, Backtest의 지지 Evidence 목록에는 이 종류가 없다. 해당 Signal에서 초기 stop 계산이 실패해 연구 실행이 중단된다. 기본 운영 Pullback V1에는 직접 영향이 없다.

- 근거: `src/backtest/swing_w150.py:41`, `src/backtest/swing_w150.py:161`, `src/strategies/swing_w150/signals.py:433`.
- 재현: 실제 COIN.csv 전체, `explicit_research_parameters()`, 비용·슬리피지 0, risk_target=100, 첫봉 warmup·249번봉 test_start·마지막봉 test_end, raw 거래일을 expected_sessions로 public `simulate_swing_v2()`에 전달했다. Signal history는 주입하지 않았다.
- 실제: 2024-11-11의 실제 생성 `PULLBACK_REVERSAL_ENTRY`에서 `ValueError: Missing pullback support evidence`.
- 기대: 선택한 parameter version의 정상 FINAL Signal을 기존 stop·비용·lot 계약으로 실행한다.
- 수정 방향: 선택한 support anchor Evidence의 detector/Backtest 계약을 맞추고 실제 돌파선 지지 경로 회귀를 추가한다.

## 검증과 범위

- root 커밋 직전 전체: `uv run pytest` 2,158 passed / 15 deselected / 기존 warning 2건, 179.12초.
- root: src/tests/연구 script Ruff, staged diff 검사, 커밋 후 CLI help와 제품·테스트 불변 확인 PASS.
- 독립 reviewer: 관련 9개 focused suite 277 passed / 기존 warning 2건, 6.82초. 전체 diff 검사 PASS, runtime Strategy history 참조 없음.
- 116파일 inventory를 runtime/coverage, Signal·Opportunity, Planner·Backtest, Observation·Shadow, renderer, 연구·문서로 나누어 검토했다. 남은 제품·script 변경 38경로는 본문 또는 작은 diff, 삭제된 Strategy 저장 7경로는 제거 효과와 consumer 경계를 확인했다. 모든 테스트·과거 문서의 모든 줄을 정밀 검증했다는 의미는 아니다.
- chart-only 책임, 실제 보유 분리, Shadow 실패 격리, ATR source 고정·FINAL terminal·PROVISIONAL 회복 경계는 확인했다.
- 전략 수익성·parameter 최적성·failure/restart 운영 선정, 새 live 시세·실계좌·실제 DB, 전체 frozen calibration 재수행은 판단 범위에서 제외했다.
- 리뷰 과정에서 파일·제품 코드를 수정하지 않았다. 이 문서는 결과를 받은 coordinator가 기록한 후속 문서다.

## 후속 — Important2 수정·재검증 (2026-10-21 23:33)

- 사용자 요청으로 Backtest의 허용 지지 목록에 `PRIOR_BREAKOUT_LEVEL`을 추가했다. 제품 변경은 1줄이며 stop 공식·source ATR·finite 방어·T+1·비용·lot/R과 기본 V1은 유지했다.
- 수정 전 신규 positive 회귀 2개가 `Missing pullback support evidence`로 실패했다. 수정 후 합성 stop103·주당 risk7·17주와 실제 COIN raw→detector→11/12 시가 2주 체결을 검증했다. 누락·None·NaN·±Inf 거부도 유지한다.
- root가 원래 실패한 COIN 전체 1,371봉을 Signal 주입 없이 실행해 2026-09-28까지 완료하고 해당 실제 체결을 확인했다. 새 시장 조회나 연구 profile 선정은 하지 않았다.
- Backtest focused 61개, root 전체 2,165개 통과(15제외·기존 경고2, 190.26초). Ruff·format·diff 검사 통과. 새 scoped reviewer는 두 수정 파일에 Spec PASS / Quality 승인(C0/I0/M0), 메모리 mutation으로 신규 positive 회귀 2개의 실패도 확인했다.
- Important2는 수정·검증 완료, Important1은 미수정이다. 이번 후속 변경은 미커밋이며 전체 branch merge 승인으로 확대하지 않는다.

## 다음 행동

사용자 지시 후 후속 수정의 commit 등 통합 작업을 진행한다. 현재 두 수정은 미커밋이며 push/merge는 실행하지 않았다. 운영 V2 승격이나 연구 parameter 재선정은 포함하지 않는다.

## 후속 — Important1 공통 대표 선택·재검증 (2026-10-22 11:06)

- 사용자 승인으로 최신 Entry 발생일을 먼저 고르고 동일일에는 과열후회복→눌림목반등→추세돌파→바닥회복 순을 적용한다. 이 순위는 대표 선택용이며 수익성 우열은 미검증이다.
- chart-only 공통 selector를 Opportunity와 Planner가 공유한다. 먼저 대표를 선택한 뒤 유효성을 평가하며, 차단/종료됐다고 하위·과거 source로 우회하지 않는다. 오늘 ALLOW·exact source guard, 청산/50% 축소 우선, history·ID와 source-local −1ATR/terminal 규칙은 보존했다.
- root의 수정 전 실제 COIN 502봉 재현은 두 Entry가 존재하지만 source TREND·ALLOW·KEEP_CURRENT·buy0이었다. 같은 raw/명시 synthetic bull benchmark/테스트 계좌로 수정 후 source PULLBACK·ALLOW·BUILD_ONLY_TO_RISK_TARGET·buy50을 확인했다. 새 live 데이터·Signal 주입·실제 주문은 없다.
- 신규 회귀 RED12실패→핵심28통과→covering199통과. frozen product21개에서 대표 source 변경은 INTC 1개이며 non-gate 전체와 source/anchor 외 gate를 보존하는 좁은 기대값 비교를 추가했다. 기존 −1ATR 비교와 원본 artifact는 유지했다.
- root 전체 `uv run pytest`: **2,193 passed / 15 deselected / 기존 warning2 / 191.01s**, exit0. src/tests/연구 script Ruff·변경Python8 format·diff·CLI help 모두 통과했다. 기존 Backtest 제품/테스트 hash는 이전 승인 상태 그대로다.
- 새 독립 reviewer는 제품·테스트6개와 필요한 bundle/adapter 경계를 검토해 Spec PASS / Quality 승인(C0/I0/M0)을 반환했다. snapshot hash가 일치하며 중복 suite는 실행하지 않았다. 정상 detector 계약 밖의 동일일·동일code 복수 identity는 새 정책으로 확장하지 않았다. 새 수익성 연구, 전체 누적 branch 재리뷰와 live 세 pipeline 실행은 이번 검증 범위가 아니다.

# 대표 Entry 선택 통일 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 같은 날 복수 Entry의 대표 source가 Opportunity와 PositionPlanner에서 일치하도록 한다.

**Architecture:** Strategies 계층의 chart-only 공통 선택 함수를 두 소비자가 재사용한다. 최신 발생일을 먼저 선택하고 같은 날만 type 우선순위를 적용한다. detector의 사건 생성과 history는 바꾸지 않는다.

**Tech Stack:** Python, Pydantic, pytest, uv, Ruff.

**Spec:** `docs/superpowers/specs/2026-10-06-strategy-signal-outcome-backtest-boundary-design.md` §7.4, §8 및 2026-10-22 사용자 승인.

## Global Constraints

- Entry 순서: POST_OVERHEAT_RECOVERY_ENTRY → PULLBACK_REVERSAL_ENTRY → TREND_BREAKOUT_ENTRY → DEEP_RECOVERY_ENTRY. 수익성 순위가 아닌 대표 선택 규칙이다.
- 가장 최근 Entry 날짜가 type 순위보다 우선한다. 미래 Signal은 Opportunity 후보에서 제외한다.
- 모든 Signal 및 ID/fingerprint, detector, Observation, source별 terminal/−1ATR 조건을 유지한다.
- 먼저 대표를 고른 뒤 유효성을 평가한다. WATCH/BLOCK/INVALIDATED/EXPIRED/NOT_EVALUATED를 이유로 하위 또는 과거 source로 우회하지 않는다.
- Planner의 오늘 Signal·오늘 ALLOW·exact source ID guard와 SMA150_EXIT → OVERHEAT_CORRECTION → Entry 안전 우선순위를 유지한다.
- Strategy는 position을 import하지 않는다. 실제 보유/DB/가상 거래 입력을 추가하지 않는다.
- 기존 미커밋 Backtest 수정과 무관한 dirty/untracked를 보존한다. 이 작업에서 commit/push/merge, 새 provider 조회를 하지 않는다.
- 코드는 별도 구현자가, 문서 및 최종 검증은 coordinator가 담당한다. 자식 에이전트의 추가 위임은 하지 않는다.

## Review Focus

- 같은 날 두 Entry의 입력 순서를 뒤집어도 대표가 같아야 한다.
- 과거의 높은 순위 Entry보다 최신의 낮은 순위 Entry가 우선해야 한다.
- 최신 대표가 무효/차단돼도 하위·과거 source로 대체하지 않는다.
- 실제 COIN의 동시 눌림목/돌파가 adapter→Opportunity→Planner에서 일치하고 양의 매수 수량으로 연결돼야 한다.
- 청산/50% 축소 우선, exact source guard, source별 −1ATR 및 PROVISIONAL 경계는 유지돼야 한다.

---

### Task 1: 공통 대표 선택과 소비자 통합 회귀

**Files:**
- Create: `src/strategies/signal_selection.py`
- Modify: `src/strategies/entry_opportunity.py`, `src/position/policy.py`
- Test: `tests/strategies/test_entry_opportunity.py`, `tests/position/test_policy.py`, `tests/strategies/swing_w150/test_adapter.py`

**Interfaces:**
- Consumes: `Sequence[StrategySignal]`, `date | None` 평가일.
- Produces: `select_latest_entry_signal(signals: Sequence[StrategySignal], *, as_of: date | None = None) -> StrategySignal | None` in `src/strategies/signal_selection.py`.
- `evaluate_signal_entry_opportunity`는 기존 completeness guard 이후 이 함수로 source를 선택한다.
- `select_current_signal`은 기존 exit/correction 우선을 유지한 뒤 이 함수로 Entry를 선택한다. 입력은 기존처럼 current_signals이다.
- 동일 날짜/동일 code의 복수 identity는 정상 detector 계약 밖이며 별도 새로운 거래 정책을 추가하지 않는다.

- [x] Step 1: 순서 반전, 최신일 우선, 미래 제외, 최신 대표 무효 시 fallback 금지의 consumer-visible 테스트를 먼저 작성한다.
- [x] Step 2: 신규 핵심 회귀를 실행해 기존 마지막-entry 선택 때문에 실패함을 기록한다. RED는 잘못된 source 또는 매수 누락이어야 한다.
- [x] Step 3: 공통 선택 함수를 구현하고 두 소비자가 재사용하도록 최소 변경한다. detector/history를 수정하지 않는다.
- [x] Step 4: 실제 `tests/fixtures/swing_w150/COIN.csv`의 `2022-07-22:2024-07-22` 502봉을 사용한 adapter→Opportunity→Planner 회귀를 추가한다. 시장 gate는 명시적인 synthetic bull benchmark, 계좌는 충분한 capital/risk, 현재 snapshot은 같은 세션의 종가를 제공한다. Signal은 주입하지 않는다. 당일 두 code를 모두 보존하고 source PULLBACK_REVERSAL_ENTRY, ALLOW, BUILD_ONLY_TO_RISK_TARGET, buy_quantity>0을 검증한다.
- [x] Step 5: 기존 exact source mismatch, 당일 EXIT/50% correction, terminal/−1ATR 및 Observation 독립성 테스트를 유지한다.
- [x] Step 6: `uv run pytest tests/position tests/strategies/test_entry_opportunity.py tests/strategies/swing_w150/test_adapter.py -q`와 변경 Python Ruff/format을 실행한다. covering tests와 RED/GREEN 수치·제한을 report에 남긴다. 전체 `uv run pytest`는 coordinator가 최종 제품 상태에서 수행한다.
- [x] Step 7: 구현자 self-review 후 수정 파일·테스트 결과·우려사항을 report에 기록하고 종료한다. commit하지 않는다.

## Coordinator 검증·기록

- [x] 합의된 정책을 worklog에 기록하고 FEATURES/change-record/기존 설계의 충돌 문구를 갱신한다.
- [x] 독립 reviewer에 제품·테스트 diff와 요구사항을 전달하고 Spec/Quality 두 판정을 받는다.
- [x] 전체 `uv run pytest`, Ruff, 변경 파일 format, `git diff --check`를 실행한다.
- [x] Important1/2의 현재 상태와 검증 제한을 reference/active-context에 반영한다. commit/push/merge는 하지 않는다.

# Breakout 1 ATR Invalidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. 승인된 단일 규칙의 작은 변경이며 commit/push/merge는 하지 않는다.

**Goal:** TREND_BREAKOUT_ENTRY의 돌파 기준선에서 source 당시 ATR 1배 이상 하락하면 기존 진입 기회를 종료한다.

**Architecture:** 기존 chart-only EntryOpportunity의 terminal 재계산에 가격 이탈을 추가한다. 지표는 기존 Technical feature를 재사용하고 source 날짜의 돌파선·ATR을 고정한다. Signal/Score/보유·주문/Shadow 정책은 변경하지 않는다.

**Tech Stack:** Python, Decimal, pandas, Pydantic, pytest, uv.

**Spec:** 이 문서의 Approved Rule은 사용자가 2026-10-21 확정한 소규모 설계다.

## Approved Rule / Global Constraints

- 대상은 이번 대화에서 검토한 `TREND_BREAKOUT_ENTRY`다. 다른 Entry 유형으로 임의 확대하지 않는다.
- source 돌파선 = `Trend_Breakout_High_Prev`(당일 제외 직전 50거래일 High 최대값), source ATR = 기존 `ATR`(14) 값.
- source 다음 봉부터 `bar.close <= breakout_level_at_signal - 1.0 * atr_at_signal`이면 `INVALIDATED`다. 고가/저가 접촉이나 다음날 시가, Signal 종가를 기준으로 삼지 않는다.
- source ATR과 돌파선은 이후 데이터로 바꾸지 않는다. 배수는 이름 있는 조정 지점으로 둔다. 불필요한 설정 모델을 추가하거나 SWING parameter payload/Signal ID를 바꾸지 않는다.
- FINAL breach는 source-local terminal로 유지한다. PROVISIONAL breach는 PROVISIONAL로 표시하며 동일 장중 봉이 회복되면 재계산으로 해소할 수 있다.
- 기존 최초 FINAL terminal·explicit exit 우선·age 20/21·latest-source/no-fallback 계약을 유지한다. 같은 날 새 가격 failure는 explicit exit 뒤, expiry 앞 순서다.
- 새 Entry Signal은 새 window다. 기존 실패를 새 Signal에 전파하지 않는다.
- 판정 불가능한 source ATR/돌파선은 조용히 ALLOW 하지 않는다. 기존에 이미 확인 가능한 terminal이 있으면 기존 terminal을 보존한다.
- 가격 failure를 가짜 StrategySignal로 만들지 않는다. `invalidated_by=None`일 때에도 정확한 reason과 종료 날짜·finality를 제공한다.
- Production policy version을 새 규칙으로 구분한다. 기존 research artifact·Signal history·frozen 실험 결과는 덮어쓰지 않는다.
- 실제 계좌·PositionPlanner 매도·Strategy DB를 추가/변경하지 않는다. 외부 시세/LLM 호출 없이 저장된 ALAB 입력을 재사용한다.
- dirty 작업은 모두 보존하며 이 작업의 순증분만 리뷰한다. commit/push/merge 및 baseline 삭제는 금지한다.

## Review Focus

- 정확히 -1 ATR인 경계와 직전 가격: 이하에서만 실패하는지.
- 하락 중 ATR 상승과 이후 가격 회복: source anchor가 바뀌거나 FINAL 실패가 부활하는지.
- explicit exit/만료/가격 failure의 시간 순서와 FINAL/PROVISIONAL 우선순위.
- 새 눌림목 Signal, Observation/Shadow ON/OFF, source별 Observation context의 종료 원인이 정상인지.
- 세 pipeline 공통 renderer에 unknown Signal/ENTRY_EXPIRED 같은 잘못된 원인이 표시되는지.

### Task 1: Production gate·배선·사용자 출력·회귀 테스트

**Files:** `src/strategies/entry_opportunity.py`, `src/strategies/swing_w150/adapter.py`, `src/pipelines/strategy_render.py`; 관련 `tests/strategies/`, `tests/pipelines/`; 필요시 직접 evaluator를 호출하는 `scripts/research_trading_observations.py`의 입력 배선만 정합성 보완. `docs/FEATURES.md`, 기존 `docs/changes/scorecard-strategy-position-separation.md`와 worklog는 결과에 맞게 갱신한다.

**Interfaces:** 기존 evaluator의 세 positional 인자는 유지한다. 필요시 keyword-only `features: SwingFeatureFrame | None = None`를 추가하고 adapter의 대표 source 및 Observation source 평가 모두에 같은 feature를 넘긴다. 지표 계산을 복제하지 않는다.

- [ ] 기존 관련 테스트를 실행해 baseline을 확인한다.
- [ ] 실패 테스트부터 작성한다: 경계 위/동일/아래, source ATR 고정, FINAL 실패 후 회복, PROVISIONAL 실패 후 수정, source-only reset, expiry/explicit exit 순서, anchor 부족, 비대상 Entry 유지.
- [ ] `uv run pytest`의 해당 신규 테스트로 기존 구현이 ALLOW를 반환하는 실패를 기록한다.
- [ ] 기존 terminal 처리에 최소 변경으로 가격 failure를 추가하고 adapter·renderer·Observation source context를 연결한다. 새 reason은 `BREAKOUT_ATR_INVALIDATED`로 사용하며 가격·돌파선·source ATR·배수·취소선을 evidence로 제공한다.
- [ ] 직접 호출 consumer에 feature 배선이 필요한지 확인한다. 다른 연구 규칙이나 결과를 변경하지 않는다.
- [ ] 실제 adapter/공통 renderer를 통해 조건과 한국어 원인이 전달되는 테스트를 추가한다.
- [ ] focused tests와 `uv run pytest` 전체, 변경 Python Ruff/format, diff 검사를 실행한다.
- [ ] 저장된 `tmp/alab-validation-20261021.sfj1jr/chart-bundle.json`으로 실제 adapter를 재실행한다. 기존 $377.8699951171875, ATR $22.97301577054907, 취소선 $354.89697934663843과 INVALIDATED 및 최초 이탈일을 확인한다.
- [ ] 사용자 문서·worklog 갱신, self-review, report 작성. commit하지 않는다.

## Controller Verification

- [ ] 구현 전 snapshot과 순증분을 비교하고 독립 spec/quality 리뷰를 진행한다.
- [ ] ALAB 최신 prefix의 결과·최초 실패 날짜·공통 출력이 일치하는지 직접 확인한다.
- [ ] 검증 수치·정책 범위·미수행 git integration을 사용자에게 보고한다.

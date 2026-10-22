# EntryOpportunity Production v1 + Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking. 기존 dirty checkout을 보존하며 commit/push/merge하지 않는다.

**Goal:** 기존 신규 진입 판정을 유지하면서 source별 종료 계약, 독립 Risk/Shadow 진단과 분석용 기록을 실제 제품에 연결한다.

**Architecture:** Production은 차트 prefix에서 source와 최초 FINAL terminal을 결정적으로 재구성한다. 별도 Shadow evaluator가 frozen anchor와 후속 차트만 읽는다. 파이프라인이 진단을 표시하고 JSONL 연구 기록을 남기며 이 기록을 Strategy가 읽지 않는다.

**Tech Stack:** Python, Pydantic, pandas, pytest, uv, JSONL.

**Spec:** `/Users/al03229901/Downloads/EntryOpportunity v1 제품 적용 + Shadow Research 구현 지시.md`

## Global Constraints

- Production age 20봉과 extension +5%는 기존 임시 운영 기본값으로 유지한다. adverse 하한을 새 gate로 추가하지 않는다.
- 기존 `SMA150_EXIT`, `OVERHEAT_CORRECTION`만 explicit invalidator로 유지한다. 최초 FINAL terminal은 이후 사건으로 바뀌거나 부활하지 않는다.
- 최신 eligible source가 terminal이어도 old source fallback 금지. 새 source는 새 window.
- PROVISIONAL 신규 평가 허용. 과거 FINAL terminal 불변. Shadow의 finality도 명시.
- 3 ATR, initial 5 bars, reclaim 3/5, 2 closes는 Shadow 가설이며 Production에 연결 금지.
- Signal/Score/Observation/Planner/Backtest 의미 변경 금지. 실제 보유·수량·stop은 Opportunity 책임 밖.
- 기존 WATCH enum 값은 호환 보존; 사용자 출력에서 EXECUTION_WATCH로 설명.
- Production policy `SWING_W150_ENTRY_OPPORTUNITY_PRODUCTION_V1`; Shadow policy `WATCH_RECLAIM_SHADOW_V1`.
- `uv` 사용. apply_patch 편집. 기존 dirty 파일·연구 worktree 보존. commit/push/merge 금지.

## Review Focus

- expiry 후 늦은 invalidator가 EXPIRED를 INVALIDATED로 덮어쓰지 않는지.
- 같은 날 exit 우선 Signal 배열 순서 때문에 invalidator가 누락되지 않는지.
- 최신 PROVISIONAL bar가 과거 FINAL terminal 또는 anchor를 바꾸지 않는지.
- Shadow 실패·비활성·기록 오류가 Production/Planner를 바꾸지 않는지.
- source 지지선 anchor가 현재 이동평균으로 떠다니거나 미래 차트를 읽지 않는지.

### Task 1: Production source lifecycle and anchors

**Files:** Modify `src/strategies/models.py`, `src/strategies/entry_opportunity.py`, `src/strategies/swing_w150/adapter.py`; Create `src/strategies/entry_anchors.py`; Test `tests/strategies/test_entry_opportunity.py`, `tests/strategies/test_entry_anchors.py`.

**Interfaces:**
- `evaluate_signal_entry_opportunity(history, bundle, params)` 기존 signature 유지.
- `EntrySourceAnchors` Pydantic: source_id/date/type, signal_price, atr_at_signal, breakout_level, origin_support, pullback_low (Decimal nullable), anchor_finality, policy_version. Signal identity/evidence 변경 없이 추출.
- `build_entry_source_anchors(source, bundle, features, observation_history)`는 source 날짜까지만 읽는다. features는 `SwingFeatureFrame`. pullback은 해당 resolved observation의 시작 지지선과 시작~source 저가 최솟값. 지지선 후보 여러 개면 observation evidence 순서상 첫 값. 없으면 nullable로 명시한다.
- `SignalEntryOpportunity`에 optional anchors 및 terminal_on/terminal_finality를 추가한다. adapter가 이미 계산한 feature/observation으로 anchors를 붙인다. 오류/직접 호출 호환을 위해 기본값 제공.

- [x] Step 1: TDD — earliest FINAL terminal, same-day invalidator, expiry-before-later-exit, FINAL invalidation after provisional recovery, newest-source/no-fallback, new-source, frozen anchors/prefix invariance 테스트를 추가하고 실패 확인.
- [x] Step 2: source 뒤 날짜의 최초 FINAL invalidator와 최초 age 초과 FINAL session 중 먼저 온 사건을 보존한다. 같은 날짜는 기존 exit 우선으로 INVALIDATED. PROVISIONAL invalidator/expiry는 잠정 표시하되 과거 FINAL terminal을 덮지 않는다. anchor source가 PROVISIONAL이면 그 사실 표시.
- [x] Step 3: 기존 market/extension 판정과 Evidence reason 호환 유지. terminal에서도 가능한 current regime/extension 계산. 새 Production version 부여.
- [x] Step 4: `uv run pytest tests/strategies/test_entry_opportunity.py tests/strategies/test_entry_anchors.py tests/strategies/swing_w150 -q` 통과 확인, TDD 결과와 변경 목록을 report에 기록. commit 금지.

### Task 2: Independent Shadow diagnostics

**Files:** Create `src/strategies/entry_shadow.py`, `tests/strategies/test_entry_shadow.py`; Modify `src/strategies/models.py`, `src/strategies/swing_w150/adapter.py`, `src/strategies/runner.py`; Test `tests/strategies/test_runner.py`.

**Interfaces:**
- Task 1의 `EntrySourceAnchors`, `SignalEntryOpportunity.anchors` 소비.
- `EntryShadowResult`: evaluation_as_of, finality, policy_version, data_status/reason, risk_level (NORMAL/CAUTION/HIGH_RISK; 비평가면 nullable), risk_flags (code/message/finality/evidence), breakout_states/pullback_states, anchors. `StrategySignalBundle.entry_shadow` optional. 미지원 source·anchor 부족을 NORMAL 안전 판정으로 오인시키지 않는다.
- `evaluate_entry_shadow(opportunity, bundle)` 순수 함수. Production 객체를 변경하거나 미래 outcome을 읽지 않는다.
- Shadow의 3ATR/5봉/2연속 설정은 별도 frozen research parameter 객체에 모아 조정 가능하게 하되 Production parameters/fingerprint/Signal ID에는 넣지 않는다. 별도 Shadow fingerprint를 결과·기록에 포함한다.
- `SwingW150SignalStrategy(..., shadow_enabled=True)`와 `StrategyRunner(..., shadow_enabled=True)` keyword 옵션. Shadow 오류는 Production bundle/data_status/eligibility를 변경하지 않고 별도 diagnostic error로 표면화.

- [x] Step 1: TDD — breakout breach→reclaim, large adverse/early failure, support와 low 각각 breach/reclaim, missing anchors, PROVISIONAL, deterministic prefix, failure isolation 테스트 실패 확인.
- [x] Step 2: B1/B4/P1/P2/P3-like 최소 상태 계산. 연구 donor `/Users/al03229901/orca/workspaces/invest-jarvis/price-volume-rule-review/src/strategies/watch_reclaim.py`는 읽기 참고만. source 뒤 완료/잠정 봉을 순차 계산하고 현재 시점 flag로 표시. B4: initial 5 bars와 signal_price−3ATR; P2: support breach 이후 low failure; P3: max(support, low) reclaim과 low 2연속. 연구 failure를 Production terminal로 전파하지 않는다.
- [x] Step 3: 구조 이탈 CAUTION, large/early/severe deterioration HIGH_RISK, reclaim 후 NORMAL + RECLAIMED flag. unsupported source/누락 anchor는 명시적인 비평가 사유. enum/internals 실험명은 주 출력에 강제 노출하지 않는다.
- [x] Step 4: `uv run pytest tests/strategies/test_entry_shadow.py tests/strategies/test_runner.py tests/strategies/swing_w150/test_adapter.py -q` 통과. shadow true/false의 Production model_dump 전체, Signals/Observations/input hashes 비교, report 작성. commit 금지.

### Task 3: Product rendering and research records

**Files:** Create `src/storage/entry_shadow.py`, `tests/storage/test_entry_shadow.py`; Modify `src/pipelines/strategy_analysis.py`, `src/pipelines/strategy_render.py`; Test `tests/pipelines/test_strategy_analysis.py`, `tests/pipelines/test_strategy_coverage.py`, `tests/pipelines/test_entry_shadow_render.py`.

**Interfaces:**
- `EntryShadowJsonlRecorder(path: Path)` with `record(run, bundle, pipeline=...)` consumes Task 2 signal bundles; no storage imports in Strategy.
- `AnalysisStrategyService(..., shadow_recorder=...)` defaults to local `data/research/entry-shadow.jsonl`; explicit `None` disables via sentinel default. `JARVIS_ENTRY_SHADOW_LOG_PATH` optional environment override, documented.
- Versioned decision rows: ticker/date/finality, source_id/type/date/age, production_status/reason/policy, risk_level/flags, shadow version/states, anchors, current close, market regime, extension, execution reference/gap, chart/parameter identity and pipeline. record per represented source per observed trading day; no retrospective outcome data. Append-only evaluation snapshots, consumer dedup key/version/finality explained; no DB or implicit replay reads.

- [x] Step 1: TDD — JSONL fields/Decimal serialization, no future outcome, repeated/provisional/final distinction, unwritable recorder nonfatal with visible warning; service path; default render risk even without today's entry.
- [x] Step 2: append one complete JSON line per decision, create only data subfolder, append writes without rewriting previous policy data. Logging failure emits logger.warning + AnalysisStrategyResult.warning without affecting Production. Default data directory gitignored. Path injectable in tests; do not introduce whole-DB state or migration.
- [x] Step 3: shared renderer used by check/analyze/brief shows status/reason/source/date/age/policy, risk/flag descriptions/finality with statement diagnostic does not gate. Preserve evidence and 5-day scores. WATCH shown EXECUTION_WATCH. No research codes forced into default UI.
- [x] Step 4: `uv run pytest tests/storage/test_entry_shadow.py tests/pipelines tests/position tests/backtest -q` passes. Report task tests, data path and any limitation. commit 금지.

## Controller validation and documentation

- [x] 각 Task 구현 후 read-only task review, 필요한 수정 후 다음 Task.
- [x] 전체 `uv run pytest -q`, targeted lint, actual `jarvis check` 3~5 tickers 및 차트 날짜별 lifecycle 사례 확인. 외부 데이터 coverage 실패를 성공으로 보고하지 않는다.
- [x] 최종 독립 리뷰. 기존 dirty 상태 대비 이번 변경만 review package로 제공.
- [x] `docs/FEATURES.md`, `docs/changes/scorecard-strategy-position-separation.md`, INDEX, `docs/CLI_USAGE.md`, worklog, active-context 갱신. detailed verification in `docs/references/2026-10-19-entry-opportunity-production-shadow-validation.md`.
- [x] 미결 WATCH/failure/source age/gap와 향후 OOS 재평가 기준(실제 수집 event 수/기간은 연구 제안으로 구분)을 보고. 추가 연구/commit/push/merge하지 않는다.

# Trading Observation v1·Pullback 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 차트 사실을 설명하는 Observation을 추가하고, 상승 사이클과 지지선 이동을 기준으로 눌림목을 관찰하되 기존 청산·실제 보유 정책을 보존한다.

**Architecture:** `Technical Evidence → Observation → Signal → EntryOpportunity → PositionPlanner`의 책임을 유지한다. 차트 prefix(해당 거래일까지의 데이터)를 순서대로 재생해 사건·episode·cycle을 복원하며, 보유 장부나 Strategy DB를 읽지 않는다. Observation 추가와 Pullback 정책 변경은 독립적인 비교 대상으로 검증한다.

**Tech Stack:** Python, pandas/numpy, Pydantic v2, pytest, uv, 기존 canonical hash·공통 indicator/pivot 계산.

**Spec:** 아래 원본과 사용자의 최종 직접 결정을 함께 읽는다. 충돌 우선순위는 아래 목록의 역순이다.

1. `/Users/al03229901/Downloads/Trading Observation Model v1 확정 및 구현 지시.md`
2. `/Users/al03229901/Downloads/Trading Observation Model v1 최종 피드백 및 실행 지시.md`
3. `/Users/al03229901/Downloads/Trading Observation Model v1 및 Pullback 구조 최종 실행 피드백.md`
4. `/Users/al03229901/Downloads/Trading Observation v1 — 추가 피드백 반영 실행 결정.md`
5. [사용자가 확정한 INITIAL ACTIVE_UP_CYCLE](../../worklog/trading-observation-v1.md)

**Status:** Task 0~6 및 최종 통합 독립 리뷰 완료. `SPEC_PASS / QUALITY_APPROVED_WITH_DEFERRED_MINOR`, 잔여 C0/I0/M1(연구 모듈 책임 분리 deferred)이다. baseline21·V1/V2별 ON/OFF각21·기존EXIT 동등성, 실제5유형7prefix, 수정후전체2,142테스트와 최종artifact/docs/provenance를 확인했다. failure/immediate/restart는 UNRESOLVED여서 Pullback parameter V1을 유지한다. 명시 V2는 연구·테스트 경로이고 운영 기본값이 아니다. commit/push/merge는 하지 않았다. 최신 검증은 `docs/references/2026-10-21-trading-observation-v1-validation.md`, 단계별 승인은 SDD ledger를 따른다. 아래 체크리스트는 계획 원형이며 완료의 근거와 범위는 task별 report/review에 기록한다.

## Global Constraints

- Score는 독립 측정이다. Observation으로 Technical Score를 가감하거나 Positive/Risk를 합산하지 않는다.
- Strategy는 실제·가상 보유, 진입가, 보유 손익/R, 실제 수량을 입력받지 않는다. 가상 체결·성과는 Backtest, 실제 수량은 PositionPlanner 책임이다.
- Strategy DB/cache를 재도입하지 않는다. 기존 외곽 JSONL 진단 기록은 계산 입력으로 사용하지 않는다.
- 차트 거래일이 사건 기준이다. 실행 시각·실행 빈도로 사건 날짜나 상태가 달라지면 안 된다.
- 실시간 PROVISIONAL을 허용한다. 미완성 봉을 FINAL history나 FINAL terminal에 확정하지 않는다. Backtest는 FINAL만 사용한다.
- `INVALIDATED`/`EXPIRED`인 기존 Opportunity는 reclaim Observation으로 부활하지 않는다. 새 Entry Signal은 새 source/window다.
- 기존 `SMA150_EXIT`의 armed/latch·연속 종가 조건과 Opportunity의 기존 invalidator 우선순위를 변경하지 않는다.
- cycle 종료나 Observation만으로 PositionPlanner의 EXIT/REDUCE/BUY를 생성하지 않는다.
- 최초 cycle의 필수조건은 `FINAL close > SMA150` AND `SMA150 flat or rising`; 확인 조건은 confirmed HH OR valid price breakout OR 독립 bullish Entry Signal 중 하나다.
- SMA50>SMA150, Supertrend UP, SMA50 slope>0, volume expansion, HIGHER_LOW를 최초 cycle의 공통 필수조건으로 추가하지 않는다.
- Correction Mode는 WATCH의 필수조건이 아니다. 현재 Supertrend DOWN·이평선 약화는 Evidence로 설명한다.
- Ladder는 `SUPERTREND / SMA50 / PRIOR_BREAKOUT_LEVEL / SMA150`만 사용한다. SMA100/SMA200과 generic base detector는 추가하지 않는다.
- SMA150은 마지막 방어선이다. 그 failure 이후 하단 breakout/SMA200으로 cycle을 유지하지 않는다.
- Signal ID는 동일 입력·동일 version·동일 설정에서 재현한다. version 간 영구 ID/alias/호환 저장 계층은 만들지 않는다.
- 신규 provider/LLM 호출 없이 로컬 CSV로 연구한다. 추가 데이터가 꼭 필요하면 대상·기간·요청 수를 먼저 제시한다.
- 기존 dirty 변경을 보존한다. `uv`만 사용한다. commit/push/PR/merge는 별도 승인을 받기 전 실행하지 않는다.
- 별도 에이전트가 구현하고 root가 검증·리뷰한다. 작업 중인 파일을 동시에 수정하는 구현 에이전트를 두지 않는다.

## Review Focus

1. 늦게 확인된 pivot과 연속 HH/HL: 실제 pivot 날짜로 소급하거나 boolean 상태를 매일 새 사건으로 중복시키지 않는다. → Task 1 테스트.
2. 같은 날 여러 source/지지선과 동적선 이동: 동일 code라도 사건을 분리하고, zone이 개별 break/reclaim을 덮지 않으며 원 지지선 가격이 바뀌지 않는다. → Task 3·4 테스트.
3. PROVISIONAL failure 후 종가 회복·실행일 누락: FINAL cycle/Observation/Opportunity를 오염시키지 않고 전체 replay와 prefix replay가 일치한다. → Task 3·4 테스트.
4. cycle 종료·다음날 근접·같은 날 exit/reversal: 과거 상승 이력으로 재활성화하지 않고, cycle failure가 기존 EXIT 조건이나 실제 매도 권한을 바꾸지 않는다. → Task 4·5 테스트.
5. source 없음·정보 부족·설정 변경: 일반 구조/거래량 Observation은 계속 계산하고, 부족한 근거를 정상/안전으로 표현하지 않으며 Observation ON/OFF가 같은 Production 정책 결과를 바꾸지 않는다. → Task 3·5·6 테스트.

## 현재 근거와 변경 경계

- 2026-10-21 확인: branch `feature/scorecard-strategy-position-separation`, `.git == git-common-dir`인 일반 checkout이다. 새 worktree는 만들지 않았다.
- 기존 V2/Shadow 구현이 modified/untracked에 포함되어 있다. HEAD만으로 새 worktree를 만들면 필요한 선행 구현이 빠진다. 기존 작업 방식대로 현재 checkout에서 baseline 대비 순차 작업한다. 다른 작업 공간이 필요해지면 먼저 합의한다.
- 현재 `signals.py::_support_candidates`는 정배열·양의 SMA slope·Supertrend UP을 요구하며 SMA200도 포함한다. cycle 모델은 없다.
- `entry_anchors.py`는 episode evidence의 첫 support code에서 origin을 복원한다. Ladder 도입 후 이 순서 의존을 명시적 anchor 문맥으로 바꿔야 한다.
- 현재 canonical serializer는 `frozenset`을 직접 지원하지 않는다. scope 집합은 Observation serializer에서 정렬된 값 목록으로 내보내며 범용 hash 코드를 불필요하게 확장하지 않는다.
- 2026-10-21 변경 전 전체 재실행: `uv run pytest -q` → 1,928 passed, 15 deselected, 기존 warning 2개, exit 0(101.67초). focused pivot/Shadow도 23 passed였다.
- 로컬 `tmp/bt_cache_long/` CSV 74개 존재. NVDA/SPY 예시 범위는 2014-01-02~2026-09-28이다. 파일별 실제 범위·누락·조정 일관성은 Task 2에서 검사한다.

## 구현 계획에서 제안하는 세부 해석

아래는 사용자가 추가로 확정한 수치가 아니라, 구현자가 임의로 결정하지 않도록 적어 둔 검토 대상이다.

- 최초 slope는 기존 21거래일 차이 `SMA150[t] - SMA150[t-21] >= 0`으로 flat/rising을 표현한다. 데이터 부족은 자격 미확정이다.
- 최초 confirmation은 현재 FINAL 거래일에 확인된 사건으로 시작한다. HH는 `confirmed_on == t`, price breakout은 `close[t] > max(high[t-50:t])` AND `close[t-1] <= max(high[t-51:t-1])`로 처음 상향 통과한 사건이다(우측 끝을 제외하는 slice 표기). 별도 거래량 gate는 없다.
- 기존 bullish Entry Signal 경로는 당일 독립 detector의 `TREND_BREAKOUT_ENTRY`와 `DEEP_RECOVERY_ENTRY`를 사용한다. WATCH/cycle에 의존하는 `PULLBACK_REVERSAL_ENTRY`를 cycle 시작·restart 원인으로 사용하지 않는다. 기존 detector 자체의 거래량 조건은 유지한다.
- 최초 cycle은 최소 history와 위 confirmation이 함께 확보된 첫 날 시작한다. 과거 전체에서 HH가 한 번 있었다는 이유로 시작하지 않는다.
- restart는 INITIAL 조건을 재활용하지 않는다. A~D calibration 결과가 `UNRESOLVED`라면 종료 상태를 유지하고 재시작 근거 미확정을 표시한다.
- 모든 restart 후보는 공통으로 `FINAL AND day > terminated_on AND close > current SMA150`를 요구하며, confirmation도 종료 이후 새로 발생해야 한다. D의 Deep Recovery도 이 조건을 우회하지 않는다. INITIAL의 SMA150 slope 조건을 restart 공통조건으로 자동 추가하지 않는다.
- `PULLBACK_WATCH`의 기존 거리 0.5 ATR·만료 10봉·reversal high lookback 1봉은 유지한다. 이번 변경으로 lookback을 2봉으로 바꾸지 않는다.
- 지지선 전환은 같은 cycle 안의 별도 anchor-test episode다. 실패한 WATCH를 닫고 새 지지선 WATCH를 열 수 있지만, 새 지지선에서 같은 날 즉시 reversal을 만들지 않는다. 이전 완료 봉의 해당 WATCH가 있어야 한다.
- frozen breakout의 확정 실패는 같은 cycle의 ladder 자격에서 제외한다. 동적선은 해당 test episode를 닫으며, 후속 reclaim과 새 support test는 별도 episode로 구분한다. reclaim 당일의 Observation만으로 WATCH나 매수 자격을 자동 생성하지 않는다.

## 파일 책임과 의존 순서

| 파일 | 책임 |
|---|---|
| `src/tools/technical/pivots.py` | 동일 pivot algorithm으로 확인 사건과 기존 boolean을 함께 제공 |
| `src/strategies/models.py` | Observation·SupportAnchor/Test·UpCycle·ObservationSourceContext의 공유 타입; swing 모듈을 import하지 않음 |
| `src/strategies/observations/registry.py` | 16개 vocabulary·lifecycle·dependency·identity·표시 설명 |
| `src/strategies/observations/parameters.py` | Observation 전용 parameter/version·calibration 선택 결과 |
| `src/strategies/swing_w150/parameters.py` | 동결 V1 및 별도 V2 Production payload·순수 SupportCycleParameters |
| `src/strategies/observations/detectors.py` | source 독립/의존 Observation을 chart prefix로 계산 |
| `src/strategies/swing_w150/support_ladder.py` | 동적/frozen anchor·test·failure·가격순 선택·zone |
| `src/strategies/swing_w150/up_cycle.py` | 최초 시작·종료·새 cycle restart |
| `src/strategies/swing_w150/signals.py` | 기존 독립 Signal 유지, 새 cycle/WATCH/reversal 조립 |
| `src/strategies/entry_anchors.py` | 선택한 WATCH anchor의 origin·source 당시 frozen 값 복원 |
| `src/backtest/observation_calibration.py` | FINAL sample·대조군·미래 outcome·후보 비교 |
| `scripts/research_trading_observations.py` | offline freeze/baseline/calibrate/compare/cases 실행 |
| `research/trading_observation_v1/protocol.json` | 사전 고정한 데이터·후보·평가·선택 계약 |
| `src/pipelines/strategy_render.py`, `src/storage/entry_shadow.py` | 공통 출력·기존 snapshot의 Observation 문맥 기록 |

의존 순서: `Task 0 → Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6`.
Task 2는 공통 사건·연구용 kernel을 먼저 검증한다. Task 3/4의 제품 detector는 그 kernel/선택 결과를 재사용하며 연구 결과를 Strategy에서 읽지 않는다.

### 공유 계약 선행 정의와 구정책 보존

- Task 1에서 `models.py`에 `SupportAnchor`, `SupportTestState`, `UpCycleState`, `ObservationSourceContext`를 선언한다. 아래 Task 4의 필드가 최소 계약이며 `ObservationSourceContext`는 `signal`, 선택 `anchors: EntrySourceAnchors`, source별 `terminal_status/terminal_on/terminal_reason`를 갖는다. models→swing/observations import는 금지한다. 함수 구현은 Task 2, 제품 배선은 Task 3·4다.
- `ObservationParameters`는 version과 독립 fingerprint, `up_volume_ratio`, `down_volume_ratio`, `contraction_ratio`, `break_buffer_atr`, `reclaim_buffer_atr`, `reacceleration_mode`, 표시 전용 `zone_distance_atr`를 소유한다. `SupportCycleParameters`는 `normal_failure_closes`, `immediate_failure_volume_ratio`, `immediate_failure_close_location`, `support_break_buffer_atr`, `restart_mode`를 소유한다. None은 미선정/UNRESOLVED이며 숫자 0이나 False와 구별한다. 기간은 양의 정수, ratio는 양수, buffer는 0 이상, close location은 [0,1]로 검증한다. immediate 두 필드는 함께 선택하거나 모두 None이다. 후보값은 Task 2 표 그대로다. zone 표시는 Production fingerprint/Signal 판단에서 제외한다.
- 기존 `SwingW150Parameters` 필드/default/asdict payload를 그대로 둔다. 별도 frozen subclass `SwingW150ParametersV2`에 새 version `SWING_W150_V2_PARAMS_V2`, `support_cycle: SupportCycleParameters`, 새 Pullback policy 식별자를 둔다. V1 registry/payload/hash는 변하지 않는다. 신규 signal-decision 필드는 모두 V2 fingerprint에 포함한다. Observation 설정은 포함하지 않는다.
- Task 2 연구는 explicit candidate params로 kernel을 호출한다. V2 미선정 필드는 자동 보충하지 않는다. failure/restart 선정이 미완료면 V2를 기본 활성화하지 않고 기존 V1을 유지하며 새 정책 미활성 사유를 출력한다. 연구 후보 실행과 제품 활성화는 구분한다.
- adapter/Runner의 선택적 `parameters` 주입으로 V1/V2를 명시 선택한다. 인자 생략 시 V1 유지, V2 활성화는 Task 4의 검증된 선정 이후에만 변경한다. V1/V2는 별도 detector 경로 선택이며 기존 V1 본체의 결과를 변경하지 않는다. cross-version ID alias는 만들지 않는다.
- bar 처리 순서는 독립 Entry 감지 → FINAL 최초/restart 자격 평가 → 현재 cycle용 신규 anchor 등록 → 모든 지지 test 갱신 → SMA150 failure에 의한 cycle 종료 → 유효 ladder 선택 → WATCH/reversal이다. support 실패는 같은 bar에 ACTIVE를 TERMINATED로 바꿀 수 있지만 종료된 cycle을 같은 bar에 재시작하지 않는다. cycle을 요구하는 Pullback Entry는 앞단 독립 Entry 목록에 넣지 않는다.
- `advance_support_tests(..., new_anchors: Sequence[SupportAnchor], ...)`로 빈 states에도 신규 frozen/dynamic anchor를 등록한다. anchor에는 해당 cycle_id와 독립 breakout source/origin을 전달한다. 기존 anchor의 frozen origin은 덮어쓰지 않는다. 동적 당일 값은 row에서 갱신한다. Task 4는 이 동일 kernel을 호출한다.
- adapter는 모든 관련 Entry source에 대해 `ObservationSourceContext`를 준비한다. Opportunity evaluator의 단일-source core를 재사용해 각 source 이후의 FINAL invalidator/age로 terminal 문맥을 계산하고 원래 WATCH로 anchors를 복원한다. terminal 로직을 Observation detector에 복제하지 않는다. 최신 source의 Opportunity 선택은 기존대로 유지한다.

---

### Task 0: 기존 dirty baseline과 비교 기준 보존

**Files:**
- Create: `scripts/research_trading_observations.py`의 `baseline` 진입점
- Create, generated: `tmp/trading_observation_v1/baseline/`의 파일 hash·원본 사본·Product projection
- Test: `tests/backtest/test_observation_calibration.py`

**Interfaces:**
- Produces: `capture_baseline(root: Path, output: Path) -> dict[str, str]`.
- Product projection은 `signal_history`, `current_signals`, Opportunity 전체, source ID/date, terminal, Planner action/수량이다. Observation 추가 필드 자체는 비교에서 제외한다.
- projection과 함께 정확한 instrument/SPY prefix·finality·exchange sessions·가짜 Account/Position/MarketSnapshot 입력, V1 parameter payload/fingerprint를 저장한다. 실제 계좌·개인 설정을 읽지 않는다. 구정책 비교는 보존한 source 사본을 격리 import하는 연구 subprocess 또는 baseline projection 재현으로 실행하고, 현재 V1 경로와 먼저 일치시킨다.
- baseline은 현재 파일 내용을 기준으로 한다. HEAD diff를 이번 변경이라고 취급하지 않는다. baseline 산출 경로가 이미 있으면 덮어쓰지 않고 중단한다.

- [ ] 쓰기 전 `git status --short`, HEAD, 대상 source/test/docs hash와 scoped 원본을 보존한다. `.env`, API key, `playbook.yaml`, 개인정보는 복사하지 않는다.
- [ ] 테스트 `test_baseline_preserves_dirty_and_untracked_inputs`에서 임시 저장소의 modified/untracked 원본과 hash가 일치하고 두 번째 capture가 실패하도록 먼저 작성한다.
- [ ] `uv run pytest tests/backtest/test_observation_calibration.py -k baseline -q`로 RED를 확인한 뒤 최소 snapshot 기능을 구현하고 GREEN을 확인한다.
- [ ] `uv run pytest -q`로 전체 baseline을 실행한다. 실패하면 새 변경 전 실패인지 구분해 보고하고 다음 구현을 보류한다.
- [ ] 기존 fixture와 Task 2의 선정 로컬 차트로 Product projection을 저장한다. 테스트에는 가짜 Account/Position만 사용한다.
- [ ] 원본 hash·테스트 결과·review 경계를 baseline manifest에 기록한다. commit은 하지 않는다.

### Task 1: 공통 confirmed pivot 사건과 Observation domain contract

**Files:**

- Modify: `src/tools/technical/pivots.py`, `src/strategies/models.py`, `src/strategies/swing_w150/parameters.py`, `src/strategies/swing_w150/signals.py`의 SETUP 생성부
- Create: `src/strategies/observations/__init__.py`, `registry.py`, `parameters.py`
- Test: `tests/tools/technical/test_pivots.py`, `tests/strategies/test_observation_models.py`, 기존 episode 생성 fixture

**Interfaces:**

- `ConfirmedPivot`: frozen dataclass. 필드는 `pivot_type: Literal['HIGH','LOW']`, `pivot_index: int`, `confirmed_index: int`, `price: float`, `previous_pivot_index: int | None`, `previous_pivot_price: float | None`, `relation: Literal['HIGHER_HIGH','HIGHER_LOW','LOWER_HIGH','LOWER_LOW'] | None`이다.
- `confirmed_pivot_events(high: np.ndarray, low: np.ndarray) -> tuple[ConfirmedPivot, ...]`. 같은 가격은 relation=None이다. 기존 `PIVOT_SPAN=3`과 좌우 비교의 부등호를 유지한다.
- 기존 `confirmed_pivots(...) -> tuple[np.ndarray, np.ndarray]`는 공통 사건으로 기존의 지속 boolean을 만들며 반환값을 보존한다.
- `ObservationCode/Kind/Direction/Scope/TemporalType`을 models에 정의한다. 기존 `ObservationStatus`에 `RESOLVED`를 추가한다.
- 기존 `StrategyObservationEpisode`를 확장한다. 필수 추가 필드는 `observation_id/ticker/schema_version/parameter_fingerprint/kind/scopes/temporal_type/finality`이다. code는 ObservationCode, direction은 ObservationDirection으로 바꾼다. 기존 날짜/status/evidence는 유지한다.
- 선택 문맥 필드는 `source_signal_id/anchor_id/anchor_type/anchor_origin_on/anchor_origin_price/pivot_date/confirmed_on/source_terminal/cycle_id`다. Signal ID를 위한 영구 호환 모델은 만들지 않는다.
- `ObservationDefinition`은 code별 kind/direction/scopes/temporal_type, start/maintain/end/reentry, source/anchor 의존, detector validity와 predictive usefulness를 보관한다.
- `make_observation(*, ticker: str, code: ObservationCode, origin: date, params: ObservationParameters, **context) -> StrategyObservationEpisode`는 registry의 분류를 적용한다. context는 위 선택 문맥과 기존 status/date/evidence다. 미정의 code는 거절한다.
- identity에는 ticker/code/temporal_type/schema·parameter version/source/anchor/origin을 넣는다. scopes는 정렬한 문자열 목록으로 serialize한다. SETUP은 NEUTRAL/ENTRY/EPISODE, VOLUME_CONTRACTION은 POSITIVE/ENTRY/EPISODE, 나머지 EVIDENCE는 각 방향과 ENTRY/POSITION scope를 갖는다.
- 위 공유 계약의 domain 타입·parameter schema를 이 단계에서 선언하고 V1 payload/fingerprint가 baseline과 같음을 검사한다. kernel·detector 제품 배선은 앞당기지 않는다.

- [ ] 기존 pivot expected arrays를 고정하고, 연속된 별도 HH/HL이 모두 남는 테스트를 추가한다.
- [ ] `test_pivot_event_is_visible_only_on_confirmation`에서 `assert event.confirmed_index == event.pivot_index + 3`, 확인 이전 prefix에서 사건 없음, 전체/prefix 결과 일치를 검증한다.
- [ ] `test_observation_identity_distinguishes_anchors_and_replays`에서 `assert sma50.observation_id != sma150.observation_id`, 동일 입력 replay ID 일치를 검증한다.
- [ ] `test_scopes_roundtrip_as_sorted_values`에서 JSON/canonical 왕복과 ENTRY/POSITION 중복 생성 없음을 검증한다.
- [ ] 위 테스트의 RED를 확인하고 공통 pivot·타입·registry를 구현한다. 기존 SETUP 생성부와 test fixture도 새 타입으로 옮기되 Signal 판단은 변경하지 않는다. 임의 OLD_WATCH 같은 fixture code는 정식 vocabulary와 날짜 조합으로 대체한다.
- [ ] `uv run pytest tests/tools/technical/test_pivots.py tests/strategies/test_observation_models.py tests/strategies/swing_w150/test_signals.py tests/pipelines/test_strategy_analysis.py -q`로 GREEN과 생성부 누락 없음을 확인한다.

### Task 2: calibration 계약·공유 kernel을 검증하고 offline 비교

**Files:**

- Create: `research/trading_observation_v1/protocol.json`, `src/backtest/observation_calibration.py`
- Create: `src/strategies/observations/detectors.py`, `src/strategies/swing_w150/support_ladder.py`, `up_cycle.py`의 순수 계산부
- Modify: `scripts/research_trading_observations.py`, `src/strategies/swing_w150/features.py`
- Test: `tests/backtest/test_observation_calibration.py`, `tests/strategies/test_observations.py`, `tests/strategies/swing_w150/test_support_ladder.py`, `test_up_cycle.py`
- Create, generated: `tmp/trading_observation_v1/calibration/`
- Create: `docs/references/2026-10-21-trading-observation-v1-calibration.md`

**Interfaces:**

- `freeze_protocol(protocol: dict, *, cache_dir: Path, output: Path) -> str`는 입력 CSV·원본 명세의 SHA256, 실제 범위/누락, 후보와 수, protocol digest를 저장한다. outcome 계산 전에 실행한다.
- manifest에 실제 실행 kernel/evaluator/script 및 `uv.lock` hash도 저장한다. 이후 의미 변경 시 결과를 무효화하고 같은 protocol로 재실행한다. Strategy는 이 manifest를 읽지 않는다.
- `run_calibration(protocol_path: Path, *, output: Path) -> dict`는 digest를 확인하고 후보별 사건/episode/outcome/comparator/summary/selection을 생성한다.
- 이 단계에서 Task 3·4에 정의한 순수 detector/support/cycle 함수를 후보 parameter로 구현한다. 아직 adapter나 Production 기본값에는 연결하지 않는다. Task 3·4는 같은 구현을 재사용한다.
- 신규 ratio/추세 값은 기존 공통 indicator 계산을 재사용한다. 현재 봉 포함 여부가 다른 기존 `Vol_SMA_20`을 신규 ratio 분모로 그대로 쓰지 않는다.
- 미래 outcome 함수는 `src/backtest/`에만 둔다. Strategy 모듈에서 evaluator나 결과 파일을 import하지 않는다.

**사전 고정할 protocol 제안:**

- Universe 20종목: `AMD, AMAT, AMZN, AVGO, CAT, COIN, CRWD, INTC, JNJ, JPM, KO, META, MSFT, MU, NVDA, QCOM, SHOP, TSLA, WMT, XOM`. 시장 비교는 SPY다. 입력은 `tmp/bt_cache_long/<ticker>.csv`다. 생존 종목의 편의 표본이며 전체 시장 성과로 표현하지 않는다.
- 2014년 이후 사용 가능한 원자료를 warmup으로 사용한다. 사건 평가 기간은 2017~2025, development=2017~2021, validation=2022/2023/2024/2025의 연도별 4fold다. 기존 연구 사용 기간을 fresh OOS라 부르지 않는다.
- EVENT는 확인 사건당 1표본, EPISODE는 시작당 1표본이다. 연속 ACTIVE 날짜를 독립 표본으로 늘리지 않는다.
- 기준 가격은 다음 거래일 open이다. 이후 5/10/20/40/60번째 봉 close return과 같은 기간 MFE/MAE를 계산한다. 각 fold 안에서 horizon이 완성되어야 하며, 미성숙/가격 누락은 null과 이유로 남긴다.
- future Entry Signal은 baseline parameter의 기존 4개 Entry code다. 사건 다음 날부터 horizon 끝까지의 FINAL 사건만 센다. `future_winner_H`는 `return_H > 0`인 방향성 라벨이며 실제 체결/전략 승률이 아니다.
- comparator는 같은 ticker·연도fold·SPY regime·가격의 SMA150 위/아래 상태에서 해당 Observation이 없는 날짜를 찾는다. 사건일 전 20거래일 중 가장 가까운 1일을 사용한다. 미매칭은 UNMATCHED다. 비교일 선택에 미래 outcome을 쓰지 않으며, 재사용/중복 horizon을 공개하고 ticker 단위 cluster로 불확실성을 표시한다.
- SPY regime은 기존 시장 gate와 동일한 `close>SMA50>SMA200: bull / close<SMA50<SMA200: bear / 나머지: sideways`를 사용한다.
- contraction 연구 문맥은 `close>SMA150 AND SMA150의 21봉 차이>=0 AND close<=직전20봉 high`다. cycle 후보 선택에 종속시키지 않으며 generic base detector로 제품화하지 않는다.
- momentum prior-trend 문맥은 직전20봉 내 `close>SMA150 AND SMA150의 21봉 차이>=0`이 존재하는 것이다. reacceleration에는 직전10봉 내 `close<SMA20`도 요구한다. SMA20 slope는 기존 5봉 차이다.

| family | 후보 | 수 |
|---|---|---:|
| UP_VOLUME_EXPANSION | close>전일close, volume/이전20봉평균>=1.2/1.4/1.5/1.7/2.0 | 5 |
| DOWN_VOLUME_EXPANSION | close<전일close, 같은 ratio>=1.3/1.5/1.7/2.0 | 4 |
| VOLUME_CONTRACTION | 최근5봉평균/그 앞20봉평균<=0.6/0.7/0.8/0.9, 위 문맥 안 | 4 |
| support break/reclaim | break buffer=0/0.25/0.5 ATR × reclaim buffer=0/0.25 ATR; 동적/frozen 분리 집계 | 6 |
| normal failure | 지지선 아래 연속 FINAL 종가=1/2/3 | 3 |
| zone 표시 | anchor 거리<=0.25/0.5/0.75 ATR | 3 |
| immediate failure | 하방종가+volume ratio>=1.3/1.5/1.7+close location<=0.25/0.35 | 6 |
| restart | 공통 FINAL·종료 이후·close>SMA150; A:reclaim+2회 FINAL 위 / B:A+slope150>0 / C:A+(새 HH 또는 직전5봉high 돌파) / D:새 독립Entry Signal | 4 |
| reacceleration | 문맥+close>SMA20+slope20 양전 / 같은 식+5봉return>0 / 같은 식+직전5봉high 돌파 | 3 |
| deceleration | prior-trend+close<SMA20+slope20 음전 시작, 약화 중 EPISODE 유지 | 1 |
| 합계 | family별 비교, 전체 직적 조합 금지 | 39 |

- volume 분모에는 당일을 제외한다. contraction 분모는 최근5봉과 겹치지 않는 직전20봉이다.
- 다른 family의 중심 후보는 UP/DOWN=1.5, contraction=0.7, break/reclaim buffer=0, failure=2회, zone=0.5 ATR, immediate=OFF로 고정한다. 공통 문맥에는 최초 cycle만 사용한다. restart 후보별 결과로 다른 family의 표본을 다시 고르지 않는다.
- detector validity는 synthetic 경계·prefix 일치·family별 날짜순 처음/25%/중앙/75%/마지막 최대5사례의 의미 점검으로 판정한다.
- predictive usefulness는 별도 결과다. 성숙 50표본 미만, 10ticker 미만 또는 3fold 미만이면 INSUFFICIENT다. 방향이 4fold 중 3개에서 일치하지 않거나 CI가 0을 포함하면 UNRESOLVED다. 연구용 제안 기준이며 Observation 표시나 BUY gate에 적용하지 않는다.
- paired 차이는 같은 사건과 comparator의 outcome 차이다. CI는 ticker 단위 cluster bootstrap 2,000회, seed=21, percentile 95%로 고정한다. 개별 행을 독립 표본으로 재추출하지 않는다.
- threshold 선택은 의미·빈도·인접 후보 plateau를 우선한다. 수익률 최고값으로 자동 선정하지 않는다. failure/restart가 불명확하면 기본값을 비워 두고 결과를 보고한다.

**family별 표본·선택 추가 계약(결과 공개 전 protocol에 동결):**

| family | risk set / 고정 sample origin | 확인·관찰 종료와 comparator | 주지표 / 보조지표 |
|---|---|---|---|
| volume/structure/momentum/break/reclaim | EVENT 확인일 또는 EPISODE 시작일; 구조는 fixed span | 위 prior20일 비발생 매칭; fold 내 horizon 성숙 | 20봉 paired return(Positive 양, Risk 음) / 나머지 horizon·MFE·MAE·빈도·future Signal |
| normal/immediate failure | 중심 buffer=0·최초 cycle만으로 고정한 개별 anchor support-test 시작 집합; 후보별 failure일로 표본 이동 금지 | 시작 후20봉 또는 fold 끝; 미확인도 한 행 유지. 동일 test에서 1/2/3회와 OFF/6개 immediate 결과를 pair 비교. 미성숙 null | failure 뒤5봉 내 reclaim 비율(낮을수록 좋음)과 최초 breach→확인 지연 / 고정 origin의20봉 return·MFE·MAE·미확인율 |
| restart | 중심 normal failure=2·immediate OFF로 고정한 terminated cycle 전체; origin=terminated_on | 종료 후20봉 또는 fold 끝; 무재시작도 한 행 유지. A~D 동일 origin pair 비교 | restart 뒤5봉 내 재failure 비율과 종료→restart 지연 / 20봉 내 새 HH 포착률·미확인율·고정 origin outcome |
| zone 표시 | 같은 날짜·개별 anchor set; sample=(ticker,day), 성과 EVENT로 세지 않음 | 같은 anchor를 0.25/0.5/0.75 ATR로 cluster, cluster 전체 가격폭이 threshold 이내; 인접일 공통 anchor만 안정성 비교 | cluster 수·최대폭·동일 anchor-pair 병합 유지율 / 개별 break/failure/reclaim·Signal 불변 |

- immediate failure의 정확한 식은 `FINAL close < anchor - buffer*ATR AND close < previous close AND volume/previous20_mean >= candidate_ratio AND (close-low)/(high-low) <= candidate_location`이다. high==low 또는 reference 누락은 미평가다.
- failure/restart의 5봉 후속 판정도 fold 안에서 성숙해야 한다. support test의 confirmed failure는 reclaim과 별도 기록한다. restart 후 재failure는 중심 failure=2·immediate OFF로 판정한다. 고정 origin은 cohort 비교용이며 후보 확인일부터의 보조 outcome도 별도 열로 구분한다. 재시작 Signal의 매매 성과로 오인하지 않는다.
- Observation detector 기본값과 predictive status를 별도 선택한다. development에서 경계·prefix·의미 검증을 통과한 후보의 빈도를 비교한다. 인접 후보 대비 사건 수 변화가 20% 이내인 plateau 중 사전 중심값에 가장 가까운 값을 잠정 선택한다(동거리면 간단한/낮은 threshold). plateau가 없으면 detector default만 UNRESOLVED로 둔다. 단일 고정식인 구조/momentum deceleration에는 인접 plateau를 요구하지 않고 의미 검증을 적용한다. 표본50/10ticker/3fold와 20봉 signed return CI·validation 3/4fold 방향은 오직 predictive usefulness를 결정한다. utility UNRESOLVED여도 detector IMPLEMENTED와 기본 표시를 허용한다. validation 결과로 detector threshold를 재선택하지 않고 나머지 horizon 최고값도 고르지 않는다.
- failure/restart는 development에서 중심 후보 대비 whipsaw와 지연이 모두 악화되지 않고 한 지표 이상 개선된 후보만 잠정 선택한다. 둘의 trade-off가 남거나 paired ticker-bootstrap CI가 개선을 지지하지 않으면 UNRESOLVED다. 중심과 같은 후보는 경계/의미 검증과 충분 표본이 모두 있어야 유지 가능하다. validation 3/4fold에서 같은 비악화 방향을 확인하고, 실패하면 재선택하지 않는다. 비교용 중심값은 운영 기본값이 아니다.
- zone은 예측 utility를 평가하지 않는다. 각 threshold의 폭 제한·개별 판단 불변을 먼저 검사하고, 인접 threshold 대비 중앙 cluster 수 변화가 10% 이내인 plateau에서 중심0.5에 가까운 값을 고른다. 없으면 UNRESOLVED로 zone 표시만 비활성한다. family별 빈도/미성숙/미매칭/중복은 모두 공개한다.

- [ ] 위 계약을 JSON으로 옮기고 `test_protocol_freezes_39_candidates_before_labels`, `test_episode_counts_one_sample`, `test_unmatured_labels_are_null`, `test_current_volume_is_not_reference`를 먼저 작성한다.
- [ ] `test_next_open_is_outcome_anchor`에서 다음 open=100, horizon close=110이면 `assert return_h == pytest.approx(0.10)`, 미완성 horizon이면 `assert return_h is None`을 검증한다.
- [ ] Task 3·4의 경계 테스트로 공유 순수 kernel을 RED→GREEN으로 구현한다. 후보 mode는 연구용이며 기본 Production 결과를 바꾸지 않는다.
- [ ] `uv run pytest tests/backtest/test_observation_calibration.py tests/strategies/test_observations.py tests/strategies/swing_w150/test_support_ladder.py tests/strategies/swing_w150/test_up_cycle.py -q`를 실행한다.
- [ ] `uv run python scripts/research_trading_observations.py freeze --protocol research/trading_observation_v1/protocol.json --output tmp/trading_observation_v1/calibration`를 실행한다.
- [ ] 같은 command의 `freeze`를 `calibrate`로 바꾸어 비교를 실행한다. provider 호출은 0회다.
- [ ] root가 원본 의미, 39후보, maturity, comparator를 검토하고 선택/UNRESOLVED와 이유를 reference에 기록한다. failure/restart 선택이 부족하면 Task 4의 Production 유효화는 보류한다. 추가 탐색은 별도 protocol로 취급한다.

### Task 3: Observation을 Production 판단과 독립적으로 연결

**Files:**

- Modify: `src/strategies/observations/detectors.py`, `registry.py`, `parameters.py`, `src/strategies/swing_w150/features.py`, `adapter.py`, `src/strategies/runner.py`
- Test: `tests/strategies/test_observations.py`, `test_runner.py`, `tests/strategies/swing_w150/test_adapter.py`

**Interfaces:**

- `evaluate_observations(ticker: str, features: SwingFeatureFrame, signals: Sequence[StrategySignal], setups: Sequence[StrategyObservationEpisode], *, source_contexts: Sequence[ObservationSourceContext], params: ObservationParameters) -> list[StrategyObservationEpisode]`.
- Adapter/Runner에 `observations_enabled: bool = True`, `observation_parameters: ObservationParameters | None = None`를 추가한다. OFF에서도 기존 SETUP은 남고, 추가 EVIDENCE만 꺼진다.
- vocabulary는 SETUP 2개, POSITIVE 7개, RISK 7개다. 임의 code를 추가하지 않는다. 구조4종·volume은 source/보유 없이 계산한다. source 의존 detector는 관련 source와 anchor마다 분리한다.
- EVENT는 확인일의 완료 history다. `status=RESOLVED, started_on=status_as_of=ended_on=confirmed_on`으로 표현하고 지속 ACTIVE 목록에 넣지 않는다.
- breach EPISODE는 기준 하단 이탈로 시작하고 reclaim 상단을 넘기 전까지 유지한다. 회복일에 RESOLVED와 별도 reclaim EVENT를 만든다. 재이탈은 새 origin이다.
- contraction은 문맥/ratio 유지 중 ACTIVE, 조건 소멸 시 RESOLVED다. deceleration은 음전으로 시작하고 close<SMA20와 slope<=0에서 유지하며 회복 또는 상위 추세 문맥 종료 시 닫는다. 재성립은 새 episode다.
- terminal source reclaim에 `source_terminal=True` 문맥을 표시하되 Opportunity 평가에는 입력하지 않는다.
- PROVISIONAL은 마지막 FINAL 상태의 복사본으로 평가한다. FINAL history나 terminal을 영구 변경하지 않는다.

- [ ] 16개 code의 분류/scope/temporal_type/의존/구현 상태를 table-driven test로 고정한다.
- [ ] `test_no_entry_source_still_emits_structure_and_volume`, `test_terminal_source_reclaim_does_not_revive_opportunity`, `test_distinct_sources_do_not_merge_same_day_breaches`를 추가한다.
- [ ] source A terminal·source B live·A anchor reclaim이 같은 날 존재할 때 A의 frozen anchor/terminal이 B 문맥과 섞이지 않는지 검증한다.
- [ ] `test_provisional_breach_disappears_after_final_reclaim`, `test_continuous_episode_is_not_reemitted_daily`, `test_missing_features_are_not_normal_observations`를 추가한다.
- [ ] RED 확인 후 Task 2 kernel을 연결한다. formula 미정이면 UNRESOLVED로 표시한다. detector IMPLEMENTED와 예측 utility UNRESOLVED는 함께 존재할 수 있다.
- [ ] `uv run pytest tests/strategies/test_observation_models.py tests/strategies/test_observations.py tests/strategies/test_runner.py tests/strategies/swing_w150/test_adapter.py -q`를 실행한다.
- [ ] baseline policy 고정 ON/OFF에서 Signal dump·Opportunity 전체·Planner 결과가 같음을 assert한다. 아직 Pullback gate는 바꾸지 않는다.

### Task 4: 상승 cycle·Support Ladder·Pullback policy 적용

**Files:**

- Modify: `src/strategies/swing_w150/up_cycle.py`, `support_ladder.py`, `signals.py`, `parameters.py`, `features.py`, `src/strategies/models.py`, `src/strategies/entry_anchors.py`
- Test: `tests/strategies/swing_w150/test_up_cycle.py`, `test_support_ladder.py`, `test_signals.py`, `test_parameters.py`, `tests/strategies/test_entry_anchors.py`

**Interfaces:**

- `SupportAnchor`는 anchor_id/type, dynamic/frozen, origin 날짜/가격, 선택 source_id/cycle_id를 갖는다. 동적선의 당일 값과 origin 값을 구분한다.
- `SupportTestState`는 anchor, `HELD/SOFT_BREACH/RECLAIMED/FAILED`, below_count, 날짜/finality다. frozen anchor의 failure latch와 reclaim fact는 별개다.
- `advance_support_tests(states: Sequence[SupportTestState], row: pd.Series, *, new_anchors: Sequence[SupportAnchor], day: date, finality: BarFinality, params: SupportCycleParameters) -> list[SupportTestState]`.
- `select_support(states: Sequence[SupportTestState], *, close: float, low: float, atr: float, params: SwingW150Parameters) -> SupportTestState | None`. 현재 가격 아래 또는 test 범위에서 가장 가까운 유효 지지를 가격순으로 고른다. zone은 표시용으로만 묶는다.
- `UpCycleState`는 cycle_id, started_on, `INACTIVE/ACTIVE/TERMINATED`, terminated_on, 원인/confirmation/finality다. Correction은 context다.
- `advance_up_cycle(state: UpCycleState | None, row: pd.Series, *, ticker: str, day: date, finality: BarFinality, confirmed_pivots: Sequence[ConfirmedPivot], independent_entries: Sequence[StrategySignal], sma150_failed: bool, params: SwingW150Parameters) -> UpCycleState`.
- Detection/Bundle에 선택 `up_cycle/support_tests`를 추가한다. coverage 부족은 미평가로 표시한다. 기존 V1 replay는 적용 대상이 아니다.
- 새 Production set은 `SWING_W150_V2_PARAMS_V2`다. Task 2에서 선택한 값만 넣는다. 기존 V1 payload는 덮어쓰지 않으며 비교용 구정책 경로를 남긴다.
- 타입 선언은 Task 1, 순수 kernel은 Task 2의 산출물을 재사용한다. V1/V2 선택 주입은 adapter·Runner에 배선하고 `test_v1_payload_fingerprint_and_product_projection_remain_frozen`으로 baseline 회귀를 검사한다. 실패/restart 미선정이면 V1 default 유지·V2 미활성 사유를 명시한다.
- Observation 설정은 독립 fingerprint로 관리한다. Signal 판단을 바꾸는 cycle/failure/restart 값은 Production fingerprint에 포함한다.
- Entry anchors는 해당 WATCH의 명시 origin 값을 사용한다. 후일 SMA 값이나 다음 지지선으로 이전 origin을 바꾸지 않는다. 기존 정책의 기존 복원 경로는 유지한다.

- [ ] mandatory 부족→INACTIVE, flat/rising+HH/breakout/독립 Entry 중 하나→ACTIVE를 테스트한다. Supertrend/MA 정배열/volume/HL 공통 gate가 없음을 검증한다.
- [ ] `test_healthy_low_volume_sma50_pullback_needs_no_correction_mode`, `test_sma150_watch_survives_supertrend_down_and_ma_weakness`에서 WATCH만 발생하고 reversal은 없음을 assert한다.
- [ ] `test_ladder_orders_by_price_not_anchor_kind`, `test_multiple_breakout_anchors_are_preserved`, `test_failed_frozen_anchor_is_not_reused_but_reclaim_is_observed`를 추가한다.
- [ ] `test_supertrend_down_removes_support_without_freezing_old_band`, `test_cluster_keeps_independent_anchor_failures`, `test_sma150_failure_overrides_lower_breakout`를 추가한다.
- [ ] `test_one_close_shakeout_and_reclaim`, `test_sma50_failure_moves_support_without_ending_cycle`, `test_cycle_failure_does_not_change_sma150_exit_detector`를 선택 rule로 고정한다.
- [ ] `test_terminated_cycle_cannot_restart_from_old_confirmation`, `test_restart_creates_new_cycle_id`, `test_cycle_cannot_bootstrap_from_own_pullback_entry`를 추가한다.
- [ ] D에서도 SMA150 아래 Deep Recovery·PROVISIONAL Entry·종료일 이전 Entry가 restart하지 않음을 각각 검증한다.
- [ ] `test_provisional_failure_does_not_terminate_final_cycle`, `test_prefix_and_full_replay_agree_after_skipped_runs`, `test_new_ladder_anchor_cannot_reverse_on_its_first_watch_day`를 추가한다.
- [ ] `test_reversal_uses_matching_watch_anchor_origin`에서 SMA50→breakout→SMA150 이동 후 새 Signal에 해당 WATCH의 origin/low만 결합됨을 검증한다.
- [ ] RED 확인 후 공유 kernel을 독립Signal→support/cycle→WATCH/reversal 순서로 연결한다. 기존 exit 본체는 보존하며 `exited`와 WATCH의 암묵적 결합만 명시한다. 같은 날 exit의 Opportunity 무효화 우선순위는 유지한다.
- [ ] `uv run pytest tests/strategies/swing_w150 tests/strategies/test_entry_anchors.py tests/strategies/test_entry_opportunity.py -q`를 실행한다.
- [ ] 변경 비교는 version ID 문자열 대신 ticker/date/code/원인/source 계보로 한다. 기존 golden을 새 출력으로 일괄 덮어쓰지 않는다.

### Task 5: check/analyze/brief 공통 출력과 연구 snapshot

**Files:**

- Modify: `src/pipelines/strategy_render.py`, `strategy_analysis.py`, `src/storage/entry_shadow.py`
- Test: `tests/pipelines/test_observation_render.py`, `test_strategy_analysis.py`, `test_quick_check.py`, `test_deep_dive.py`, `test_brief.py`, `tests/storage/test_entry_shadow.py`, `tests/position/test_planner.py`

**Interfaces:**

- 기존 `render_strategy_sections(...)`를 확장한다. pipeline별 detector를 만들지 않는다.
- 표시 순서는 Score/5일 이력→cycle/support→SETUP→Positive/Risk Observations→Signal→EntryOpportunity→기존 source-specific Shadow→PositionPlanner다.
- 의미/원인/발생일/확인일/FINAL·PROVISIONAL/anchor/source/주요 실측과 기준은 기본 출력에 포함한다. 상세 모드에서 전체 Evidence와 설정/ID를 추가한다.
- ACTIVE EPISODE, 당일 EVENT, 최근20거래일 history를 구분한다. 오래된 ACTIVE를 cutoff로 숨기지 않는다. 미구현/미평가와 발생 없음을 구분한다.
- Supertrend DOWN은 기존 Technical Evidence 경고로 표시한다. 새 ObservationCode나 global Risk Level을 만들지 않고 기존 Shadow Risk Level에 가산하지 않는다.
- 새 version의 외곽 snapshot에 Observation/cycle/support를 포함한다. scopes는 정렬된 JSON array다. 기존 JSONL을 고쳐 쓰거나 계산에서 읽지 않는다.

- [ ] `test_default_render_explains_sma150_watch_with_supertrend_warning`, `test_event_is_history_not_persistent_active`, `test_unresolved_detector_is_not_rendered_as_no_risk`를 먼저 작성한다.
- [ ] source/보유가 없어도 구조와 volume을 표시하고 동일 관측을 scope별로 이중 생성하지 않음을 검증한다.
- [ ] 3개 pipeline이 공통 renderer를 사용하고 기존 5일 Score와 Signal/Opportunity 원인이 유지됨을 검증한다.
- [ ] `test_cycle_termination_alone_does_not_exit_real_position`에서 cycle만 달라지면 action/quantity가 동일함을 assert한다. 실제 Production exit 발생 시에는 기존 exit 우선순위를 확인한다.
- [ ] RED→연결→GREEN 후 `uv run pytest tests/pipelines tests/storage/test_entry_shadow.py tests/position -q`를 실행한다.
- [ ] 연구 기록이 tmp_path에 격리되며 실제 JSONL에 synthetic 입력이 섞이지 않았음을 확인한다.

### Task 6: 신구 비교·실제 사례·독립 리뷰

**Files:**

- Modify: `scripts/research_trading_observations.py`
- Test: `tests/backtest/test_observation_calibration.py`, `tests/strategies/swing_w150/test_golden.py`, `tests/backtest/test_swing_w150.py`
- Create: `docs/references/2026-10-21-trading-observation-v1-validation.md`
- 검증 후 Update: `docs/FEATURES.md`, `docs/changes/scorecard-strategy-position-separation.md`, `docs/changes/INDEX.md`, `docs/CLI_USAGE.md`, `docs/worklog/trading-observation-v1.md`, `docs/active-context.md`

**Interfaces:**

- `compare --baseline ... --protocol ... --output ...`는 A:같은 정책의 Observation ON/OFF, B:구/신 Pullback 정책의 두 비교표를 생성한다.
- A에서는 Signal/source/Opportunity/Planner가 같아야 한다. B에서는 WATCH/reversal 수, Opportunity 상태/원인, Planner 하류 차이를 날짜별로 설명한다.
- `cases --protocol ... --output ...`는 로컬 실제 OHLCV로 전체 경로를 실행한다. synthetic fixture, 과거 실제 사례, 현재 시장 데이터를 구분한다.

- [ ] evaluator 미래 라벨이 Strategy 출력에 없고, 같은 정책의 Observation ON/OFF 결과가 같은지 검증한다.
- [ ] `uv run python scripts/research_trading_observations.py compare --baseline tmp/trading_observation_v1/baseline --protocol research/trading_observation_v1/protocol.json --output tmp/trading_observation_v1/comparison`을 실행한다.
- [ ] 같은 script의 `cases --protocol research/trading_observation_v1/protocol.json --output tmp/trading_observation_v1/cases`를 실행한다.
- [ ] healthy SMA50, ST DOWN/SMA150 WATCH, 1일 shakeout/reclaim, SMA150 종료/새 cycle, terminal 후 reclaim 사례를 날짜·가격·Evidence와 함께 출력한다. 찾지 못한 실제 사례는 없다고 밝힌다. ALAB/COHR 추가 수집은 별도 범위를 제시한다.
- [ ] Backtest t+1 open/FINAL-only, exit 조건 불변, Observation isolation, 의도한 Pullback 차이를 각각 보고한다.
- [ ] `uv run pytest -q`, `uv run ruff check src tests scripts/research_trading_observations.py`, 변경 Python의 `uv run ruff format --check <files>`, `git diff --check`를 실행한다. 기존 warning과 새 warning을 구분한다.
- [ ] root가 baseline 상대 diff와 실측을 확인한 후 별도 에이전트의 spec/quality 리뷰를 받는다. Critical/Important는 수정·재검증한다. Pro 모델은 별도 사전 승인 없이 사용하지 않는다.
- [ ] 검증한 범위만 기능 문서·변경 기록에 반영하고 worklog/status를 갱신한다. commit/push/merge는 하지 않는다.

## 계획 자체 점검

- 최신 실행 명세와 INITIAL 직접 결정을 Task 1의 사건/타입, Task 2의 calibration, Task 3의 Observation, Task 4의 cycle/ladder, Task 5의 출력, Task 6의 비교에 배정했다.
- Task 2에서 미배선 순수 kernel을 먼저 구현하므로 calibration이 아직 없는 제품 구현에 순환 의존하지 않는다.
- Review Focus 5개에 경계 테스트를 배정했다. Observation 불변성과 Pullback의 의도적 변화는 구분했다.
- 후보 수는 39개다. 데이터/공식이 부족한 항목은 UNRESOLVED로 두고 임의 기본값으로 승격하지 않는다.
- 최초 세부 해석과 calibration 수치는 계획 제안이며 사용자 확정 정책과 구분했다.
- 구현 방식은 별도 에이전트 위임이다. 이 계획을 확인받은 후 구현을 시작한다.

# Strategy Signal Boundary Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chart-only Observation·Signal·EntryOpportunity를 모든 pipeline에 제공하고, 장중 PositionPlan과 versioned Backtest를 지원하면서 PostgreSQL `strategy_history` subsystem을 제거한다.

**Architecture:** Raw OHLCV는 공통 `IndicatorCalculator`를 거쳐 `SwingFeatureFrame`이 되고, causal detector가 Observation history와 Signal history를 만든다. PositionPlanner는 오늘 Signal만, Backtest는 FINAL Signal만 사용한다. parameter canonical fingerprint가 모든 결과 identity를 고정한다.

**Tech Stack:** Python 3.13, Pydantic v2, dataclasses, pandas/numpy, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-10-06-strategy-signal-outcome-backtest-boundary-design.md`

## 현재 상태 (2026-10-08)

Tasks 1~9은 구현·review 수정·문서·검증을 마쳤으며 미커밋 상태다. 최종 focused 411개·전체 1825개
test와 Ruff·diff-check·삭제 import 검색을 통과했다. 최초 live 실행의 지지선 소실·NumPy bool
serialization·영숫자 KRX finality 결함을 수정하고 `check NVDA`·`analyze NVDA`·`brief`를 모두
exit 0으로 재검증했다. 정확한 실행 결과·제한과 기존 Critical 5개·Important 8개 대조는 Task 9
보고서에서 관리한다.

사용자 최신 요청에 따라 최종 독립 `reason=xhigh` 리뷰는 Task 9 이후 coordinator가 별도로 수행한다.
commit·stage·push·PR·merge는 이번 실행에 포함하지 않는다.

최종 독립 리뷰의 Important 4건은 별도 TDD 수정을 마쳤다. 독립 US/KRX exchange calendar,
종목 typed coverage의 Signal·실제 매도 차단, V2 Backtest의 expected/no-trade session 계약,
EntryOpportunity의 당일 종가 추정·이후 실제 시가 표시를 수정한다. 위 검증 숫자와 실제 pipeline
결과는 수정 전 기준이며, 수정 후 focused 435개·전체 1849개와 Ruff·format·diff 검사를 통과했다.
최신 결과·제한은 `review-important-fixes-report.md`에서 관리한다. 수정 후 live는 미실행이다.
Minor 2건은 이번 수정 범위에서 제외한다.

coordinator의 후속 live 확인에서 정상 `2y` 응답이 nominal 첫 거래일 하나를 제외해 V2를 막는
회귀를 발견했다. 첫 session 1개만 빠지고 나머지가 연속일 때만 `effective_start`를 명시하여 허용하고,
nominal 요청·독립 calendar와 중간/끝·시작 2개 누락 차단은 유지한다. 이 보완은 focused 238개를
통과했으며, 위 전체 1849개는 보완 전 기준이다. 최신 전체·live 재검증은 coordinator가 수행한다.

## Global Constraints

- Strategy 입력은 ChartBundle prefix, strategy version, canonical parameter fingerprint뿐이다.
- 실제·가상 position, 평균단가, 체결, DB row를 Strategy 입력으로 사용하지 않는다.
- Observation은 상태 기간, Signal은 단일 거래일 사건이다.
- `current_signals == [s for s in signal_history if s.occurred_on == as_of]`를 지킨다.
- PositionPlanner는 PROVISIONAL과 FINAL current Signal을 모두 사용할 수 있다.
- Backtest는 FINAL Signal만 사용한다.
- 미설명 instrument provider gap은 COMPLETE Signal·실제 보유 매도·체결 성과를 만들지 않는다.
- 미국·한국 expected sessions는 benchmark 관측 행과 독립적이고 V2 Backtest는 명시적 no-trade만 건너뛴다.
- Strategy output과 renderer에 virtual entry, position stop, risk, R을 넣지 않는다.
- PostgreSQL `strategy_history` code, migration, test, runtime wiring을 전부 삭제한다.
- 모든 조정값은 versioned parameter 또는 execution/risk policy에 둔다.
- package와 test command는 `uv`만 사용한다.
- unrelated dirty file을 수정·stage하지 않는다. commit·push·merge는 별도 승인 뒤 수행한다.

## Review Focus

- 과거 exit가 오늘 주문에 재사용되거나 correction 뒤 old entry가 다시 살아나지 않아야 한다.
- 과열·눌림목·SMA150 sequence가 한 번만 발생하고 명시적 reset 뒤에만 재무장되어야 한다.
- parameter version, canonical payload, fingerprint가 1:1 identity를 유지해야 한다.
- 장중 provisional과 완료 final 결과가 동일한 interface에서 명확히 구분되어야 한다.
- V1 Golden을 유지하면서 V2 50%·stop·lot R·기간 경계가 독립적으로 검증되어야 한다.

---

### Task 1: Parameter registry, fingerprint, domain model

**Files:**
- Create: `src/strategies/swing_w150/parameters.py`
- Modify: `src/strategies/models.py`
- Modify: `src/storage/canonical.py`
- Modify: `src/strategies/protocol.py`
- Modify: `src/strategies/runner.py`
- Create: `tests/strategies/swing_w150/test_parameters.py`
- Modify: `tests/storage/test_canonical.py`
- Modify: `tests/strategies/test_runner.py`

**Interfaces:**
- Produces: `SwingW150Parameters`, `ParameterRegistry`, `parameter_fingerprint()`, 새 Observation/Signal/Opportunity/Bundle models
- Consumes: canonical JSON utility, `ChartBundle`

- [ ] **Step 1: production registry와 custom fingerprint RED test를 작성한다.**

```python
def test_registered_version_has_one_canonical_payload():
    params = SWING_W150_PARAMETER_REGISTRY.get("SWING_W150_V2_PARAMS_V1")
    assert params.parameter_fingerprint == parameter_fingerprint(params)
    with pytest.raises(ValueError, match="registered parameter payload mismatch"):
        SWING_W150_PARAMETER_REGISTRY.validate(
            replace(params, overheat_extension=0.35)
        )


def test_custom_parameters_get_distinct_fingerprint():
    base = SWING_W150_PARAMETER_REGISTRY.get("SWING_W150_V2_PARAMS_V1")
    custom = replace(base, parameter_set_version="CUSTOM", overheat_extension=0.35)
    assert parameter_fingerprint(custom) != parameter_fingerprint(base)
```

- [ ] **Step 2: model invariant RED test를 작성한다.**

```python
def test_current_signals_must_equal_today_history(bundle_values, today_signal):
    with pytest.raises(ValidationError):
        StrategySignalBundle(
            **bundle_values,
            signal_history=[today_signal],
            current_signals=[],
        )


def test_signal_rejects_empty_evidence_and_uses_decimal_price(signal_values):
    with pytest.raises(ValidationError):
        StrategySignal(**signal_values, evidence=[])
    signal = StrategySignal(**signal_values, signal_price=Decimal("100.25"))
    assert signal.signal_price == Decimal("100.25")
```

- [ ] **Step 3: input hash에 fingerprint가 포함되는 RED test를 작성한다.**

```python
def test_strategy_input_hash_changes_with_parameter_fingerprint(bundle):
    first = strategy_input_hash(
        bundle,
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_fingerprint="aaa",
    )
    second = strategy_input_hash(
        bundle,
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_fingerprint="bbb",
    )
    assert first != second
```

- [ ] **Step 4: RED를 확인한다.**

Run: `uv run pytest tests/strategies/swing_w150/test_parameters.py tests/storage/test_canonical.py tests/strategies/test_runner.py -q`
Expected: missing registry/model/hash fields로 FAIL

- [ ] **Step 5: parameter와 model을 구현한다.**

`SwingW150Parameters`는 spec의 모든 field를 frozen dataclass로 구현한다. registry는 production version과 canonical payload를 고정한다. custom payload는 fingerprint를 identity로 사용한다.

```python
class SignalStrategyProtocol(Protocol):
    strategy_id: str
    strategy_version: str
    parameters: SwingW150Parameters

    def evaluate_signals(self, bundle: ChartBundle) -> StrategySignalBundle: ...
```

Runner는 legacy `verdicts`와 V2 `signal_bundles`를 분리한다.

- [ ] **Step 6: focused test를 GREEN으로 만든다.**

Run: `uv run pytest tests/strategies/swing_w150/test_parameters.py tests/storage/test_canonical.py tests/strategies/test_runner.py -q`
Expected: PASS

- [ ] **Step 7: 승인된 경우 정확한 Task 1 파일만 checkpoint commit한다.**

### Task 2: Bar finality와 raw OHLCV → feature 경계

**Files:**
- Modify: `src/strategies/models.py`
- Modify: `src/strategies/chart_bundle.py`
- Create: `src/strategies/swing_w150/features.py`
- Modify: `src/pipelines/strategy_analysis.py`
- Modify: `src/tools/technical/tool.py`
- Modify: `tests/strategies/test_chart_bundle.py`
- Create: `tests/strategies/swing_w150/test_features.py`
- Modify: `tests/pipelines/test_strategy_analysis.py`
- Modify: `tests/tools/technical/test_tool.py`

**Interfaces:**
- Produces: `BarFinality`, `SwingFeatureFrame`, `build_swing_features(raw_ohlcv, params)`
- Consumes: raw OHLCV, exchange session close metadata, `IndicatorCalculator`

- [ ] **Step 1: finality RED test를 작성한다.**

```python
def test_current_open_session_is_provisional(chart_bundle_factory):
    bundle = chart_bundle_factory(current_session_open=True)
    assert bundle.instrument.bars[-1].finality is BarFinality.PROVISIONAL


def test_historical_and_closed_sessions_are_final(chart_bundle_factory):
    bundle = chart_bundle_factory(current_session_open=False)
    assert all(bar.finality is BarFinality.FINAL for bar in bundle.instrument.bars)
```

- [ ] **Step 2: raw-to-feature contract RED test를 작성한다.**

```python
def test_feature_builder_calculates_all_signal_inputs(raw_ohlcv, params):
    features = build_swing_features(raw_ohlcv, params)
    required = {
        "SMA_20", "SMA_50", "SMA_150", "SMA_200",
        "ATR", "SuperTrend_Up", "SuperTrend_Dir", "cRSI", "MACD",
    }
    assert required <= set(features.frame.columns)


def test_feature_builder_requires_only_minimum_history(raw_ohlcv, params):
    assert build_swing_features(raw_ohlcv.tail(250), params).data_status is DataStatus.COMPLETE
    assert build_swing_features(raw_ohlcv.tail(249), params).data_status is DataStatus.INSUFFICIENT_DATA
```

- [ ] **Step 3: RED를 확인한다.**

Run: `uv run pytest tests/strategies/test_chart_bundle.py tests/strategies/swing_w150/test_features.py tests/pipelines/test_strategy_analysis.py tests/tools/technical/test_tool.py -q`
Expected: missing finality/feature boundary와 기존 3y expectation으로 FAIL

- [ ] **Step 4: finality와 feature builder를 구현한다.**

Feature builder만 `IndicatorCalculator`를 호출한다. Detector는 raw OHLCV나 DataFrame 임의 column을 직접 계산하지 않고 typed `SwingFeatureFrame`만 받는다. SMA50·150·200 방향은 `direction_lookback_bars=21`로 동일하게 계산한다.

- [ ] **Step 5: 실시간 period를 2y로 바꾼다.**

`TechnicalAnalysisTool.CANONICAL_TECHNICAL_PERIOD`와 market loader period를 `2y`로 변경한다. 실제 bar 수가 250보다 작으면 추정하지 않고 insufficient data를 반환한다. Backtest는 이 period를 사용하지 않는다.

- [ ] **Step 6: focused test를 GREEN으로 만든다.**

Run: `uv run pytest tests/strategies/test_chart_bundle.py tests/strategies/swing_w150/test_features.py tests/pipelines/test_strategy_analysis.py tests/tools/technical/test_tool.py -q`
Expected: PASS

- [ ] **Step 7: 승인된 경우 정확한 Task 2 파일만 checkpoint commit한다.**

### Task 3: Causal Observation·Signal detector

**Files:**
- Create: `src/strategies/swing_w150/signals.py`
- Modify: `src/strategies/swing_w150/rules.py`
- Modify: `tests/strategies/swing_w150/conftest.py`
- Create: `tests/strategies/swing_w150/test_signals.py`
- Create: `tests/fixtures/swing_w150/v2_signal_path.csv`
- Create: `tests/fixtures/swing_w150/v2_signal_path.json`

**Interfaces:**
- Produces: `detect_swing(ticker, features, params) -> SwingSignalDetection`
- Consumes: typed `SwingFeatureFrame`, canonical parameters

- [ ] **Step 1: 과열 transition RED test를 작성한다.**

```python
def test_overheat_sequence_emits_each_transition_once(signal_factory, params):
    result = detect_test(signal_factory.overheat_correction_recovery(), params)
    assert codes(result) == [
        "OVERHEAT",
        "OVERHEAT_CORRECTION",
        "POST_OVERHEAT_RECOVERY_ENTRY",
    ]


def test_overheat_resolve_and_expiry_reset_without_recovery_entry(signal_factory, params):
    resolved = detect_test(signal_factory.overheat_then_reset_extension(), params)
    expired = detect_test(signal_factory.overheat_then_expiry(), params)
    assert codes(resolved)[-1] == "OVERHEAT_RESOLVED"
    assert codes(expired)[-1] == "OVERHEAT_EXPIRED"
    assert "POST_OVERHEAT_RECOVERY_ENTRY" not in codes(resolved) + codes(expired)


def test_corrected_phase_expires_after_twenty_bars(signal_factory, params):
    result = detect_test(signal_factory.correction_without_recovery(20), params)
    assert observation(result, "POST_OVERHEAT_RECOVERY_WATCH").status is ObservationStatus.EXPIRED
```

- [ ] **Step 2: 눌림목 lifecycle RED test를 작성한다.**

```python
@pytest.mark.parametrize("support", ["SMA_50", "SMA_150", "SMA_200", "SuperTrend_Up"])
def test_pullback_support_to_signal_once(signal_factory, params, support):
    result = detect_test(signal_factory.pullback_reversal(support, atr_distance=0.5), params)
    episode = observation(result, "PULLBACK_WATCH")
    assert episode.status is ObservationStatus.RESOLVED_TO_SIGNAL
    assert codes(result).count("PULLBACK_REVERSAL_ENTRY") == 1


def test_pullback_invalidates_or_expires_and_does_not_late_fire(signal_factory, params):
    invalid = detect_test(signal_factory.pullback_invalidated(), params)
    expired = detect_test(signal_factory.pullback_expired_then_breakout(), params)
    assert observation(invalid, "PULLBACK_WATCH").status is ObservationStatus.INVALIDATED
    assert observation(expired, "PULLBACK_WATCH").status is ObservationStatus.EXPIRED
    assert "PULLBACK_REVERSAL_ENTRY" not in codes(expired)
```

- [ ] **Step 3: SMA150 one-shot과 same-day priority RED test를 작성한다.**

```python
def test_sma150_exit_emits_on_second_below_close_only(signal_factory, params):
    result = detect_test(signal_factory.sma150_below_for_four_days(), params)
    assert codes(result).count("SMA150_EXIT") == 1


def test_all_same_day_events_are_kept_in_priority_order(signal_factory, params):
    result = detect_test(signal_factory.same_day_exit_and_entry(), params)
    today = [item.code for item in result.current_signals]
    assert today == ["SMA150_EXIT", "PULLBACK_REVERSAL_ENTRY"]
```

- [ ] **Step 4: raw OHLCV Golden RED test를 작성한다.**

```python
def test_raw_price_to_final_signal_golden(v2_raw_fixture, v2_expected_fixture, params):
    features = build_swing_features(v2_raw_fixture, params)
    result = detect_swing("TEST", features, params)
    assert result.model_dump(mode="json") == v2_expected_fixture
```

- [ ] **Step 5: RED를 확인한다.**

Run: `uv run pytest tests/strategies/swing_w150/test_signals.py -q`
Expected: missing causal detector로 FAIL

- [ ] **Step 6: explicit phase machine을 구현한다.**

Overheat phase는 `NORMAL/OVERHEATED/CORRECTED`, pullback phase는 `NONE/WATCHING`, SMA150은 `ABOVE/BELOW_ONCE/LATCHED_EXIT`로 한 번의 함수 호출 안에서만 추적한다. phase, support identity, 시작 bar, expiry는 차트 prefix에서 매번 재생한다.

- [ ] **Step 7: prefix 불변성을 bundle 전체로 검증한다.**

각 evaluation date에서 prefix만 전달한 결과와 긴 one-pass 결과를 비교한다. Observation history, Signal history, current signals가 모두 같아야 한다.

- [ ] **Step 8: focused test를 GREEN으로 만든다.**

Run: `uv run pytest tests/strategies/swing_w150/test_signals.py -q`
Expected: PASS

- [ ] **Step 9: 승인된 경우 정확한 Task 3 파일만 checkpoint commit한다.**

### Task 4: 항상 존재하고 supersession을 아는 EntryOpportunity

**Files:**
- Modify: `src/strategies/entry_opportunity.py`
- Modify: `src/strategies/swing_w150/adapter.py`
- Modify: `tests/strategies/test_entry_opportunity.py`
- Modify: `tests/strategies/swing_w150/test_adapter.py`

**Interfaces:**
- Produces: `evaluate_entry_opportunity(signal_history, bundle, params) -> EntryOpportunity`
- Consumes: entry/exit/correction Signal history, market chart

- [ ] **Step 1: total status truth table RED test를 작성한다.**

```python
@pytest.mark.parametrize(
    ("case", "status"),
    [
        ("age_20_bull_within_limit", EntryOpportunityStatus.ALLOW),
        ("age_21", EntryOpportunityStatus.EXPIRED),
        ("no_entry_complete_history", EntryOpportunityStatus.NO_RECENT_SIGNAL),
        ("no_entry_truncated_history", EntryOpportunityStatus.NOT_EVALUATED),
        ("bear_market", EntryOpportunityStatus.BLOCK),
        ("entry_then_correction", EntryOpportunityStatus.INVALIDATED),
        ("entry_then_sma150_exit", EntryOpportunityStatus.INVALIDATED),
    ],
)
def test_entry_opportunity_truth_table(cases, case, status):
    result = evaluate_entry_opportunity(**cases[case])
    assert result.status is status
    assert result.evidence
```

- [ ] **Step 2: 새로운 entry가 old invalidation을 대체하는 RED test를 작성한다.**

```python
def test_new_entry_after_correction_becomes_source(history_case):
    result = evaluate_entry_opportunity(**history_case)
    assert result.entry_signal.code == "PULLBACK_REVERSAL_ENTRY"
    assert result.invalidated_by is None
```

- [ ] **Step 3: provisional/final propagation RED test를 작성한다.**

```python
def test_opportunity_uses_source_and_current_bar_finality(provisional_case):
    result = evaluate_entry_opportunity(**provisional_case)
    assert result.finality is SignalFinality.PROVISIONAL
```

- [ ] **Step 4: RED를 확인한다.**

Run: `uv run pytest tests/strategies/test_entry_opportunity.py tests/strategies/swing_w150/test_adapter.py -q`
Expected: legacy nullable stop/R opportunity로 FAIL

- [ ] **Step 5: EntryOpportunity와 adapter를 구현한다.**

V2 adapter는 `replay_trace()`와 고정 3년 origin을 사용하지 않는다. `entry_signal`, `invalidated_by`, age, market regime, extension, Evidence만 반환하며 opportunity는 절대 `None`이 아니다.

- [ ] **Step 6: 미래 suffix 불변성을 최종 bundle로 검증한다.**

동일 evaluation date의 prefix 결과와 미래 suffix가 붙은 frame을 같은 date에서 자른 결과의 Observation history, Signal history, current signals, EntryOpportunity가 모두 같아야 한다.

- [ ] **Step 7: focused test를 GREEN으로 만든다.**

Run: `uv run pytest tests/strategies/test_entry_opportunity.py tests/strategies/swing_w150/test_adapter.py -q`
Expected: PASS

- [ ] **Step 8: 승인된 경우 정확한 Task 4 파일만 checkpoint commit한다.**

### Task 5: Pipeline wiring과 PostgreSQL strategy_history 제거

**Files:**
- Modify: `src/strategies/runner.py`
- Modify: `src/pipelines/strategy_analysis.py`
- Modify: `src/pipelines/strategy_render.py`
- Modify: `src/pipelines/quick_check.py`
- Modify: `src/pipelines/deep_dive.py`
- Modify: `src/pipelines/brief.py`
- Modify: `src/tools/brief/models.py`
- Modify: `src/tools/brief/render.py`
- Delete: `src/storage/strategy_history/`
- Delete: `tests/storage/strategy_history/`
- Delete: `migrations/strategy_history/`
- Modify: `tests/pipelines/test_strategy_analysis.py`
- Modify: `tests/pipelines/test_quick_check.py`
- Modify: `tests/pipelines/test_deep_dive.py`
- Modify: `tests/pipelines/test_brief.py`
- Modify: `tests/storage/postgres/test_migrations.py`

**Interfaces:**
- Produces: DB 없는 `AnalysisStrategyService.evaluate()`와 공통 renderer
- Removes: persistence session lifecycle와 모든 `strategy_history` runtime import

- [ ] **Step 1: 세 pipeline parity와 history 출력 RED test를 작성한다.**

```python
def test_three_surfaces_show_same_core_strategy_content(rendered_surfaces):
    for rendered in rendered_surfaces:
        assert "PULLBACK_WATCH" in rendered
        assert "PULLBACK_REVERSAL_ENTRY" in rendered
        assert "오늘 EntryOpportunity" in rendered


def test_observation_and_signal_history_are_separate(rendered):
    assert "최근 Observation history" in rendered
    assert "최근 Signal history" in rendered
```

- [ ] **Step 2: V2 persistence가 완전히 없는 RED contract를 작성한다.**

```python
def test_strategy_analysis_has_no_persistence_dependency():
    source = inspect.getsource(AnalysisStrategyService)
    assert "persistence" not in source
    assert "strategy_history" not in source


def test_no_strategy_history_runtime_or_migration_files():
    assert not Path("src/storage/strategy_history").exists()
    assert not Path("migrations/strategy_history").exists()
```

- [ ] **Step 3: RED를 확인한다.**

Run: `uv run pytest tests/pipelines/test_strategy_analysis.py tests/pipelines/test_quick_check.py tests/pipelines/test_deep_dive.py tests/pipelines/test_brief.py tests/storage/postgres/test_migrations.py -q`
Expected: legacy persistence와 mixed renderer로 FAIL

- [ ] **Step 4: runtime wiring과 renderer를 전환한다.**

기본 출력은 현재 Observation, 최근 20거래일 Observation history, 최근 20거래일 Signal history,
오늘 EntryOpportunity를 표시한다. detailed 출력은 모든 Evidence와 방향을 보여준다. 기존
`summarize_swing_w150()` production 출력은 제거한다.

- [ ] **Step 5: strategy_history subsystem을 삭제한다.**

repository, replay, episodes, maturity, envelopes, migration loader, schema SQL, 관련 tests와 imports를 삭제한다. PostgreSQL 공통 connection/migration utility와 canonical hash utility는 유지한다.

- [ ] **Step 6: focused test와 import search를 GREEN으로 만든다.**

Run: `uv run pytest tests/pipelines/test_strategy_analysis.py tests/pipelines/test_quick_check.py tests/pipelines/test_deep_dive.py tests/pipelines/test_brief.py tests/storage/postgres/test_migrations.py -q`
Expected: PASS

Run: `rg -n "storage\.strategy_history|migrations/strategy_history" src tests migrations`
Expected: no matches

- [ ] **Step 7: 승인된 경우 정확한 Task 5 파일만 checkpoint commit한다.**

### Task 6: 두 기준을 분리한 on-demand SignalPerformance

**Files:**
- Create: `src/strategies/signal_performance.py`
- Create: `tests/strategies/test_signal_performance.py`
- Modify: `src/pipelines/strategy_analysis.py`
- Modify: `src/pipelines/strategy_render.py`

**Interfaces:**
- Produces: `SignalPerformance`, `evaluate_signal_performance()`
- Consumes: entry Signal, instrument bars, evaluation date

- [ ] **Step 1: estimate와 executed return RED test를 작성한다.**

```python
def test_signal_day_has_estimate_but_no_executed_return(signal, signal_day_chart):
    result = evaluate_signal_performance(signal, signal_day_chart)
    assert result.estimated_return_from_signal_close == Decimal("0")
    assert result.executed_return_from_next_tradable_open is None


def test_next_tradable_open_creates_executed_return(signal, suspended_chart):
    result = evaluate_signal_performance(signal, suspended_chart)
    assert result.execution_delay_sessions == 2
    assert result.execution_reference_price == suspended_chart.instrument.bars[-1].open
```

- [ ] **Step 2: 비거래 평가일과 missing next bar RED test를 작성한다.**

```python
def test_non_trading_evaluation_uses_previous_final_session(signal, weekend_chart):
    result = evaluate_signal_performance(signal, weekend_chart, requested_as_of=date(2026, 10, 11))
    assert result.evaluation_as_of == date(2026, 10, 9)


def test_missing_next_bar_is_explicitly_not_evaluated(signal, signal_day_chart):
    result = evaluate_signal_performance(signal, signal_day_chart)
    assert result.executed_data_status is DataStatus.NOT_EVALUATED
```

- [ ] **Step 3: RED를 확인한다.**

Run: `uv run pytest tests/strategies/test_signal_performance.py -q`
Expected: missing performance module로 FAIL

- [ ] **Step 4: pure calculator와 renderer를 구현한다.**

Calculator는 repository를 import하지 않는다. estimate와 executed metric의 가격·basis·status를 별도 field로 반환하고 parameter fingerprint를 포함한다.

- [ ] **Step 5: focused test를 GREEN으로 만든다.**

Run: `uv run pytest tests/strategies/test_signal_performance.py tests/pipelines/test_strategy_analysis.py -q`
Expected: PASS

- [ ] **Step 6: 승인된 경우 정확한 Task 6 파일만 checkpoint commit한다.**

### Task 7: V1 compatibility와 causal V2 Backtest

**Files:**
- Create: `src/backtest/swing_w150.py`
- Create: `tests/backtest/test_swing_w150.py`
- Create: `tests/fixtures/swing_w150/v2_backtest_expected.json`
- Modify: `tests/strategies/swing_w150/test_golden.py`

**Interfaces:**
- Produces: `SwingExecutionPolicy`, `SwingRiskPolicy`, `simulate_swing_v2()`
- Consumes: FINAL Signal history, OHLCV, explicit warmup/test period

- [ ] **Step 1: V1 baseline 불변 RED test를 유지·확장한다.**

기존 `engine.py`와 V1 fixture를 변경하지 않고 기존 Golden 전체가 그대로 통과해야 한다.

- [ ] **Step 2: 기간과 causal identity RED test를 작성한다.**

```python
def test_backtest_excludes_warmup_signals_and_cuts_at_test_end(case):
    result = simulate_swing_v2(
        case.bars,
        case.params,
        case.execution_policy,
        warmup_start=date(2025, 1, 1),
        test_start=date(2026, 1, 1),
        test_end=date(2026, 6, 30),
    )
    assert all(date(2026, 1, 1) <= trade.entry_date <= date(2026, 6, 30) for trade in result.trades)
    assert result.identity.test_end == date(2026, 6, 30)


def test_one_pass_matches_evaluation_prefixes(case):
    assert case.one_pass_result.signal_history == case.prefix_recomputed_history
```

- [ ] **Step 3: 체결 우선순위와 50% RED test를 작성한다.**

```python
def test_gap_stop_fills_at_open_before_close_signal(case):
    result = simulate_swing_v2(**case)
    assert result.orders[0].reason == "gap_stop"
    assert result.orders[0].price == case.bars.loc[case.gap_day, "Open"]


def test_overheat_correction_sells_half_rounding_up(case):
    result = simulate_swing_v2(**case.with_quantity(5))
    order = next(item for item in result.orders if item.reason == "OVERHEAT_CORRECTION")
    assert order.quantity == 3
```

- [ ] **Step 4: lot risk와 recovery RED test를 작성한다.**

```python
def test_partial_exit_keeps_remaining_lot_basis_and_risk(case):
    result = simulate_swing_v2(**case)
    assert result.open_lots[0].entry_price == case.original_entry
    assert result.open_lots[0].initial_risk_per_share == case.original_risk


def test_recovery_entry_creates_new_lot_and_aggregate_r(case):
    result = simulate_swing_v2(**case)
    assert len(result.closed_lots) == 2
    expected = sum(lot.realized_pnl for lot in result.closed_lots) / sum(
        lot.initial_risk_capital for lot in result.closed_lots
    )
    assert result.aggregate_r == expected
```

- [ ] **Step 5: RED를 확인한다.**

Run: `uv run pytest tests/backtest/test_swing_w150.py tests/strategies/swing_w150/test_golden.py -q`
Expected: missing V2 adapter로 FAIL, V1 Golden PASS

- [ ] **Step 6: V2 execution/risk policy와 lot ledger를 구현한다.**

Spec의 네 entry stop 산식, T+1 실제 거래 가능 시가, stop 우선, fee/slippage, 50% correction,
risk target recovery를 구현한다. provisional Signal은 validation error로 거부한다.

- [ ] **Step 7: V2 Golden과 focused test를 GREEN으로 만든다.**

Run: `uv run pytest tests/backtest/test_swing_w150.py tests/strategies/swing_w150/test_golden.py -q`
Expected: PASS

- [ ] **Step 8: 승인된 경우 정확한 Task 7 파일만 checkpoint commit한다.**

### Task 8: Provisional current Signal을 사용하는 PositionPlanner

**Files:**
- Modify: `src/position/models.py`
- Modify: `src/position/policy.py`
- Modify: `src/position/planner.py`
- Modify: `src/pipelines/strategy_analysis.py`
- Modify: `tests/position/test_policy.py`
- Modify: `tests/position/test_planner.py`
- Modify: `tests/pipelines/test_strategy_analysis.py`

**Interfaces:**
- Produces: `plan_position_from_signals()`와 finality/snapshot-bound `PositionPlan`
- Consumes: current signals, EntryOpportunity, real position/account/current market snapshot

- [ ] **Step 1: 과거 Signal 비사용과 current priority RED test를 작성한다.**

```python
def test_old_exit_never_overrides_today_entry(bundle_with_old_exit_today_entry):
    plan = plan_position_from_signals(**bundle_with_old_exit_today_entry)
    assert plan.directive.kind is DirectiveKind.BUILD_ONLY_TO_RISK_TARGET


def test_same_day_exit_wins_over_entry(bundle_with_same_day_conflict):
    plan = plan_position_from_signals(**bundle_with_same_day_conflict)
    assert plan.directive.kind is DirectiveKind.FLAT
```

- [ ] **Step 2: provisional plan RED test를 작성한다.**

```python
def test_provisional_signal_calculates_snapshot_bound_quantity(provisional_case):
    plan = plan_position_from_signals(**provisional_case)
    assert plan.signal_finality is SignalFinality.PROVISIONAL
    assert plan.market_snapshot_hash == provisional_case["market_snapshot"].snapshot_hash
    assert plan.buy_quantity > 0
```

- [ ] **Step 3: correction/exit 실제 수량 RED test를 작성한다.**

```python
def test_correction_sells_half_rounding_up(position_5_case):
    plan = plan_position_from_signals(**position_5_case)
    assert plan.sell_quantity == 3
    assert plan.target_quantity == 2


def test_flat_position_keeps_sell_signal_but_quantity_zero(flat_exit_case):
    plan = plan_position_from_signals(**flat_exit_case)
    assert plan.sell_quantity == 0
```

- [ ] **Step 4: RED를 확인한다.**

Run: `uv run pytest tests/position tests/pipelines/test_strategy_analysis.py -q`
Expected: missing signal planner와 finality fields로 FAIL

- [ ] **Step 5: compatibility wrapper와 공통 directive planner를 구현한다.**

기존 `plan_position(verdict, ...)` signature는 Playbook용으로 유지한다. 새 함수는 `bundle.current_signals`와 opportunity만 읽고 공통 내부 quantity calculator를 호출한다. provisional도 계산하되 결과에 finality, `calculated_at`, snapshot hash를 표시한다.

- [ ] **Step 6: focused test를 GREEN으로 만든다.**

Run: `uv run pytest tests/position tests/pipelines/test_strategy_analysis.py -q`
Expected: PASS

- [ ] **Step 7: 승인된 경우 정확한 Task 8 파일만 checkpoint commit한다.**

### Task 9: 문서, 전체 검증, 실제 pipeline

**Files:**
- Modify: `docs/FEATURES.md`
- Modify: `docs/changes/scorecard-strategy-position-separation.md`
- Modify: `docs/changes/INDEX.md`
- Modify: `docs/worklog/swing-w150-engine.md`
- Modify: `docs/active-context.md`
- Modify: `docs/superpowers/specs/2026-10-06-strategy-signal-outcome-backtest-boundary-design.md`
- Modify: `docs/superpowers/plans/2026-10-06-strategy-signal-boundary-migration.md`

**Interfaces:**
- Produces: 최신 사용자 문서, 검증 evidence, handoff 가능한 상태

- [x] **Step 1: 문서를 실제 동작으로 갱신한다.**

Observation/Signal 차이, provisional PositionPlan, parameter fingerprint, 과열·눌림목 상태 전이,
V1/V2 Backtest, PostgreSQL 제거를 반영한다.

- [x] **Step 2: focused architecture suite를 실행한다.**

Run: `uv run pytest tests/strategies tests/position tests/backtest/test_swing_w150.py tests/pipelines/test_strategy_analysis.py tests/pipelines/test_quick_check.py tests/pipelines/test_deep_dive.py tests/pipelines/test_brief.py tests/storage/test_canonical.py tests/storage/postgres/test_migrations.py -q`
Expected: PASS

- [x] **Step 3: 전체 verification을 실행한다.**

Run: `uv run pytest -q`
Expected: all tests PASS

Run: `uv run ruff check src tests`
Expected: PASS

Run: `git diff --check`
Expected: PASS

Run: `rg -n "storage\.strategy_history|migrations/strategy_history" src tests migrations docs`
Expected: historical worklog/change-record 설명을 제외한 runtime·migration·test match 0건

- [x] **Step 4: 실제 pipeline을 실행한다.**

Run: `uv run jarvis check NVDA`
Expected: Observation history, Signal history, provisional/final 표시, EntryOpportunity 출력

Run: `uv run jarvis analyze NVDA`
Expected: check와 같은 core Signal 의미 출력

Run: `uv run jarvis brief`
Expected: 각 종목의 동일한 core Signal·EntryOpportunity 요약

provider/network가 없으면 정확한 오류와 미검증 범위를 기록하고 성공으로 간주하지 않는다.

- [x] **Step 5: self-review로 기존 독립 review finding을 모두 대조한다.**

이번 계획 전에 수행한 단 한 번의 독립 review에서 나온 Critical 5개와 Important 8개를 체크리스트로
대조한다. Task 9 담당자는 self-review만 수행하며, 사용자 최신 요청의 최종 독립 `reason=xhigh`
리뷰는 Task 9 이후 coordinator가 수행한다.

- [ ] **Step 6: 승인된 경우 task 파일만 명시적으로 stage해 final commit한다.**

`git status --short`와 `git diff --name-only`를 확인하고 unrelated dirty file을 제외한다. push·PR·merge는 각각 별도 승인 후 수행한다.

# Scorecard · Strategy · Position 분리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 5축 기술 Scorecard, ChartBundle-only Strategy 세 종류, 실제 계좌 기반 PositionPlanner를 분리하고 세 pipeline에서 같은 결과를 표시·PostgreSQL에 추적한다.

**Architecture:** 기존 technical component 계산은 재사용하되 측정 모델은 `src/tools/technical/scorecard_*`, 전략 모델과 실행기는 `src/strategies/`, 실제 수량 계산은 `src/position/`에 둔다. `check`, `analyze`, `brief`는 공통 `AnalysisStrategyService`를 호출하며 PostgreSQL은 immutable history/cache로만 사용한다.

**Tech Stack:** Python 3.12, Pydantic v2, pandas, psycopg 3, Typer/Rich, pytest, uv

**Spec:** `docs/superpowers/specs/2026-10-01-scorecard-strategy-position-separation-design.md`

## Global Constraints

- `StrategyVerdict = f(ChartBundle prefix, strategy_version)`이며 holding, account, actual trade, news, fundamental, disclosure, flow, macro, DB state를 읽지 않는다.
- `PositionPlanner`만 실제 position/account snapshot을 읽으며 `REDUCE`는 `ceil(current_quantity * 0.5)` 매도다.
- 신호·상태 기준은 거래소 session date이고 `computed_at`만 Jarvis 실행 시각이다.
- production Strategy는 `TECHNICAL_LEGACY`, `PLAYBOOK_V1`, `SWING_W150` 세 개다.
- 미국 EntryOpportunity benchmark는 SPY이며 한국은 검증 전 `NOT_EVALUATED`다.
- persistence 미설정·실패는 계산 결과를 막지 않고 warning으로 드러낸다.
- package 설치와 test 실행은 항상 `uv`를 사용한다.
- `src/` 변경 완료 시 `docs/changes/`와 `docs/changes/INDEX.md`를 갱신한다.

## Review Focus

- 동일 ChartBundle을 서로 다른 pipeline·DB 상태에서 실행해도 canonical verdict bytes가 같은지 Task 6·8에서 검증한다.
- rolling 3년 coverage가 잘렸거나 session manifest가 불완전하면 SWING이 추측하지 않고 `NOT_EVALUATED`인지 Task 5에서 검증한다.
- 같은 날 SWING 복수 event와 event 없는 intent transition이 deterministic episode anchor를 갖는지 Task 9에서 검증한다.
- Playbook에 dated entry 기준가가 없을 때 gap 제한을 만들지 않고 session/data만 검사하는지 Task 7에서 검증한다.
- provider timeout·DB write 실패 뒤 재실행이 immutable result identity를 점유하거나 pipeline을 실패시키지 않는지 Task 9에서 검증한다.

## Test Fixture Contracts

- `make_calculated_df()`는 `tests/fixtures/swing_w150/PYPL.csv`를 읽어 날짜 index와 OHLCV를 반환하고, `make_legacy_result()`는 그 frame을 `TechnicalScorer.score(..., include_history=False)`에 넣은 결과다.
- `df_without_volume()`은 같은 frame에서 `Volume`을 제거한다. required input 결측 경로 외의 값은 바꾸지 않는다.
- `make_bundle(manifest=...)`는 PYPL instrument와 같은 날짜의 synthetic SPY benchmark를 포함하며 bundle hash는 Task 1 serializer로 계산한다.
- `make_cross_df(short, long)`는 260개의 일정한 장기선 구간 뒤 마지막 두 bar에서 short SMA가 long SMA 아래→위로 한 번만 바뀌는 OHLCV를 만든다. `make_trigger_df()`와 `make_breakout_then_failure_df()`는 각각 마지막 10 bar에 돌파 1회, 돌파 뒤 종가 이탈 1회를 넣는다.
- `entry_event(reference_entry)`는 `SWING_W150_ENTRY_V1` event와 stop 90을 만들고, `bundle_for_regime(regime, close)`는 SPY의 `Close/SMA50/SMA200` 관계를 bull=`110/105/100`, sideways=`105/100/102`, bear=`90/95/100`으로 만든다.
- `make_runner(cache)`는 `TECHNICAL_LEGACY`, `PLAYBOOK_V1`, `SWING_W150`을 고정 순서로 주입한다. `preloaded_cache(result)`는 같은 `strategy_input_hash`의 immutable verdict bytes만 반환한다.
- `shared_bundle_fixture()`는 위 PYPL/프록시 SPY bundle 한 개를 세 pipeline에 같은 객체로 주입한다. pipeline별 provider mock이 새 시각이나 다른 frame을 만들지 못하게 한다.
- PostgreSQL repository tests는 Docker를 요구하지 않는 recording connection으로 SQL/transaction 경계를 고정하고, 실제 PostgreSQL integration mark에서는 임시 `strategy_history` schema를 생성·rollback한다.

---

### Task 1: Canonical identity와 ChartBundle 경계

**Files:**
- Create: `src/strategies/models.py`
- Create: `src/strategies/chart_bundle.py`
- Create: `src/storage/canonical.py`
- Modify: `src/strategies/__init__.py`
- Test: `tests/storage/test_canonical.py`
- Test: `tests/strategies/test_chart_bundle.py`

**Interfaces:**
- Consumes: 종목·benchmark OHLCV `pd.DataFrame`, exchange session dates
- Produces: `ChartSeries`, `CoverageManifest`, `ChartBundle`, `canonical_bytes(value)`, `canonical_hash(domain, value)`, `strategy_input_hash(bundle, strategy_id, strategy_version)`

- [ ] **Step 1: canonical serializer RED test 작성**

```python
def test_canonical_numbers_and_datetimes_have_one_representation():
    assert canonical_bytes({"n": 1}) == canonical_bytes({"n": 1.0})
    assert canonical_bytes({"n": Decimal("1.00")}) == canonical_bytes({"n": 1})
    assert canonical_bytes({"n": -0.0}) == canonical_bytes({"n": 0})
    with pytest.raises(ValueError):
        canonical_bytes({"n": float("nan")})
    with pytest.raises(ValueError):
        canonical_bytes({"at": datetime(2026, 10, 2, 9, 0)})
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/storage/test_canonical.py -q`
Expected: FAIL with missing `src.storage.canonical`.

- [ ] **Step 3: canonical serializer와 hash 구현**

```python
def canonical_hash(domain: str, value: object) -> str:
    payload = canonical_bytes(value)
    return hashlib.sha256(domain.encode() + b"\0" + payload).hexdigest()

def strategy_input_hash(
    bundle: ChartBundle, *, strategy_id: str, strategy_version: str
) -> str:
    return canonical_hash(
        "jarvis:strategy-input:v1",
        {
            "chart_bundle_hash": bundle.bundle_hash,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
        },
    )
```

Serializer는 key 정렬, UTF-8, compact JSON, UTC `Z`, normalized decimal string을 사용한다.

- [ ] **Step 4: ChartBundle coverage RED test 작성**

```python
def test_chart_bundle_rejects_unproven_coverage():
    manifest = CoverageManifest(
        requested_start=date(2023, 10, 2),
        actual_start=date(2024, 1, 2),
        actual_end=date(2026, 10, 2),
        complete=False,
        truncation_reason="provider_limit",
    )
    bundle = make_bundle(manifest=manifest)
    assert bundle.has_complete_coverage(date(2023, 10, 2), date(2026, 10, 2)) is False
```

- [ ] **Step 5: ChartBundle 모델과 DataFrame adapter 구현**

```python
class ChartBundle(BaseModel):
    profile_version: str
    ticker: str
    as_of: date
    instrument: ChartSeries
    market: ChartSeries | None
    industry: ChartSeries | None
    exchange_sessions: tuple[date, ...]
    bundle_hash: str

    def prefix(self, as_of: date, *, origin: date | None = None) -> "ChartBundle":
        return slice_and_rehash_bundle(self, origin=origin, as_of=as_of)

    def has_complete_coverage(self, start: date, end: date) -> bool:
        manifest = self.instrument.coverage
        return (
            manifest.complete
            and manifest.requested_start <= start
            and manifest.actual_start <= start
            and manifest.actual_end >= end
        )
```

- [ ] **Step 6: GREEN 및 commit**

Run: `uv run pytest tests/storage/test_canonical.py tests/strategies/test_chart_bundle.py -q`
Expected: PASS.

```bash
git add src/storage/canonical.py src/strategies/models.py src/strategies/chart_bundle.py src/strategies/__init__.py tests/storage/test_canonical.py tests/strategies/test_chart_bundle.py
git commit -m "feat: add canonical chart bundle identity"
```

### Task 2: 5축 Scorecard 모델과 지속 상태 산식

**Files:**
- Create: `src/tools/technical/scorecard_models.py`
- Create: `src/tools/technical/scorecard.py`
- Modify: `src/tools/technical/scorer.py`
- Modify: `src/tools/technical/models.py`
- Test: `tests/tools/technical/test_scorecard.py`

**Interfaces:**
- Consumes: `TechnicalResult.components`, `IndicatorSnapshot`, calculated OHLCV
- Produces: `TechnicalScorecard`, `ScoreDimension`, `DirectionalMetric`, `Observation`, `Evidence`, `ScoreContribution`

- [ ] **Step 1: dimension mapping·결측 RED test 작성**

```python
def test_scorecard_maps_each_state_rule_to_one_dimension():
    scorecard = build_scorecard(make_calculated_df(), make_legacy_result())
    owners = [
        (dimension.code, contribution.rule_code)
        for dimension in scorecard.dimensions()
        for contribution in dimension.score_contributions
    ]
    assert len(owners) == len({rule for _, rule in owners})
    assert scorecard.legacy_adjusted_score == make_legacy_result().adjusted_score

def test_required_input_missing_does_not_reweight_dimension():
    result = build_scorecard(df_without_volume(), make_legacy_result())
    assert result.demand.score is None
    assert result.demand.data_status is DataStatus.INSUFFICIENT_DATA
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/tools/technical/test_scorecard.py -q`
Expected: FAIL with missing scorecard module.

- [ ] **Step 3: Pydantic 모델과 `build_scorecard` 구현**

```python
def build_scorecard(
    df: pd.DataFrame,
    legacy: TechnicalResult,
    *,
    ticker: str,
    as_of: date,
    version: str = "TECHNICAL_SCORECARD_V1",
) -> TechnicalScorecard:
    dimensions = build_dimensions(df, legacy)
    return TechnicalScorecard(
        version=version,
        ticker=ticker,
        as_of=as_of,
        **dimensions,
        triggers=detect_analysis_triggers(df, as_of=as_of),
        legacy_raw_total=legacy.component_raw_total,
        legacy_adjusted_score=legacy.adjusted_score,
    )
```

기존 component 지속 상태를 `minervini/supertrend → trend`, `patterns → structure`, `velocity/crsi/divergence → momentum`, `volume → demand`, `risk → safety`로 한 번만 배치한다. event성 bonus는 제외하고 spec의 0~100 정규화식을 적용한다.

- [ ] **Step 4: 방향성 metric test와 구현**

```python
def test_directional_metrics_preserve_value_slope_and_acceleration():
    metric = build_scorecard(make_calculated_df(), make_legacy_result()).trend.metrics["sma150"]
    assert metric.slope_lookback_bars == 21
    assert metric.direction in Direction
    assert metric.acceleration in Acceleration
    assert metric.calculation_version == "DIRECTION_V1"
```

SMA는 21-bar percentage slope, cRSI/MACD/volume은 5-bar slope, relative strength는 5·20-bar slope를 사용한다.

- [ ] **Step 5: scorer에 shadow scorecard 연결 후 GREEN**

`TechnicalResult`에 `scorecard: TechnicalScorecard | None = None`을 추가하고 기존 `technical_verdict`, totals, history는 그대로 둔다.

Run: `uv run pytest tests/tools/technical/test_scorecard.py tests/tools/technical/test_scoring_models.py tests/tools/technical/test_scorer.py -q`
Expected: PASS.

- [ ] **Step 6: commit**

```bash
git add src/tools/technical/scorecard_models.py src/tools/technical/scorecard.py src/tools/technical/scorer.py src/tools/technical/models.py tests/tools/technical/test_scorecard.py
git commit -m "feat: add five-axis technical scorecard"
```

### Task 3: 최근 20거래일 Analysis Trigger registry

**Files:**
- Create: `src/tools/technical/triggers.py`
- Create: `src/tools/technical/trigger_registry.py`
- Modify: `src/tools/technical/scorecard.py`
- Test: `tests/tools/technical/test_triggers.py`

**Interfaces:**
- Consumes: calculated OHLCV prefix
- Produces: `list[AnalysisTriggerEvent]`, `TriggerRuleDefinition`

- [ ] **Step 1: crossover·미래정보 차단 RED test 작성**

```python
@pytest.mark.parametrize("short,long", [(20, 50), (50, 150), (50, 200), (150, 200)])
def test_sma_cross_is_emitted_once_on_transition(short, long):
    events = detect_analysis_triggers(make_cross_df(short, long))
    code = f"analysis.sma.{short}_{long}.golden_cross"
    assert [e.code for e in events].count(code) == 1

def test_prefix_event_does_not_read_future_bars():
    full = make_trigger_df()
    cutoff = full.index[-6]
    assert detect_analysis_triggers(full.loc[:cutoff]) == detect_analysis_triggers(full).snapshot_at(cutoff)
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/tools/technical/test_triggers.py -q`
Expected: FAIL with missing trigger registry.

- [ ] **Step 3: registry와 detector 구현**

```python
def detect_analysis_triggers(
    df: pd.DataFrame, *, as_of: date, display_bars: int = 20
) -> list[AnalysisTriggerEvent]:
    calculated = IndicatorCalculator().calculate(df.loc[:pd.Timestamp(as_of)].copy())
    events = [event for rule in TRIGGER_RULES for event in rule.evaluate(calculated)]
    return sorted(
        (event for event in events if event.bars_ago <= display_bars),
        key=lambda event: (event.occurred_on, event.code),
        reverse=True,
    )
```

cRSI band cross, MACD/Fast MACD cross와 histogram zero cross, SMA direction/price/MA cross, Supertrend transition, 20·50-day high, VCP, Pocket Pivot, Power Gap, volume breakdown을 versioned definition으로 등록한다.

- [ ] **Step 4: invalidation·expiry·20-bar 경계 test 추가**

```python
def test_invalidated_event_remains_visible_inside_twenty_bars():
    event = detect_analysis_triggers(make_breakout_then_failure_df(), as_of=date(2026, 10, 2))[0]
    assert event.status is TriggerStatus.INVALIDATED
    assert event.invalidated_on is not None
    assert event.bars_ago <= 20
```

- [ ] **Step 5: Scorecard 연결 및 GREEN**

Run: `uv run pytest tests/tools/technical/test_triggers.py tests/tools/technical/test_scorecard.py -q`
Expected: PASS.

- [ ] **Step 6: commit**

```bash
git add src/tools/technical/triggers.py src/tools/technical/trigger_registry.py src/tools/technical/scorecard.py tests/tools/technical/test_triggers.py
git commit -m "feat: add versioned analysis triggers"
```

### Task 4: 공통 Strategy contract와 legacy adapter

**Files:**
- Modify: `src/strategies/models.py`
- Create: `src/strategies/protocol.py`
- Create: `src/strategies/legacy_technical.py`
- Test: `tests/strategies/test_legacy_technical.py`

**Interfaces:**
- Consumes: `ChartBundle`, legacy `TechnicalVerdict`
- Produces: `StrategyProtocol.evaluate(bundle) -> StrategyVerdict`, `LegacyTechnicalStrategy`

- [ ] **Step 1: mapping table RED test 작성**

```python
@pytest.mark.parametrize(
    ("action", "entry", "exit"),
    [
        ("buy", EntryIntent.ALLOW, ExitIntent.HOLD),
        ("add", EntryIntent.ALLOW, ExitIntent.HOLD),
        ("hold", EntryIntent.WATCH, ExitIntent.HOLD),
        ("watch", EntryIntent.WATCH, ExitIntent.HOLD),
        ("accumulate", EntryIntent.WATCH, ExitIntent.HOLD),
        ("reduce", EntryIntent.BLOCK, ExitIntent.REDUCE),
        ("avoid", EntryIntent.BLOCK, ExitIntent.NOT_EVALUATED),
    ],
)
def test_legacy_mapping(action, entry, exit):
    verdict = LegacyTechnicalStrategy().from_legacy(make_legacy_verdict(action))
    assert (verdict.entry.intent, verdict.exit.intent) == (entry, exit)
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/strategies/test_legacy_technical.py -q`
Expected: FAIL with missing adapter.

- [ ] **Step 3: typed verdict/state/event models와 protocol 구현**

```python
class StrategyProtocol(Protocol):
    strategy_id: str
    strategy_version: str
    def evaluate(self, bundle: ChartBundle) -> StrategyVerdict:
        raise NotImplementedError
```

`StrategyVerdict`는 entry와 exit를 항상 모두 반환하고 target exposure, quantity, holding 필드를 갖지 않는다.

- [ ] **Step 4: adapter 구현·GREEN·commit**

Run: `uv run pytest tests/strategies/test_legacy_technical.py -q`
Expected: PASS.

```bash
git add src/strategies/models.py src/strategies/protocol.py src/strategies/legacy_technical.py tests/strategies/test_legacy_technical.py
git commit -m "feat: add chart-only strategy contract"
```

### Task 5: SWING_W150 adapter와 EntryOpportunity

**Files:**
- Modify: `src/strategies/swing_w150/models.py`
- Modify: `src/strategies/swing_w150/engine.py`
- Create: `src/strategies/swing_w150/adapter.py`
- Create: `src/strategies/entry_opportunity.py`
- Test: `tests/strategies/swing_w150/test_adapter.py`
- Test: `tests/strategies/test_entry_opportunity.py`

**Interfaces:**
- Consumes: instrument ChartBundle, 미국 종목의 SPY ChartSeries
- Produces: full `StrategyVerdict`, dated `StrategyEvent`, `SwingRuntimeState`, 0..20-bar `EntryOpportunity`

- [ ] **Step 1: replay profile RED test 작성**

```python
def test_incomplete_rolling_coverage_returns_not_evaluated():
    verdict = SwingW150Strategy().evaluate(bundle_with_truncated_three_year_history())
    assert verdict.entry.intent is EntryIntent.NOT_EVALUATED
    assert verdict.exit.intent is ExitIntent.NOT_EVALUATED

def test_origin_before_open_cycle_uses_versioned_flat_seed():
    verdict = SwingW150Strategy().evaluate(bundle_whose_first_bar_is_mid_market_cycle())
    assert verdict.strategy_state == expected_flat_seed_replay_state()
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/strategies/swing_w150/test_adapter.py -q`
Expected: FAIL with missing adapter.

- [ ] **Step 3: engine replay trace 확장**

```python
def replay_trace(df: pd.DataFrame) -> SwingReplayTrace:
    """FLAT seed에서 시작해 모든 transition event와 마지막 typed state를 반환한다."""
```

기존 `replay`, `current_state`, 4개 golden fixture 결과는 바꾸지 않고 내부 trace에서 entry, stop, overheat_sell, rebuy, graduation, sma150_exit event를 보존한다.

- [ ] **Step 4: truth table과 같은 날 복수 event test 작성·구현**

stop은 short-circuit하며 sell/rebuy와 SMA150 exit가 겹친 날은 실제 평가된 event를 모두 남기고 최종 `BLOCK/EXIT/CLOSED`를 반환한다.

- [ ] **Step 5: EntryOpportunity RED test와 구현**

```python
@pytest.mark.parametrize(
    ("regime", "extension", "intent"),
    [
        ("bull", 0.05, EntryIntent.ALLOW),
        ("bull", 0.051, EntryIntent.WATCH),
        ("sideways", 0.00, EntryIntent.WATCH),
        ("bear", 0.00, EntryIntent.BLOCK),
    ],
)
def test_entry_opportunity_v1(regime, extension, intent):
    opportunity = evaluate_entry_opportunity(
        event=entry_event(reference_entry=100.0),
        bundle=bundle_for_regime(regime, close=100.0 * (1.0 + extension)),
        evaluation_as_of=date(2026, 10, 2),
    )
    assert opportunity.intent is intent
```

`evaluate_entry_opportunity(event, bundle, evaluation_as_of)`는 age 0..20만 평가하고 stop/SMA150 invalidation을 `BLOCK`, 한국 종목을 `NOT_EVALUATED`로 반환한다.

- [ ] **Step 6: golden·GREEN·commit**

Run: `uv run pytest tests/strategies/swing_w150 tests/strategies/test_entry_opportunity.py -q`
Expected: 기존 golden trade 날짜·가격·R·partial 수와 신규 adapter test 모두 PASS.

```bash
git add src/strategies/swing_w150 src/strategies/entry_opportunity.py tests/strategies/swing_w150 tests/strategies/test_entry_opportunity.py
git commit -m "feat: expose swing verdict events and opportunities"
```

### Task 6: Chart-only Playbook adapter와 StrategyRunner

**Files:**
- Create: `src/strategies/playbook.py`
- Create: `src/strategies/runner.py`
- Modify: `src/tools/playbook/gate.py`
- Modify: `src/tools/playbook/exit_rules.py`
- Test: `tests/strategies/test_playbook.py`
- Test: `tests/strategies/test_runner.py`

**Interfaces:**
- Consumes: `ChartBundle`, Task 4·5 strategies
- Produces: `PlaybookStrategy`, `StrategyRunner.run(bundle, legacy_result) -> StrategyRunBundle`

- [ ] **Step 1: holding/account 독립성 RED test 작성**

```python
def test_playbook_strategy_has_no_position_inputs():
    signature = inspect.signature(PlaybookStrategy.evaluate)
    assert tuple(signature.parameters) == ("self", "bundle")

def test_runner_result_is_independent_of_pipeline_and_cache():
    cold = make_runner(cache=None).run(bundle, legacy_result)
    warm = make_runner(cache=preloaded_cache(cold)).run(bundle, legacy_result)
    assert canonical_bytes(cold.verdicts) == canonical_bytes(warm.verdicts)
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/strategies/test_playbook.py tests/strategies/test_runner.py -q`
Expected: FAIL with missing modules.

- [ ] **Step 3: Playbook chart-only rules 구현**

기존 gate/exit에서 trend, structure, momentum, relative strength, risk만 재사용한다. holdings, account capital, sizing, news, fundamental, flow, sector snapshot fetch는 adapter에서 호출하지 않는다. gate와 exit를 같은 호출에서 모두 계산한다.

- [ ] **Step 4: StrategyRunner 구현**

```python
class StrategyRunner:
    def run(
        self, bundle: ChartBundle, *, legacy_result: TechnicalResult
    ) -> StrategyRunBundle:
        verdicts = [
            strategy.evaluate(bundle)
            for strategy in self.production_strategies(legacy_result)
        ]
        return StrategyRunBundle.from_verdicts(bundle=bundle, verdicts=verdicts)
```

세 strategy를 고정 순서로 실행하고 실패한 strategy도 `ERROR` verdict slot과 reason을 남긴다. run/input ID에는 Analysis run, DB state, pipeline 이름, 실행 시각을 넣지 않는다.

- [ ] **Step 5: GREEN·commit**

Run: `uv run pytest tests/strategies/test_playbook.py tests/strategies/test_runner.py tests/tools/playbook -q`
Expected: PASS.

```bash
git add src/strategies/playbook.py src/strategies/runner.py src/tools/playbook/gate.py src/tools/playbook/exit_rules.py tests/strategies/test_playbook.py tests/strategies/test_runner.py
git commit -m "feat: run chart-only production strategies"
```

### Task 7: PositionPolicy, execution check, PositionPlanner

**Files:**
- Create: `src/position/__init__.py`
- Create: `src/position/models.py`
- Create: `src/position/policy.py`
- Create: `src/position/planner.py`
- Create: `src/position/execution.py`
- Test: `tests/position/test_policy.py`
- Test: `tests/position/test_planner.py`
- Test: `tests/position/test_execution.py`

**Interfaces:**
- Consumes: authority `StrategyVerdict`, `PositionSnapshot`, `AccountSnapshot`, market open/session snapshot
- Produces: `PositionDirective`, `EntryExecutionCheck`, `PositionPlan`

- [ ] **Step 1: 4×4 truth table RED test 작성**

```python
@pytest.mark.parametrize("entry", list(EntryIntent))
@pytest.mark.parametrize("exit", list(ExitIntent))
def test_position_policy_truth_table(entry, exit):
    assert decide_directive(entry, exit) == EXPECTED[(entry, exit)]
```

`EXIT > REDUCE > ALLOW` 우선순위와 `NOT_EVALUATED exit → FREEZE`를 16개 조합으로 고정한다.

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/position -q`
Expected: FAIL with missing position package.

- [ ] **Step 3: policy와 50% planner 구현**

```python
def plan_position(
    verdict: StrategyVerdict,
    directive: PositionDirective,
    position: PositionSnapshot,
    account: AccountSnapshot | None,
    execution_check: EntryExecutionCheck | None,
) -> PositionPlan:
    if directive.kind is DirectiveKind.REDUCE_CURRENT_BY_FRACTION:
        sell = math.ceil(position.quantity * directive.fraction)
        return PositionPlan.sell(current=position.quantity, quantity=sell)
    if directive.kind is DirectiveKind.FLAT:
        return PositionPlan.sell(current=position.quantity, quantity=position.quantity)
    return plan_non_exit_directive(verdict, directive, position, account, execution_check)
```

`REDUCE_CURRENT_BY_FRACTION`은 `sell_quantity=ceil(current*0.5)`, `FLAT`은 전량 매도, 계좌 없음은 quantity `UNAVAILABLE`, 미보유 exit는 0주로 계산한다.

- [ ] **Step 4: execution check test·구현**

SWING source event는 +5% next-open gap을 검사한다. `source_event_id=None`인 Playbook V1은 `PASS/STALE_SESSION/MISSING_MARKET_DATA`만 반환하며 `GAP_LIMIT_EXCEEDED`를 만들지 않는다.

- [ ] **Step 5: GREEN·commit**

Run: `uv run pytest tests/position -q`
Expected: PASS.

```bash
git add src/position tests/position
git commit -m "feat: separate position policy and quantity planning"
```

### Task 8: 세 pipeline 공통 orchestration과 출력

**Files:**
- Create: `src/pipelines/strategy_analysis.py`
- Create: `src/pipelines/strategy_render.py`
- Modify: `src/pipelines/quick_check.py`
- Modify: `src/pipelines/deep_dive.py`
- Modify: `src/pipelines/brief.py`
- Modify: `src/tools/brief/models.py`
- Modify: `src/tools/brief/render.py`
- Modify: `src/cli/main.py`
- Test: `tests/pipelines/test_strategy_analysis.py`
- Modify: `tests/pipelines/test_technical_contract_parity.py`
- Modify: `tests/pipelines/test_quick_check.py`
- Modify: `tests/pipelines/test_deep_dive.py`
- Modify: `tests/pipelines/test_brief.py`

**Interfaces:**
- Consumes: technical OHLCV/result, benchmark loader, StrategyRunner, optional position/account
- Produces: 동일 `TechnicalScorecard`, `StrategyRunBundle`, optional `PositionPlan`과 공통 renderer sections

- [ ] **Step 1: pipeline parity RED test 확장**

```python
@pytest.mark.asyncio
async def test_same_chart_bundle_has_byte_equal_scorecard_and_verdicts_in_all_pipelines():
    check, analyze, brief = await run_three_pipelines(shared_bundle_fixture())
    assert canonical_bytes(check.scorecard) == canonical_bytes(analyze.scorecard)
    assert canonical_bytes(check.strategy_verdicts) == canonical_bytes(analyze.strategy_verdicts)
    assert canonical_bytes(check.strategy_verdicts) == canonical_bytes(brief.strategy_verdicts)
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/pipelines/test_technical_contract_parity.py -q`
Expected: FAIL because pipelines do not share StrategyRunBundle.

- [ ] **Step 3: 공통 service와 renderer 구현**

```python
class AnalysisStrategyService:
    async def evaluate(
        self, ticker: str, technical: TechnicalResult, *, as_of: date
    ) -> AnalysisStrategyResult:
        bundle = await self.chart_loader.load(ticker=ticker, as_of=as_of)
        run = self.strategy_runner.run(bundle, legacy_result=technical)
        return AnalysisStrategyResult(scorecard=technical.scorecard, strategy_run=run)
```

기본 출력 순서는 Scorecard → 중요 상태 → 최근 Analysis Trigger → 최근 Strategy Event → 전략별 Entry/Exit → 현재 진입 가능성 → Position Plan이다. 상세 출력은 모든 metric/evidence를 포함한다.

- [ ] **Step 4: 세 pipeline 연결과 기존 출력 parity 유지**

기존 total/technical action/Playbook/SWING 한 줄은 한 release 동안 새 섹션과 함께 유지한다. brief ranking authority는 기존 Playbook 결과를 즉시 바꾸지 않고 새 `PLAYBOOK_V1` verdict와 병렬 비교한다.

- [ ] **Step 5: GREEN·pipeline 회귀 test**

Run: `uv run pytest tests/pipelines/test_strategy_analysis.py tests/pipelines/test_technical_contract_parity.py tests/pipelines/test_quick_check.py tests/pipelines/test_deep_dive.py tests/pipelines/test_brief.py tests/tools/brief -q`
Expected: PASS.

- [ ] **Step 6: commit**

```bash
git add src/pipelines/strategy_analysis.py src/pipelines/strategy_render.py src/pipelines/quick_check.py src/pipelines/deep_dive.py src/pipelines/brief.py src/tools/brief src/cli/main.py tests/pipelines tests/tools/brief
git commit -m "feat: expose scorecard and strategies in all pipelines"
```

### Task 9: PostgreSQL history/cache와 성과 maturity

**Files:**
- Create: `src/storage/postgres/__init__.py`
- Create: `src/storage/postgres/connection.py`
- Create: `src/storage/postgres/migrations.py`
- Create: `src/storage/strategy_history/__init__.py`
- Create: `src/storage/strategy_history/repository.py`
- Create: `src/storage/strategy_history/maturity.py`
- Create: `migrations/strategy_history/001_initial.sql`
- Modify: `src/pipelines/stock_report/db.py`
- Modify: `src/pipelines/stock_report/pipeline.py`
- Modify: `src/pipelines/stock_report/pdf_ingest.py`
- Modify: `src/pipelines/strategy_analysis.py`
- Test: `tests/storage/postgres/test_migrations.py`
- Test: `tests/storage/strategy_history/test_repository.py`
- Test: `tests/storage/strategy_history/test_maturity.py`
- Modify: `tests/pipelines/stock_report/test_pipeline.py`
- Modify: `tests/pipelines/stock_report/test_pdf_ingest.py`

**Interfaces:**
- Consumes: Analysis/Chart/Strategy/episode/outcome domain objects
- Produces: shared PostgreSQL connection/migration helpers, `StrategyHistoryRepository.persist_result(result)`, `mature_due_outcomes(conn, batch_size)`

- [ ] **Step 1: stock-report compatibility RED tests 작성**

```python
def test_stock_report_dsn_and_migration_contract_survives_extraction(monkeypatch):
    monkeypatch.setenv("STOCK_REPORT_DB_DSN", "postgresql://stock")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fallback")
    assert stock_report_db.resolve_db_dsn() == "postgresql://stock"
    assert stock_report_db.apply_migrations(fake_conn(), fixture_migrations()) == ["001.sql"]
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/storage/postgres/test_migrations.py tests/pipelines/stock_report/test_pipeline.py tests/pipelines/stock_report/test_pdf_ingest.py -q`
Expected: new shared module tests FAIL; existing tests remain baseline GREEN.

- [ ] **Step 3: 공통 PostgreSQL helper 추출**

```python
def resolve_db_dsn(env_keys: tuple[str, ...], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for key in env_keys:
        if value := os.getenv(key):
            return value
    raise ValueError(f"DB DSN이 없습니다: {', '.join(env_keys)}")
def apply_checksum_migrations(
    conn: Any,
    migrations_dir: Path,
    *,
    history_table: str,
    bootstrap: Callable[[Any], None] | None = None,
) -> list[str]:
    if bootstrap is not None:
        bootstrap(conn)
    return MigrationRunner(conn, history_table).apply_directory(migrations_dir)
```

stock-report facade, public migration table, 선행 commit, 파일별 commit/rollback, monkeypatch import path를 그대로 유지한다.

- [ ] **Step 4: schema migration과 repository RED test 작성**

Migration은 spec 10.2의 table, FK, unique/check constraints를 `strategy_history` schema에 생성한다. Repository test는 같은 identity/same payload insert-or-compare 성공, same identity/different payload hard error, pre-input timeout nullable identity, post-input full identity, DB failure warning을 고정한다.

- [ ] **Step 5: repository 구현**

```python
class StrategyHistoryRepository:
    def begin_attempt(self, request: StrategyAttemptRequest) -> UUID:
        return self.attempts.insert_running(request)

    def persist_result(self, result: PersistableStrategyResult) -> None:
        with self.connection.transaction():
            self.results.insert_or_compare(result)

    def finish_attempt(self, attempt_id: UUID, result: AttemptResult) -> None:
        self.attempts.finish(attempt_id, result)
```

result transaction은 chart bundle, run, verdict, events, usage, replayed trigger/evaluation/episode, pending outcome child를 원자적으로 저장한다. persistence failure는 service warning으로 변환하고 계산 결과는 유지한다.

- [ ] **Step 6: episode anchor와 maturity fencing test·구현**

```python
def test_stale_worker_cannot_finish_after_reclaim():
    old = claim_due_outcome(conn)
    expire_and_reclaim(conn, old)
    assert finish_outcome(conn, old.token, status="error") is False
    assert finish_outcome(conn, old.token, status="matured") is False
```

모든 episode는 event priority 또는 `INTENT_TRANSITION` anchor를 갖는다. maturity claim은 DB `clock_timestamp()`, `FOR UPDATE SKIP LOCKED`, 새 token과 lease를 한 transaction에서 갱신하며 성공·오류 모두 full PK/status/token으로 fence한다.

- [ ] **Step 7: GREEN·commit**

Run: `uv run pytest tests/storage tests/pipelines/stock_report/test_pipeline.py tests/pipelines/stock_report/test_pdf_ingest.py -q`
Expected: PASS.

```bash
git add src/storage src/pipelines/stock_report src/pipelines/strategy_analysis.py migrations/strategy_history tests/storage tests/pipelines/stock_report
git commit -m "feat: persist strategy history in postgres"
```

### Task 10: 전체 검증, change record, migration 종료 조건

**Files:**
- Create: `docs/changes/scorecard-strategy-position-separation.md`
- Modify: `docs/changes/INDEX.md`
- Modify: `docs/FEATURES.md`
- Modify: `docs/worklog/swing-w150-engine.md`

**Interfaces:**
- Consumes: Task 1~9 결과
- Produces: 사용자 관점 변경 기록과 release 검증 근거

- [ ] **Step 1: targeted suite 실행**

Run: `uv run pytest tests/tools/technical tests/strategies tests/position tests/pipelines/test_technical_contract_parity.py tests/storage -q`
Expected: PASS.

- [ ] **Step 2: 기존 pipeline·CLI 회귀 suite 실행**

Run: `uv run pytest tests/pipelines/test_quick_check.py tests/pipelines/test_deep_dive.py tests/pipelines/test_brief.py tests/cli -q`
Expected: PASS.

- [ ] **Step 3: 전체 정적·test 검증**

Run: `uv run ruff check src tests`
Expected: PASS.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 4: 문서 기록 작성**

Change record에는 기존 점수/action과 새 5축/세 Strategy 병렬 출력, PositionPlanner만 실제 보유를 읽는 경계, PostgreSQL `strategy_history`, 호환 기간과 rollback 기준을 기록한다. `docs/FEATURES.md`에는 세 pipeline의 공통 출력과 chart-only 재현 계약을 반영한다.

- [ ] **Step 5: final diff와 독립 리뷰**

Run: `git diff --check`
Expected: no output, exit 0.

독립 리뷰는 설계 invariant 58개 중 구현에 해당하는 항목, 사용자 dirty 파일 보존, migration/stock-report compatibility, SWING golden parity를 확인한다. Critical/Important가 있으면 해당 task의 RED test부터 보완한다.

- [ ] **Step 6: docs commit**

```bash
git add docs/changes/scorecard-strategy-position-separation.md docs/changes/INDEX.md docs/FEATURES.md docs/worklog/swing-w150-engine.md
git commit -m "docs: record strategy separation rollout"
```

## 완료 조건

- 같은 canonical ChartBundle과 strategy version은 pipeline·실행일·DB 상태와 무관하게 같은 Scorecard/StrategyVerdict를 만든다.
- 실제 holding/account 변경은 PositionPlan만 바꾼다.
- 최근 20거래일 Analysis Trigger와 Strategy event, EntryOpportunity가 세 pipeline에 같은 의미로 표시된다.
- SWING golden fixture와 기존 stock-report PostgreSQL 계약이 유지된다.
- strategy history 저장 실패가 계산 결과를 숨기지 않으며 immutable identity 충돌은 hard error로 드러난다.
- 전체 test, ruff, `git diff --check`, 독립 리뷰가 통과한다.

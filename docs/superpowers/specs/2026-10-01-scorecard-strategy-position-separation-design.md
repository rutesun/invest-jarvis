# Technical Scorecard · Strategy · Position Planning 분리 설계

> **2026-10-06 변경**: 이 문서의 `SwingRuntimeState`, rolling 3년 `FLAT` replay,
> 가상 진입가·stop·risk·R, Strategy 내부 lifecycle/position 계약은
> [`2026-10-06-strategy-signal-outcome-backtest-boundary-design.md`](2026-10-06-strategy-signal-outcome-backtest-boundary-design.md)가 대체한다.
> 점수·Observation·Analysis Trigger·PositionPlanner·PostgreSQL history/cache 원칙은 유지한다.
> 기존 본문은 현재 구현과 결정 이력을 설명하는 자료로 보존한다.

- **작성일**: 2026-10-01
- **상태**: 일부 대체됨 — 2026-10-06 최소 스펙 참조
- **대상**: `check`, `analyze`, `brief`와 production technical strategy
- **관련 결정**: `docs/worklog/swing-w150-engine.md`
- **대체 후보**: ADR-0010의 TechnicalVerdict·Playbook 책임 경계

## 1. 목적

가격·지표·점수 측정과 매매 전략, 실제 주문 수량 계산을 분리한다.

```text
Analysis
  가격·지표·5축 점수·최근 사건 측정
        ↓
Strategy
  실제 보유 여부와 무관한 진입·청산 의견
        ↓
PositionPolicy
  선택 전략의 의견을 목표 포지션으로 변환
        ↓
PositionPlanner
  실제 보유·계좌와 목표 포지션의 차이를 수량으로 계산
```

같은 ticker, 같은 `as_of`, 같은 ChartBundle과 strategy version이면 실행 날짜·pipeline·DB 상태와 무관하게 `check`, `analyze`, `brief`는 byte-equivalent한 분석과 전략 결과를 보여야 한다. 실제 보유·계좌·매매기록이 달라져도 Analysis와 Strategy 결과는 바뀌지 않고 PositionPlan만 달라져야 한다.

```text
Strategy = f(ChartBundle의 as_of까지 prefix, strategy version)
PositionPlan = f(선택된 StrategyVerdict, 실제 PositionSnapshot, AccountSnapshot)
```

`ChartBundle`은 종목 OHLCV, 시장 benchmark OHLCV, 전략이 명시적으로 요구하는 업종 benchmark OHLCV, 거래소 calendar와 각 series의 session date로만 구성한다. 뉴스·재무·공시·실제 수급·보유·평균단가·계좌·실제 체결·과거 매매기록·DB에 저장된 이전 전략 상태는 Strategy 입력이 아니다.

## 2. 현재 문제

현재 `TechnicalScorer`는 8개 component 점수를 단순 합산한 뒤 `ScoreAggregator`에서 과열 감점, 하락추세 상한, 강제 `avoid/reduce`와 action 선택까지 수행한다. 측정과 전략 판단이 한 객체에 섞여 있다.

현재 `PlaybookEngine`은 실제 보유 여부에 따라 gate 또는 exit만 평가하고, gate 통과 직후 계좌 자본을 읽어 수량까지 계산한다. 그 결과 같은 종목의 전략 판단이 보유 여부에 따라 숨겨지고 전략 간 비교가 어렵다.

## 3. 범위

### 포함

- 5축 Technical Scorecard
- 영역별 원본 metric, 방향성, observation, evidence
- 최근 20거래일 production Analysis Trigger와 Strategy event
- 공통 `StrategyVerdict`와 `StrategyRunBundle`
- Analysis / Strategy / PositionPolicy / PositionPlanner 경계
- `check`, `analyze`, `brief` 공통 출력 계약
- 기존 TechnicalVerdict·Playbook·SWING_W150 adapter와 migration
- 놓친 Trigger의 현재 진입 가능성을 판정하는 versioned EntryOpportunity
- Entry/Exit truth table과 `REDUCE=현재 보유량의 50% 매도` 정책
- 전략별 5·10·20거래일 shadow 성과 계약
- Analysis·Strategy·Trigger·Strategy event·PositionPlan·shadow 성과의 기존 PostgreSQL 영속 저장

### 제외

- 포트폴리오 전체 위험 예산과 종목 간 자본 배분
- 실제 주문 전송
- 신규 전략 성과가 검증되기 전 authority 자동 교체
- 연구용 backtest script를 production strategy 목록에 자동 등록하는 범용 registry

`REDUCE`는 `PositionPolicy V1`에서 현재 보유량의 50%를 매도하는 상대 지시로 고정한다. 실제 주문 전송과 체결 추적은 범위 밖이며 PositionPlan까지만 생성한다.

## 4. 핵심 용어

- **Metric**: cRSI 값, SMA150 값, MACD Histogram처럼 계산된 수치
- **Directional Metric**: 현재 값과 상승·하락 방향을 함께 가진 metric
- **Observation**: `cRSI 과열`, `MACD선이 Signal선 위`처럼 현재 유지되는 상태
- **Analysis Trigger**: `cRSI 상단밴드 하향 이탈`, `20일 신고가 돌파`처럼 전략과 무관하게 가격·지표에서 관측되는 특정 거래일의 사건
- **Strategy Event**: `SWING_W150 과열 매도`, `stop 종료`, `재매수`처럼 특정 전략의 state transition과 verdict를 만든 사건
- **EntryOpportunity**: 과거 Entry Trigger가 현재도 진입 가능한지 매일 다시 평가한 상태
- **ChartBundle**: 종목·시장·필요시 업종의 OHLCV와 거래소 session 정보. Strategy가 읽을 수 있는 유일한 외부 입력
- **Strategy**: Analysis 결과를 해석해 진입과 청산 의견을 내는 규칙
- **PositionPolicy**: 선택 전략의 의견을 목표 포지션으로 변환하는 versioned 규칙
- **PositionPlanner**: 목표 포지션과 실제 계좌의 차이를 주문 수량으로 바꾸는 계산기

## 5. Analysis 계약

### 5.1 공통 상태 enum

```python
class DataStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"

class Direction(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"
    UNKNOWN = "unknown"

class Acceleration(StrEnum):
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"
    STABLE = "stable"
    UNKNOWN = "unknown"

class Importance(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
```

결측값을 0점이나 횡보로 바꾸지 않는다. 계산할 수 없으면 `UNKNOWN`과 해당 `DataStatus`를 명시한다.

### 5.2 DirectionalMetric

```python
class DirectionalMetric(BaseModel):
    code: str
    value: float | None
    unit: str | None
    direction: Direction
    delta_1d: float | None
    slope: float | None
    slope_unit: str | None
    slope_lookback_bars: int
    acceleration: Acceleration
    calculation_version: str
    data_status: DataStatus
    missing_reason: str | None
```

기본 계산 계약은 다음과 같다.

| 지표 | 현재 방향 | 함께 보존할 값 |
|---|---|---|
| SMA20·50·100·150·200 | 21거래일 percentage slope | 현재가 대비 위치, `delta_1d`, slope, acceleration |
| cRSI | 1일 변화 + 5거래일 slope | 상·하단밴드, 밴드 내 위치, acceleration |
| MACD | 1일 변화 + 5거래일 slope | MACD선·Signal선·Histogram 각각의 방향 |
| 거래량 평균·상대거래량 | 1일 변화 + 5거래일 slope | 20·50일 평균 대비 비율 |
| 상대강도 | 5·20거래일 slope | 시장·업종 대비 값 |

`FLAT` 판정 threshold와 slope 계산법은 `calculation_version`으로 고정한다. threshold가 바뀌면 같은 version으로 과거 결과를 덮어쓰지 않는다.

### 5.3 관계, 상태, 근거

```python
class Evidence(BaseModel):
    code: str
    message: str
    observed_value: float | None
    reference_value: float | None
    importance: Importance
    source: str

class Observation(BaseModel):
    code: str
    message: str
    direction: Direction | None
    importance: Importance
    source_metrics: list[str]
    evidence: list[Evidence]
```

Observation이 자신을 뒷받침하는 Evidence를 소유한다. 영역 수준의 독립 `evidence` 목록을 두어 같은 근거를 중복 전달하지 않는다. 관계는 원본 metric을 덮지 않고 Observation으로 둔다.

- MACD선 `ABOVE/BELOW` Signal선
- 종가 `ABOVE/BELOW` SMA20·50·150·200
- cRSI `ABOVE/INSIDE/BELOW` 동적 밴드
- SMA 단기선 `ABOVE/BELOW` 장기선

예를 들어 `cRSI 과열`은 현재 Observation이고 `cRSI 상단밴드 하향 이탈`은 dated Trigger다.

### 5.4 최근 20거래일 Analysis Trigger

```python
class TriggerStatus(StrEnum):
    ACTIVE = "active"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"

class AnalysisTriggerEvent(BaseModel):
    code: str
    trigger_version: str
    occurred_on: date
    bars_ago: int
    direction: Direction | None
    source: str
    observed_value: float | None
    reference_value: float | None
    status: TriggerStatus
    status_as_of: date
    status_changed_on: date
    status_reason: str
    expires_after_bars: int | None
    invalidated_on: date | None
    expired_on: date | None
    evidence: list[Evidence]
```

규칙은 다음과 같다.

1. `bars_ago <= 20`인 모든 production Trigger를 최신순으로 전달한다. 20거래일은 화면 표시 범위이며 Trigger validity TTL과는 별개다.
2. 매일 반복되는 상태가 아니라 상태가 바뀐 거래일의 event만 기록한다.
3. 무효화된 Trigger도 삭제하지 않고 `INVALIDATED`와 무효화 날짜를 표시한다.
4. 각 과거 봉까지의 데이터만 사용해 Trigger를 재생한다. 미래 데이터 사용을 contract test로 금지한다.
5. Trigger code는 `analysis.<source>.<event>` namespace를 사용하고 판정 version과 함께 성과 추적 identity로 사용한다.
6. Trigger의 발생은 `occurred_on`으로 이미 확정되므로 별도 `CONFIRMED` 상태를 두지 않는다. 유효 조건이 유지되면 `ACTIVE`, 무효화 조건을 만나면 `INVALIDATED`, 전략별 유효기간이 끝나면 `EXPIRED`다.

모든 production Trigger는 이름만 등록하지 않고 다음 규칙을 versioned registry에 선언한다.

```python
class TriggerRuleDefinition(BaseModel):
    code: str
    trigger_version: str
    required_inputs: list[str]
    occurrence_predicate: str
    equality_policy: str
    invalidation_predicate: str | None
    expires_after_bars: int | None
    event_date_rule: str
    source: str
```

발생식·무효화식·TTL·결측 처리가 registry에 없는 Trigger는 production 목록에 넣지 않는다. 상태 전환 이력은 run별 Scorecard snapshot으로 보존하며 과거 `as_of` 조회에 현재 최신 상태를 역으로 적용하지 않는다.

초기 production Analysis Trigger에는 다음을 포함한다.

- cRSI 상단밴드 하향 이탈·하단밴드 상향 돌파
- MACD·Fast MACD 골든/데드크로스와 Histogram 0선 전환
- SMA 방향 전환과 종가의 주요 이동평균선 교차
- SMA20/SMA50, SMA50/SMA150, SMA50/SMA200, SMA150/SMA200 골든·데드크로스
- Supertrend 방향 전환
- 20·50일 신고가 돌파
- VCP breakout, Pocket Pivot, Power Gap
- 거래량 동반 breakdown

SWING_W150의 S/D 진입·stop·과열 매도·재매수·SMA150 종료는 Analysis Trigger가 아니라 `StrategyVerdict.events`에 둔다. `OverheatCycleStrategy`의 과열·조정·재상승 event는 전략 규칙이 승인되기 전까지 planned inventory일 뿐 production Analysis Trigger 목록에 넣지 않는다.

### 5.5 5축 Scorecard

```python
class ScoreContribution(BaseModel):
    rule_code: str
    raw_state: str
    points: int
    required_inputs: list[str]
    missing_inputs: list[str]
    calculation_version: str
    evidence: list[Evidence]

class ScoreDimension(BaseModel):
    code: str
    score: int | None        # 0..100
    raw_state_points: int | None
    minimum_points: int
    maximum_points: int
    calculation_version: str
    data_status: DataStatus
    coverage_pct: float
    metrics: dict[str, DirectionalMetric | float | int | str | bool | None]
    observations: list[Observation]
    score_contributions: list[ScoreContribution]

class TechnicalScorecard(BaseModel):
    version: str
    ticker: str
    as_of: date
    trend: ScoreDimension
    structure: ScoreDimension
    momentum: ScoreDimension
    demand: ScoreDimension
    safety: ScoreDimension
    triggers: list[AnalysisTriggerEvent]
    legacy_raw_total: int | None
    legacy_adjusted_score: int | None
```

영역별 주재료는 다음과 같다.

| 영역 | 주재료 |
|---|---|
| 추세 | Minervini 조건, 이동평균선 배열·방향, Supertrend, 52주 위치 |
| 구조 | VCP, 고점·저점 구조, support/resistance, 수축·돌파 준비 상태 |
| 모멘텀 | Velocity, cRSI, RSI, MACD, divergence |
| 수급·거래량 | 상대거래량, 상승·하락일 거래량, Pocket Pivot, Power Gap, accumulation/distribution |
| 안전도 | ATR, 이격도, 과열, support까지 거리, breakdown, 변동성 |

동일 metric은 한 영역에서만 점수에 반영한다. 다른 영역은 근거를 참조할 수 있지만 재가산하지 않는다. Trigger는 Scorecard에 전달하되 5축 점수 합계에 일회성 bonus로 넣지 않는다.

새 단일 총점은 만들지 않는다. 기본 화면은 5축 점수를 그대로 보여준다. 기존 `component_raw_total`과 `adjusted_score`는 migration과 성과 비교를 위해 legacy 필드로 유지한다.

#### Scorecard v1 산식

Scorecard v1은 architecture migration 중 임의의 신규 가중치를 만들지 않는다.

1. 기존 component의 **지속 상태 기여분**을 다음과 같이 한 영역에만 배치한다.
   - `minervini`, `supertrend` → 추세
   - `patterns`의 수축·구조 상태 → 구조
   - `velocity`, `crsi`, `divergence`의 지속 상태 → 모멘텀
   - `volume`의 지속 상태 → 수급·거래량
   - `risk` → 안전도
2. Hook, crossover, breakout, surge처럼 하루에 발생하는 기여분은 영역 점수에서 빼고 Trigger로 이동한다.
3. 각 영역 rule은 `points`, `minimum_points`, `maximum_points`, `required_inputs`, `calculation_version`을 선언한다.
4. 영역 점수는 다음 식으로 0~100에 정규화한다.

```text
score = round(
  100 × (raw_state_points - minimum_points)
      / (maximum_points - minimum_points)
)
```

5. 범위 밖 값은 0~100으로 clamp한다. 점수와 함께 raw state points와 rule별 기여를 `ScoreContribution`으로 보존한다.
6. required input이 하나라도 없으면 점수를 추정하지 않고 `score=None`, `data_status=INSUFFICIENT_DATA`로 둔다. optional input 결측은 `coverage_pct`와 `PARTIAL`로 드러내며 남은 항목의 비중을 재분배하지 않는다.
7. 방향성 metric은 v1에서 표시·전략 입력으로만 사용한다. 기존 component에 없던 방향성 가감점은 holdout 검증과 version bump 전에는 추가하지 않는다.

따라서 새 5축 점수는 기존 상태 판단을 설명 가능한 영역으로 재배치한 결과이고, legacy total과는 별도 version으로 병행된다.

## 6. Strategy 계약

### 6.1 두 축 verdict

```python
class EntryIntent(StrEnum):
    ALLOW = "allow"
    WATCH = "watch"
    BLOCK = "block"
    NOT_EVALUATED = "not_evaluated"

class ExitIntent(StrEnum):
    HOLD = "hold"
    REDUCE = "reduce"
    EXIT = "exit"
    NOT_EVALUATED = "not_evaluated"

class ReferenceEntryBasis(StrEnum):
    SIGNAL_CLOSE_ESTIMATE = "signal_close_estimate"
    NEXT_OPEN_ACTUAL = "next_open_actual"

class StructureStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"

class EntryOpportunity(BaseModel):
    source_event_id: str
    source_event_code: str
    source_event_date: date
    evaluation_as_of: date
    age_bars: int
    reference_entry: float
    reference_entry_basis: ReferenceEntryBasis
    reference_stop: float
    extension_pct: float
    extension_r: float | None
    extension_atr: float | None
    breakout_distance_pct: float | None
    sma20_distance_pct: float | None
    market_regime: str
    structure_status: StructureStatus
    policy_version: str
    next_open_recheck_required: bool

class StrategyEvent(BaseModel):
    event_id: str
    code: str
    event_version: str
    occurred_on: date
    direction: Direction | None
    evidence: list[Evidence]

class EntryVerdict(BaseModel):
    intent: EntryIntent
    opportunity: EntryOpportunity | None
    data_status: DataStatus
    reasons: list[Evidence]

class ExitVerdict(BaseModel):
    intent: ExitIntent
    data_status: DataStatus
    reasons: list[Evidence]

class StrategyState(BaseModel):
    state_type: str
    state_version: str

class SwingRuntimeState(StrategyState):
    state_type: Literal["swing_w150"]
    lifecycle: Literal["active", "closed"]
    cycle_phase: Literal["signal", "active", "awaiting_rebuy", "closed"]
    kind: Literal["S", "D"] | None
    entry: float | None
    stop: float | None
    risk: float | None
    graduated: bool | None
    overheat_armed: bool | None
    previous_below_exit_line: bool | None

class StrategyVerdict(BaseModel):
    verdict_schema_version: str
    strategy_id: str
    strategy_version: str
    ticker: str
    as_of: date
    entry: EntryVerdict
    exit: ExitVerdict
    events: list[StrategyEvent]
    strategy_state: StrategyState | None
```

`strategy_state`는 실제 구현에서 `state_type`을 discriminator로 삼는 typed union이다. SWING은 `SwingRuntimeState`로 역직렬화되어야 하며 임의 문자열이나 자유 형식 JSON으로 저장하지 않는다.

Strategy는 ChartBundle과 자신의 versioned rule만 읽는다. 실제 holding, 평균단가, 계좌 자본, 주문 수량, target exposure, 실제 매매기록, 이전 DB row를 읽거나 반환하지 않는다. `entry=ALLOW`, `exit=REDUCE`처럼 두 축이 충돌해도 하나의 action으로 합치지 않는다.

미보유 종목도 `entry`와 `exit`를 모두 가진다. `exit`는 “이 차트 경로에 전략 규칙을 적용했을 때 현재 상태를 어떻게 관리할 것인가”를 뜻한다. 실제 보유 수량이 0이면 PositionPlanner가 매도 수량을 0으로 계산할 뿐 StrategyVerdict를 숨기지 않는다. 사용자 보유 여부가 아니라 ChartBundle의 필수 series나 lookback이 부족할 때만 `NOT_EVALUATED`를 사용한다.

`strategy_state`는 strategy version이 선언한 replay origin부터 `as_of`까지 ChartBundle을 replay한 파생 출력이다. 다음 실행의 입력이나 실제 매매장부가 아니다. 같은 ChartBundle prefix를 다시 replay하면 DB 저장 여부와 관계없이 같은 state·event·verdict가 나와야 한다.

공통 confidence 숫자는 두지 않는다. 서로 다른 전략의 confidence 정의가 같다는 근거가 없기 때문이다.

### 6.2 Entry Trigger를 놓친 뒤의 현재 진입 판단

Trigger는 발생일 하루의 사건이고 EntryOpportunity는 그 사건이 현재도 실행 가능한지 매일 재평가한 상태다. 동일 Trigger를 다음 날 새 event로 반복 생성하지 않는다. 각 거래일의 평가는 `(source_event_id, evaluation_as_of, policy_version)` identity로 별도 보존한다.

`SWING_W150_ENTRY_OPPORTUNITY_V1`은 별도 에이전트가 73개 미국 종목, SWING_W150 Trigger 806개로 검증한 결과를 기준으로 다음처럼 고정한다.

1. Trigger 당일은 `age_bars=0`, 유효 범위는 `0..20`, `age_bars=21`부터 만료다.
2. 평가일 시장 국면은 같은 `as_of`의 SPY `Close/SMA50/SMA200`으로 계산한다.
3. 강세장(`Close > SMA50 > SMA200`)에서는 현재 종가가 기준 진입가의 `+5%` 이내면 `ALLOW`, 초과하면 `WATCH`다.
4. 횡보장은 가격과 무관하게 `WATCH`, 하락장(`Close < SMA50 < SMA200`)은 `BLOCK`이다.
5. 시장 국면 입력이 없으면 `NOT_EVALUATED`다.
6. V1의 `structure_status=INVALID`는 원래 손절선이 Trigger 이후 한 번이라도 닿았거나 SWING의 canonical stop/SMA150 lifecycle exit가 발생한 경우만 뜻하며 `BLOCK`이다. 그 밖의 구조 metric은 표시만 하고 V1 gate에 사용하지 않는다.
7. Trigger 당일에는 아직 T+1 시가를 모르므로 종가를 `SIGNAL_CLOSE_ESTIMATE`로 표시한다. 다음 거래일부터 기존 SWING의 T+1 실제 시가를 `NEXT_OPEN_ACTUAL` 기준 진입가로 사용한다.
8. 종가 기준 `StrategyVerdict`와 EntryOpportunity는 확정 뒤 변경하지 않는다. SWING dated entry처럼 versioned 기준 진입가와 gap threshold가 있는 경우 실제 실행 시점의 다음 시가가 `+5%` 한도를 넘으면 별도 `EntryExecutionCheck`가 주문 생성을 막고 `GAP_LIMIT_EXCEEDED`를 반환한다.
9. R·ATR·돌파선·SMA20 이격은 모두 저장·표시하지만 V1 차단식에는 사용하지 않는다.

복합 `% + R + ATR` 기준은 체결 건 평균을 높였지만 전체 Trigger 분모 기대값을 안정적으로 개선하지 못했으므로 V1 gate에서 제외한다. threshold 변경은 policy version을 올리고 고정 cohort에서 다시 검증한다.

### 6.3 초기 전략 inventory

| strategy_id | 기존 출처 | 변경 |
|---|---|---|
| `TECHNICAL_LEGACY` | `ScoreAggregator._choose_action()` | legacy score 해석 adapter로 이동 |
| `PLAYBOOK_V1` | gate + exit rules | holding 분기 없이 두 축 모두 평가 |
| `SWING_W150` | `src/strategies/swing_w150` | 공통 verdict와 당일 exit event 제공 |
| `OVERHEAT_CYCLE_V1` | 신규 | 규칙·acceptance가 별도 승인되기 전 `NOT_IMPLEMENTED`, production 제외 |

`HoldingCycleOverlay`라는 이름은 실제 보유정보 의존으로 오해되므로 `OverheatCycleStrategy`를 사용한다.

초기 production StrategyRunner에는 `TECHNICAL_LEGACY`, `PLAYBOOK_V1`, `SWING_W150`만 들어간다. `OVERHEAT_CYCLE_V1`은 정확한 독립 규칙과 acceptance가 승인된 뒤 shadow production으로 승격한다.

세 production 전략 모두 ChartBundle-only 계약을 지킨다. `PLAYBOOK_V1`의 기존 gate/exit 중 실제 보유·평균단가·계좌·실제 체결이나 news·fundamental·flow를 읽는 규칙은 Strategy adapter에서 제거한다. 차트로 계산 가능한 trend·structure·momentum·relative strength·risk 규칙만 두 축 verdict를 만든다. 비차트 정보는 별도 Analysis/설명에 표시할 수 있지만 intent를 변경하지 않는다.

실험용 A-prime은 `TECHNICAL_APRIME_EXPERIMENTAL` shadow로 유지하며 production StrategyRunner와 authority 대상에 넣지 않는다.

### 6.4 Legacy adapter mapping

기존 action을 임의로 재해석하지 않도록 adapter mapping을 table-driven test로 고정한다.

| 기존 출력 | Entry | Exit |
|---|---|---|
| Technical `buy`, `add` | `ALLOW` | `HOLD` |
| Technical `hold`, `watch`, `accumulate` | `WATCH` | `HOLD` |
| Technical `reduce` | `BLOCK` | `REDUCE` |
| Technical `avoid` | `BLOCK` | `NOT_EVALUATED` |
| Playbook gate 명시적 통과 | `ALLOW` | 별도 exit 평가값 |
| Playbook gate 명시적 실패 | `BLOCK` | 별도 exit 평가값 |
| Playbook gate 필수 입력 부족 | `NOT_EVALUATED` | 별도 exit 평가값 |
| Playbook exit `hold`, `reduce`, `liquidate` | 별도 gate 평가값 | `HOLD`, `REDUCE`, `EXIT` |

`TECHNICAL_LEGACY`는 기존 action을 보존하는 shadow opinion이다. `reduce`의 Exit=`REDUCE`는 성과 비교용 의견이며 주문 authority가 아니다. 기존 `avoid`는 신규 진입 회피 의미였으므로 청산 권한으로 확대하지 않는다. PositionPolicy authority는 parity 기간 계속 `PLAYBOOK_V1`만 사용한다.

SWING_W150은 event와 지속 상태를 다음처럼 분리한다.

| SWING 상태/event | Entry | Exit | lifecycle / cycle_phase |
|---|---|---|---|
| S/D 진입 Trigger 당일 | EntryOpportunity 결과 | `HOLD` | `ACTIVE / SIGNAL` |
| 다음 시가 기준 cycle 활성화 후 | `WATCH` | `HOLD` | `ACTIVE / ACTIVE` |
| 과열 매도 당일 | `BLOCK` | `EXIT` | `ACTIVE / AWAITING_REBUY` |
| 재매수 대기 지속 | `WATCH` | `EXIT` | `ACTIVE / AWAITING_REBUY` |
| 과열 재매수 당일 | `ALLOW` | `HOLD` | `ACTIVE / ACTIVE` |
| stop 또는 SMA150 종료 | `BLOCK` | `EXIT` | `CLOSED / CLOSED` |

`AWAITING_REBUY`에서 `Exit=EXIT`를 유지하므로 과열 매도를 놓친 사용자도 다음 날 계속 청산 안내를 받는다. 이미 실제 수량이 0이면 PositionPlanner의 매도 수량만 0이다.

현재 SWING 평가 순서는 stop → 과열 sell/rebuy → D graduation → SMA150 exit다. stop은 즉시 lifecycle을 닫고 뒤 규칙을 평가하지 않으므로 stop 조건이 참인 날의 Strategy event는 stop 하나다. stop short-circuit가 없는 경로에서 같은 날 실제 평가된 Strategy event는 하나도 버리지 않고 모두 보존한다. sell/rebuy와 SMA150 exit가 겹치면 최종 verdict는 `Entry=BLOCK`, `Exit=EXIT`, lifecycle=`CLOSED`, cycle_phase=`CLOSED`다. entry/exit 충돌은 숨기지 않고 PositionPolicy가 Exit를 우선한다.

SWING은 저장된 매매장부나 checkpoint에서 이어서 계산하지 않고 strategy version에 고정된 replay profile로 ChartBundle을 replay한다. `SWING_W150_V1`의 profile은 다음과 같다.

- `replay_origin_rule=ROLLING_3_CALENDAR_YEARS_V1`: 각 평가 `as_of`의 3년 전 날짜 이후 첫 거래 session부터 시작한다. 상장일이 그보다 늦으면 검증된 상장 첫 session을 origin으로 사용한다.
- `initial_state=FLAT`: origin 이전의 실제 시장 cycle은 V1 모델 범위 밖이며 가상 보유나 DB state로 복원하지 않는다.
- 첫 250개 bar는 indicator warm-up으로만 사용하고 그 뒤부터 event와 state transition을 평가한다.
- ChartBundle은 요청 origin, 실제 coverage start/end, expected session 범위, 종목별 bar/no-trade coverage와 provider truncation 여부를 manifest로 가진다. origin부터 `as_of`까지 완전성을 증명하지 못하거나 warm-up이 부족하면 `NOT_EVALUATED/INSUFFICIENT_DATA`다.
- 최근 날짜를 prefix backfill할 때는 가장 이른 평가일의 origin까지 한 번 수집하되, 각 평가일은 자신의 rolling origin부터 해당 `as_of`까지만 잘라 replay한다. 따라서 나중 봉이나 현재 실행일의 더 짧은 window를 읽지 않는다.

이 profile과 초기 상태는 `strategy_version`의 일부다. origin rule, warm-up, 초기 상태 또는 coverage 판정이 바뀌면 strategy version을 올린다. 현재 provider의 관행적 `3y` 응답을 완전성 증거로 간주하지 않으며 loader가 manifest를 만들 수 없으면 실패를 숨기지 않는다.

## 7. Strategy 실행과 pipeline

```text
공통 AnalysisBundle
        ↓
ChartBundleLoader
  종목·시장·필요시 업종 OHLCV와 거래소 calendar를 한 번 수집
        ↓
StrategyRunner
  production 전략을 각각 한 번 실행
        ↓
StrategyRunBundle
  scorecard + 모든 strategy verdict + 오류 상태
        ↓
check / analyze / brief
```

```python
class StrategyRunBundle(BaseModel):
    ticker: str
    as_of: date
    input_data_hash: str
    strategy_versions: dict[str, str]
    chart_profile_version: str
    chart_bundle_hash: str
    strategy_input_hashes: dict[str, str]
    scorecard: TechnicalScorecard
    verdicts: list[StrategyVerdict]
    data_status: DataStatus
    errors: list[str]
```

`ChartBundleLoader`는 종목·시장·필요시 업종 OHLCV와 거래소 calendar를 canonical JSON으로 직렬화하고 `chart_bundle_hash`를 만든다. 상대강도와 시장 국면은 이 chart series에서 Strategy가 결정적으로 계산한다. fundamental·news·disclosure·flow·macro는 별도 Analysis/설명에 표시할 수 있지만 StrategyVerdict를 바꾸지 않는다.

전략별 `strategy_input_hash`는 `chart_bundle_hash`, `strategy_id`, `strategy_version`을 담은 canonical envelope의 hash다. chart schema·calendar·normalization version은 canonical ChartBundle과 `chart_bundle_hash` 안에 포함한다. rule configuration, replay profile, EntryOpportunity rule, verdict serialization contract는 모두 `strategy_version`에 흡수한다. 이 중 하나가 바뀌면 strategy version을 올린다. DB state, checkpoint, Analysis run, pipeline 실행 시각은 hash input에 넣지 않는다.

`strategy_run_id`는 domain prefix와 `strategy_input_hash`를 담은 canonical envelope의 deterministic hash다. DB unique identity도 `strategy_input_hash`와 정확히 일치시킨다. Analysis 결과와 Strategy 결과의 연결은 별도 usage row에 기록하며 Strategy identity에 넣지 않는다. DB cache hit는 이 exact identity의 이미 계산된 결과를 반환할 수 있지만, 이전 state를 이어받아 새 verdict를 만들지는 않는다. 세 pipeline이 같은 ChartBundle을 전달할 때만 같은 결과를 재사용한다. cold cache의 `check`는 현재보다 느려질 수 있으나 Playbook을 제외해 속도를 맞추지는 않는다.

전략 하나가 실패해도 화면에서 생략하지 않는다. `PARTIAL`, `INSUFFICIENT_DATA`, `ERROR` 중 하나와 이유를 표시하고 나머지 전략은 계속 실행한다. 다만 transient `ERROR`는 immutable deterministic result로 저장하지 않고 `strategy_run_attempts`에 기록한다. 성공한 결과와 입력으로 재현 가능한 `PARTIAL`/`INSUFFICIENT_DATA`만 `strategy_runs`와 `strategy_verdicts`를 점유한다.

## 8. PositionPolicy와 PositionPlanner

- 초기 선택 전략은 `PLAYBOOK_V1`이다.
- `PositionPolicy`는 선택 전략의 entry/exit intent를 versioned 목표 포지션으로 변환한다.
- `PositionPlanner`만 실제 보유 수량, 평균단가, 실제 체결로 만들어진 현재 PositionSnapshot, 계좌 자본, risk budget을 읽는다. 과거 매매기록이 필요하면 PositionSnapshot을 구성하는 position repository에서 읽으며 Strategy로 전달하지 않는다.
- `EntryExecutionCheck`는 Strategy 확정 뒤 실제 주문 시점의 시가·gap·session을 검사하고, 통과한 경우에만 PositionPlanner가 매수 수량을 만든다.
- 위험 충돌 우선순위는 `EXIT > REDUCE > ALLOW`다.
- 계좌정보가 없으면 전략 verdict는 정상 표시하고 quantity만 `UNAVAILABLE`로 표시한다.
- `REDUCE`는 현재 보유 수량의 50%를 매도하며 추가매수를 만들지 않는다.

PositionPolicy는 실제 holding을 읽지 않고 다음 directive만 반환한다.

```text
BUILD_ONLY_TO_RISK_TARGET
KEEP_CURRENT
REDUCE_CURRENT_BY_FRACTION(0.5)
FLAT
FREEZE
```

truth table은 다음과 같다.

| Entry \ Exit | HOLD | REDUCE | EXIT | NOT_EVALUATED |
|---|---|---|---|---|
| `ALLOW` | `BUILD_ONLY_TO_RISK_TARGET` | `REDUCE_CURRENT_BY_FRACTION(0.5)` | `FLAT` | `FREEZE` |
| `WATCH` | `KEEP_CURRENT` | `REDUCE_CURRENT_BY_FRACTION(0.5)` | `FLAT` | `FREEZE` |
| `BLOCK` | `KEEP_CURRENT` | `REDUCE_CURRENT_BY_FRACTION(0.5)` | `FLAT` | `FREEZE` |
| `NOT_EVALUATED` | `KEEP_CURRENT` | `REDUCE_CURRENT_BY_FRACTION(0.5)` | `FLAT` | `FREEZE` |

`BUILD_ONLY_TO_RISK_TARGET`은 목표보다 적을 때만 매수하고 초과 보유를 자동 매도하지 않는다. `FREEZE`는 신규매수와 강제매도를 모두 만들지 않고 경고를 표시한다. `REDUCE_CURRENT_BY_FRACTION(0.5)`는 Planner가 `sell_quantity = ceil(current_quantity × 0.5)`, `target_quantity = current_quantity - sell_quantity`로 계산해 실제로 위험이 줄어들게 한다. 1주 보유 시 결과는 1주 매도다.

`EntryExecutionCheck` ID는 필수 `strategy_run_id`, nullable `source_event_id`, 거래소 기준 `market_session`, `market_snapshot_hash`, `policy_version`으로 만든다. SWING처럼 dated entry event가 있으면 `source_event_id`와 versioned policy의 기준 진입가를 연결한다. 이때만 next-open gap을 계산해 `GAP_LIMIT_EXCEEDED`를 반환할 수 있다. Playbook처럼 현재 차트 gate만 있고 승인된 기준 진입가·gap threshold가 없는 전략은 `source_event_id=null`로 두고 V1에서 `STALE_SESSION`, `MISSING_MARKET_DATA`, `PASS`만 판정한다. 실제 관측 시각 `checked_at`과 `result`는 payload에만 둔다. 이 검사는 T 종가의 StrategyVerdict나 EntryOpportunity를 수정하지 않는다.

기존 `playbook/sizing.py`의 신규 매수 계산은 PositionPlanner로 이동한다. parity 기간에는 기존 결과와 나란히 비교하되 Playbook Strategy가 실제 계좌나 매매기록을 읽는 경로는 남기지 않는다.

## 9. 출력 계약

세 pipeline은 같은 의미와 정렬 순서로 다음을 표시한다.

```text
[Technical Scorecard]
추세 82 | 구조 71 | 모멘텀 64 | 수급 77 | 안전도 43

[중요 상태]
- cRSI 68.1: 과열 해소, 5일 방향 하락
- SMA150 21일 기울기 +2.4%: 상승
- MACD선은 Signal선 위, Histogram은 3일 연속 축소

[최근 Analysis Trigger — 20거래일]
- 3일 전 cRSI 상단밴드 하향 이탈 — 유효
- 7일 전 Pocket Pivot — 유효
- 12일 전 20일 신고가 돌파 — 이후 돌파가 이탈로 무효

[최근 Strategy Event — 20거래일]
- 2일 전 SWING_W150 S 진입
- 오늘 SWING_W150 과열 재매수와 SMA150 종료 동시 발생 — 최종 BLOCK/EXIT

[전략]
TECHNICAL_LEGACY  entry=ALLOW  exit=HOLD
PLAYBOOK_V1       entry=WATCH  exit=HOLD
SWING_W150        entry=ALLOW  exit=HOLD

[Planned Strategy]
OVERHEAT_CYCLE_V1 not_implemented — production 결과 아님

[현재 진입 가능성]
- SWING_W150 S Trigger: 2거래일 전
- 기준 진입가 50,000 / 현재가 51,200 / +2.4%
- 강세장 +5% 한도 이내 — 지금 진입 가능, 다음 시가 재확인 필요

[Position Plan]
계좌정보가 있으면 목표·현재·차이·주문 수량 표시
```

기본 출력은 5축 점수, `HIGH` 중요도의 Observation/Evidence, 최근 20거래일 Analysis Trigger와 Strategy event 전체, 모든 StrategyVerdict를 보여준다. 상세 출력은 모든 metric, 방향성, evidence를 보여준다.

## 10. PostgreSQL 영속 저장

### 10.1 목적과 위치

전략 비교와 5·10·20거래일 성과 성숙 처리는 실행이 끝난 뒤에도 원본 판단을 조회할 수 있어야 한다. PostgreSQL은 계산 결과의 history/cache이며 Strategy 판단의 source of truth가 아니다. DB를 비운 뒤 같은 ChartBundle과 version으로 다시 실행해도 같은 event·state·verdict를 재생성할 수 있어야 한다. 저장소에 이미 있는 `psycopg` PostgreSQL 연결과 checksum migration 관례를 재사용한다.

- database: 기존 stock-report가 사용하는 동일 PostgreSQL database
- Strategy history DSN 우선순위: `JARVIS_DB_DSN` → `STOCK_REPORT_DB_DSN` → `DATABASE_URL`
- schema: `strategy_history`
- 공통 PostgreSQL infrastructure: `src/storage/postgres/`
- strategy repository: `src/storage/strategy_history/`
- migration: `migrations/strategy_history/*.sql`
- migration history: `strategy_history.schema_migrations`

pipeline 계층의 `src/pipelines/stock_report/db.py`를 Strategy 또는 storage가 역으로 import하지 않는다. 기존 connection·checksum migration 공통부를 `src/storage/postgres/`로 추출하고 stock-report와 strategy history가 함께 사용한다. 공통 DSN resolver는 고정 우선순위를 내장하지 않고 호출자가 env key 순서를 넘긴다. stock-report는 기존 `STOCK_REPORT_DB_DSN → DATABASE_URL` 순서와 facade/re-export, 테스트 monkeypatch import path를 유지하고 Strategy history만 위의 새 순서를 사용한다.

stock-report facade는 기존 migration history 선행 commit, migration 파일별 commit/rollback 범위, 적용된 filename 목록 반환값을 그대로 유지한다. `src.pipelines.stock_report.pipeline.resolve_db_dsn/apply_migrations` 등 기존 monkeypatch 경로도 회귀 테스트로 고정한다. `strategy_history`의 advisory-lock bootstrap semantics를 기존 stock-report runner에 역으로 적용하지 않는다.

DB 설정이 없으면 `check`, `analyze`, `brief` 계산을 실패시키지 않는다. persistence를 비활성화하고 사용자 출력과 `logger.warning`에 저장이 생략됐음을 표시한다. DSN이 설정됐으나 연결·migration·write가 실패한 경우도 계산 결과는 반환하되 해당 실행의 persistence 상태를 warning으로 드러낸다.

빈 database에서도 시작할 수 있도록 migration bootstrap은 일반 migration 조회보다 먼저 다음 순서로 실행한다.

1. 고정 advisory lock 획득
2. `CREATE SCHEMA IF NOT EXISTS strategy_history`
3. `strategy_history.schema_migrations` 생성
4. 적용된 filename/checksum 조회
5. 미적용 migration을 transaction 안에서 순서대로 실행
6. advisory lock 해제

stock-report의 기존 public migration history table 이름과 적용 내역은 변경하지 않는다. migration은 파일명과 SHA-256 checksum을 기록하며 이미 적용된 파일 변경을 오류로 처리한다. `strategy_history`의 신규 table만 항상 schema-qualified로 사용하며 기존 stock-report SQL의 unqualified table 이름은 그대로 유지한다.

deterministic ID와 hash는 `TEXT`, canonical payload는 `JSONB`, 기준일은 `DATE`, 생성·갱신 시각은 `TIMESTAMPTZ`로 저장한다. enum 성격 컬럼은 `CHECK` constraint로 허용값을 고정하고 모든 FK·unique constraint는 PostgreSQL이 집행한다.

hash는 PostgreSQL JSONB의 내부 표현이 아니라 application에서 만든 canonical bytes를 대상으로 계산한다. 각 원본 payload hash envelope에는 `schema_version`, 관련 `profile_version`, `calculation_version`을 포함한다. 다른 immutable hash를 참조하는 상위 identity는 하위 version을 다시 중복하지 않는다. 예를 들어 `chart_bundle_hash`가 chart profile을, `strategy_version`이 rule·replay·verdict contract를 이미 고정하므로 `strategy_input_hash`는 둘과 strategy id만 참조한다. serializer는 object key 정렬, UTF-8, compact separator, `date` ISO-8601, `datetime` UTC ISO-8601, Decimal/float 정규화, 명시적 `null` 보존을 고정하고 NaN/±Infinity를 거부한다. JSONB는 조회용 복사본이며 identity 계산의 원본이 아니다.

ID hash는 `SHA-256(domain_prefix + NUL + canonical_bytes)`로 고정하고 entity별 `jarvis:<entity>:v<schema>` domain을 사용해 서로 다른 ID 종류의 충돌을 막는다. 숫자는 `Decimal(str(value))`로 변환해 trailing zero와 exponent를 제거한 base-10 문자열로 인코딩하며 `1`, `1.0`, `Decimal("1.00")`은 모두 `1`, `-0.0`은 `0`이다. timezone 없는 datetime은 거부하고 timezone-aware datetime만 UTC `Z`로 변환한다. 이 규칙은 exact input/output test vector로 고정한다.

모든 `as_of`는 실행 날짜가 아니라 해당 ticker 거래소 기준으로 분석에 실제 사용한 마지막 유효 가격 봉의 session date다. 시장·업종 context는 자신의 기준 session date도 canonical context에 별도로 기록한다.

### 10.2 저장 단위

#### `analysis_runs`

동일 AnalysisBundle을 한 번만 저장한다.

| 컬럼 | 의미 |
|---|---|
| `run_id` | deterministic hash primary key |
| `ticker`, `as_of` | 종목과 기준 거래일 |
| `input_data_hash` | 실제 분석 입력 identity |
| `scorecard_version` | 5축 점수 계약 version |
| `data_status` | complete/partial/insufficient_data |
| `scorecard_json` | metric·direction·observation·score contribution 전체 |
| `payload_hash` | immutable payload 비교용 hash |
| `computed_at`, `created_at` | 계산 시각과 최초 저장 시각. identity에는 미포함 |

Unique identity는 `(ticker, as_of, input_data_hash, scorecard_version)`이다. `check`, `analyze`, `brief`가 같은 AnalysisBundle을 사용하면 같은 `run_id`를 재사용한다. 실제 전략 context는 Analysis identity에 섞지 않는다.

#### `analysis_run_usages`

동일 분석 결과를 어떤 pipeline이 사용했는지 기록한다.

| 컬럼 | 의미 |
|---|---|
| `run_id` | `analysis_runs` foreign key |
| `pipeline` | check/analyze/brief |
| `used_at` | 사용 시각 |

#### `chart_bundles`

| 컬럼 | 의미 |
|---|---|
| `chart_bundle_hash` | canonical ChartBundle bytes hash primary key |
| `chart_profile_version` | chart schema·calendar·normalization version |
| `chart_bundle_json` | 종목·시장·필요시 업종 OHLCV, 각 session date, replay coverage manifest |
| `payload_hash` | immutable payload 비교용 hash |
| `created_at` | 최초 저장 시각 |

#### `strategy_runs`

| 컬럼 | 의미 |
|---|---|
| `strategy_run_id` | deterministic hash primary key |
| `chart_bundle_hash` | `chart_bundles` foreign key |
| `strategy_input_hash` | chart bundle·전략 rule/version의 canonical hash |
| `strategy_id`, `strategy_version` | 실행 전략 identity |
| `run_status` | complete/partial/insufficient_data |
| `payload_hash` | immutable run metadata hash |
| `computed_at`, `created_at` | 계산 시각과 최초 저장 시각. identity에는 미포함 |

Unique identity는 `strategy_input_hash`이며 `strategy_run_id`의 hash input과 동일하다. `chart_bundle_hash`, `strategy_id`, `strategy_version`은 조회·provenance용 컬럼이고 이미 `strategy_input_hash` 안에 포함된다. `StrategyVerdict.verdict_schema_version`은 serialization payload에 남지만 contract 변경은 반드시 `strategy_version`을 올리므로 별도 run identity 축이 아니다.

#### `strategy_run_attempts`

실행 시도와 deterministic 결과를 분리한다. 일시적 provider/timeout/serialization 오류는 이 table에 남기고 같은 identity의 이후 성공을 막지 않는다.

| 컬럼 | 의미 |
|---|---|
| `attempt_id` | 매 실행 시도의 UUID primary key |
| `ticker`, `requested_as_of`, `chart_profile_version` | ChartBundle load 전 요청 identity |
| `chart_bundle_hash`, `strategy_input_hash` | ChartBundle 생성 뒤 채우는 nullable candidate identity |
| `strategy_id`, `strategy_version` | 대상 전략 |
| `pipeline`, `started_at`, `finished_at` | 호출 경로와 실행 시각 |
| `attempt_status` | running/succeeded/error |
| `strategy_run_id` | 성공한 immutable result, 실패 시 null |
| `error_json` | 실패 종류·메시지·재시도 가능 여부 |

attempt는 ChartBundle provider 호출 전에 ticker·requested_as_of·profile·strategy version으로 먼저 기록한다. 이 단계의 실패는 이 request identity와 오류만 복원 가능하다. `chart_bundle_hash`와 `strategy_input_hash`는 canonical ChartBundle 생성 뒤 채우며 provider timeout이면 null로 남긴다. 이후 단계의 실패는 full candidate Strategy identity를 복원할 수 있다. 성공 시 연결되는 `strategy_run_id`에만 nullable FK를 둔다.

#### `analysis_strategy_usages`

| 컬럼 | 의미 |
|---|---|
| `analysis_run_id` | `analysis_runs` foreign key |
| `strategy_run_id` | `strategy_runs` foreign key |
| `pipeline` | check/analyze/brief |
| `used_at` | 사용 시각 |

Primary key는 `(analysis_run_id, strategy_run_id, pipeline)`이다. 같은 Strategy result가 다른 Analysis 실행이나 pipeline에서 사용되어도 Strategy run identity는 바뀌지 않는다.

#### `strategy_verdicts`

| 컬럼 | 의미 |
|---|---|
| `strategy_run_id` | 전략 실행 foreign key/primary key |
| `strategy_id`, `strategy_version` | 전략 identity |
| `entry_intent`, `exit_intent` | 두 축 verdict |
| `entry_data_status`, `exit_data_status` | 각 축 complete/partial/insufficient_data |
| `strategy_state_json` | 전략 고유 typed state |
| `verdict_json` | 전체 canonical `StrategyVerdict`와 reason Evidence |
| `payload_hash` | immutable payload 비교용 hash |

`verdict_json`만으로 저장 당시 두 축과 EntryOpportunity를 lossless하게 복원할 수 있어야 한다.

#### `analysis_trigger_events`

| 컬럼 | 의미 |
|---|---|
| `event_id` | deterministic hash primary key |
| `ticker` | 종목 |
| `trigger_code`, `trigger_version` | Trigger identity |
| `occurred_on` | 발생 거래일 |
| `direction`, `source` | 방향과 원천 |
| `status` | active/invalidated/expired |
| `status_as_of`, `status_changed_on`, `status_reason` | 현재 상태의 기준일·전환일·이유 |
| `expires_after_bars`, `expired_on` | validity TTL과 만료일 |
| `invalidated_on` | 무효화 거래일 |
| `event_json` | 당시 값·기준값·Evidence |
| `event_payload_hash` | 최신 event payload fingerprint. schema 호환용이며 충돌 거부에 사용하지 않음 |
| `first_seen_run_id`, `last_seen_run_id` | 발견·최종 평가 Analysis 실행 |

Unique identity는 `(ticker, trigger_code, trigger_version, occurred_on)`이다. 이 table은 최신 Trigger 조회를 위한 mutable projection이다. incoming `status_as_of`가 저장값과 같거나 최신이면 status, event payload, `event_payload_hash`, `last_seen_run_id`를 최신 계산값으로 갱신한다. 과거 backfill은 `last_seen_run_id`만 갱신하고 최신 projection을 되돌리지 않는다. `bars_ago`는 조회 기준 `as_of`에 따라 바뀌므로 canonical event 컬럼으로 저장하지 않고 run의 `scorecard_json` 또는 조회 시 계산한다. 정확한 실행별 결과와 입력 identity는 immutable Analysis run·Scorecard snapshot에서 복원한다.

#### `strategy_events`

| 컬럼 | 의미 |
|---|---|
| `event_id` | deterministic hash primary key |
| `strategy_run_id` | event를 만든 `strategy_runs` foreign key |
| `strategy_id`, `strategy_version` | 전략 identity |
| `ticker`, `occurred_on` | 종목과 발생 거래일 |
| `event_code`, `event_version` | stop/overheat_sell/rebuy/SMA150_exit 등 event identity |
| `event_json`, `payload_hash` | canonical event와 immutable hash |

Unique identity는 `(ticker, strategy_id, strategy_version, event_code, event_version, occurred_on)`이다. `strategy_run_id`는 이 event를 최초 확정한 run을 가리킨다. 같은 날 rebuy와 SMA150 exit처럼 서로 다른 event가 발생하면 각각 별도 row로 모두 보존한다.

#### `entry_opportunity_evaluations`

| 컬럼 | 의미 |
|---|---|
| `source_event_id` | 원 Entry Strategy event foreign key |
| `evaluation_as_of` | 매일 재평가한 거래일 |
| `policy_version` | EntryOpportunity 규칙 version |
| `strategy_run_id` | 평가 근거가 된 immutable run |
| `age_bars`, `market_regime` | Trigger 경과일과 시장 국면 |
| `entry_intent`, `structure_status` | 그날의 ALLOW/WATCH/BLOCK/NOT_EVALUATED와 구조 상태 |
| `evaluation_json`, `payload_hash` | 가격 이격·R·ATR·SMA20 등 전체 근거 |
| `computed_at` | 이 과거 상태를 실제 계산한 시각, identity에는 미포함 |

Primary key는 `(source_event_id, evaluation_as_of, policy_version)`이다. Trigger 당일만 저장하지 않고 0~20거래일 각 cohort 평가를 보존한다.

별도 일일 materializer는 Strategy 정확성의 전제조건이 아니다. `check`, `analyze`, `brief`가 실행되면 현재 ChartBundle을 과거 거래일 prefix별로 replay해 `occurred_on`, `evaluation_as_of`, intent transition 날짜를 차트에서 복원한다. DB의 저장 PK와 비교해 빠진 날짜가 있으면 그 날짜 prefix로 on-demand backfill하되 이후 봉은 읽지 않는다. `evaluation_as_of`는 차트 거래일이고 `computed_at`은 실제 실행 시각이다. DB가 비어 있거나 며칠간 pipeline을 실행하지 않아도 같은 ChartBundle이면 같은 event·state·verdict가 나와야 한다.

#### `entry_execution_checks`

| 컬럼 | 의미 |
|---|---|
| `execution_check_id` | deterministic primary key |
| `strategy_run_id` | 확정 Strategy result, 필수 anchor |
| `source_event_id` | 원 Entry Strategy event가 있으면 FK, Playbook처럼 event가 없으면 null |
| `checked_at`, `market_session` | 실제 실행 검사 시점 |
| `market_snapshot_hash`, `policy_version` | 시가·session 입력과 검사 규칙 |
| `result` | pass/gap_limit_exceeded/stale_session/missing_market_data |
| `check_json`, `payload_hash` | gap과 한도 등 전체 근거 |

동일 실행 context 재검사는 insert-or-compare한다. gap 취소와 policy 차단은 후행 진입 simulated cohort에서 0-return으로 집계하며 과거 StrategyVerdict를 변경하지 않는다.

#### `entry_opportunity_outcomes`

daily EntryOpportunity 정책을 age별 고정 분모로 비교하는 simulated outcome이다. 실제 주문 체결 기록으로 해석하지 않는다.

| 컬럼 | 의미 |
|---|---|
| `source_event_id`, `evaluation_as_of`, `policy_version` | 원 daily evaluation composite FK |
| `horizon_bars`, `outcome_version` | 5/10/20거래일 평가 계약 |
| `execution_check_id` | 실행 검사가 있었다면 해당 row, 아니면 null |
| `simulated_execution_status` | filled/gap_cancelled/policy_blocked/not_evaluated |
| `entry_session`, `entry_price` | evaluation 다음 거래일과 그 시가. 미진입이면 null |
| `maturity_status` | pending/maturing/matured/error |
| `cohort_return` | simulated filled면 수익률, 그 외 고정 분모 0 |
| `benchmark_symbol`, `benchmark_return`, `benchmark_excess_return` | benchmark provenance와 비교 성과 |
| `matured_on`, `mfe`, `mae` | 성숙 거래일과 최대 유리·불리 움직임 |
| `outcome_payload_hash` | 성숙 결과의 immutable hash, pending이면 null |
| `claim_token`, `lease_expires_at` | worker claim과 crash recovery, 미claim이면 null |
| `error_json` | terminal error의 진단 정보, 그 외 null |
| `price_input_hash`, `calculated_at` | 가격 provenance와 계산 시각 |

Primary key는 `(source_event_id, evaluation_as_of, policy_version, horizon_bars, outcome_version)`이다. 실제 주문 전송이 범위 밖이므로 `filled`는 정책과 가격 자료로 재현한 simulated fill만 뜻한다. EntryExecutionCheck가 없는 과거 backfill도 evaluation 다음 거래일의 ChartBundle open을 사용해 같은 gap policy를 replay한다. evaluation 전체 상태는 세 child horizon의 `maturity_status`에서 조회 시 계산한다.

#### `strategy_episodes`

매일 반복되는 HOLD 대신 Entry와 Exit 각 축의 intent 전환을 별도 episode로 추적한다.

| 컬럼 | 의미 |
|---|---|
| `episode_id` | deterministic hash primary key |
| `ticker`, `strategy_id`, `strategy_version` | 대상 전략 |
| `axis` | entry/exit |
| `anchor_date`, `anchor_type` | 최초 Trigger/intent 전환 |
| `from_intent`, `to_intent` | 해당 축 전환 |
| `anchor_code`, `anchor_version` | 모든 episode에 필수인 provenance code/version |
| `source_event_id` | primary dated event가 있으면 provenance, 순수 상태 전환이면 null |
| `strategy_run_id` | 원본 전략 실행 |
| `reference_price` | T 종가 |
| `input_cutoff_date` | episode 분류에 사용 가능한 마지막 거래일, 항상 anchor_date |
| `payload_hash` | immutable anchor payload hash |

`episode_id`는 `(ticker, strategy_id, strategy_version, axis, anchor_date, from_intent, to_intent, anchor_code, anchor_version, nullable source_event_id)` canonical tuple의 hash다. dated Strategy event가 있으면 strategy version에 고정된 `episode_anchor_priority`로 primary event를 하나 선택해 그 code/version과 ID를 anchor로 쓴다. 같은 날의 나머지 event도 `strategy_events`에는 모두 보존한다. event 없이 차트 상태만 전환된 episode는 필수 synthetic code `INTENT_TRANSITION`과 해당 strategy version이 고정한 anchor version을 사용한다. Entry 변화는 Entry episode만, Exit 변화는 Exit episode만 만든다. 이후 가격이나 outcome을 보고 과거 episode의 축·intent·anchor를 변경하지 않는다.

#### `strategy_outcomes`

| 컬럼 | 의미 |
|---|---|
| `episode_id`, `horizon_bars` | episode와 5/10/20거래일 horizon |
| `maturity_status` | pending/maturing/matured/error |
| `matured_on` | 평가가 가능해진 거래일 |
| `forward_return` | T+1 시가 기준 수익률 |
| `benchmark_excess_return` | benchmark 초과수익률 |
| `benchmark_symbol`, `benchmark_return` | 비교 기준 identity와 수익률 |
| `mfe`, `mae` | 최대 유리·불리 움직임 |
| `avoided_return` | exit 평가용 `-forward_return` |
| `outcome_payload_hash` | 성숙 결과의 immutable hash, pending이면 null |
| `claim_token`, `lease_expires_at` | worker claim과 crash recovery, 미claim이면 null |
| `error_json` | terminal error의 진단 정보, 그 외 null |
| `outcome_version`, `price_input_hash` | 계산 계약과 가격 입력 provenance |
| `calculated_at` | 계산 시각 |

Primary key는 `(episode_id, horizon_bars, outcome_version)`이며 `horizon_bars`는 5, 10, 20만 허용한다. episode 전체 상태는 세 child horizon의 `maturity_status`에서 조회 시 계산하며 immutable parent row를 갱신하지 않는다.

#### `position_plans`

실제 계좌를 사용한 결과는 전략 판단과 분리해 감사 가능하도록 저장한다.

| 컬럼 | 의미 |
|---|---|
| `plan_id` | primary key |
| `strategy_run_id` | 원본 전략 실행 |
| `entry_execution_check_id` | 매수 plan이면 통과한 실행 검사, 그 외 null |
| `authority_strategy_id`, `authority_strategy_version` | 수량 계산 기준 |
| `policy_version`, `planner_version` | directive·수량 계산 계약 version |
| `holding_snapshot_hash`, `account_snapshot_hash`, `market_snapshot_hash` | 실제 상태와 계획 시점 가격 identity |
| `current_quantity`, `target_quantity`, `order_quantity` | 실제 수량 계산 |
| `order_side` | buy/sell/none/unavailable |
| `plan_json` | stop·risk budget·계산 근거 |
| `payload_hash` | immutable payload 비교용 hash |
| `created_at` | 생성 시각 |

`position_plans`는 전략 성과 계산 입력으로 사용하지 않는다. holding/account 변경이 `strategy_verdicts`를 바꾸지 않는다는 invariant를 유지한다.

```text
plan_id = hash(
  strategy_run_id,
  authority_strategy_id,
  authority_strategy_version,
  policy_version,
  planner_version,
  holding_snapshot_hash,
  account_snapshot_hash,
  market_snapshot_hash,
  entry_execution_check_id,
)
```

### 10.3 transaction과 idempotency

한 pipeline 실행의 attempt와 deterministic result는 다음 세 단계로 나눠 저장한다.

1. 짧은 ledger transaction으로 `strategy_run_attempts(running)`을 먼저 commit한다.
2. 별도 result transaction에서 다음을 원자적으로 처리한다.
   - `analysis_runs` insert-or-compare
   - 성공 또는 재현 가능한 결과의 `chart_bundles`, `strategy_runs`, `strategy_verdicts`, `strategy_events` insert-or-compare
   - `analysis_run_usages`, `analysis_strategy_usages` 기록
   - ChartBundle prefix replay에서 복원된 `analysis_trigger_events` projection upsert. 같거나 최신 `status_as_of`는 최신 payload/status로 update하고 과거 backfill은 projection을 되돌리지 않음
   - replay 범위의 `entry_opportunity_evaluations`, intent transition `strategy_episodes`, 각 5·10·20일 pending outcome child insert-or-compare
   - 실행 검사가 있으면 `entry_execution_checks`, 계좌정보가 있으면 `position_plans` insert-or-compare
3. 별도 ledger transaction으로 attempt를 `succeeded`와 `strategy_run_id` 또는 `error`와 `error_json`으로 마감한다.

result transaction 중간 실패 시 전체 result를 rollback하고 attempt 오류는 별도 ledger transaction에 남긴다. pipeline 결과에는 persistence warning을 표시한다. 분석과 전략 계산은 성공했는데 PostgreSQL 저장만 실패한 경우 계산 결과를 숨기지 않되, 성과 추적이 누락됐음을 `logger.warning`과 사용자 출력에 명시한다. process crash로 `running`에 남은 attempt는 운영 진단 대상으로 식별할 수 있어야 한다.

immutable insert는 `INSERT ... ON CONFLICT DO NOTHING RETURNING`을 사용한다. conflict면 같은 transaction에서 기존 payload hash를 읽어 application canonical bytes hash와 비교한다. hash가 다르면 nondeterminism, 누락된 input identity 또는 version 누락으로 보고 transaction을 rollback한 뒤 hard error를 낸다. overwrite나 ignore로 숨기지 않는다. 두 writer가 동시에 같은 identity를 저장하는 integration test로 이 동작을 고정한다.

각 immutable result hash는 domain payload만 대상으로 한다. current status, maturity status, first/last-seen run, claim token/lease, error JSON, created/updated/calculated timestamp 같은 운영 필드는 제외한다. 성숙 결과는 `outcome_payload_hash`, 나머지 immutable result row는 `payload_hash`를 사용한다. Analysis Trigger의 `event_payload_hash`는 최신 projection fingerprint이며 immutable 충돌 검사를 하지 않는다.

transient 오류가 난 attempt는 `strategy_run_attempts.attempt_status=error`와 `error_json`을 남기고 deterministic `strategy_runs` row는 만들지 않는다. 따라서 같은 입력의 재시도 성공이 이전 오류 때문에 막히지 않는다.

새 episode와 daily evaluation을 저장할 때 5·10·20 horizon child outcome row를 `pending`으로 미리 만든다. maturity worker는 PostgreSQL `clock_timestamp()`을 공통 clock으로 사용하고 `pending OR (maturing AND lease_expires_at < clock_timestamp())`인 due child row를 `FOR UPDATE SKIP LOCKED`로 선택한다. claim transaction 안에서 새 `claim_token`, `lease_expires_at`, `maturing`을 update하고 `RETURNING`으로 소유권을 확정한 뒤 계산한다. 성공과 오류를 포함한 모든 terminal update는 `WHERE <full-primary-key> AND maturity_status='maturing' AND claim_token=:owned_token` fencing 조건을 만족할 때만 각각 `matured` 또는 `error`로 전환한다. lease 만료 후 다른 worker가 재claim해 token이 바뀌었다면 이전 worker의 늦은 성공·오류 결과는 row count 0으로 감지해 모두 폐기한다. 5·10·20 horizon은 각각 독립 상태를 가지며 부모의 전체 상태는 child row에서 파생한다. 동일 horizon/version 재실행은 기존 outcome payload와 비교하므로 중복 표본을 만들지 않는다.

### 10.4 보존과 조회

- Analysis·verdict·Analysis Trigger·Strategy event·daily evaluation·episode·outcome은 자동 삭제하지 않는다.
- PositionPlan은 PostgreSQL `strategy_history` schema에 저장하되 외부 egress 대상에는 포함하지 않는다.
- strategy/version별 5·10·20거래일 성과, 표본 수, MFE/MAE, entry/exit 성과를 SQL로 직접 집계할 수 있어야 한다.
- schema version이 다른 row를 하나의 cohort로 자동 합산하지 않는다.

## 11. Shadow 성과

- 신호 확정: T 종가
- 기준 가격: T+1 시가
- 평가: 5·10·20거래일 종가 수익률, benchmark excess return, MFE, MAE
- entry와 exit를 별도 episode와 cohort로 평가하며 exit는 `avoided_return = -forward_return`도 기록
- 매일 반복되는 HOLD가 아니라 intent 전환 또는 episode anchor만 새 표본으로 기록
- `strategy_id + strategy_version + episode anchor code/version`별 cohort 분리
- EntryOpportunity 후행 진입은 `policy_version + age_bars + market_regime`별 cohort를 원 Trigger 고정 분모로 비교한다. 차단·미체결은 0으로 포함해 체결 건 생존편향을 피한다.
- benchmark symbol/return, outcome version, price input hash를 결과마다 보존한다.
- episode의 축·anchor·intent는 `input_cutoff_date` 이후 정보로 변경하지 않는다.
- 승률과 함께 표본 수와 신뢰구간 표시

## 12. Migration

1. typed Entry/Exit verdict, EntryOpportunity, Analysis Trigger registry, Strategy event, ChartBundle model을 추가하고 기존 출력은 유지한다.
2. env key 순서를 받는 공통 PostgreSQL connection helper와 bootstrap-safe migration runner를 추출하되 stock-report facade·migration history·DSN 동작을 그대로 유지한다.
3. `strategy_history` schema에 attempt ledger, immutable Analysis/Strategy result, Analysis Trigger와 Strategy event store를 추가한다.
4. 5축 Scorecard와 directional metric을 shadow로 계산·저장한다.
5. 최근 20거래일 Analysis Trigger replay와 out-of-order-safe status 전이를 추가한다.
6. `TECHNICAL_LEGACY` mapping table을 구현하고 A-prime은 experimental shadow로 유지한다.
7. Playbook gate와 exit를 ChartBundle-only로 항상 평가하고 holding·account·actual trade·sizing 의존성을 PositionPlanner로 이동한다.
8. SWING_W150이 DB state/checkpoint 없이 versioned rolling origin부터 ChartBundle을 replay해 event/state/verdict를 만드는 adapter를 production에 연결한다.
9. `SWING_W150_ENTRY_OPPORTUNITY_V1`의 0~20거래일 on-demand prefix replay/backfill과 별도 EntryExecutionCheck를 연결한다.
10. PositionPolicy truth table과 50% REDUCE directive, deterministic PositionPlanner를 추가한다.
11. StrategyRunner를 `check`, `analyze`, `brief`에 연결한다.
12. entry/exit axis별 episode와 daily EntryOpportunity의 5·10·20거래일 outcome maturity 처리를 추가한다.
13. 한 release parity 후 기존 단일 action, holding 기반 Playbook 분기, 중복 renderer 제거를 검토한다.
14. `OVERHEAT_CYCLE_V1`은 별도 규칙·acceptance 승인 뒤 shadow production으로 추가한다.

## 13. 검증 계약

필수 invariant는 다음과 같다.

1. 실제 holding/account/평균단가/매매기록만 바꾸면 `TechnicalScorecard`와 `StrategyVerdict[]`는 같고 PositionPlan만 달라진다.
2. 같은 ticker, as-of, AnalysisBundle과 canonical ChartBundle이면 세 pipeline의 Scorecard와 verdict가 byte-equivalent하다.
3. entry/exit 충돌은 serialization과 화면에서 손실되지 않는다.
4. 모든 directional metric은 값, lookback, slope, version을 함께 가진다.
5. Trigger replay는 해당 시점 이후의 봉을 읽지 않는다.
6. `bars_ago <= 20`의 production Trigger가 누락되지 않고 invalidated event도 보존된다.
7. 결측 metric은 0이나 `FLAT`으로 변환되지 않는다.
8. 같은 metric이 여러 score dimension에 중복 가산되지 않는다.
9. legacy score와 원래 action 표시는 migration 기간 기존 fixture와 parity를 유지하며 Technical `avoid`가 Exit authority로 확대되지 않는다.
10. 세 pipeline이 같은 AnalysisBundle을 저장하면 `analysis_runs`는 한 row이고 usage만 추가된다.
11. 같은 identity의 immutable result payload가 달라지면 overwrite하지 않고 hard error를 낸다. mutable `analysis_trigger_events` projection은 제외한다.
12. PostgreSQL transaction 실패는 partial row를 남기지 않고 계산 결과에 persistence warning을 남긴다.
13. PostgreSQL row를 읽어 저장 당시 Scorecard와 StrategyVerdict를 lossless하게 복원할 수 있다.
14. Entry와 Exit의 `data_status` 및 episode를 각각 복원·집계할 수 있다.
15. Analysis Trigger는 발생일에 한 번만 생성되고 이후에는 같은 event의 `bars_ago`와 status만 변한다.
16. Analysis Trigger의 `ACTIVE → INVALIDATED/EXPIRED` 전이, status 기준일, 20거래일 표시 경계를 고정한다.
17. 각 `as_of` prefix 실행 결과는 전체 데이터 실행의 같은 날짜 snapshot과 일치하며 T 시점에 T+1 open을 읽지 않는다.
18. EntryOpportunity의 강세 +5%, 횡보 WATCH, 하락 BLOCK, 20거래일 만료를 고정하고 next-open gap guard가 과거 verdict를 변경하지 않는지 검증한다.
19. 기존 SWING 골든 trade의 날짜·가격·R·partial 수는 그대로 유지한다.
20. 과열 sell 이후 `AWAITING_REBUY` 동안 event는 반복되지 않고 `Exit=EXIT`가 지속된다.
21. awaiting 상태의 stop·SMA150 종료 우선순위를 검증한다. stop+rebuy 조건일에는 stop event 하나만 남고, stop short-circuit가 없는 sell+SMA150 또는 rebuy+SMA150일에는 평가된 복수 Strategy event가 모두 저장되며 최종 `Entry=BLOCK`, `Exit=EXIT`, `CLOSED/CLOSED`다.
22. PositionPolicy 4×4 조합 전체를 table-driven test로 고정한다.
23. REDUCE는 현재 수량의 50%를 매도하고 매수 주문을 만들지 않으며 목표가 현재보다 커지지 않는다.
24. 같은 strategy/account/holding/market snapshot은 같은 plan ID와 payload를 만들고 snapshot 변경은 새 plan ID를 만든다.
25. 동일 episode/horizon/outcome version 재실행은 `strategy_outcomes` 표본 수를 늘리지 않는다.
26. SWING은 각 평가일의 versioned rolling replay origin에서 `FLAT`으로 시작하며 ChartBundle manifest가 origin부터 `as_of`까지 coverage를 증명하지 못하면 DB state로 보완하지 않고 `NOT_EVALUATED`다. origin 이전 cycle이 열려 있는 fixture도 V1의 `FLAT` seed 기준 결과를 고정한다.
27. `OVERHEAT_CYCLE_V1`과 A-prime은 승인 전 production 목록에 나타나지 않는다.
28. 빈 database에서 advisory lock → schema → migration history → migration 순서로 bootstrap되고 concurrent bootstrap도 한 번만 적용된다.
29. stock-report의 DSN 우선순위, public migration history, facade/re-export와 monkeypatch import path가 바뀌지 않는다.
30. DB env 미설정과 PostgreSQL write 실패가 `check`, `analyze`, `brief` 계산을 실패시키지 않고 persistence warning을 남긴다.
31. canonical serializer는 key 순서·date/datetime·Decimal/float·null을 동일 bytes로 만들고 NaN/±Infinity를 거부한다.
32. 동일 identity를 두 writer가 동시에 insert해도 한 immutable row만 남고 payload 불일치는 rollback/hard error다.
33. transient ERROR attempt 뒤 같은 입력의 성공 result를 저장할 수 있고 attempt 두 건이 모두 감사 가능하다.
34. 과거 Analysis Trigger backfill은 최신 projection을 되돌리지 않으며 같은 `status_as_of` 재계산은 최신 payload와 status로 갱신된다.
35. Strategy event는 `strategy_run_id` FK를 가지며 같은 날 복수 event를 모두 보존한다.
36. EntryOpportunity는 source event별 0~20거래일 daily evaluation을 누락 없이 저장한다.
37. maturity worker 두 개가 동시에 실행돼도 `FOR UPDATE SKIP LOCKED`로 같은 episode나 daily evaluation을 중복 성숙시키지 않는다.
38. DB를 비우고 같은 ChartBundle을 cold replay한 결과가 cache hit 결과와 byte-equivalent하며, DB state/checkpoint는 Strategy 입력으로 사용되지 않는다.
39. 매수 PositionPlan은 `PASS`인 EntryExecutionCheck를 참조하고 gap 취소·policy 차단은 원 Trigger simulated cohort에 0-return으로 남는다.
40. EntryOpportunity의 age별 outcome은 원 Trigger 고정 분모로 집계되고 simulated fill과 실제 주문 체결을 혼동하지 않는다.
41. `strategy_run_id`, DB unique identity, 저장 컬럼이 같은 `strategy_input_hash`를 사용하며 canonical ChartBundle 또는 strategy version 변경만 input hash와 run ID를 바꾼다. Analysis run이나 pipeline usage 변경은 run ID를 바꾸지 않는다.
42. immutable result payload hash는 mutable status·lease·timestamp를 제외한다. Analysis Trigger의 hash는 최신 projection fingerprint로만 사용한다.
43. pipeline을 며칠 실행하지 않거나 중간 evaluation row 하나를 제거해도 다음 실행의 on-demand replay가 ChartBundle 거래일 기준 누락분을 prefix-only로 채우고 각 run의 `as_of`가 evaluation 날짜와 일치한다.
44. 같은 nullable event/run/session/policy/market snapshot의 EntryExecutionCheck 재시도는 `checked_at`이 달라도 같은 ID를 사용한다.
45. maturity worker crash 뒤 lease 만료 row가 재claim되고 5·10·20 horizon 상태는 서로 독립적으로 성숙한다.
46. lease 만료 후 새 token으로 재claim된 row에는 이전 worker의 늦은 `matured`와 `error` terminal update가 모두 full PK·status·token fencing 조건에 막혀 결과를 덮지 못한다.
47. canonical ChartBundle 생성 전 실패 attempt는 request identity를, 생성 후 실패 attempt는 `chart_bundle_hash + strategy_input_hash + strategy_id/version` full candidate identity를 복원할 수 있다.
48. 모든 production Strategy는 종목·시장·필요시 업종 ChartBundle 외의 news·fundamental·flow·actual position·trade history를 읽지 않는다.
49. 과거 event의 `occurred_on/as_of`는 차트 거래일이고 `computed_at`만 실제 Jarvis 실행 시각이다.
50. 미국 EntryOpportunity는 SPY Chart를 사용하고, 한국 정책이 별도 검증되기 전 KR EntryOpportunity는 숨기지 않고 `NOT_EVALUATED`로 표시한다.
51. ChartBundle provider timeout도 nullable input hash를 가진 invocation attempt로 기록되며 이후 성공 result identity를 점유하지 않는다.
52. EntryOpportunity outcome은 evaluation 다음 거래일 open, entry session/price, gap policy, benchmark identity/return, matured date를 lossless하게 복원한다.
53. SHA-256 domain prefix와 `1/1.0/Decimal("1.00")`, `-0.0`, exponent, timezone-aware/naive datetime exact canonical test vector를 고정한다.
54. 공통 PostgreSQL helper 추출 전후 stock-report의 migration history commit, 파일별 commit/rollback, 적용 filename 반환값, monkeypatch import path가 같다.
55. maturity claim은 DB `clock_timestamp()`와 `pending OR expired lease` predicate, token update와 `RETURNING`을 한 transaction에서 수행한다.
56. 모든 production Strategy의 ChartBundle prefix replay가 호출 사이의 누락 intent transition episode를 차트 거래일로 복원하고 pending outcome child를 같은 result transaction에 만든다.
57. 모든 Strategy episode는 필수 `anchor_code/version`을 가지며, 같은 날 복수 event의 primary anchor priority와 event 없는 `INTENT_TRANSITION` synthetic anchor가 strategy version에 고정된다.
58. Playbook V1 EntryExecutionCheck는 승인된 기준 진입가와 gap threshold가 없으므로 `GAP_LIMIT_EXCEEDED`를 만들지 않고 session freshness와 market data 존재만 검사한다.

## 14. ADR 후보

구현 범위가 채택되면 새 ADR을 추가한다.

- Analysis / Strategy / PositionPolicy / PositionPlanner 4계층 분리
- 5축 Scorecard와 directional metric 계약
- Strategy의 position-independent 두 축 verdict
- 모든 production Strategy의 ChartBundle-only deterministic input 계약
- PositionPlanner만 실제 계좌·보유정보를 읽는 규칙
- dated Trigger, 지속 EntryOpportunity, 실제 주문 계획의 분리
- PositionPolicy truth table과 `REDUCE=현재 보유량 50% 매도`
- 기존 PostgreSQL의 `strategy_history` schema를 Analysis·Strategy·Analysis Trigger·Strategy event·성과 추적의 history/cache로 사용하되 판단 source of truth로 사용하지 않는 결정
- ADR-0010의 TechnicalVerdict·Playbook 책임 경계 supersede

수락된 ADR-0010 본문은 수정하지 않고 새 ADR에서 대체 관계를 명시한다.

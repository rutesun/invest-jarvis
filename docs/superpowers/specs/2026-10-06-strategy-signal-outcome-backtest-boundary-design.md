# Strategy Observation · Signal · EntryOpportunity · Backtest 책임 분리 설계

- **작성일**: 2026-10-06
- **최종 수정일**: 2026-10-08
- **상태**: 최종 리뷰 Important 4건 수정 후 live 2y 시작 경계 보완·focused 검증 완료 — coordinator 전체·live 재검증 대기
- **대상**: production Strategy, `check`·`analyze`·`brief`, Backtest, PositionPlanner
- **제거 범위**: Strategy 가상 position replay, PostgreSQL `strategy_history` subsystem 전체
- **유지 범위**: Scorecard, Analysis Observation/Evidence/Trigger, 실제 보유정보 입력

## 1. 목적

차트에서 관찰 중인 상태, 특정 날짜에 완성된 사건, 오늘 진입 가능성, 실제 주문 수량을 분리한다.
모든 Strategy 결과는 차트에서 재계산하며 PostgreSQL에 저장하지 않는다.

```text
Raw OHLCV
  → IndicatorCalculator
  → SwingFeatureFrame
  → Strategy
       ├─ Observation history: 지켜본 과정
       ├─ Signal history: 조건이 완성된 사건
       ├─ Current signals: 오늘 발생한 사건
       └─ EntryOpportunity: 오늘 신규 진입 가능 여부
             ├─ check / analyze / brief
             ├─ 현재가 성과
             ├─ Backtest
             └─ PositionPlanner → 실제 수량
```

```text
StrategyResult = f(
  ChartBundle prefix,
  strategy_version,
  parameter_fingerprint,
)
```

같은 입력이면 실행일, PostgreSQL, 실제 보유·체결과 무관하게 같은 결과를 내야 한다.

## 2. 핵심 용어와 책임

| 구성요소 | 의미 | 사용처 |
|---|---|---|
| Observation | 여러 거래일 지속될 수 있는 관찰 상태 | 화면·설명 |
| Signal | 특정 거래일에 한 번 발생한 차트 사건 | 화면·성과·Backtest |
| Current signals | `occurred_on == as_of`인 Signal | PositionPlanner |
| EntryOpportunity | 가장 최근 진입 Signal을 오늘 실행해도 되는지 | 화면·PositionPlanner |
| SignalPerformance | Signal 기준 가격 대비 평가일 가격 | 화면·비교 |
| Backtest | Signal을 사용한 가상 체결·장부·성과 | 연구 |
| PositionPlanner | 실제 보유·계좌 기반 주문 수량 | 실제 실행 계획 |

Strategy는 실제·가상 position, 평균단가, 체결 장부, position stop, R을 읽거나 반환하지 않는다.

## 3. 출력 계약

```python
class SignalFinality(StrEnum):
    PROVISIONAL = "provisional"
    FINAL = "final"


class ObservationStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED_TO_SIGNAL = "resolved_to_signal"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class EntryOpportunityStatus(StrEnum):
    ALLOW = "allow"
    WATCH = "watch"
    BLOCK = "block"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    NO_RECENT_SIGNAL = "no_recent_signal"
    NOT_EVALUATED = "not_evaluated"


class StrategyObservationEpisode(BaseModel):
    code: str
    started_on: date
    status_as_of: date
    ended_on: date | None
    status: ObservationStatus
    direction: Direction | None
    evidence: list[Evidence] = Field(min_length=1)


class StrategySignal(BaseModel):
    signal_id: str
    strategy_id: str
    strategy_version: str
    parameter_set_version: str
    parameter_fingerprint: str
    code: str
    occurred_on: date
    finality: SignalFinality
    direction: Direction | None
    signal_price: Decimal
    evidence: list[Evidence] = Field(min_length=1)
    data_status: DataStatus


class EntryOpportunity(BaseModel):
    evaluation_as_of: date
    finality: SignalFinality
    status: EntryOpportunityStatus
    entry_signal: StrategySignal | None
    invalidated_by: StrategySignal | None
    age_bars: int | None
    signal_price: Decimal | None
    execution_reference_price: Decimal | None
    extension_pct: Decimal | None
    market_regime: str | None
    structure_status: StructureStatus
    evidence: list[Evidence] = Field(min_length=1)
    policy_version: str


class StrategySignalBundle(BaseModel):
    strategy_id: str
    strategy_version: str
    parameter_set_version: str
    parameter_fingerprint: str
    ticker: str
    as_of: date
    observation_history: list[StrategyObservationEpisode]
    signal_history: list[StrategySignal]
    current_signals: list[StrategySignal]
    entry_opportunity: EntryOpportunity
    data_status: DataStatus
```

`current_signals`는 `signal_history` 중 `occurred_on == as_of`인 항목과 정확히 같아야 한다.
Observation은 주문과 Backtest 체결을 만들지 않는다. 모든 Signal과 EntryOpportunity는 Evidence를 가진다.

## 4. 장중 후보와 확정 사건

최신 장중 가격도 계산에 사용한다. 현재 거래일의 미완성 daily bar에서 나온 결과는
`PROVISIONAL`, 완료된 거래일 bar의 결과는 `FINAL`이다.

- `check`, `analyze`, `brief`: 둘 다 표시하고 장중 후보 여부를 명시
- PositionPlanner: `PROVISIONAL`도 현재 가격 snapshot 기준 수량 계산 가능
- PositionPlan: 사용한 finality, 계산 시각, market snapshot hash를 포함
- 기본 PositionPlan 출력에는 finality와 장중 후보/확정을, 상세 출력에는 계산 시각과 snapshot hash도 표시
- Backtest: `FINAL` Signal만 사용
- 과거 Signal을 장중 값으로 덮어쓰거나 저장하지 않음

`ChartBundle`은 마지막 bar의 `finality`를 가진다. 과거 session은 항상 `FINAL`이며 현재 session은
명시적 session 종료 metadata 또는 거래소 정규 종료 시각과 15분 close buffer로 판정한다.
현재 provider는 조기 종료 metadata를 제공하지 않는다.

### 4.1 거래일과 입력 충족 경계

미국·한국 거래소 calendar는 종목·benchmark의 관측 행과 독립적으로 expected session을 제공한다.
종목 history의 미설명 누락은 typed coverage로 feature·detector까지 전달하고 `PARTIAL`로 표시한다.
이 입력으로 Observation·Signal을 생성하거나 실제 보유 매도 후보를 만들지 않는다.
시장 chart만 없으면 완전한 종목 Signal은 유지하고 EntryOpportunity만 `NOT_EVALUATED`로 제한한다.
live `2y` 응답은 nominal 요청의 첫 exchange session 1개만 빠지고 이후 as_of까지 연속인 경우에만
정상 rolling 기간 경계로 허용한다. 원래 `requested_start`와 전체 exchange calendar는 보존하고,
유효 평가 시작 `effective_start`부터의 expected sessions를 별도로 기록한다. 시작 2개 이상·중간·끝
누락은 여전히 incomplete이며, complete 입력의 effective_start는 첫 exchange session 하나만 건너뛸 수 있다.
prefix는 원래 생략된 첫 exchange session이 sliced calendar에 남아 있을 때만 effective 시작을 보존한다.
휴장일 origin 등으로 생략 session이 잘려 나가면 요청 시작을 origin으로 rebase하고 effective 보정을 제거한다.
직접 구성한 동일 prefix와 내용·hash가 같아야 하며, 원래 요청 첫날까지 complete coverage가 있다고 주장하지 않는다.
이 제한적 허용은 live loader에만 적용하며 명시적 Backtest calendar·no-trade 계약은 완화하지 않는다.
상장일·거래정지를 관측 행으로 추정하지 않는다.

## 5. Parameter identity

```python
@dataclass(frozen=True)
class SwingW150Parameters:
    parameter_set_version: str = "SWING_W150_V2_PARAMS_V1"
    minimum_history_bars: int = 250
    direction_lookback_bars: int = 21

    trend_breakout_lookback: int = 50
    trend_breakout_volume_multiple: float = 1.4
    deep_recovery_breakout_lookback: int = 20
    structure_breakdown_volume_multiple: float = 1.5
    structure_weak_close_location: float = 0.25

    overheat_extension: float = 0.40
    overheat_reset_extension: float = 0.20
    overheat_expiry_bars: int = 20
    post_correction_recovery_expiry_bars: int = 20

    pullback_support_sma_periods: tuple[int, ...] = (50, 150, 200)
    pullback_support_atr_distance: float = 0.5
    pullback_watch_expiry_bars: int = 10
    pullback_reversal_high_lookback: int = 1

    sma_exit_consecutive_closes: int = 2
    entry_opportunity_max_age_bars: int = 20
    entry_opportunity_max_extension: float = 0.05
```

Production parameter는 registry에서 version과 canonical payload를 1:1로 고정한다.

```text
parameter_fingerprint = SHA256(canonical parameter JSON)
```

- production version에 등록된 값과 다른 payload는 생성 단계에서 거부
- Backtest custom parameter는 fingerprint를 자동 생성하고 표시 이름에 fingerprint suffix 사용
- Signal ID, Strategy input hash, SignalPerformance, BacktestResult에 fingerprint 포함
- version 문자열이 같아도 fingerprint가 다르면 같은 결과 집단으로 합치지 않음

## 6. Signal inventory

| code | 발생 조건 | 주문 의미 |
|---|---|---|
| `TREND_BREAKOUT_ENTRY` | 상승 구조에서 50봉 고가를 거래량 1.4배로 최초 돌파 | 진입 후보 |
| `DEEP_RECOVERY_ENTRY` | 깊은 조정 뒤 SMA20·50 회복과 20봉 돌파 또는 SMA50 재탈환 | 진입 후보 |
| `PULLBACK_REVERSAL_ENTRY` | 다중 지지 눌림 뒤 전일 고가 최초 돌파 | 진입 후보 |
| `OVERHEAT` | SMA50 대비 +40% 최초 도달 | 경고만 |
| `OVERHEAT_CORRECTION` | 과열 뒤 SMA20 최초 하향 이탈 | 실제 보유 50% 축소 |
| `OVERHEAT_RESOLVED` | 과열 뒤 이격 +20% 이하 | 주문 없음 |
| `OVERHEAT_EXPIRED` | 마지막 +40% bar 뒤 20거래일 | 주문 없음 |
| `POST_OVERHEAT_RECOVERY_ENTRY` | correction 뒤 SMA20 회복과 전일 고가 최초 돌파 | 진입 후보 |
| `SMA150_EXIT` | SMA150 위 상승 구조 뒤 2일 연속 종가 이탈 | 전량 청산 |

V1의 `S_ENTRY`, `D_ENTRY`는 V2에서 각각 `TREND_BREAKOUT_ENTRY`,
`DEEP_RECOVERY_ENTRY`로 이름을 바꾼다.

## 7. 차트 sequence truth table

### 7.1 과열

| 현재 phase | 조건 | 발생 사건 | 다음 phase |
|---|---|---|---|
| `NORMAL` | 이격이 처음 +40% 이상 | `OVERHEAT` | `OVERHEATED` |
| `OVERHEATED` | SMA20 최초 하향 이탈 | `OVERHEAT_CORRECTION` | `CORRECTED` |
| `OVERHEATED` | 이격 +20% 이하 | `OVERHEAT_RESOLVED` | `NORMAL` |
| `OVERHEATED` | 마지막 +40% bar 뒤 20일 | `OVERHEAT_EXPIRED` | `NORMAL` |
| `CORRECTED` | SMA20 회복 + 전일 고가 돌파 | `POST_OVERHEAT_RECOVERY_ENTRY` | `NORMAL` |
| `CORRECTED` | 20거래일 경과 | Observation `EXPIRED` | `NORMAL` |
| 모든 phase | `SMA150_EXIT` | 기존 sequence 종료 | `NORMAL` |

같은 bar에서 correction과 resolve/expire가 겹치면 correction이 우선한다. 회복과 correction 이후
20거래일 만료가 겹치면 회복이 우선한다. 각 전이는 한 번만 발생하고 reset 뒤 다시 시작할 수 있다.

### 7.2 눌림목

상승 구조 gate:

```text
SMA50 > SMA150 > SMA200
SMA50·SMA150·SMA200 각각 현재값 > 21거래일 전 값
SuperTrend_Dir == 1
```

| 현재 phase | 조건 | 출력 | 다음 phase |
|---|---|---|---|
| `NONE` | SMA50·150·200·Supertrend 중 하나 이상 0.5 ATR 이내 접근 후 종가 방어 | `PULLBACK_WATCH ACTIVE` | `WATCHING` |
| `WATCHING` | 지지 위에서 전일 고가 최초 돌파 | `PULLBACK_REVERSAL_ENTRY`, Observation resolved | `NONE` |
| `WATCHING` | 지지선보다 0.5 ATR 초과 아래 마감 | Observation invalidated | `NONE` |
| `WATCHING` | watch 시작 시 포착한 지지선이 모두 사라짐 | Observation invalidated | `NONE` |
| `WATCHING` | 10거래일 경과 | Observation expired | `NONE` |
| `WATCHING` | `SMA150_EXIT` | Observation invalidated | `NONE` |

WATCHING은 시작일, 지지선 집합, 최신 Evidence를 가진다. 새로운 더 최근 지지 접근은 기존 watch를
종료하고 새 episode를 시작한다. 여러 지지선이 겹치면 Signal은 하나이고 Evidence는 모두 보존한다.
cRSI·MACD 방향은 Evidence로만 보여주며 V2 gate에는 사용하지 않는다.

반전과 watch 만료가 겹치면 반전이 우선한다. 같은 bar에 `SMA150_EXIT`도 발생하면 두 Signal은
history에 보존하되 Observation은 `INVALIDATED`로 끝내고 PositionPlanner는 exit을 선택한다.
Supertrend-only watch에서 상승 지지선이 사라지면 기존 episode를 무효화한다. 여러 포착 지지선 중
일부만 사라지고 다른 지지선이 유효하면 그 지지선으로 반전을 판단하며 사라진 값은 Evidence에 남긴다.

### 7.3 SMA150 Exit 반복 방지

두 번째 연속 이탈 bar에서 한 번만 `SMA150_EXIT`을 만든다. SMA150 아래에 계속 머무르면 반복하지
않으며 종가가 SMA150 위로 회복된 뒤에만 다시 무장한다.

### 7.4 같은 날 우선순위

모든 사건은 history에 보존하되 PositionPlanner는 다음 우선순위를 사용한다.
2026-10-22 사용자 승인으로 대표 Entry는 Opportunity와 Planner의 공통 규칙으로 선택한다.
가장 최근 Entry 발생일을 우선하고, 같은 날에만 아래 Entry type 순서를 적용한다.
이 순서는 대표 선택용이며 수익성 순위의 검증을 의미하지 않는다. 오늘 주문의 청산·축소 우선은 유지한다.

```text
SMA150_EXIT
> OVERHEAT_CORRECTION
> POST_OVERHEAT_RECOVERY_ENTRY
> PULLBACK_REVERSAL_ENTRY
> TREND_BREAKOUT_ENTRY
> DEEP_RECOVERY_ENTRY
> OVERHEAT / OVERHEAT_RESOLVED / OVERHEAT_EXPIRED
```

## 8. EntryOpportunity

평가 대상은 가장 최근 진입 Signal이다.

```text
TREND_BREAKOUT_ENTRY
DEEP_RECOVERY_ENTRY
PULLBACK_REVERSAL_ENTRY
POST_OVERHEAT_RECOVERY_ENTRY
```

완전한 차트·시장 입력을 확인한 다음, history에서 가장 최근 entry를 선택한다. 같은 날짜에 여러 entry가
있으면 공통 Entry 우선순위로 원천을 선택한다. 먼저 대표를 선택하고 그 source의 유효성을 평가하며,
허용되지 않는다고 하위 또는 과거 Entry로 우회하지 않는다. 이 규칙은 PositionPlanner와 공유한다.
원천 뒤 `SMA150_EXIT` 또는 `OVERHEAT_CORRECTION`이 있으면 age 만료보다 먼저 `INVALIDATED`다.
그 뒤 새로운 entry가 발생하면 새 원천으로 평가한다. source와 invalidator의 strategy version·parameter
identity가 현재 설정과 다르면 `NOT_EVALUATED`다.

| 조건 | status |
|---|---|
| age 0..20, 구조 유효, 강세장, 실행 기준가 대비 +5% 이하 | `ALLOW` |
| age 0..20, 구조 유효, 횡보장 또는 +5% 초과 | `WATCH` |
| age 0..20, 하락장 | `BLOCK` |
| source 뒤 correction/exit | `INVALIDATED` |
| ChartBundle 내 최신 entry가 21 bars 이상 | `EXPIRED` |
| 완전한 ChartBundle 안에 entry가 없음 | `NO_RECENT_SIGNAL` |
| coverage·시장·거래일 정렬 부족 또는 active Signal identity 불일치 | `NOT_EVALUATED` |

`age=20`은 유효하고 `age=21`부터 만료다. 2y window 자체가 불완전하면 Signal 부재로 단정하지 않고
`NOT_EVALUATED`다.

구조 무효는 source 이후 명시적인 correction·exit만 의미하고 `INVALIDATED`에 대응한다.
유효 기간 안에서 invalidator가 없으면 구조는 `VALID`다. source 당일 실행 기준가는 Signal 종가,
다음 bar부터는 다음 실제 instrument bar의 시가다. 미국은 `SPY`, KOSPI·6자리 KRX는 `^KS11`,
KOSDAQ은 `^KQ11`을 시장 benchmark로 사용한다.

## 9. Pipeline 출력

기본 화면은 최근 20거래일을 보여준다.

```text
현재 Observation
- PULLBACK_WATCH ACTIVE — SMA150·Supertrend 지지

최근 Observation history
- 10월 2~4일 PULLBACK_WATCH → RESOLVED_TO_SIGNAL

최근 Signal history
- 10월 4일 PULLBACK_REVERSAL_ENTRY [PROVISIONAL]

오늘 EntryOpportunity
- ALLOW [PROVISIONAL] — 기준가 대비 +2.1%
```

20거래일 이전 기록은 기본 화면에서 숨기되 상세 분석과 Backtest에서 차트로 재계산할 수 있다.

## 10. SignalPerformance

수익률 기준을 하나의 필드에서 중간에 바꾸지 않는다.

- Signal 당일: `estimated_return_from_signal_close`
- T+1 이후: `executed_return_from_next_tradable_open`
- T+1 bar가 없으면 executed return은 `NOT_EVALUATED`
- 거래정지면 다음 실제 bar의 시가와 지연 session 수를 표시
- 평가일이 비거래일이면 직전 완료 session을 `evaluation_as_of`로 사용
- 장중 최신 가격으로도 계산하며 각 metric은 `PARTIAL`, 완료 가격이면 `COMPLETE`
- 누락된 exchange session이 모두 coverage의 no-trade session으로 선언된 경우에만 거래정지 지연 인정
- provider gap이면 estimate는 유지하고 executed는 `NOT_EVALUATED`

계산은 요청 시 수행하고 저장하지 않는다.

## 11. Backtest

### 11.1 V1 호환

기존 `engine.py`와 기존 Golden fixture는 V1 compatibility baseline으로 유지한다. V1은 과열 전량매도,
기존 stop·재매수·체결 순서를 그대로 검증한다. V2 구현을 위해 V1 결과를 변경하지 않는다.

### 11.2 V2 execution/risk policy

- `FINAL` Signal만 사용
- `warmup_start`, `test_start`, `test_end`를 명시하고 결과 identity에 포함
- warm-up 중 Signal은 거래하지 않지만 전체 입력 기간 Signal의 FINAL·identity·실제 bar를 검증
- 종목 가격과 독립적인 expected exchange sessions를 필수 입력으로 받음
- warm-up부터 종료일까지 미설명 누락은 명시적 오류로 중단하고, 확인된 no-trade session만 건너뜀
- observed bar와 no-trade 선언은 겹치지 않으며, no-trade는 expected sessions 안에 있어야 함
- 평가 기간 안의 calendar·no-trade 선언은 결과 identity에 포함하고 미래 선언은 제외
- close 확정 Signal은 다음 실제 거래 가능 session 시가에 체결
- 장중 stop은 close Signal보다 먼저 처리
- 시가가 stop 아래로 gap이면 시가에 체결
- `OVERHEAT_CORRECTION`은 현재 수량의 50%를 올림해 매도
- 잔여 lot의 entry basis와 주당 최초 risk는 유지하고, 수량별 risk capital은 청산·잔여 slice로 분리
- recovery entry는 policy risk target까지 보충
- 각 추가매수는 별도 lot과 initial risk를 가짐
- aggregate R은 청산된 slice의 실현손익 합계 / 청산된 slice의 초기 risk capital 합계
- 수수료·slippage는 모든 fill에 적용
- 평가 기간 밖 미래 bar는 계산·검증에서 제외하며 종료일 강제청산은 하지 않음

V2 초기 stop:

| Entry code | stop |
|---|---|
| `TREND_BREAKOUT_ENTRY` | `min(SMA150, entry - 3 ATR)` |
| `DEEP_RECOVERY_ENTRY` | `max(Low20 - 0.5 ATR, entry × 0.85)` |
| `PULLBACK_REVERSAL_ENTRY` | `support - 0.5 ATR`, 최대 손실 15% 제한 |
| `POST_OVERHEAT_RECOVERY_ENTRY` | `SMA20 - 0.5 ATR`, 최대 손실 15% 제한 |

stop multiplier와 최대 손실도 execution/risk policy parameter로 둔다.

Backtest detector는 전체 미래 frame을 보고 과거 결과를 만드는 API를 사용하지 않는다. 날짜순 one-pass
causal 계산 또는 평가일별 prefix 결과와 동일함을 Golden Test로 검증한다.

## 12. PositionPlanner

PositionPlanner는 `current_signals`만 사용한다. 과거 Signal history는 주문 판단에 사용하지 않는다.

- `PROVISIONAL`과 `FINAL` 모두 수량 계산 가능
- PositionPlan에 finality, `calculated_at`, market snapshot hash 포함
- 오늘 priority-selected entry와 source Signal ID가 일치하고 오늘 평가된 `ALLOW`만 신규 매수
- 과거 entry의 `ALLOW`만 있으면 신규 매수 0이며 source mismatch 시 낮은 우선순위로 대체하지 않음
- `WATCH/BLOCK/INVALIDATED/EXPIRED/NO_RECENT_SIGNAL/NOT_EVALUATED`는 신규 매수 0
- `OVERHEAT_CORRECTION`은 실제 보유 50% 올림 매도(5주 → 3주)
- `SMA150_EXIT`은 실제 보유 전량 매도
- 미보유 종목의 sell Signal은 표시하고 sell quantity만 0
- 매수는 현재 session의 유효한 가격 snapshot과 실제 계좌 risk가 필요하고 부족하면 수량 `UNAVAILABLE`
- 보유 축소·전량 매도는 실제 수량으로 계산하며 가격·계좌 없이도 가능

기존 Playbook `plan_position(verdict, ...)`는 compatibility wrapper로 유지하고, 새
`plan_position_from_signals(bundle, ...)`가 공통 내부 directive planner를 호출한다.

## 13. PostgreSQL 제거

운영 적용된 schema와 legacy row가 없으므로 `strategy_history` subsystem을 전체 삭제한다.

- `migrations/strategy_history/`
- `src/storage/strategy_history/`
- `tests/storage/strategy_history/`
- `AnalysisStrategyService`의 persistence session 시작·attach·persist·close
- strategy history DSN/config/documentation
- Analysis Trigger, Strategy Event, EntryOpportunity, Outcome, PositionPlan 저장 경로

`src/storage/canonical.py`처럼 DB와 무관한 canonical hash utility는 유지한다. Observation, Trigger,
Signal, EntryOpportunity, SignalPerformance는 차트에서 재계산하고 PositionPlan은 현재 요청 결과로만 반환한다.

## 14. Migration 순서

1. parameter registry·fingerprint와 새 domain model 추가
2. ChartBundle bar finality와 raw OHLCV→feature 경계 추가
3. causal Observation/Signal detector 구현
4. 항상 존재하는 EntryOpportunity 구현
5. runner·세 pipeline 연결과 `strategy_history` subsystem 제거
6. 저장 없는 SignalPerformance 구현
7. V1 호환 Backtest 유지, V2 Backtest 추가
8. PositionPlanner current/provisional Signal 연결
9. 문서·전체 검증·실제 pipeline 확인

## 15. 검증 계약

1. 동일 prefix·version·fingerprint는 같은 전체 bundle을 만든다.
2. 같은 과거 prefix에 다른 미래 suffix를 붙여도 Observation episode, Signal, EntryOpportunity가 같다.
3. 모든 sequence 사건은 한 번만 발생하고 reset 뒤에만 재발생한다.
4. old exit/correction은 오늘 PositionPlanner directive로 재사용되지 않는다.
5. source entry 뒤 exit/correction은 EntryOpportunity를 invalidated한다.
6. parameter version과 canonical payload 불일치는 거부한다.
7. raw OHLCV부터 최종 Signal까지 Golden Test를 통과한다.
8. 장중 bar는 provisional, 완료 bar는 final이며 둘 다 PositionPlan 계산이 가능하다.
9. Backtest는 provisional을 거부하고 final만 사용한다.
10. age 20/21, no signal, truncated history를 각각 구분한다.
11. V1 Golden은 유지되고 V2 50% 정책은 별도 Golden을 가진다.
12. V2 결과는 persistence row/table로 변환되지 않는다.
13. `strategy_history` code·migration·test·runtime import가 0건이다.
14. `check`, `analyze`, `brief`는 같은 핵심 내용을 표시한다.
15. 종목과 benchmark가 같은 거래일을 누락해도 calendar에서 사라지지 않는다. 미국·한국 휴장은 누락이 아니다.
16. 미설명 종목 gap은 Signal·실제 매도 후보·체결 성과로 승격되지 않으며, 시장 부재는 완전한 종목 exit을 막지 않는다.
17. V2 Backtest의 warm-up·T+1·보유 중 누락을 거부하고 명시적 no-trade 지연만 허용한다.
18. 실제 EntryOpportunity의 age 0 기준은 `Signal 종가 추정`, age 1 이상은 `다음 실제 거래 가능 시가`로 세 화면에 표시한다.

## 16. 제외 범위

- Strategy 관련 PostgreSQL 저장
- 별도 Strategy Tracker·ForwardTracker
- 실제 broker 주문 전송
- 기존 연구 Backtest 전체 일괄 재작성

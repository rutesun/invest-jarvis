# 단계형 모멘텀 매매 시스템 룰 v0.4

> 목적: v0.3의 매매 철학은 유지하되, 사람이 해석해야 했던 모호한 부분을 줄이고 **백테스트와 자동 실행이 가능한 상태 머신 명세**로 만든다.
>
> 중요: 아래 수치들은 최종 최적값이 아니라 `v0.4 initial test parameters`다. 구조와 파라미터를 분리하고, 홀드아웃 검증 전에는 사례별로 값을 조정하지 않는다.

---

# 0. v0.4에서 달라진 점

v0.4는 새로운 지표를 추가하는 버전이 아니다.

다음 여섯 가지를 완결한다.

1. `PositionState`와 `ManagementMode` 분리
2. PROBE의 성공·실패·만료 규칙 정의
3. 고정 비중 대신 Risk 기반 Position Sizing 도입
4. Early / Confirm / Add Trigger 역할 분리
5. WINNER를 Risk Level + Target Exposure 방식으로 관리
6. Signal 시점과 실제 체결 시점을 분리하는 Execution Contract 확정

기존 핵심 구조는 유지한다.

```text
REGIME
  ↓
SETUP / RANKING
  ↓
TRIGGER
  ↓
LOCATION
  ↓
RISK
  ↓
POSITION
  ↓
ACTION
```

핵심 원칙:

> Score는 우선순위, State + Trigger + Location + Risk + Position은 행동을 결정한다.

---

# 1. 시스템 상태 구조

## 1.1 Technical Regime

```text
WEAK
TRANSITION
TREND
BROKEN
```

`DEEP_RECOVERY_READY`는 Regime이 아니라 별도 진입 경로 플래그다.

## 1.2 PositionState

```text
FLAT
PROBE
CORE
FULL
```

의미:

- `FLAT`: 미보유
- `PROBE`: 가설 검증용 소규모 포지션
- `CORE`: 본 포지션은 있으나 목표 최대 비중 미만
- `FULL`: 목표 최대 비중 도달

## 1.3 ManagementMode

```text
NORMAL
WINNER
```

WINNER는 PositionState가 아니다.

예:

```text
FULL + NORMAL
FULL + WINNER
CORE + WINNER
```

처럼 동시에 표현한다.

## 1.4 Action

```text
WATCH
PROBE_ENTRY
BUY
ADD
HOLD
REDUCE
EXIT
CHASE_WAIT
```

---

# 2. Regime 판정

## 2.1 BROKEN

BROKEN은 항상 최우선이다.

```text
if hard_breakdown:
    regime = BROKEN
```

`hard_breakdown`은 아래 8장의 Primitive Specification에서 정확히 계산한다.

## 2.2 TREND

다음 중 하나면 TREND:

```text
stage2 == true
```

또는:

```text
close > sma200
AND close > sma50
AND sma20 > sma50
AND supertrend_up
```

## 2.3 TRANSITION

필수조건:

```text
close > sma200
AND regime != TREND
AND hard_breakdown == false
```

그리고 아래 3개 개선 그룹 중 2개 이상:

### A. Price Recovery

```text
close > sma20
OR valid_sma50_reclaim
```

### B. Structure Improvement

```text
sma20_slope > 0
OR higher_low
```

### C. Direction Improvement

```text
supertrend_up
```

따라서:

```text
if close > sma200
   and improvement_groups >= 2
   and not trend
   and not hard_breakdown:
    regime = TRANSITION
```

그 외는 WEAK.

---

# 3. DEEP_RECOVERY_READY

SMA200 아래에서 시작하는 SNOW형 홈런을 위한 별도 경로다.

```text
close < sma200
AND close > sma20
AND close > sma50
AND sma20_slope > 0
AND higher_low
AND supertrend_up
AND hard_breakdown == false
```

이면:

```text
deep_recovery_ready = true
```

이 상태만으로는 매수하지 않는다.

```text
DEEP_RECOVERY_READY
+ EARLY_TRIGGER
+ Location OK
+ Risk OK

→ RECOVERY_PROBE candidate
```

Normal Probe와 Recovery Probe는 반드시 별도 cohort로 성과를 측정한다.

---

# 4. Trigger 체계

v0.4부터 Trigger를 목적별로 분리한다.

## 4.1 EARLY_TRIGGER

TRANSITION 또는 DEEP_RECOVERY에서 초기 참여 여부를 결정한다.

```text
EARLY_BREAKOUT
SMA50_RECLAIM
POWER_GAP
POCKET_PIVOT
```

### EARLY_BREAKOUT

```text
close[t] > max(high[t-20 : t-1])
AND close[t-1] <= max(high[t-21 : t-2])
```

종가 확정 기준으로 판단한다.

### SMA50_RECLAIM

Raw event:

```text
close[t-1] <= sma50[t-1]
AND close[t] > sma50[t]
```

`Higher Low`, `Strong Close`, `Volume`은 Trigger 자체에 섞지 않고 Quality attribute로 저장한다.

### POWER_GAP

기존 detector 결과를 사용한다.

단, 현재 문서만으로는 기존 detector의 정확한 수식이 정의되어 있지 않으므로 v0.4 구현체는 다음 계약을 지켜야 한다.

```text
power_gap: bool
power_gap_version: string
```

기존 detector 수식이 확보되면 Primitive Specification에 고정한다.

### POCKET_PIVOT

기존 detector 결과를 사용한다.

마찬가지로:

```text
pocket_pivot: bool
pocket_pivot_version: string
```

을 저장한다.

---

## 4.2 CONFIRM_TRIGGER

PROBE를 본 포지션으로 승격시키기 위한 확인 사건.

v0.4에서는 다음 중 하나:

```text
CONFIRMED_BREAKOUT
FOLLOW_THROUGH
STRONG_RECLAIM
TIGHT_PULLBACK_BREAKOUT
```

초기 정의:

### CONFIRMED_BREAKOUT

```text
fresh 20D close breakout
AND trigger day low를 종가로 이탈하지 않음
```

### FOLLOW_THROUGH

EARLY_TRIGGER 이후 10거래일 이내:

```text
close > early_trigger_close
AND close_location >= 0.60
AND daily_return > 0
```

### STRONG_RECLAIM

```text
close가 sma20 또는 sma50을 아래에서 위로 회복
AND close_location >= 0.70
```

### TIGHT_PULLBACK_BREAKOUT

```text
최근 3~10거래일 조정폭이 ATR 기준 축소
AND 조정 구간 고점을 종가로 돌파
```

세부 threshold는 Parameter Registry에서 관리한다.

---

## 4.3 ADD_TRIGGER

이미 CORE 포지션이 있고 수익 중일 때만 사용한다.

```text
NEW_BASE_BREAKOUT
PULLBACK_BREAKOUT
RECLAIM_AFTER_PULLBACK
CONTINUATION_PIVOT
```

ADD는 항상:

```text
position_pnl > 0
AND regime == TREND
AND not entry_overextended
AND hard_risk == false
```

를 요구한다.

손실 중 물타기는 금지한다.

---

# 5. Trigger Quality / Demand Evidence

Trigger와 Quality를 분리한다.

Trigger는:

> 무슨 사건이 발생했는가?

Quality는:

> 그 사건이 얼마나 좋은가?

저장값:

```text
volume_ratio20
close_location
gap_pct
daily_return
distance_sma20_pct
distance_sma50_pct
distance_sma200_pct
distance_52w_high_pct
distance_sma20_atr
atr14
```

초기에는 Quality를 하나의 마법 점수로 합치지 않는다.

각 feature의 효과를 별도로 검증한다.

예:

```text
Early Breakout 전체
vs Early Breakout + volume_ratio20 >= 1.5

Early Breakout 전체
vs Early Breakout + close_location >= 0.75
```

---

# 6. Location / Entry Overextension / Chase Guard

Signal과 Execution을 분리한다.

## 6.1 Signal-day Overextension

초기 테스트 정의:

```text
entry_overextended =
    distance_sma20_atr >= 2.5
    OR distance_sma20_pct >= 15%
```

이 값은 확정값이 아니라 테스트 파라미터다.

TREND 확인 자체가 BUY를 의미하지 않는다.

```text
TREND + Confirm Trigger + not overextended
→ BUY

TREND + overextended
→ HOLD_PROBE / WATCH
```

## 6.2 Next-open Chase Guard

신호는 t일 종가에 계산하고 실제 신규 진입은 t+1 시가에서 검토한다.

```text
open[t+1] > trigger_price * 1.05
→ CHASE_WAIT
```

단순 5%와 ATR 기반 조건은 향후 비교한다.

신호 자체는 삭제하지 않는다.

```text
signal_generated = true
order_executed = false
execution_block_reason = CHASE
```

로 기록한다.

---

# 7. Risk와 Position Sizing

고정 포지션 %보다 먼저 손실 허용량을 계산한다.

## 7.1 1R

기본 백테스트 값:

```text
ACCOUNT_RISK_UNIT = 계좌자산의 0.50%
```

이 값은 Parameter Registry에서 변경 가능하다.

## 7.2 Entry별 Risk Budget

초기값:

```text
Recovery Probe = 0.25R
Normal Probe   = 0.50R
Direct BUY     = 1.00R
ADD            = 0.50R
```

동일 종목 총 초기 위험은 별도 `MAX_POSITION_RISK`를 넘지 않는다.

초기값:

```text
MAX_POSITION_RISK = 1.50R
```

## 7.3 Position Size 계산

```text
risk_per_share = entry_price - effective_stop

risk_based_position =
    risk_budget_amount / risk_per_share
```

계좌 비중으로 환산 후 다음 cap을 적용한다.

```text
Recovery Probe max = 15%
Normal Probe max   = 25%
Direct BUY max     = 60%
Total Position max = 100%
```

즉:

```text
actual_size = min(risk_based_size, position_cap)
```

---

# 8. Stop / Invalidation

v0.4에서 PROBE는 반드시 세 가지 종료 조건을 가진다.

## 8.1 Structural Stop

Trigger별 구조적 invalidation:

### EARLY_BREAKOUT

초기 정의:

```text
breakout_level = prior_20d_high
structural_stop = breakout_level - 0.5 * ATR14
```

### SMA50_RECLAIM

```text
structural_stop = sma50 - 0.5 * ATR14
```

### POWER_GAP

```text
structural_stop = power_gap_day_low
```

### POCKET_PIVOT

```text
structural_stop = min(signal_day_low, sma20)
```

단 기존 detector 정의 확보 후 재검토한다.

## 8.2 Hard Loss Stop

초기값:

```text
Normal Probe hard stop   = -5%
Recovery Probe hard stop = -4%
Direct BUY hard stop     = -7%
```

실제 stop은 더 가까운 손절선을 사용한다.

롱 포지션에서는:

```text
effective_stop =
    max(structural_stop, hard_stop_price)
```

## 8.3 Time Stop

PROBE가 일정 기간 동안 확인되지 않으면 실패로 본다.

초기값:

```text
PROBE_CONFIRM_WINDOW = 10 trading days
```

10거래일 내:

```text
TREND 전환
+
CONFIRM_TRIGGER
```

가 없으면:

```text
PROBE_EXPIRED
→ EXIT
→ FLAT
```

단 수익 중이고 구조가 매우 강한 경우를 따로 예외 처리하지 않는다. v0.4에서는 단순하게 시작하고 데이터로 검증한다.

---

# 9. PROBE Lifecycle

## 9.1 Normal Probe Entry

```text
PositionState == FLAT
AND regime == TRANSITION
AND EARLY_TRIGGER
AND not hard_risk
AND not entry_overextended
AND chase_guard 통과

→ PROBE_ENTRY
```

## 9.2 Recovery Probe Entry

```text
PositionState == FLAT
AND deep_recovery_ready
AND EARLY_TRIGGER
AND not hard_risk
AND chase_guard 통과

→ RECOVERY_PROBE_ENTRY
```

Recovery Probe는 일반 Probe보다 작은 Risk Budget을 사용한다.

## 9.3 PROBE Success

```text
PositionState == PROBE
AND regime == TREND
AND CONFIRM_TRIGGER
AND not entry_overextended
AND not hard_risk

→ BUY / CORE 승격
```

## 9.4 PROBE Hold

```text
PROBE
AND invalidation 없음
AND confirm 아직 없음
AND age < confirm_window

→ HOLD_PROBE
```

## 9.5 PROBE Failure

다음 중 하나면 EXIT:

```text
close/low가 effective_stop 이탈
OR hard_breakdown
OR PROBE_CONFIRM_WINDOW 만료
```

결과:

```text
PositionState = FLAT
ManagementMode = NORMAL
Episode 종료
```

---

# 10. Direct BUY

PROBE를 거치지 않아도 된다.

```text
PositionState == FLAT
AND regime == TREND
AND CONFIRM_TRIGGER 또는 유효한 TREND_ENTRY_TRIGGER
AND not entry_overextended
AND not hard_risk
AND chase_guard 통과

→ BUY
→ PositionState = CORE
```

PANW형 Base Breakout이 대표 사례다.

---

# 11. ADD

ADD 조건:

```text
PositionState in [CORE]
AND regime == TREND
AND position_pnl > 0
AND ADD_TRIGGER
AND not entry_overextended
AND not hard_risk
AND total_position < max_position
```

초기:

```text
최대 ADD 횟수 = 2
```

목표 흐름 예:

```text
BUY 50~60%
→ ADD 75~80%
→ ADD 100%
```

하지만 실제 비중은 Risk 기반 계산과 cap의 작은 값을 사용한다.

---

# 12. WINNER Mode

## 12.1 WINNER 진입

논리 연산 우선순위를 명확히 한다.

```text
(
    position_return >= 20%
    OR max_open_profit_r >= 2R
)
AND regime == TREND
AND hard_risk == false
```

이면:

```text
ManagementMode = WINNER
```

`position_return`은 현재 전체 포지션의 가중평균 매입가 기준이다.

---

# 13. WINNER Risk Level과 Target Exposure

WINNER에서는 개별 매도 명령보다 목표 비중을 계산한다.

## Level 0 — Healthy Winner

조건:

```text
regime == TREND
AND no winner damage signal
```

목표:

```text
target_exposure = 100%
```

## Level 1 — Climax / Extension

초기 조건:

```text
return_5d >= 20%
AND distance_sma20_atr >= 2.5
```

목표:

```text
target_exposure = 85%
```

Core는 유지하고 Trading 일부만 줄인다.

## Level 2 — Short-term Damage

다음 중 하나:

```text
close < sma20 for 2 consecutive closes
```

또는:

```text
supertrend_down
AND 2거래일 내 sma20 reclaim 실패
```

목표:

```text
target_exposure = 65%
```

Trading tranche 대부분 제거.

## Level 3 — Intermediate Damage

```text
close < sma50 for 2 consecutive closes
AND
(
    sma20 <= sma50
    OR 3거래일 내 sma50 reclaim 실패
)
```

목표:

```text
target_exposure = 35%
```

Core도 축소.

## Level 4 — BROKEN

```text
hard_breakdown
OR regime == BROKEN
```

목표:

```text
target_exposure = 0%
```

즉 EXIT.

## 다중 경고 처리

여러 조건이 동시에 발생하면 가장 높은 Risk Level 하나만 사용한다.

```text
winner_risk_level = max(all_active_levels)
```

예:

```text
Level 1 + Level 2 동시
→ Level 2
→ target 65%
```

중복 매도하지 않는다.

---

# 14. WINNER Hysteresis

악화는 빠르게, 회복은 천천히 한다.

## 악화

현재보다 더 높은 Risk Level 조건이 발생하면 즉시 반영한다.

```text
Level 0 → Level 2
```

도 가능하다.

## 회복

한 번에 한 단계만 낮춘다.

초기 조건:

```text
3 consecutive closes
AND 해당 Risk Level을 만든 조건 해소
AND regime != BROKEN
```

그리고 Level 1 이하로 복원할 때 신규 Demand Trigger 또는 reclaim을 요구한다.

예:

```text
Level 3
→ Level 2
→ Level 1
→ Level 0
```

```text
35% → 65% → 85% → 100%
```

하루 반등으로 즉시 FULL 복원하지 않는다.

---

# 15. Setup / Ranking의 역할

v0.4에서는 SETUP이 Action을 직접 결정하지 않는다.

```text
SETUP = Ranking only
```

동시에 여러 Candidate가 있을 때 우선순위를 정하는 데만 사용한다.

후보 feature:

```text
Relative Strength
Industry Strength
Tightness
Volume Dry-up
VCP quality
Liquidity
Momentum persistence
```

현재 v0.4 실행 엔진은 이 점수가 없어도 동일한 BUY/PROBE/HOLD 결과를 내야 한다.

---

# 16. Market Mode Hook

시장 상태는 종목 Technical Signal을 바꾸지 않는다.

향후:

```text
RISK_ON
NEUTRAL
RISK_OFF
```

를 별도 레이어로 둘 수 있다.

예:

```text
Stock Signal = BUY
Market Mode = RISK_OFF

→ BUY 신호는 유지
→ Portfolio Risk Budget만 축소
```

v0.4에서는 interface만 남기고 실제 Market Mode 산식은 구현 범위 밖으로 둔다.

---

# 17. Primitive Specification

백테스트 전에 아래 값은 모든 구현체가 동일하게 계산해야 한다.

## 17.1 ATR14

Wilder ATR 14.

```text
TR = max(
    high-low,
    abs(high-prev_close),
    abs(low-prev_close)
)
```

초기 14개 TR 평균 후 Wilder smoothing 사용.

## 17.2 close_location

```text
if high > low:
    close_location = (close-low)/(high-low)
else:
    close_location = 0.5
```

범위 0~1.

## 17.3 volume_ratio20

```text
volume[t] /
mean(volume[t-20:t-1])
```

오늘 거래량은 분모에 포함하지 않는다.

## 17.4 SMA20 slope

```text
sma20_slope = sma20[t] - sma20[t-5]
```

초기 v0.4에서는 5거래일 변화량 사용.

## 17.5 Confirmed Pivot Low

pivot index `i`가 다음을 만족:

```text
low[i] < min(low[i-3:i])
AND
low[i] <= min(low[i+1:i+4])
```

pivot은 `i+3` 거래일이 끝난 뒤에만 알려진 것으로 처리한다.

즉 미래정보를 당겨 쓰지 않는다.

## 17.6 Higher Low

최근 두 개의 **확정된** Pivot Low를 `p1`, `p2`라 할 때:

```text
p2.low > p1.low
```

## 17.7 valid_sma50_reclaim

```text
최근 5거래일 안에
close가 sma50 아래→위로 cross

AND current close >= current sma50
```

## 17.8 hard_breakdown v0.4

초기 실행 정의:

다음 중 하나면 true.

### A. Major Low Breakdown

```text
close < prior_20d_low
AND volume_ratio20 >= 1.5
```

### B. Heavy SMA50 Failure

```text
close < sma50
AND close_location <= 0.25
AND volume_ratio20 >= 1.5
AND supertrend_down
```

### C. Long-term Structural Failure

```text
close < sma200
AND close < sma50
AND supertrend_down
AND lower_high_lower_low_structure
```

`lower_high_lower_low_structure`는 최근 확정 pivot high와 pivot low가 모두 이전 pivot보다 낮은 경우다.

이 정의와 threshold는 반드시 별도 holdout에서 검증한다.

## 17.9 hard_risk

```text
hard_risk =
    hard_breakdown
    OR active_stop_breach
```

## 17.10 entry_overextended

초기값:

```text
distance_sma20_atr >= 2.5
OR distance_sma20_pct >= 15%
```

---

# 18. Execution Contract

이 항목은 백테스트에서 절대 변경하지 않는다.

## 18.1 Signal Time

모든 일봉 Signal은 `t`일 종가가 확정된 뒤 계산한다.

사용 가능한 데이터:

```text
<= t
```

만 허용한다.

## 18.2 Entry Time

신규 주문은 기본적으로 `t+1` 시가에 체결 검토한다.

```text
signal_date = t
execution_date = next trading day
```

## 18.3 Chase

`t+1` 시가가 Chase Guard를 위반하면:

```text
order_executed = false
action = CHASE_WAIT
```

Signal은 기록에 남긴다.

## 18.4 Stop Fill

장중 low가 stop 이하라면:

```text
fill_price = stop_price
```

단 시가가 stop보다 아래로 gap-down이면:

```text
fill_price = open
```

으로 처리한다.

슬리피지는 별도 차감한다.

## 18.5 Cost

초기 백테스트 설정:

```text
commission = configurable
slippage_bps = configurable
```

기본값 0으로 결과를 만들더라도 반드시 비용 포함 결과를 함께 산출한다.

## 18.6 Corporate Actions

기술지표용 가격은 주식분할을 일관되게 조정한다.

배당 재투자용 total-return series를 OHLC 기술지표에 섞지 않는다.

---

# 19. Episode 정의

한 Episode는:

```text
첫 Position 진입
→ 최종 FLAT 복귀
```

까지다.

```text
episode_start = first executed entry
episode_end = final exit
```

EXIT 후 동일 종목에서 새 신호가 나오면 새 Episode다.

과거 WINNER였다는 사실은 새 Episode의 진입 권한을 주지 않는다.

---

# 20. 상태 전이 전체

```text
[FLAT]

BROKEN
→ WATCH / AVOID

DEEP_RECOVERY_READY + EARLY_TRIGGER + location/risk OK
→ RECOVERY_PROBE

TRANSITION + EARLY_TRIGGER + location/risk OK
→ NORMAL_PROBE

TREND + CONFIRM/TREND_ENTRY_TRIGGER + location/risk OK
→ DIRECT_BUY


[PROBE]

Stop / Hard Breakdown
→ EXIT

Confirm Window Expired
→ EXIT

TREND + CONFIRM_TRIGGER + not overextended
→ CORE

그 외
→ HOLD_PROBE


[CORE]

Hard Breakdown
→ EXIT

TREND + profitable + ADD_TRIGGER + not overextended
→ ADD

Winner condition
→ ManagementMode = WINNER

그 외
→ HOLD


[FULL]

Hard Breakdown
→ EXIT

Winner condition
→ ManagementMode = WINNER

그 외
→ HOLD


[WINNER MODE]

Risk Level 0
→ target 100

Risk Level 1
→ target 85

Risk Level 2
→ target 65

Risk Level 3
→ target 35

Risk Level 4
→ target 0 / EXIT
```

---

# 21. Golden Regression Fixtures

이 종목들은 성능 검증용이 아니라 룰이 의도대로 동작하는지 확인하는 회귀 테스트용이다.

## 21.1 PANW — Base → Breakout → Home Run

기대:

```text
2026-05-04  WATCH
2026-05-07  DIRECT_BUY candidate
2026-05-08  NO_CHASE_ADD
5월 중순    WINNER mode 진입
이후 정상 TREND → HOLD
```

핵심 질문:

> 긴 Base를 너무 일찍 사지 않고 실제 돌파에서 진입하는가?

## 21.2 SNOW — Deep Recovery Rocket

기대:

```text
2026-04-15  DEEP_RECOVERY_WATCH
2026-05-15  RECOVERY_PROBE candidate
2026-05-28  BUY promotion candidate
2026-05-29  NO_CHASE_ADD
```

핵심 질문:

> SMA200 아래에서 시작하는 홈런을 전부 놓치지 않는가?

## 21.3 BE — Transition → Probe → Buy

기대:

```text
2026-08-12  TRANSITION / WATCH
2026-09-03  NORMAL_PROBE candidate
2026-09-08  BUY promotion candidate
```

핵심 질문:

> 단순 회복은 거르고 실제 Early Ignition에서만 Probe하는가?

## 21.4 HOOD — Probe 후 추격 방지

기대:

```text
2026-08-13  WATCH
2026-08-21  NORMAL_PROBE candidate
2026-09-04  TREND but OVEREXTENDED → HOLD_PROBE
2026-09-18  BUY promotion candidate
```

핵심 질문:

> TREND가 늦게 확인됐다는 이유만으로 추격하지 않는가?

## 21.5 삼성전기 Episode #1 — Winner Management

기대:

```text
2026-04-08  BUY
2026-04-16  ADD
2026-04-21  FULL / WINNER
2026-05-29  Winner Risk Level 1
6월 말      Winner Risk Level 2
7월 초      Winner Risk Level 3
2026-07-13  Winner Risk Level 4 / EXIT
```

핵심 질문:

> 홈런을 오래 먹되 추세 붕괴 때 수익 대부분을 반납하기 전에 단계적으로 줄이는가?

## 21.6 삼성전기 Episode #2 — Signal vs Execution

기대:

```text
2026-07-31  WATCH
2026-08-12  TRANSITION
2026-08-13  PROBE signal candidate
2026-08-14  CHASE_WAIT 가능
2026-09-10  TREND but no entry trigger → WATCH
2026-09-22  BUY candidate
```

핵심 질문:

> 좋은 Signal과 나쁜 실제 체결 가격을 구분하는가?

---

# 22. v0.4 Parameter Registry

아래 값들은 코드에 흩어 쓰지 않고 한 곳에서 관리한다.

```yaml
atr_period: 14
sma20_slope_lookback: 5
pivot_left: 3
pivot_right: 3

reclaim_valid_days: 5

chase_pct: 0.05

overextended_sma20_pct: 0.15
overextended_sma20_atr: 2.5

risk_unit_pct: 0.005
recovery_probe_r: 0.25
normal_probe_r: 0.50
direct_buy_r: 1.00
add_r: 0.50
max_position_r: 1.50

recovery_probe_cap: 0.15
normal_probe_cap: 0.25
direct_buy_cap: 0.60
max_position_cap: 1.00

recovery_probe_hard_stop_pct: 0.04
normal_probe_hard_stop_pct: 0.05
direct_buy_hard_stop_pct: 0.07
probe_confirm_window: 10

winner_return_threshold: 0.20
winner_r_threshold: 2.0
winner_climax_5d_return: 0.20
winner_climax_atr_extension: 2.5

winner_level_0_target: 1.00
winner_level_1_target: 0.85
winner_level_2_target: 0.65
winner_level_3_target: 0.35
winner_level_4_target: 0.00

winner_recovery_confirm_days: 3

hard_breakdown_volume_ratio: 1.5
hard_breakdown_close_location: 0.25
```

이 숫자들은 **검증 대상**이다.

특정 fixture를 맞추기 위해 변경하지 않는다.

---

# 23. 백테스트에서 반드시 출력할 로그

각 거래일마다 최소 다음을 기록한다.

```text
date
ticker

regime
deep_recovery_ready

early_triggers[]
confirm_triggers[]
add_triggers[]

volume_ratio20
close_location
distance_sma20_pct
distance_sma20_atr
atr14

entry_overextended
hard_breakdown
hard_risk

position_state
management_mode
winner_risk_level
current_exposure
target_exposure

signal_generated
signal_type
order_executed
execution_block_reason
entry_price
effective_stop

episode_id
days_in_probe
unrealized_pnl_pct
unrealized_pnl_r

action
reason_codes[]
```

`reason_codes`가 중요하다.

예:

```text
action = HOLD_PROBE

reason_codes =
[
  TREND_CONFIRMED,
  ENTRY_OVEREXTENDED,
  NO_CONFIRM_TRIGGER
]
```

처럼 왜 그 행동이 나왔는지 재현 가능해야 한다.

---

# 24. v0.4 검증 순서

v0.4는 다음 순서로 검증한다.

## Step 1 — Golden Fixture Regression

PANW, SNOW, BE, HOOD, 삼성전기에서 의도한 상태 전이가 유지되는지 확인한다.

목적:

```text
코드가 설계를 그대로 구현했는가?
```

이지 성능 검증이 아니다.

## Step 2 — Primitive Unit Test

각 primitive:

```text
Higher Low
SMA50 Reclaim
Breakout
Overextension
Hard Breakdown
Probe Timeout
Winner Level
```

을 인공 데이터와 실제 데이터 일부에서 독립 테스트한다.

## Step 3 — Episode Backtest

후보일이 아니라 Episode 단위로 측정한다.

```text
Entry
Add
Reduce
Exit
```

전체를 하나의 거래 흐름으로 평가한다.

## Step 4 — Holdout

Golden Fixture에 사용하지 않은 종목·기간에서 평가한다.

최소 비교:

```text
Normal Probe vs no-trigger Transition
Recovery Probe vs no-trigger Deep Recovery
Direct Buy vs Trend days without trigger
Winner Management vs simple trailing exit
```

## Step 5 — Parameter Stability

하나의 최적값을 찾지 않는다.

예:

```text
Probe timeout: 5 / 10 / 15
Chase: 3% / 5% / 7%
ATR extension: 2.0 / 2.5 / 3.0
```

에서 넓은 범위에 걸쳐 결과가 안정적인지 본다.

---

# 25. v0.4에서 아직 하지 않는 것

다음은 v0.4 core에 넣지 않는다.

```text
Market Mode 실제 산식
Sector RS hard gate
Fundamental data
Earnings surprise
뉴스
Options flow
복잡한 ML model
Trigger quality 통합 점수
```

이들은 v0.4 core가 독립적으로 검증된 뒤 추가 실험한다.

---

# 26. v0.4의 최종 의도

v0.3은:

> 좋은 차트에서 어떻게 단계적으로 사고 큰 승자를 관리할 것인가?

를 정의했다.

v0.4는:

> 그 아이디어를 컴퓨터가 날짜마다 동일하게 판정하고, 실제 체결과 손실 한도까지 포함해 재현할 수 있는가?

를 정의한다.

최종 흐름:

```text
WEAK
  ↓
TRANSITION / DEEP_RECOVERY
  ↓
EARLY_TRIGGER
  ↓
PROBE
  ↓
[Stop / Timeout / Confirmation]
  ↓
TREND + CONFIRM_TRIGGER
  ↓
CORE
  ↓
ADD_TRIGGER
  ↓
FULL
  ↓
WINNER MODE
  ↓
Risk Level 0 / 1 / 2 / 3 / 4
  ↓
HOLD / REDUCE / EXIT
  ↓
FLAT
  ↓
새 Episode
```

핵심 원칙:

> **빨리 참여하되 작게 위험을 건다. 맞으면 비중을 늘린다. 큰 승자는 Core를 오래 보유한다. 그러나 구조가 망가지면 위험 단계에 따라 기계적으로 줄이고, 완전히 깨지면 과거의 성공과 무관하게 EXIT한다.**

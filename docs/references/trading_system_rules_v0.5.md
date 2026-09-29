# 단계형 모멘텀 매매 시스템 룰 v0.5

> 목적: v0.4의 `Regime → Trigger → Location → Risk → Position` 운용 엔진 앞에 **Watchlist / Scanner / Alert 레이어**를 추가해, 아직 보유하지 않은 여러 종목을 지속적으로 감시하고 진입 신호가 발생했을 때만 `PROBE_CANDIDATE` 또는 `BUY_CANDIDATE`로 승격시키는 완결형 연구·조언 시스템을 만든다.
>
> 중요: v0.5는 자동 주문 시스템이 아니다. `Execution Contract`는 **백테스트에서 현실적인 가상 체결을 재현하고, 실제 사용자에게 다음 행동 후보를 제시하기 위한 계약**이다.
>
> 모든 수치 임계값은 `initial test parameter`다. Golden Fixture를 맞추기 위해 사례별로 조정하지 않는다.

---

# 0. v0.5 핵심 변화

v0.4는 **포지션을 가진 뒤 어떻게 관리할 것인가**를 완결했다.

v0.5는 그 앞단을 추가한다.

```text
WATCHLIST
   ↓
DAILY SCANNER
   ↓
WATCH STATE
   ↓
ARMED
   ↓
ENTRY CANDIDATE
   ↓
ALERT
   ↓
NEXT-OPEN EXECUTION CHECK
   ↓
PROBE / CORE
   ↓
POSITION MANAGEMENT
   ↓
WINNER
   ↓
REDUCE / EXIT
```

v0.5의 주요 변경점:

1. `WatchState` 추가 — 미보유 종목의 사전 상태 관리
2. Watchlist 전체를 매일 스캔하는 `Daily Scanner` 정의
3. `ENTRY_CANDIDATE`와 실제 주문 실행을 분리
4. 여러 후보가 동시에 나오면 `Ranking`으로 우선순위 결정
5. `Portfolio Risk Budget`으로 신규 진입 총량 제한
6. `CHASE_WAIT`, `COOLDOWN`, Candidate 만료 규칙 추가
7. Alert / Daily Digest 규칙 정의
8. 기존 Score는 Action 엔진이 아니라 Ranking 전용으로 명시
9. look-ahead 없는 confirmed pivot만 백테스트에 사용
10. 정의가 없는 `POWER_GAP`, `POCKET_PIVOT`은 core trigger에서 비활성화
11. `TREND_ENTRY_TRIGGER`를 제거하고 `CONFIRM_TRIGGER`로 통합
12. KR/US 시장별 실행계약을 `MarketProfile`로 분리

---

# 1. 시스템의 목적과 범위

## 1.1 시스템이 하는 일

- 관심종목 수십~수백 개를 매일 일봉 기준으로 스캔한다.
- 각 종목의 Regime / Trigger / Location / Risk를 계산한다.
- 미보유 종목을 `IGNORE / WATCH / ARMED / ENTRY_CANDIDATE / CHASE_WAIT / COOLDOWN`으로 분류한다.
- 신규 진입 후보만 사용자에게 우선적으로 알린다.
- 실제 진입 후에는 v0.4 방식으로 `PROBE / CORE / FULL / WINNER`를 관리한다.
- 과거 데이터를 이용해 동일 규칙을 Episode 단위로 백테스트한다.

## 1.2 시스템이 하지 않는 일

- 자동 주문 전송
- 뉴스/펀더멘털을 이용한 신호 변경
- 특정 종목의 과거 차트를 맞추기 위한 임계값 튜닝
- 기존 점수 하나로 BUY/ADD/SELL을 직접 결정

---

# 2. 전체 레이어

```text
[1] WATCHLIST
      ↓
[2] DATA / PRIMITIVES
      ↓
[3] TECHNICAL REGIME
      ↓
[4] TRIGGER
      ↓
[5] LOCATION / RISK
      ↓
[6] WATCH STATE
      ↓
[7] ENTRY CANDIDATE
      ↓
[8] RANKING / PORTFOLIO RISK
      ↓
[9] EXECUTION CHECK
      ↓
[10] POSITION STATE
      ↓
[11] MANAGEMENT MODE
      ↓
[12] ACTION / ALERT / LOG
```

핵심 원칙:

> **Score = 어떤 후보를 먼저 볼 것인가**
>
> **State + Trigger + Location + Risk = 매매 자격이 있는가**
>
> **Position + ManagementMode = 실제로 어떤 행동을 할 것인가**

---

# 3. Watchlist

## 3.1 Watchlist의 의미

Watchlist는 현재 보유 여부와 관계없이 지속적으로 분석하고 싶은 종목 집합이다.

예:

```text
PANW
SNOW
BE
HOOD
NVDA
CRWD
PLTR
009150.KS
...
```

## 3.2 Watchlist 종목 상태

각 종목은 다음 정보를 가진다.

```text
ticker
market
watch_enabled
position_state
management_mode
watch_state
last_signal_date
last_entry_candidate_date
cooldown_until
```

보유하지 않은 종목은 기본적으로:

```text
position_state = FLAT
management_mode = NORMAL
```

이다.

---

# 4. Daily Scanner

매 거래일 종가 확정 후 Watchlist 전체에 동일한 순서로 실행한다.

```text
1. Data freshness 확인
2. Primitive 계산
3. Regime 계산
4. Trigger 계산
5. Location 계산
6. Risk 계산
7. WatchState 계산
8. Entry Candidate 생성
9. Setup / Ranking 계산
10. Alert 생성
11. 다음 거래일 실행 후보 저장
```

의사코드:

```text
for ticker in watchlist:
    if not data_is_fresh(ticker):
        mark DATA_STALE
        continue

    features = compute_primitives(ticker)
    regime = compute_regime(features)
    triggers = compute_triggers(features)
    location = compute_location(features)
    risk = compute_risk(features)

    if position_state == FLAT:
        watch_state = compute_watch_state(...)
        candidate = generate_entry_candidate(...)
    else:
        action = manage_open_position(...)
```

---

# 5. WatchState

WatchState는 **아직 사지 않은 종목을 관리하기 위한 상태**다.

```text
IGNORE
WATCH
ARMED
ENTRY_CANDIDATE
CHASE_WAIT
COOLDOWN
```

PositionState와 섞지 않는다.

---

## 5.1 IGNORE

다음과 같은 경우:

```text
regime == BROKEN
```

또는 데이터가 불충분하고 분석 자체가 신뢰되지 않는 경우.

행동:

```text
신규진입 없음
Alert 없음
Daily Digest 하단으로 제외 가능
```

---

## 5.2 WATCH

아직 진입 조건과 거리가 있는 일반 관심 상태.

대표:

```text
regime == WEAK
AND hard_breakdown == false
```

행동:

```text
매일 계속 계산
신규진입 없음
```

---

## 5.3 ARMED

**방아쇠만 기다리는 상태**.

다음 중 하나:

```text
regime == TRANSITION
OR deep_recovery_ready == true
OR regime == TREND
```

단 아직 유효한 Entry Trigger가 없다.

행동:

```text
신규진입 없음
Daily Digest 상단에 표시
Trigger 발생 시 즉시 ENTRY_CANDIDATE 검토
```

---

## 5.4 ENTRY_CANDIDATE

오늘 종가 기준으로 **실제 신규 진입 자격을 얻은 상태**.

종류:

```text
RECOVERY_PROBE_CANDIDATE
NORMAL_PROBE_CANDIDATE
DIRECT_BUY_CANDIDATE
```

이 상태는 **주문 체결이 아니다**.

```text
signal_generated = true
order_executed = false
```

다음 거래일 Execution Contract를 통과해야 실제 PositionState가 바뀐다.

---

## 5.5 CHASE_WAIT

신호 자체는 유효하지만 다음 거래일 가격이 지나치게 멀어진 경우.

```text
ENTRY_CANDIDATE
+
next_open violates chase guard
→ CHASE_WAIT
```

중요:

> CHASE_WAIT에서는 오래된 신호를 나중에 자동 실행하지 않는다.

새로운 정상 진입 구조가 다시 나타나야 한다.

예:

```text
Pullback
Reclaim
New Breakout
```

발생 시 새로운 Candidate를 생성한다.

---

## 5.6 COOLDOWN

최근 진입 Episode가 실패했거나 신호가 빠르게 무효화된 종목의 즉시 재진입을 억제한다.

초기값:

```text
cooldown_days = 5 trading days
```

단 다음과 같은 **명백히 새로운 구조적 Trigger**는 cooldown을 해제할 수 있다.

```text
new_confirmed_breakout_after_new_base
strong_reclaim_after_structural_reset
```

이 override는 반드시 reason code를 남긴다.

---

# 6. Technical Regime

```text
WEAK
TRANSITION
TREND
BROKEN
```

`DEEP_RECOVERY_READY`는 별도 플래그다.

---

## 6.1 BROKEN

최우선.

```text
if hard_breakdown:
    regime = BROKEN
```

---

## 6.2 TREND

다음 중 하나:

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

---

## 6.3 TRANSITION

필수:

```text
close > sma200
AND regime != TREND
AND hard_breakdown == false
```

그리고 3개 개선 그룹 중 2개 이상.

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

---

## 6.4 DEEP_RECOVERY_READY

SMA200 아래에서 시작되는 SNOW형 회복.

```text
close < sma200
AND close > sma20
AND close > sma50
AND sma20_slope > 0
AND higher_low
AND supertrend_up
AND hard_breakdown == false
```

이 플래그만으로 매수하지 않는다.

---

# 7. Trigger 체계

v0.5에서는 Trigger를 역할별로 분리한다.

```text
EARLY_TRIGGER
CONFIRM_TRIGGER
ADD_TRIGGER
```

---

## 7.1 EARLY_TRIGGER

TRANSITION / DEEP_RECOVERY에서 PROBE 후보를 만든다.

**v0.5 core에서 활성화하는 Trigger는 두 개만 사용한다.**

```text
EARLY_BREAKOUT
SMA50_RECLAIM
```

정의가 아직 확정되지 않은 다음 Trigger는 core에서 비활성화한다.

```text
POWER_GAP        = EXPERIMENTAL_DISABLED
POCKET_PIVOT     = EXPERIMENTAL_DISABLED
```

수식이 Primitive Specification에 고정되고 독립 검증된 뒤 추가한다.

### EARLY_BREAKOUT

```text
close[t] > max(high[t-20 : t-1])
AND close[t-1] <= max(high[t-21 : t-2])
```

### SMA50_RECLAIM

```text
close[t-1] <= sma50[t-1]
AND close[t] > sma50[t]
```

Higher Low / Strong Close / Volume은 Trigger 자체가 아니라 Quality attribute다.

---

## 7.2 CONFIRM_TRIGGER

PROBE를 CORE로 승격시키거나, FLAT + TREND 종목의 Direct BUY를 허용한다.

**별도의 `TREND_ENTRY_TRIGGER`는 사용하지 않는다.**

```text
CONFIRMED_BREAKOUT
FOLLOW_THROUGH
STRONG_RECLAIM
TIGHT_PULLBACK_BREAKOUT
```

### CONFIRMED_BREAKOUT

```text
fresh 20D close breakout
AND close >= trigger_day_low
```

### FOLLOW_THROUGH

EARLY_TRIGGER 이후 `probe_confirm_window` 내:

```text
close > early_trigger_close
AND close_location >= follow_through_close_location
AND daily_return > 0
```

### STRONG_RECLAIM

```text
close가 sma20 또는 sma50을 아래에서 위로 회복
AND close_location >= strong_reclaim_close_location
```

### TIGHT_PULLBACK_BREAKOUT

최근 3~10거래일 조정폭이 ATR 기준 축소된 뒤 그 조정구간 고점을 종가로 돌파.

정확한 축소 threshold는 Parameter Registry에서 관리한다.

---

## 7.3 ADD_TRIGGER

이미 CORE/FULL이고 수익 중인 포지션만 사용.

```text
NEW_BASE_BREAKOUT
PULLBACK_BREAKOUT
RECLAIM_AFTER_PULLBACK
CONTINUATION_PIVOT
```

공통 조건:

```text
position_pnl > 0
AND regime == TREND
AND entry_overextended == false
AND hard_risk == false
```

손실 중 물타기 금지.

---

# 8. Trigger Quality / Demand Evidence

Trigger와 Quality를 분리한다.

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

초기 v0.5에서는 Quality를 Action hard gate로 최소화한다.

목적:

```text
Trigger = 사건
Quality = 사건의 질
```

향후 비교:

```text
Breakout 전체
vs Breakout + Strong Close
vs Breakout + Volume Expansion
vs Breakout + Strong Close + Volume Expansion
```

---

# 9. Setup / Ranking

SETUP은 **Action을 결정하지 않는다**.

```text
SETUP = Ranking only
```

기존 invest-jarvis의 `adjusted_score`가 있다면 Action authority를 제거하고 ranking feature로만 사용한다.

후보 ranking feature:

```text
legacy_adjusted_score
Relative Strength
Industry Strength
Tightness
VCP quality
Volume Dry-up
Momentum Persistence
Liquidity
Trigger Quality
Location Quality
```

여러 Entry Candidate가 동시에 발생했을 때 우선순위를 정한다.

예:

```text
A, B, C 모두 BUY_CANDIDATE

→ Ranking A > C > B
→ Risk Budget이 2개만 허용하면 A, C를 우선 검토
```

---

# 10. Entry Candidate 생성

PositionState가 `FLAT`일 때만 신규 Candidate를 만든다.

## 10.1 Recovery Probe Candidate

```text
deep_recovery_ready
AND early_trigger exists
AND hard_risk == false
AND entry_overextended == false
AND watch_state != COOLDOWN

→ RECOVERY_PROBE_CANDIDATE
```

## 10.2 Normal Probe Candidate

```text
regime == TRANSITION
AND early_trigger exists
AND hard_risk == false
AND entry_overextended == false
AND watch_state != COOLDOWN

→ NORMAL_PROBE_CANDIDATE
```

## 10.3 Direct Buy Candidate

```text
regime == TREND
AND confirm_trigger exists
AND hard_risk == false
AND entry_overextended == false
AND watch_state != COOLDOWN

→ DIRECT_BUY_CANDIDATE
```

PROBE는 필수 단계가 아니다.

---

# 11. Candidate Lifecycle

Entry Candidate는 무기한 살아 있지 않는다.

```text
GENERATED
→ EXECUTED
→ EXPIRED
→ CHASE_WAIT
→ INVALIDATED
```

## 11.1 GENERATED

`t` 종가 후 생성.

```text
candidate_date = t
```

## 11.2 EXECUTED

`t+1` 시가에서:

```text
data fresh
AND chase guard OK
AND risk budget available
AND portfolio risk available
```

이면 실행.

## 11.3 CHASE_WAIT

`t+1` 시가가 너무 멀면 실행하지 않는다.

오래된 candidate를 그대로 보관하지 않는다.

## 11.4 EXPIRED

기본 Candidate는 `t+1` 실행 검토가 끝나면 만료한다.

CHASE_WAIT에서 새 진입을 하려면 **새로운 Entry Trigger**가 필요하다.

## 11.5 INVALIDATED

다음 거래일 이전이라도 hard breakdown 또는 구조적 무효화가 확인되면 candidate 취소.

---

# 12. Alert 정책

목적은 알림 과다를 피하면서 중요한 상태변화만 보여주는 것이다.

## 12.1 즉시 Alert

다음 이벤트:

```text
ENTRY_CANDIDATE 생성
CHASE_WAIT 발생
실제 Entry 승인
PROBE 실패/EXIT
PROBE → CORE 승격
WINNER 진입
WINNER Risk Level 변화
BROKEN / EXIT
```

## 12.2 Daily Digest

매일 장 마감 후:

```text
1. ENTRY_CANDIDATE
2. ARMED
3. 기존 Position Action 변화
```

순으로 표시.

WATCH/IGNORE가 변하지 않았으면 반복 알림하지 않는다.

## 12.3 Alert 예시

```text
[BE] NORMAL_PROBE_CANDIDATE
Regime: TRANSITION
Trigger: SMA50_RECLAIM
Volume Ratio: 1.33x
Close Location: 0.89
Distance SMA20: +4.2%
Risk: OK
Next: next-open chase/risk check
```

---

# 13. PositionState / ManagementMode

## 13.1 PositionState

```text
FLAT
PROBE
CORE
FULL
```

## 13.2 ManagementMode

```text
NORMAL
WINNER
```

예:

```text
FULL + WINNER
CORE + WINNER
```

WINNER는 PositionState가 아니다.

---

# 14. Risk Unit과 Position Sizing

## 14.1 1R

초기값:

```text
1R = account_equity * risk_unit_pct
risk_unit_pct = 0.5%
```

검증 대상 파라미터다.

## 14.2 Entry별 Risk Budget

```text
Recovery Probe = 0.25R
Normal Probe   = 0.50R
Direct Buy     = 1.00R
Add            = 0.50R
```

## 14.3 Position Size

```text
risk_per_share = abs(entry_price - effective_stop)
position_value = allocated_risk / stop_distance_pct
```

실제 비중:

```text
actual_size = min(risk_based_size, entry_type_cap)
```

초기 cap:

```text
Recovery Probe max = 15%
Normal Probe max   = 25%
Direct Buy max     = 60%
Total Position max = 100%
```

---

# 15. Portfolio Risk Budget

Watchlist에서 여러 종목이 동시에 신호를 낼 수 있으므로 종목별 Risk만으로는 부족하다.

## 15.1 Open Risk

각 보유 포지션:

```text
open_risk = max(0, entry_or_current_reference - active_stop) * shares
```

포트폴리오 전체:

```text
portfolio_open_risk = sum(open_risk)
```

## 15.2 Portfolio Risk Cap

초기 테스트값:

```text
portfolio_risk_cap_r = 5.0R
```

신규 Candidate 실행 전:

```text
current_open_risk_r
+ candidate_allocated_risk_r
<= portfolio_risk_cap_r
```

이어야 한다.

초과하면:

```text
signal = 유지
order = BLOCKED
reason = PORTFOLIO_RISK_LIMIT
watch_state = ARMED 또는 ENTRY_CANDIDATE_BLOCKED 기록
```

## 15.3 후보가 많을 때

Risk Budget이 부족하면 Ranking 순으로 배정한다.

중요:

> Ranking이 BUY 자격을 만들지는 않는다. 이미 자격을 얻은 후보들의 우선순위만 정한다.

---

# 16. Stop / Invalidation

## 16.1 Structural Stop

Trigger별 구조적 무효화 지점을 계산한다.

### EARLY_BREAKOUT

초기 후보:

```text
min(trigger_day_low, breakout_base_support)
```

### SMA50_RECLAIM

초기 후보:

```text
min(trigger_day_low, sma50 - atr_buffer)
```

세부 buffer는 registry 관리.

## 16.2 Hard Loss Stop

Entry type별 최대 허용 손실 상한:

```text
Recovery Probe: 4%
Normal Probe:   5%
Direct Buy:     7%
```

실제 stop:

```text
effective_stop = tighter(structural_stop, hard_loss_stop)
```

단 최소 stop distance가 지나치게 좁은 경우 entry를 거절할 수 있다.

## 16.3 Time Stop

PROBE가 일정 기간 내 확인되지 않으면 종료.

```text
probe_confirm_window = 10 trading days
```

---

# 17. PROBE Lifecycle

## 17.1 Entry

실제 주문이 실행되면:

```text
position_state = PROBE
watch_state = null / POSITION_OPEN
```

## 17.2 Success

```text
regime == TREND
AND confirm_trigger exists
AND entry_overextended == false
AND hard_risk == false
```

이면:

```text
PROBE → CORE
```

추가 매수 규모는 risk budget으로 계산한다.

## 17.3 Hold

TREND가 아직 확인되지 않았지만 stop/time invalidation도 없으면:

```text
HOLD_PROBE
```

## 17.4 Failure

다음 중 하나:

```text
structural_stop breach
hard_loss_stop breach
hard_breakdown
probe timeout
```

이면:

```text
EXIT
position_state = FLAT
watch_state = COOLDOWN
```

---

# 18. Direct BUY

FLAT 상태에서 이미 TREND인 종목.

```text
regime == TREND
AND confirm_trigger exists
AND entry_overextended == false
AND hard_risk == false
```

다음 거래일 Execution Contract 통과 시:

```text
position_state = CORE
management_mode = NORMAL
```

---

# 19. ADD

ADD 조건:

```text
position_state in [CORE, FULL]
AND position_pnl > 0
AND regime == TREND
AND add_trigger exists
AND entry_overextended == false
AND hard_risk == false
AND portfolio risk available
```

손실 중 ADD 금지.

초기 최대 ADD 횟수:

```text
2
```

FULL에 도달하면 추가 확대 금지.

---

# 20. WINNER Mode

## 20.1 진입

초기 조건:

```text
(position_return >= 20%
 OR position_pnl_r >= 2R)
AND regime == TREND
AND hard_risk == false
```

이면:

```text
management_mode = WINNER
```

---

# 21. WINNER Risk Level / Target Exposure

WINNER에서는 매도 명령을 누적하지 않고 **현재 Risk Level 하나에 대응하는 목표 비중**을 사용한다.

```text
Level 0 → 100%
Level 1 → 85%
Level 2 → 65%
Level 3 → 35%
Level 4 → 0%
```

## Level 0 — Healthy Winner

```text
TREND 정상
가격 진전 유지
hard risk 없음
```

## Level 1 — Climax / Extension

초기 후보:

```text
5D return >= 20%
AND distance_sma20_atr >= 2.5
```

## Level 2 — Short-term Damage

예:

```text
close < sma20 for 2 closes
```

또는:

```text
supertrend_down
AND fast_reclaim_failed
```

## Level 3 — Intermediate Damage

예:

```text
close < sma50 for 2 closes
AND (
    sma20 <= sma50
    OR sma50_reclaim_failed
)
```

## Level 4 — BROKEN

```text
regime == BROKEN
```

## 21.1 다중 경고

가장 높은 Risk Level 하나만 적용한다.

```text
current exposure 100%
Level 1 + Level 2 동시 발생
→ target exposure = 65%
```

---

# 22. WINNER Hysteresis

악화는 빠르게, 회복은 천천히.

```text
Level 0 → 2 가능
Level 2 → 0 직접 복구 금지
```

회복:

```text
Level 3 → 2 → 1 → 0
```

각 단계 회복은:

```text
winner_recovery_confirm_days 동안 안정
+
reclaim 또는 demand trigger
```

를 요구한다.

---

# 23. Market Mode

시장 상태는 개별 종목 Technical Signal을 바꾸지 않는다.

```text
RISK_ON
NEUTRAL
RISK_OFF
```

v0.5 core에서 Market Mode 산식은 아직 실험 대상이다.

사용 방식:

```text
Stock = BUY_CANDIDATE
Market = RISK_OFF

→ BUY_CANDIDATE는 유지
→ 실제 Risk Budget만 축소
```

즉 Market은 **신호 엔진이 아니라 포트폴리오 위험량 조절 레이어**다.

---

# 24. Primitive Specification

백테스트용 primitive는 미래정보를 사용하지 않는다.

## 24.1 ATR14

Wilder ATR14.

## 24.2 close_location

```text
if high > low:
    close_location = (close - low) / (high - low)
else:
    close_location = 0.5
```

## 24.3 volume_ratio20

```text
volume[t] / mean(volume[t-20:t-1])
```

오늘 거래량은 분모에서 제외.

## 24.4 SMA20 slope

```text
sma20_slope = sma20[t] - sma20[t-5]
```

## 24.5 Confirmed Pivot Low — look-ahead safe

pivot 후보 index `i`:

```text
low[i] < min(low[i-3:i])
AND low[i] <= min(low[i+1:i+4])
```

그러나 이 pivot은 **i+3 거래일 종가가 끝난 뒤에만 시스템이 알 수 있다.**

백테스트 시:

```text
pivot_event_date = i + 3
pivot_price_date = i
```

로 분리 저장한다.

기존 `argrelextrema` 결과를 과거 index i에 바로 기록해 신호에 사용하지 않는다.

## 24.6 Confirmed Pivot High

동일 방식으로 미래 3봉 확인 후 event_date에서만 사용 가능.

## 24.7 Higher Low

최근 두 개의 **이미 확정된** Pivot Low를 p1, p2라고 할 때:

```text
p2.low > p1.low
```

## 24.8 valid_sma50_reclaim

```text
최근 reclaim_valid_days 안에
close가 sma50 아래 → 위 cross
AND current close >= current sma50
```

## 24.9 hard_breakdown

다음 중 하나.

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

구조 판정은 confirmed pivots만 사용.

## 24.10 entry_overextended

초기값:

```text
distance_sma20_atr >= 2.5
OR distance_sma20_pct >= 15%
```

---

# 25. Execution Contract

Execution Contract는 자동주문 명세가 아니라 **현실적인 백테스트 가상체결 계약**이다.

## 25.1 Signal Time

일봉 Signal은 시장별 종가 확정 후 계산.

```text
available_data <= t close
```

만 허용.

## 25.2 Entry Time

기본:

```text
signal at t close
→ execution check at t+1 open
```

## 25.3 Chase Guard

```text
next_open > trigger_reference_price * (1 + chase_pct)
→ order_executed = false
→ watch_state = CHASE_WAIT
```

신호는 로그에 남긴다.

## 25.4 Stop Fill

```text
intraday low <= stop
→ fill = stop
```

단:

```text
open < stop
→ fill = open
```

슬리피지는 별도 적용.

## 25.5 비용

```text
commission = configurable
slippage_bps = configurable
```

## 25.6 Corporate Actions

- 기술지표 가격은 split-adjusted 기준 일관성 유지
- 배당 total-return series를 OHLC 기술지표에 섞지 않음

---

# 26. MarketProfile — KR / US

실행계약은 시장별 캘린더와 데이터 확정 시점을 사용한다.

```text
MarketProfile.US
MarketProfile.KR
```

각 profile은 최소:

```text
exchange_calendar
session_close_time
next_session_open_time
data_freshness_rule
price_adjustment_rule
```

를 가진다.

중요:

> KR/US 모두 동일한 상태 머신을 쓰되, “오늘 종가가 확정됐는가 / 다음 거래일은 언제인가”는 시장별로 계산한다.

---

# 27. Episode / Cooldown

Episode:

```text
첫 실제 진입
→ 최종 FLAT 복귀
```

EXIT 후:

```text
position_state = FLAT
management_mode = NORMAL
watch_state = COOLDOWN
```

과거 WINNER였다는 사실은 새 Episode 진입 권한을 주지 않는다.

Cooldown 이후 다시:

```text
WATCH / ARMED
→ 새 Trigger
→ 새 Candidate
```

를 처음부터 밟는다.

---

# 28. 전체 상태 전이

```text
                    [WATCHLIST]
                        │
                        ▼
                  DAILY SCANNER
                        │
                        ▼
              ┌──────────────────┐
              │   WatchState     │
              └──────────────────┘
                        │
        ┌───────────────┼────────────────┐
        │               │                │
      IGNORE          WATCH            ARMED
                                         │
                                         │ Trigger
                                         ▼
                                ENTRY_CANDIDATE
                                         │
                                  t+1 execution
                                  ┌──────┴──────┐
                                  │             │
                               CHASE          EXECUTE
                                  │             │
                            CHASE_WAIT          ▼
                                           PROBE / CORE
                                               │
                         ┌─────────────────────┴────────────────────┐
                         │                                          │
                    invalidation                               confirmation
                         │                                          │
                        EXIT                                      CORE
                         │                                          │
                     COOLDOWN                                    ADD
                                                                    │
                                                                   FULL
                                                                    │
                                                                 WINNER
                                                                    │
                                                     Risk 0→1→2→3→4
                                                                    │
                                                          100→85→65→35→0
                                                                    │
                                                                   EXIT
```

---

# 29. Golden Regression Fixtures

Golden Fixture는 성능 검증이 아니라 **의도한 동작이 코드 변경 후 유지되는지 확인**하는 회귀 테스트다.

## 29.1 PANW — Base → Breakout → Home Run

```text
2/23~4/28  ARMED / BASE BUILD
5/4        아직 BUY 아님
5/7        DIRECT_BUY_CANDIDATE
5/8        CHASE ADD 금지 / HOLD
5월 중순   WINNER 진입
```

핵심 질문:

> 긴 Base에서 너무 일찍 사지 않고 실제 close-confirmed breakout을 잡는가?

## 29.2 SNOW — Deep Recovery Rocket

```text
4/15       DEEP_RECOVERY_WATCH
5/15       RECOVERY_PROBE_CANDIDATE
5/28       CONFIRM / CORE 승격
이후        WINNER
```

핵심 질문:

> SMA200 아래에서 시작되는 홈런을 완전히 놓치지 않는가?

## 29.3 BE — Transition → Probe → Core

```text
8/12       ARMED / no trigger
9/3        NORMAL_PROBE_CANDIDATE
9/4        HOLD_PROBE
9/8        CONFIRM → CORE
```

## 29.4 HOOD — Probe 후 추격 방지

```text
8/13       ARMED / no entry
8/21       NORMAL_PROBE_CANDIDATE
9/3        strong continuation
9/4        overextended → HOLD_PROBE / no chase
9/18       reclaim → CORE 승격 후보
```

## 29.5 삼성전기 Episode #1 — Winner Management

```text
4월        BUY / ADD
4월말      FULL + WINNER
5월말      Level 1 → 85%
6월말      Level 2 → 65%
7월초      Level 3 → 35%
7월중순    Level 4 → EXIT
```

## 29.6 삼성전기 Episode #2 — Signal vs Execution

```text
7/31       WATCH
8/12       ARMED
8/13       NORMAL_PROBE_CANDIDATE
8/14       next open chase → CHASE_WAIT
8/18       no position
9/10       TREND but no confirm trigger → ARMED
9/22       DIRECT_BUY_CANDIDATE
```

---

# 30. Watchlist Regression Tests

v0.5에서 새로 추가되는 회귀 테스트.

## 30.1 No Alert Spam

같은 종목이 WATCH 상태를 10일 유지하면:

```text
10일 연속 즉시 Alert 금지
Daily Digest에서만 상태 유지 표시 가능
```

## 30.2 ARMED → Candidate

```text
TRANSITION + no trigger
→ ARMED

다음날 EARLY_BREAKOUT
→ ENTRY_CANDIDATE
```

## 30.3 Candidate → Chase Wait

```text
ENTRY_CANDIDATE at t close
next open > chase limit
→ no execution
→ CHASE_WAIT
```

## 30.4 Failed Probe → Cooldown

```text
PROBE
→ stop
→ FLAT + COOLDOWN
```

Cooldown 동안 동일한 사소한 reclaim으로 즉시 재진입하지 않는다.

## 30.5 Multiple Candidates

3개 종목이 동시에 Candidate:

```text
A rank 1
B rank 3
C rank 2
```

Risk Budget이 2개만 허용하면:

```text
A, C 우선
B = PORTFOLIO_RISK_LIMIT
```

---

# 31. Parameter Registry v0.5

```yaml
# primitives
atr_period: 14
sma20_slope_lookback: 5
pivot_left: 3
pivot_right: 3
reclaim_valid_days: 5

# entry/location
chase_pct: 0.05
overextended_sma20_pct: 0.15
overextended_sma20_atr: 2.5
follow_through_close_location: 0.60
strong_reclaim_close_location: 0.70

# risk unit
risk_unit_pct: 0.005
recovery_probe_r: 0.25
normal_probe_r: 0.50
direct_buy_r: 1.00
add_r: 0.50
max_position_r: 1.50
portfolio_risk_cap_r: 5.0

# position caps
recovery_probe_cap: 0.15
normal_probe_cap: 0.25
direct_buy_cap: 0.60
max_position_cap: 1.00

# stop / timeout
recovery_probe_hard_stop_pct: 0.04
normal_probe_hard_stop_pct: 0.05
direct_buy_hard_stop_pct: 0.07
probe_confirm_window: 10
cooldown_days: 5

# winner
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

# breakdown
hard_breakdown_volume_ratio: 1.5
hard_breakdown_close_location: 0.25

# experimental trigger flags
power_gap_enabled: false
pocket_pivot_enabled: false
```

모든 숫자는 검증 대상이다.

---

# 32. 로그 스키마

매 거래일 최소 다음을 기록한다.

```text
date
ticker
market

data_fresh

regime
deep_recovery_ready
watch_state

position_state
management_mode
winner_risk_level

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

candidate_type
candidate_date
candidate_rank
candidate_status

signal_generated
signal_type
alert_generated

order_executed
execution_block_reason
entry_price
effective_stop

allocated_risk_r
portfolio_open_risk_r
current_exposure
target_exposure

episode_id
days_in_probe
unrealized_pnl_pct
unrealized_pnl_r

action
reason_codes[]
```

---

# 33. Alert Reason Codes

예:

```text
ARMED_TRANSITION
ARMED_TREND
EARLY_BREAKOUT
SMA50_RECLAIM
CONFIRMED_BREAKOUT
STRONG_RECLAIM
ENTRY_OVEREXTENDED
CHASE_LIMIT
PORTFOLIO_RISK_LIMIT
COOLDOWN_ACTIVE
PROBE_TIMEOUT
STOP_BREACH
WINNER_LEVEL_1
WINNER_LEVEL_2
WINNER_LEVEL_3
BROKEN
DATA_STALE
```

사용자는 Alert만 보고도 왜 후보가 올라왔는지 알 수 있어야 한다.

---

# 34. 검증 순서

## Step 1 — Primitive Unit Test

특히:

```text
confirmed pivot
higher low
SMA50 reclaim
breakout
hard breakdown
overextension
```

미래정보 사용 여부를 검증한다.

## Step 2 — Golden Fixture Regression

PANW / SNOW / BE / HOOD / 삼성전기에서 기대 상태전이가 유지되는지 확인.

## Step 3 — Watchlist State Regression

```text
WATCH → ARMED → CANDIDATE
Candidate → CHASE_WAIT
Failed Probe → COOLDOWN
```

을 테스트.

## Step 4 — Episode Backtest

Entry → Add → Reduce → Exit 전체를 Episode 단위로 평가.

## Step 5 — Scanner Backtest

과거 각 날짜에 Watchlist 전체를 실제로 스캔했다고 가정한다.

중요:

> 미래에 유명해진 종목만 Watchlist에 넣으면 안 된다.

가능하면 당시 시점에서 이용 가능했던 역사적 universe를 사용한다.

## Step 6 — Holdout

Golden Fixture에 쓰지 않은 종목/기간에서 검증.

최소 비교:

```text
Normal Probe vs no-trigger Transition
Recovery Probe vs no-trigger Deep Recovery
Direct Buy vs Trend without trigger
Winner Management vs simple trailing exit
Scanner Candidate vs non-candidate ARMED
```

## Step 7 — Parameter Stability

하나의 최적값이 아니라 넓은 안정 구간을 찾는다.

```text
chase: 3 / 5 / 7%
probe timeout: 5 / 10 / 15
cooldown: 3 / 5 / 10
portfolio risk cap: 3R / 5R / 7R
```

---

# 35. invest-jarvis 적용 원칙

v0.5는 기존 스냅샷 점수 엔진 안에 억지로 끼워 넣지 않는다.

권장 구조:

```text
Providers
   ↓
Shared Technical Primitives
   ├───────────────┐
   │               │
Snapshot Advice    Trading Research Engine
quick_check        Scanner / State Machine
legacy score       Episode / Backtest
   │               │
   └───────┬───────┘
           ↓
        Report / CLI
```

## 35.1 기존 Score

기존 `adjusted_score → action`의 action authority는 v0.5 엔진과 병행할 때 제거한다.

```text
legacy_adjusted_score
→ Ranking / Explanation only
```

v0.5 Action은:

```text
Regime + Trigger + Location + Risk + WatchState/PositionState
```

가 결정한다.

## 35.2 기존 Swing Detector

미래봉을 사용해 과거 pivot index에 신호를 기록하는 detector는 백테스트에 사용하지 않는다.

표시용으로 남길 수 있지만 Research Engine은 look-ahead-safe confirmed pivot을 사용한다.

## 35.3 목적

v0.5의 1차 목적:

```text
규칙 검증 + 스캐닝 + 조언
```

자동 주문은 범위 밖이다.

---

# 36. v0.5에서 아직 하지 않는 것

```text
실제 자동주문
Market Mode 최종 산식
Sector RS hard gate
Fundamental hard gate
News sentiment hard gate
Options flow
ML scoring
Power Gap 활성화
Pocket Pivot 활성화
Intraday execution optimization
Portfolio correlation model
```

이들은 core 룰이 독립적으로 검증된 후 추가한다.

---

# 37. 최종 운영 예시

Watchlist 100개가 있다고 가정.

## 장 마감 후

```text
100개 Scan

3개 ENTRY_CANDIDATE
12개 ARMED
55개 WATCH
30개 IGNORE
```

사용자에게:

```text
[ENTRY]
1. NVDA — DIRECT_BUY_CANDIDATE
2. BE   — NORMAL_PROBE_CANDIDATE
3. SNOW — RECOVERY_PROBE_CANDIDATE

[ARMED]
PANW, CRWD, HOOD ...
```

## 다음 거래일

```text
NVDA open → chase OK → BUY 승인
BE open   → chase OK → PROBE 승인
SNOW open → +9% gap → CHASE_WAIT
```

## 이후

```text
BE confirmation 발생
→ PROBE → CORE

NVDA +20% & trend healthy
→ WINNER

SNOW pullback 후 new reclaim
→ 새 Candidate 생성
```

---

# 38. v0.5 한 문장

> **v0.5는 관심종목을 계속 감시하다가 `준비됨(ARMED) → 실제 신호(ENTRY_CANDIDATE) → 현실적인 다음날 가격 확인 → 작은 시험 또는 본매수 → 확인되면 확대 → 큰 승자는 오래 보유 → 망가지면 단계적으로 축소`까지 전체 생명주기를 하나의 상태 머신으로 연결한 시스템이다.**

---

# 39. 가장 중요한 운영 원칙

```text
1. 안 산 종목도 매일 동일하게 계산한다.
2. WATCH와 ARMED를 구분한다.
3. 신호와 체결을 구분한다.
4. Score는 후보 순위만 정한다.
5. 여러 후보가 뜨면 Portfolio Risk Budget 안에서만 산다.
6. PROBE는 실패/시간초과가 있다.
7. WINNER는 100→85→65→35→0으로 위험에 맞춰 관리한다.
8. EXIT 후에는 새 Episode로 완전히 초기화한다.
9. 미래정보가 필요한 pivot을 과거 시점에 당겨 쓰지 않는다.
10. Golden Fixture는 회귀검사일 뿐 성능 증명이 아니다.
```

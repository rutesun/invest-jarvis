# Technical Scoring Redesign 설계 스펙

- **작성일**: 2026-07-16
- **상태**: Draft v2 (사용자 승인 + subagent review + reason/score trend 반영)
- **대상**: `jarvis check`, `analyze`, `brief`에서 쓰는 기술 점수의 신뢰도 개선
- **범위**: raw OHLCV 별도 점수 추가 없이 `MarketContext + ScoreAggregator + technical verdict`로 기존 component 점수를 재해석

---

## 1. 배경과 문제

현재 `TechnicalScorer`는 component analyzer를 실행한 뒤 component 점수를 단순 합산해 `total_score`를 만든다.

```text
minervini + velocity + crsi + volume + patterns + supertrend + divergence + risk
= total_score
```

이 구조는 빠르고 설명하기 쉽지만, 실전 판단에서는 세 가지가 섞인다.

- 추세가 강한가
- 지금 새로 사기 좋은가
- 이미 많이 올라 보유만 해야 하는가

예를 들어 같은 90점이라도 `PANW 2026-04-30`은 좋은 추가매수 신호였고, 급등 후 고점권의 90점은 신규 추격 매수가 아니라 보유 관리 신호일 수 있다. 따라서 문제는 "점수가 항상 틀린 것"이 아니라 "점수의 행동 의미가 분리되지 않은 것"이다.

## 2. 목표

1. 별도 raw OHLCV score를 만들지 않는다.
2. raw OHLCV는 `MarketContext`라는 상태 정보로만 쓴다.
3. 기존 component 점수는 유지하되, context에 따라 cap, penalty, override를 적용한다.
4. user-facing 출력은 `adjusted_score`와 `technical_verdict`를 중심으로 한다.
5. `technical_verdict`는 technical-only hint로 한정하고, 최종 포지션 판단은 `playbook`이 맡는다.

## 3. 비목표

- LLM으로 점수를 판단하지 않는다.
- 계좌 비중, 현금, 포지션 사이징을 technical scorer에 넣지 않는다.
- `playbook`의 최종 매매 판단 책임을 technical scorer로 가져오지 않는다.
- 산식을 한 번에 최적화하지 않는다. 먼저 구조와 테스트를 만든 뒤 성과 기반으로 가중치를 조정한다.

## 4. 핵심 설계

### 4.1 데이터 흐름

```text
OHLCV
  -> IndicatorCalculator
  -> MarketContext
  -> component analyzers
  -> ScoreAggregator
  -> TechnicalResult
       - component_raw_total
       - adjusted_score
       - technical_verdict
       - score_history
       - score_history_warning
       - aggregation_trace
```

`component_raw_total`은 기존 단순합이다. 디버그와 회귀 비교를 위해 남긴다.

`adjusted_score`는 context cap, penalty, override가 반영된 user-facing 기술 점수다.

`technical_verdict`는 가격/거래량 기준의 기술적 행동 힌트다. 예: `buy`, `add`, `hold`, `watch`, `reduce`, `avoid`. 이 값은 보유 여부를 직접 판단하지 않는다. `add`는 "보유자가 있다면 추가매수 후보"라는 기술적 힌트이며, 실제 보유 여부는 `playbook`이 판단한다.

`score_history`는 최근 N거래일의 점수와 verdict 흐름이다. 기본값은 5거래일이며, 각 날짜의 값은 해당 날짜까지의 OHLCV만 사용해 계산한다. 이력은 "오늘 점수가 높은가"보다 "점수가 개선되는 중인가, 악화되는 중인가"를 보여주기 위한 보조 정보다.

### 4.2 MarketContext

`MarketContext`는 점수가 아니다. 원천 OHLCV에서 만든 판정용 상태 묶음이다.

예상 필드:

```text
close_above_sma20
close_above_sma50
close_above_sma150
close_above_sma200
sma20_above_sma50
ret_5d
ret_10d
distance_from_20d_high_pct
distance_from_sma20_pct
distance_from_sma50_pct
volume_ratio_20d
rsi
atr_pct
supertrend_direction
is_overextended
is_breakdown
is_uptrend
is_downtrend
```

필드는 `IndicatorSnapshot`의 원천값을 복사하는 데 그치지 않고, scoring rule에서 바로 쓰는 boolean/ratio 중심으로 둔다.

### 4.3 Component Signal Metadata

Aggregator가 문자열 signal을 파싱하면 깨지기 쉽다. component는 기존 `signals`, `evidence`, `metrics`, `score`를 유지하되, 구조화 metadata를 추가한다.

예상 필드:

```text
signal_type: breakout | pullback | reversal | breakdown | overextension | support | resistance
bias: bullish | bearish | neutral
intent: entry | hold | risk | watch
severity: low | medium | high
entry_eligible: true | false
```

예:

```text
cRSI oversold in uptrend
  signal_type: pullback
  bias: bullish
  intent: entry
  entry_eligible: true

cRSI oversold in downtrend
  signal_type: reversal
  bias: neutral
  intent: watch
  entry_eligible: false
```

## 5. Aggregator Rules

### 5.1 기본 원칙

Aggregator는 점수를 다시 만드는 역할이 아니다. component 점수를 context에 맞게 조정한다.

```text
adjusted_score =
  component_raw_total
  + context_adjustments
  + risk_overrides
  + extension_penalties
```

### 5.2 Cap Rules

반전 신호는 하락 추세에서 매수 점수를 크게 올릴 수 없다.

```text
if context.is_downtrend and signal_type == reversal:
    contribution_cap = watch_level
```

예:

- 하락 추세의 cRSI 과매도
- 하락 추세의 bullish divergence
- Supertrend 하락 중 candlestick reversal

이 신호들은 `watch` 이유가 될 수 있지만, 단독으로 `buy`를 만들면 안 된다.

### 5.3 Extension Rules

과열은 종목을 나쁘게 보는 신호가 아니다. 신규 진입을 제한하는 신호다.

예상 조건:

```text
rsi >= 75
ret_5d >= 15%
ret_1d >= 8%
price far above supertrend line
distance_from_sma20_pct too high
```

결과:

```text
trend score remains positive
new_entry_allowed = false
technical_verdict = hold
```

### 5.4 Risk Override Rules

일부 리스크는 단순 감점보다 action 제한으로 처리한다.

예상 override:

```text
SMA50 하향 이탈 + 거래량 증가
Supertrend sell transition
20일 저점 이탈 + 거래량 증가
close below SMA20 and SMA50 with negative 10d momentum
```

결과:

```text
technical_verdict = reduce or avoid
new_entry_allowed = false
```

Risk override의 우선순위는 다음과 같다.

1. volume-backed breakdown
2. Supertrend sell transition
3. SMA50 break
4. support break

## 6. Technical Verdict

`technical_verdict`는 technical-only hint다. 계좌 상태, 기존 보유 여부, position sizing은 판단하지 않는다.

| Verdict | 의미 |
|---|---|
| `buy` | 신규 진입 가능 |
| `add` | 기존 추세에서 추가매수 가능 |
| `hold` | 추세는 좋지만 신규 진입보다 보유 관리 |
| `watch` | 관심 유지, 확인 신호 필요 |
| `reduce` | 비중 축소 고려 |
| `avoid` | 신규 매수 금지 |

`playbook`은 이 hint를 입력으로 참고할 수 있지만, 최종 매매 판단의 상위 계층으로 남는다.

### 6.1 Reason 출력

`technical_verdict`는 최종 기술 판단의 이유를 구조화해서 가진다.

예상 필드:

```text
action
entry_mode
confidence
new_entry_allowed
reasons: list[str]
cautions: list[str]
invalidation_level
score_trend_summary
```

`reasons`는 최종 action을 만든 핵심 이유 3-5개만 담는다. component별 evidence 전체를 복사하지 않는다. 예를 들어 "20일선 위에서 pullback 신호가 발생했고 거래량이 평균 이상"처럼 사용자가 행동 의미를 바로 이해할 수 있는 문장으로 만든다.

`cautions`는 판단을 약하게 만드는 조건이다. 예를 들어 `adjusted_score`가 높아도 `is_overextended`가 true라면 "추세는 강하지만 5일 수익률 과열로 신규 진입 제한"을 cautions에 넣는다.

`invalidation_level`은 technical verdict가 틀렸다고 봐야 하는 가격 기준이다. 예를 들어 buy/add verdict에서는 최근 지지선, SMA20/SMA50, breakout base 하단 중 가장 설명 가능한 값을 사용한다. 명확한 기준이 없으면 값을 만들지 않고 `null`로 둔다.

`score_trend_summary`는 최근 5거래일의 변화 방향을 한 문장으로 요약한다. 예: "최근 5거래일 adjusted score는 42 -> 58로 개선됐지만, 마지막 2일은 거래량 둔화로 정체".

### 6.2 최근 5거래일 점수 추이

`score_history`는 ticker 분석 결과에 함께 표시한다.

예상 모델:

```text
ScoreHistoryPoint
  date
  close
  component_raw_total
  adjusted_score
  verdict_action
  one_line_reason
```

계산 방식:

1. 동일 OHLCV dataframe을 사용한다.
2. 최근 거래일 5개를 선택한다.
3. 각 날짜 `d`에 대해 `df.loc[:d]`만 scorer에 넣는다.
4. 해당 날짜의 `component_raw_total`, `adjusted_score`, `technical_verdict.action`을 저장한다.
5. `one_line_reason`은 그 날짜의 verdict reason 중 가장 중요한 1개만 사용한다.

추가 API 호출은 하지 않는다. 이미 내려받은 OHLCV 범위가 부족해 5개를 만들 수 없으면 가능한 날짜만 표시한다. 이력 계산 중 특정 날짜만 실패하면 전체 분석을 실패시키지 않고 `score_history_warning`에 원인을 남긴다.

## 7. Downstream 영향

### 7.1 `total_score` 계약

현재 테스트와 downstream 코드는 `total_score == sum(component scores)`를 전제로 한다. Aggregator 도입 시 이 계약을 명확히 바꾼다.

권장 모델:

```text
component_raw_total: int
adjusted_score: int
total_score: int  # compatibility 기간에는 adjusted_score alias 또는 deprecation policy 필요
aggregation_trace: list
```

1차 구현에서는 `total_score`를 바로 바꾸지 않고 `adjusted_score`를 추가하는 방식이 안전하다. 이후 downstream을 모두 이전한 뒤 `total_score` 의미를 재정의한다.

### 7.2 `analyze_decision`

`analyze_decision`은 현재 `abs(total_score) >= 100/40`와 부호로 technical factor 역할을 판단한다. Aggregator 결과를 쓰려면 다음 중 하나를 선택해야 한다.

- `adjusted_score` 기준으로 임계값 재조정
- `technical_verdict`를 직접 입력으로 사용

추천은 `technical_verdict`를 우선하고, 점수는 magnitude 보조값으로 쓰는 방식이다.

### 7.3 `quick_check`, `deep_dive`, `brief`

`quick_check` 출력에는 다음 필드를 추가한다.

```text
adjusted_score
technical_verdict.action
technical_verdict.entry_mode
technical_verdict.confidence
technical_verdict.reasons
technical_verdict.cautions
technical_verdict.invalidation_level
technical_verdict.score_trend_summary
score_history
score_history_warning
```

`deep_dive`와 `brief` LLM에는 component list뿐 아니라 verdict, aggregation trace, score history를 넘긴다. LLM은 점수를 재판단하지 않고, rule output으로 확정된 verdict와 최근 점수 흐름을 자연어로 설명한다.

## 8. 테스트 전략

### 8.1 Synthetic Fixture

필수 fixture:

1. `uptrend_pullback`: 상승 추세의 cRSI 과매도는 entry 가능
2. `downtrend_oversold`: 하락 추세의 cRSI 과매도는 watch만 가능
3. `supertrend_up_overextended`: 추세는 강하지만 신규 매수 제한
4. `bullish_divergence_downtrend`: 반전 신호만으로 buy 불가
5. `sma50_break_volume_breakdown`: risk override로 reduce/avoid

### 8.2 Real Regression Fixture

실제 OHLCV CSV를 fixture로 저장해 회귀를 고정한다.

대상:

- `PANW 2026-04-21..2026-05-14`
- `BE 2026-06-01..2026-07-15`
- `005930.KS 2026-06-01..2026-07-16`

기대 동작:

```text
PANW 2026-04-22: action=buy, entry_mode=breakout_entry, confidence high
PANW 2026-04-30: action=add, entry_mode=pullback_add, confidence high
BE 2026-06-18: hold, new_entry_allowed false
BE 2026-06-26: reduce or avoid
005930.KS 2026-07-02: reduce or avoid
```

### 8.3 Contract Tests

- `component_raw_total`은 기존 component 합과 같아야 한다.
- `adjusted_score`는 Aggregator rule을 반영해야 한다.
- `technical_verdict`는 playbook final verdict가 아니라 technical-only hint여야 한다.
- Aggregator는 string signal을 파싱하지 않고 metadata를 사용해야 한다.
- `score_history`의 과거 날짜 값은 해당 날짜 이후 OHLCV를 바꿔도 변하지 않아야 한다.
- `technical_verdict.reasons`는 component evidence 전체가 아니라 최종 action을 설명하는 핵심 이유여야 한다.

## 9. 구현 단계

1. `MarketContext` 모델과 builder 추가
2. `ComponentSignal` metadata 모델 추가
3. component analyzer에 metadata 추가, 기존 score는 유지
4. `ScoreAggregator` 추가
5. `TechnicalVerdict`에 `reasons`, `cautions`, `invalidation_level`, `score_trend_summary` 추가
6. `ScoreHistoryPoint` 모델과 최근 5거래일 rolling score 계산 추가
7. `TechnicalResult`에 `component_raw_total`, `adjusted_score`, `technical_verdict`, `score_history`, `score_history_warning`, `aggregation_trace` 추가
8. `quick_check` 출력에 verdict reason과 5거래일 점수 추이 추가
9. `deep_dive`와 `brief` 설명 입력에 verdict reason과 score history 추가
10. `analyze_decision` 입력을 adjusted score/verdict 기준으로 이전
11. synthetic fixture 테스트 추가
12. real regression fixture 테스트 추가

## 10. 승인된 설계 결정

| 결정 | 내용 |
|---|---|
| D1 | raw OHLCV 별도 점수는 만들지 않는다 |
| D2 | raw OHLCV는 `MarketContext` 상태로만 쓴다 |
| D3 | 기존 component 점수는 유지하고 Aggregator에서 context를 반영한다 |
| D4 | `ActionVerdict`는 technical-only hint로 제한한다 |
| D5 | playbook은 최종 매매 판단의 상위 계층으로 유지한다 |
| D6 | `total_score` 계약 변경은 단계적으로 진행한다 |
| D7 | string signal 파싱 대신 구조화 metadata를 도입한다 |
| D8 | ticker 분석에는 최종 판단 이유와 최근 5거래일 점수 추이를 함께 표시한다 |

## 11. ADR 후보

- `TechnicalScorer`의 단순합 계약을 `component_raw_total + adjusted_score + technical_verdict` 구조로 확장
- technical verdict와 playbook verdict의 책임 경계

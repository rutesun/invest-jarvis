# Trading Observation Model v1 — 최종 실행 지시에 대한 추가 피드백

- 작성일: 2026-10-20
- 검토 대상: 「Trading Observation Model v1 최종 피드백 및 실행 지시」
- 대상 독자: 프로젝트 코드와 이전 대화에 접근할 수 없는 설계 작성 에이전트
- 목적: 기존 결정은 유지하고, 최근 대화와 충돌하는 요구 및 실행 전 미정 사항을 보완한다.
- 문서 성격: 전달용 리뷰 피드백. 이 문서 작성으로 코드 구현이나 실험이 완료된 것은 아니다.

## 1. 요청 요약

최신 설계는 이전 리뷰를 대부분 반영했다. 전체 구조나 vocabulary를 다시 논의할 필요는 없다.

다음 네 항목을 반영해 수정된 명세와 구현 계획을 작성해 달라.

1. Signal ID의 버전 간 영구 보존 요구를 완화한다.
2. Prior Trend 자격 조건과 현재 SMA slope의 역할을 명확히 한다.
3. Observation detector의 구현 가능성과 미래 매매 효용의 검증 상태를 구분한다.
4. Calibration의 입력·표본·비교 기준·선택 절차를 실행 전에 고정한다.

이하의 현행 사실은 코드를 확인한 구현 측에서 제공하는 배경이다. 저장소에 직접 접근해야만 답할 수 있는 요청으로 바꾸지 말고, 부족한 사항은 필요한 결정으로 표시해 달라.

## 2. 유지할 결정과 필요한 시스템 배경

### 2.1 유지할 결정

- Technical Evidence → Observation → Signal → EntryOpportunity → PositionPlanner의 책임 경계.
- 고정된 Observation v1 vocabulary. 새로운 top-level code를 임의로 추가하지 않는다.
- EVENT와 EPISODE의 구분 및 EPISODE별 시작·유지·종료·재발생 계약.
- pivot_date와 confirmed_on의 분리. Observation 발생 시점은 당시 확인 가능한 날짜다.
- source-independent Observation은 진입 Signal 없이도 계산한다.
- terminal 이후에도 reclaim이라는 차트 사실은 표시할 수 있다. 과거 Opportunity는 부활하지 않는다.
- 기존 source-specific Shadow Risk Level은 유지한다. 새 Observation 개수로 global Risk Level을 만들지 않는다.
- Observation 추가와 Pullback 전략 변경은 서로 다른 변경으로 검증한다.
- 실시간 PROVISIONAL 결과를 허용하며, 종가에서 소멸한 장중 후보를 FINAL history에 고정하지 않는다.

### 2.2 재계산과 보유 정보

Strategy는 차트를 분석할 때 과거 Signal과 Observation도 다시 계산한다. 저장된 Signal ID나 실제 매매장부를 읽어서 전략 상태를 복원하지 않는다. Strategy DB는 이번 작업의 요구사항이 아니다.

동일한 차트·finality·계산 버전·설정에서는 같은 결과가 재현되어야 한다. 실제 보유·계좌 정보는 PositionPlanner에서 행동·수량 계획에 사용한다. 가상 매매와 미래 성과는 Backtest / Research Evaluation에 둔다.

현재 EntryOpportunity는 상단 확장 +5%, age 20거래봉 설정과 기존 시장 gate를 사용한다. 명시적 invalidator는 SMA150_EXIT와 OVERHEAT_CORRECTION이다. 이번 추가 피드백은 이 정책을 바꾸자는 요청이 아니다.

## 3. 수정 요청 1 — Signal ID 영구 보존을 필수 조건에서 제외

관련 절: §17 Observation isolation, §25 parameter/version 분리.

### 3.1 최근 대화에서 정리한 내용

Signal ID는 특정 전략·종목·거래일·신호 종류·계산 설정의 신호를 식별한다. 프로그램 실행마다 새 난수 ID를 발급하는 방식은 아니다.

동일한 과거 Signal은 재계산해도 같은 설정에서는 같은 ID를 받는다. 계산 버전이나 설정이 달라졌을 때까지 과거 ID를 영구 보존할 필요는 없다.

현재 구현은 전략 parameter 전체의 fingerprint를 Signal ID에 포함한다. 따라서 관찰용 설정을 같은 parameter 묶음에 추가하면 ID가 달라질 수 있다. 하지만 차트에서 전체를 재계산하는 구조에서는 이 사실만으로 매매 판단이 잘못되지는 않는다.

초기 리뷰에서 이 문제의 중요도를 높게 잡았다. 최근 대화에서는 버전 변경에 따른 ID 변경 자체를 구현 차단 사유로 두지 않기로 정리했다.

### 3.2 원문 수정 요청

§25의 다음 요구를 절대 조건으로 두지 말아 달라.

```text
Observation 설정 변경만으로 기존 Signal ID가 변하지 않도록 한다.
```

다음 수준으로 바꿔 달라.

```text
동일 차트·finality·계산 버전·설정에서는 Signal ID를 재현한다.

버전/설정이 변경되면 Signal ID는 달라질 수 있다.
버전을 넘어 기존 ID를 영구 보존할 의무는 없다.

과거 연구 결과를 비교할 때 계산 버전과 설정을 구분한다.
실행 중에는 EntryOpportunity와 그 source Signal 등 연결 관계가 일치해야 한다.
```

Observation 전용 설정을 Production 설정과 분리하는 설계는 책임 분리 차원에서 유지할 수 있다. 다만 ID 영구 보존만을 위한 변환 계층·호환 alias·별도 상태 저장은 요구하지 않는다.

§17의 isolation test는 유지한다. 같은 Production 계산 버전·설정에서 Observation 기능만 ON/OFF했을 때 기존 매매 판단과 연결 관계가 동일한지 검증하는 것이다. 서로 다른 전략 버전까지 ID가 같아야 한다는 요구와 구분해 달라.

## 4. 수정 요청 2 — Prior Trend와 현재 slope의 역할을 구체화

관련 절: §13 Prior Trend Context, §15 MA 정배열, §16 reversal confirmation, §18 ALAB 유형.

### 4.1 현재 설계에서 확정된 방향

현재 Supertrend UP과 완전한 SMA 정배열을 PULLBACK_WATCH 시작의 필수조건에서 제거한다. 대신 과거 상승 맥락과 현재 지지 테스트를 확인하고, 현재 구조 손상은 Evidence로 보여준다.

이 방향은 유지한다. 이전 Supertrend gate만 제거하던 범위보다 넓어진 전략 변경임을 명시한다.

### 4.2 현행 구현에서 주의할 조건

기존 Watch 시작 조건에는 다음 세 묶음이 모두 있다.

```text
현재 SMA50 > SMA150 > SMA200
현재 SMA50·SMA150·SMA200의 21봉 slope가 모두 양수
현재 Supertrend UP
```

정배열과 Supertrend 조건을 제거하더라도 모든 slope 양수 조건이 그대로 남으면 깊은 눌림을 계속 놓칠 수 있다.

원안은 slope deterioration도 현재 위험 맥락으로 표시한다고 설명하므로, 다음 질문에 명시적으로 답해 달라.

```text
현재 SMA slope가 하락해도
과거 상승 맥락 + 의미 있는 지지 테스트가 성립하면
PULLBACK_WATCH를 허용하는가?
```

현재 slope는 설명 정보로 두고, 과거 상승 맥락의 자격 조건을 별도로 정의하는 방향을 권한다. 장기 추세 조건 일부를 필수로 유지하려면 대상 SMA·lookback·이유를 명시해 달라. 이 권고를 이미 확정된 세부 공식으로 간주하지 않는다.

### 4.3 구현 전 확정할 계약

| 항목 | 필요한 명세 |
|---|---|
| Prior Trend 관측 범위 | 얼마나 최근의 상승 맥락까지 인정하는가 |
| 자격 계산 | 어떤 가격·이평선·추세 조건을 언제 충족했어야 하는가 |
| source 필요 여부 | 과거 진입 Signal이 없는 종목도 가격 구조로 자격을 얻을 수 있는가 |
| 현재 손상 | 정배열·slope·Supertrend 중 어떤 것은 Evidence이고 어떤 것은 실제 제한인가 |
| Watch 유지·종료 | 지지 이탈·기간 초과·추세 맥락 노후화 시 어떻게 처리하는가 |
| Exit와의 관계 | SMA150_EXIT 발생일 또는 이후 SMA200 지지 관찰을 허용하는가 |
| 같은 날 사건 우선순위 | exit와 reversal 조건이 동시에 성립하면 Observation·Signal·Opportunity를 어떻게 처리하는가 |

이 피드백은 “과거 진입 Signal 필수”를 새로운 자격 조건으로 추가하라는 뜻이 아니다. source를 eligibility의 한 방법으로 쓸 수는 있지만, source가 없는 상승 종목의 취급을 명시해야 한다.

현재 reversal high lookback은 1봉이다. 별도 선택 없이 2봉 등으로 바꾸지 말고, 지지 유지 + 이전 고가 돌파라는 반등 확인과 PROVISIONAL 허용을 유지한다.

Watch 후보가 늘면 후속 Signal 및 EntryOpportunity·PositionPlanner 결과도 달라질 수 있다. support touch만으로 Signal을 만들지 않는다는 원칙과 실제 전략 영향이 없다는 주장은 구분해 달라.

## 5. 수정 요청 3 — 관찰 사실의 구현과 매매 효용 검증을 분리

관련 절: §19~24 calibration과 detector 채택.

소규모 calibration experiment는 유지한다. 다만 다음 두 질문은 별도로 평가해 달라.

```text
A. 이 detector가 이름에 맞는 차트 사실을 재현 가능하게 감지하는가?
B. 그 사실 이후 수익률·위험·후속 Signal에 유용한 차이가 있는가?
```

예를 들어 거래량이 기준의 1.5배이고 가격이 전일보다 올랐다는 사실은 계산할 수 있다. 그 후 수익률이 좋지 않다는 이유만으로 UP_VOLUME_EXPANSION이라는 사실까지 미구현으로 둘 필요는 없다.

반면 MOMENTUM_DECELERATION처럼 의미에 맞는 재현 가능한 공식 자체를 정하지 못한 경우에는 detector를 UNRESOLVED로 둘 수 있다.

### 요청하는 상태 구분

다음은 개념 구분 예시이며 새 enum 이름을 강제하는 것은 아니다.

| 상황 | Detector 구현 | 미래 매매 효용 |
|---|---|---|
| 사실을 안정적으로 감지하고 outcome 차이도 관측됨 | 구현 가능 | 연구 결과를 증거 수준과 함께 보고 |
| 사실은 안정적으로 감지하지만 outcome 우위 불명확 | 구현 가능 | UNRESOLVED 또는 우위 미확인 |
| 의미에 맞는 계산식을 정하지 못함 | UNRESOLVED 가능 | 별도 판단 불가 |
| 데이터 부족으로 계산하지 못함 | 미평가·부족 사유 표시 | Observation 부재나 무효용으로 단정하지 않음 |

§24의 “fold별 미래 수익률 방향이 불안정하므로 detector 미구현”은 일률적으로 적용하지 말아 달라. 구현 불확실성과 predictive usefulness 불확실성을 구분해야 한다.

POSITIVE / RISK는 해당 차트 구조의 해석 방향을 나타낸다. 이를 모든 표본에서 미래 수익률의 부호를 보장하는 표지로 사용하지 않는다.

미래 수익률을 보고 그때그때 관찰 정의를 바꾸는 방식도 피한다. 감지 의미와 계산 후보를 먼저 고정하고, 미래 outcome은 별도 결과로 보고한다. 매매 규칙 승격은 여전히 별도 검증이다.

## 6. 수정 요청 4 — Calibration의 최소 실험 계약을 먼저 고정

관련 절: §20 후보 공식, §21 지표, §22 선택 기준, §30 최종 보고서.

소규모 실험에 필요한 최소 정의를 먼저 작성해 달라. 대규모 최적화나 새로운 연구 플랫폼을 요구하는 것은 아니다.

### 6.1 입력·후보·분할

- 사용 종목과 선정 기준, 기간, 필요한 차트·benchmark 데이터.
- 비교할 formula·threshold 목록과 최대 후보 수.
- 시간순 development / validation 분할과 평가에 필요한 미래 구간의 경계 처리.
- 이전에 결과를 확인한 데이터는 새로운 미관측 검증 구간으로 표현하지 않는다.
- validation 결과를 보고 후보를 다시 고르면 그 구간은 더 이상 독립 검증이 아님을 명시한다.

### 6.2 비교 기준과 표본 단위

- 수익률의 비교 기준을 정한다. 예를 들어 같은 종목·유사한 시장 맥락의 비발생 구간 또는 적절한 benchmark를 사용할 수 있다.
- 강세장에서 Observation 후 수익률이 양수라는 사실만으로 detector의 추가 효용을 주장하지 않는다.
- EVENT는 확인 사건을 기준으로 집계한다.
- EPISODE는 시작 사건을 기본 단위로 삼는지, 매일 상태를 별도 분석하는지 구분한다. 연속 ACTIVE 날짜들을 독립 사건처럼 집계하지 않는다.
- 반복 사건과 서로 겹치는 10/20/40/60봉 outcome의 의존성을 설명한다. 최소한 사건 수·종목 수·episode 수를 구분해 보고한다.

### 6.3 Outcome 정의

- 관찰 날짜와 기준가격을 정한다. 관찰일 종가 기준의 연구 수익률과 다음 시가 가상 체결 수익률을 구분한다.
- MFE·MAE의 기간, 가격 기준과 당일 봉 포함 여부를 명시한다.
- future entry Signal의 대상 종류·기간·전략 버전을 정한다.
- future winner의 threshold와 기간을 결과 확인 전에 정한다. 정의하기 어렵다면 이번 실험에서 제외한다고 명시한다.
- 60봉이 지나지 않은 최근 사건은 60봉 미성숙 표본으로 처리한다. 수익률 0이나 실패로 대체하지 않는다.
- 각 horizon에 이용 가능한 표본 수와 제외 사유를 보고한다.

### 6.4 선택과 해석

- 안정적인 감지 의미·빈도·인접값의 결과를 우선 보고하고 최고 수익률 숫자 하나를 고르지 않는다.
- 표본이 적거나 결과가 불안정하면 해당 불확실성을 유지한다.
- 사실 감지를 위한 v1 기본값 선택과 매매 효용 입증은 별도 결론으로 쓴다.
- 연구 결과나 선택된 Observation 기본값을 Production BUY/EXIT gate로 자동 승격하지 않는다.

## 7. 구현 및 검증을 나눌 기준

다음 두 작업 구분은 유지해 달라.

| 작업 | 검증 기준 |
|---|---|
| A. Observation 모델·detector·출력 추가 | 같은 Production 설정에서 기존 Signal·Opportunity·Position action에 영향 없음. 새 관찰 결과만 추가 |
| B. Pullback Watch 정책 변경 | 의도한 Watch·후속 Signal 차이를 비교하고 downstream Opportunity·Position action 영향까지 확인 |

다음 대표 입력은 구현 계획의 수용 테스트에 포함해 달라.

```text
과거 상승 맥락 있음
+ 현재 SMA150 지지 테스트
+ Supertrend DOWN
+ 정배열 일부 손상 또는 현재 SMA slope 일부 하락
+ 반등 미확인
→ 허용된 새 자격 조건 아래 WATCH와 위험 Evidence 표시
→ support touch만으로 진입 Signal 생성 금지

이후 지지 유지 + 반등 확인
→ 새로운 진입 Signal을 해당 정책으로 평가

과거 source가 FINAL terminal
+ 해당 frozen level reclaim
→ 회복 Observation 표시 가능
→ 과거 Opportunity는 terminal 유지
```

## 8. 요청하는 다음 회신

문서 전체의 원칙을 다시 토론하기보다 다음을 제공해 달라.

1. §25 및 관련 검증 문구의 수정안. 버전 간 ID 영구 보존과 동일 설정 재현성을 구분할 것.
2. Prior Trend·현재 slope·Watch 유지/종료·exit/reversal 우선순위의 구체적 계약. 새 제안은 미확정임을 표시할 것.
3. Observation 감지 정의와 미래 매매 효용을 나눈 상태·보고 방식.
4. 실행 전 고정할 소규모 calibration 명세. 표본·비교 기준·outcome·선택 절차를 포함할 것.
5. 기존 결정과 충돌하지 않는 구현 단계 및 수용 테스트.

새 vocabulary 탐색, EntryOpportunity 임계값 변경, Signal ID 영구 보존 장치, Strategy DB, 실제·가상 보유의 Strategy 유입, 새로운 자동 BUY/EXIT 규칙은 추가하지 않는다.

최근 Signal ID 논의와 충돌하는 이전 리뷰 문구는 이 피드백으로 정정한다. 나머지 기존 결정은 유지하며, 미정 항목은 구현 계획에서 명시적으로 확정할 수 있도록 정리해 달라.

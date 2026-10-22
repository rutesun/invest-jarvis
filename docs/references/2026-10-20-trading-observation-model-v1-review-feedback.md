# Trading Observation Model v1 — 설계 보완 피드백

- 작성일: 2026-10-20
- 검토 대상: 「Trading Observation Model v1 확정 및 구현 지시」
- 독자: 프로젝트 코드와 이전 대화를 직접 확인할 수 없는 설계 작성 시스템
- 상태: 리뷰 의견. 아래 권고는 아직 채택·구현된 규칙이 아니다.

## 1. 요청과 검토 결론

원안의 책임 분리와 vocabulary 방향에는 동의한다. 다만 구현자가 동일한 결과를 만들 수 있도록 발생·종료·식별·계산 기준과 기존 시스템의 연결 방식을 보완해 달라.

이 문서는 원본 코드나 이전 대화 없이 읽을 수 있도록 현행 동작과 기존 합의를 제공한다. 아래 정보를 전제로 원안을 수정하고, 결정이 필요한 부분은 별도로 표시해 달라. 저장소 조사나 코드 수정은 요청하지 않는다.

다음 세 종류의 정보를 구분한다.

- 현행 사실: 현재 코드를 확인한 결과다. 장기적으로 유지해야 하는 정책이라는 뜻은 아니다.
- 기존 합의: 사용자가 앞서 승인한 방향이다. 아직 구현되지 않은 것도 있다.
- 리뷰 권고: 이번 리뷰에서 제안하는 보완이다. 자동으로 확정 정책이 되지 않는다.

유지할 원안의 핵심은 다음과 같다.

- Observation은 차트에서 관찰한 의미 있는 사실·상태를 설명한다.
- Observation 발생만으로 BUY·EXIT 또는 EntryOpportunity 변경을 수행하지 않는다.
- Positive와 Risk를 검증되지 않은 가중치로 상쇄하지 않는다.
- 동일 관찰을 미보유용·보유용으로 중복 생성하지 않고 scopes로 구분한다.
- 미래 성과는 별도 Research Evaluation에서 계산한다.
- 미완성 장중 결과와 확정 결과를 구분하고, 장중 후보를 FINAL history에 고정하지 않는다.

## 2. 원안 작성 시스템에 제공하는 기존 시스템 배경

### 2.1 책임 경계 — 기존 합의

| 영역 | 책임 | 포함하지 않는 것 |
|---|---|---|
| Technical Evidence / Technical Score | 지표·방향·점수와 산출 근거 | 실제 보유에 따른 매수·매도 수량 |
| Strategy Observation | 차트의 setup과 의미 있는 상태·변화 | 실제·가상 보유 상태 |
| Strategy Signal | 전략 규칙으로 완성된 차트 사건 | 실제 체결 여부 |
| EntryOpportunity | 특정 진입 Signal을 기준으로 오늘의 진입 가능 여부 평가 | 실제 매수·매도 수량 |
| PositionPlanner | 전략 결과와 실제 보유·계좌 정보를 결합해 행동·수량 계획 | 차트 Observation을 보유 여부에 따라 변경하는 계산 |
| Backtest / Research Evaluation | 가상 매매·성과 및 미래 outcome 평가 | 미래 결과를 현재 detector에 전달하는 동작 |

현재 실제 보유·수량 계획을 담당하는 구성요소의 이름은 PositionPlanner다. 원안의 PositionManager는 개념적 명칭으로 이해하되, 이번 작업에 별도의 보유 관리 엔진 신설을 포함하지 말아 달라.

Strategy는 동일한 차트 history·finality·계산 설정을 입력하면 동일한 결과를 재계산해야 한다. 실제 매매장부나 과거 실행 기록은 Strategy의 상태 원천이 아니다.

차트의 거래일은 사건과 상태의 기준이고, 프로그램 실행 시각은 계산·기록 시각이다. Strategy DB는 현재 사용하지 않으며 이번 설계 때문에 재도입할 필요가 없다.

### 2.2 EntryOpportunity — 현행 사실

- 시장 gate, 기준 실행가격 대비 상단 확장 +5%, age 20거래봉 설정을 사용한다.
- 명시적 후속 invalidator는 `SMA150_EXIT`, `OVERHEAT_CORRECTION`이다.
- FINAL로 확정된 INVALIDATED / EXPIRED는 동일 source에서 부활하지 않는다.
- 새로운 Signal은 새로운 source와 진입 window를 만들 수 있다.
- 최신 source가 불리하다고 과거 source의 ALLOW로 되돌아가지 않는다.
- 이탈·큰 ATR 하락 같은 Shadow 경고가 자동으로 Production 상태를 바꾸지는 않는다.
- 위 수치는 현행 설정 설명이며, 연구로 최적성이 확정됐다는 의미가 아니다.

Opportunity 종료는 실제 보유의 자동 매도 명령이 아니다.

### 2.3 PROVISIONAL / FINAL — 기존 합의

실시간 제품은 PROVISIONAL 결과를 표시하고 사용할 수 있다. PositionPlanner도 장중 결과를 사용할 수 있다. 이번 작업에서 전체 전략을 FINAL-only로 바꾸면 안 된다.

다만 장중 Observation이 사라지면 FINAL history에 남지 않아야 한다. Backtest에서는 FINAL 데이터와 다음 거래 가능 시가 체결을 구분해 사용한다.

### 2.4 기존 Setup과 SMA150 문제 — 현행 사실 및 미구현 합의

현재 `PULLBACK_WATCH`와 `POST_OVERHEAT_RECOVERY_WATCH`는 기간을 가진 setup이다.

현재 눌림 지지 후보는 SMA50·SMA150·SMA200 및 상승 Supertrend 지지선이다. SMA 정배열·상승 방향·ATR 기준 접근/유지 조건을 사용하며, 모든 후보에 Supertrend 상승을 공통 선행 조건으로 요구한다.

이 때문에 SMA150 지지 조건이 성립해도 Supertrend 하락이면 PULLBACK_WATCH 자체가 표시되지 않는다.

사용자가 앞서 승인했으나 아직 구현되지 않은 방향은 다음과 같다.

- SMA 지지 후보를 Supertrend 상승 여부와 분리해서 관찰한다.
- Supertrend 하락은 `SUPERTREND_DOWN` 경고로 함께 보여준다.
- 경고 자체가 Observation·Signal·Production을 차단하지 않는다.
- 지지선 touch만으로 진입 Signal을 만들지 않는다.
- 기존 지지 유지와 이전 고가 돌파에 의한 반등 확인을 유지한다. 현재 reversal high lookback은 1봉이다.

이 gate 분리는 새 setup과 후속 Signal의 발생 시점도 바꿀 수 있다. 단순 화면 경고 추가와 동일한 변경이 아니다.

### 2.5 기존 Shadow — 현행 사실

현재 독립 Shadow는 특정 source Signal의 frozen anchor를 기준으로 이탈·회복·악화 후보를 계산한다. 지원 source는 `TREND_BREAKOUT_ENTRY`, `PULLBACK_REVERSAL_ENTRY`다. source가 없으면 미평가한다.

Risk Level은 `NORMAL`, `CAUTION`, `HIGH_RISK`이며 미평가 시 값이 없다. NORMAL은 해당 진단에서 추적하는 악화 조건이 없다는 뜻이고, 종목 전체가 안전하다는 보장은 아니다.

현재 Flag는 다음 9개다.

```text
BREAKOUT_LEVEL_BREACH
BREAKOUT_LEVEL_RECLAIMED
LARGE_ADVERSE_MOVE
EARLY_FAILED_BREAKOUT_CANDIDATE
ORIGIN_SUPPORT_BREACH
ORIGIN_SUPPORT_RECLAIMED
PULLBACK_LOW_BREACH
PULLBACK_LOW_RECLAIMED
SEVERE_PULLBACK_DETERIORATION
```

`SUPERTREND_DOWN`은 추가 합의만 있으며 미구현이다.

제품의 check·analyze·brief는 공통 전략 결과를 표시한다. 기존 Shadow는 실행 시 연구용 JSONL snapshot을 기록할 수 있다. Strategy는 이 기록을 읽어서 판단하지 않는다. 자동 미래 outcome evaluator는 현재 구현되어 있지 않다.

## 3. 보완 요청 1 — Observation 추가와 기존 전략 변경을 분리해 달라

관련 원안: §6 기존 SETUP 유지, §13 Signal 경계, §29 Production isolation test.

원안은 기존 Signal과 Production 결과의 동일성을 요구한다. 반면 위에서 설명한 SMA 지지 후보의 Supertrend 공통 gate 제거는 기존 결과를 바꿀 수 있다.

### 수정 요청

다음 두 작업을 구분해서 범위를 명시해 달라.

| 작업 | 허용되는 영향 |
|---|---|
| A. Observation Model v1 및 설명 정보 추가 | 기존 Signal history·ID, EntryOpportunity, Position action 유지 |
| B. 승인된 SMA 지지 후보의 Supertrend gate 분리 | 별도 규칙 변경으로 관리하고 의도한 setup·Signal 차이를 검증 |

A만으로 기존 SMA150 관찰 누락이 해결된다고 설명하지 말아 달라. B를 이번 작업에 포함한다면 A의 무변경 검증과 B의 의도된 변경 검증을 분리해야 한다.

고정 Observation vocabulary에는 `SUPERTREND_DOWN`이 없다. 이를 기존 Shadow 경고로 둘지, 관련 Observation의 evidence로 표시할지 명시하고, 새 top-level ObservationCode는 임의로 추가하지 말아 달라.

보완된 문서는 최소한 다음 상황의 기대 출력을 설명해야 한다.

```text
SMA150 지지 후보 성립 + Supertrend 하락 + 반등 미확인
→ 지지 관찰과 Supertrend 경고 표시
→ touch만으로 새 진입 Signal 생성 금지
→ 기존 source의 EntryOpportunity는 해당 정책으로 별도 평가
```

## 4. 보완 요청 2 — pivot 사건과 확인 날짜의 계약을 명시해 달라

관련 원안: §8.1~8.2, §9.4~9.5, §23.

### 현행 계산의 제약

현재 공통 pivot 판정은 앞 3봉과 뒤 3봉을 이용한다. 원래 pivot 봉을 i라고 하면 i+3봉에서 확인 가능하다.

공개 결과는 pivot 사건 목록이 아니라 각 봉의 다음 두 boolean 상태다.

```text
마지막 두 확정 저점이 상승하는가?
마지막 두 확정 저점과 고점이 동시에 하락하는가?
```

HIGHER_HIGH·LOWER_HIGH·LOWER_LOW의 독립 사건과 pivot 가격·날짜는 이 두 값만으로 복원할 수 없다.

예를 들어 저점이 90 → 95 → 100으로 높아지면 두 번째 저점 확인 후 boolean이 계속 True다. True인 매일을 새 사건으로 기록하면 중복되고, False → True 변화만 기록하면 세 번째 저점 확인을 놓친다.

### 수정 요청

- 동일한 pivot 판정 알고리즘을 재사용하면서 확정 pivot 사건을 공통 결과로 제공하는 계약을 정의해 달라.
- 원래 pivot 날짜, 확인 날짜, 가격, 이전 비교 pivot을 구분해 달라.
- Observation의 당시 이용 가능 시점은 확인 날짜를 기준으로 해 달라. 원래 pivot 날짜로 소급해 당시 이미 알았던 사건처럼 취급하면 안 된다.
- 확인에 필요한 마지막 봉이 장중이면 후보의 finality를 구분해 달라.
- 기존 boolean 결과는 보존하여 기존 Signal 의미를 바꾸지 않도록 해 달라.

### 필요한 검증 예시

```text
같은 방향의 새 pivot이 두 번 연속 확인됨
→ 서로 다른 두 확인 사건을 식별할 수 있음

확인에 필요한 뒤 3봉이 아직 없음
→ FINAL pivot Observation 없음

장중 확인 후보가 종가에서 불성립
→ FINAL history에 고정되지 않음
```

## 5. 보완 요청 3 — Observation별 lifecycle과 식별 기준을 정해 달라

관련 원안: §4 Status, §5 모델, §17 Registry, §20 Reclaim history.

ACTIVE·RESOLVED 등의 상태 이름만으로는 각 Observation이 언제 끝나는지 결정할 수 없다. 지속 setup, 특정 날짜의 확인 사건, 현재 구조 상태가 같은 모델에 들어오므로 차이를 정의해야 한다.

예를 들어 UP_VOLUME_EXPANSION이 며칠 전 발생했는데 계속 ACTIVE로 남으면 현재도 거래량 확대 중인 것처럼 보일 수 있다. 반대로 매일 새 객체를 만들면 같은 지속 상태를 여러 표본으로 중복 평가할 수 있다.

### 수정 요청

각 code에 다음 계약을 표로 추가해 달라.

```text
발생 조건 / 유지 조건 / 종료 조건 / 재발생 조건
같은 사건·episode를 식별하는 문맥
현재 표시와 과거 history 표시 방식
```

Observation의 논리적 식별과 실행 시 snapshot을 구분해 달라. code만 같다는 이유로 다른 source·setup·지지선의 사건을 합치면 안 되고, 실행할 때마다 별개의 사건으로 만들면 안 된다.

특히 다음 상황을 구분할 수 있어야 한다.

- 같은 날 SMA50과 SMA150이 모두 이탈한 경우.
- 동일 종목에서 서로 다른 돌파 Signal의 기준선을 추적하는 경우.
- 진입 Signal이 생기기 전 PULLBACK_WATCH만 존재하는 경우.
- 같은 지지선의 이탈 → 회복 → 재이탈이 반복되는 경우.

일반적인 시장 구조·거래량 Observation은 진입 source 없이도 평가해야 한다. source가 필요한 Observation만 그 의존성을 명시해 달라. POSITION scope는 활용 문맥이며 실제 보유가 있어야 생성된다는 뜻이 아니다.

이 식별 계약은 DB 저장이나 매매장부 도입 요구가 아니다. 동일 차트에서 재계산해도 같은 관찰을 식별하고 연구 중복을 막기 위한 것이다.

## 6. 보완 요청 4 — vocabulary와 실행 가능한 계산 명세를 구분해 달라

관련 원안: §8.4~8.7, §9.2·9.6·9.7, §24, §31.8.

이름의 의미가 명확해도 계산식이 미정이면 구현자마다 결과가 달라진다. 다음 내용을 보완해 달라.

| 항목 | 필요한 결정 |
|---|---|
| VOLUME_CONTRACTION | 조정·consolidation의 판정, 비교 기간, 수축 조건 |
| UP/DOWN_VOLUME_EXPANSION | 상승·하락 기준이 전일 종가 대비인지 시가 대비인지, 기준 거래량·기간·threshold |
| 공통 volume reference | 현재 봉 포함 여부, 장중 불완전 거래량 취급, 기준값 부족 시 처리 |
| MOMENTUM_REACCELERATION / DECELERATION | 사용하는 feature, AND/OR 조합, lookback, 기존 상승 추세 및 둔화/재가속의 정의 |
| SUPPORT_BREAK / RECLAIM | 대상 지지선 선택, frozen 기준 날짜, 이탈·회복의 경계값과 동일 anchor 연결 |

지지선 예시:

```text
최초 SMA150 = 100
현재 SMA150 = 110
현재 가격 = 105

최초 frozen level은 회복함
현재 SMA150은 회복하지 못함
```

두 사실은 구분해서 표시할 수 있어야 한다. 이탈은 당시 이동 지지선으로 판정하고 회복은 다른 frozen 기준으로 판정하는 식의 혼합을 피해야 한다. source 없는 지지선 관찰의 anchor 생성·종료 방식도 명시해 달라.

### 설정과 기존 Signal ID 보존

현행 시스템에서는 전략 parameter 전체를 해시한 fingerprint가 Signal ID에 포함된다. 관찰용 parameter를 기존 전략 parameter에 단순 추가하면 매매 규칙이 같아도 기존 Signal ID가 바뀔 수 있다.

Observation 계산 설정·버전의 식별을 기존 Production Signal 식별과 분리하는 계약을 명시해 달라. 공유 지표 계산을 유지하면서도 관찰 설정 변경만으로 source ID가 바뀌지 않도록 해야 한다.

이번 요청은 최적 parameter 탐색이 아니다. v1에서 재현 가능한 계산식·기본값·데이터 부족 시 행동을 정해 달라는 요청이다. 현재 정보로 정확히 정의할 수 없는 code는 vocabulary에는 남기되 미구현 상태와 이유를 명시하고, 전체 구현 완료로 표현하지 말아 달라.

## 7. 보완 요청 5 — terminal 이후 reclaim의 표시 범위를 명확히 해 달라

관련 원안: §8.3의 “terminal 되기 전에”, §21 terminal invariant.

원안 앞부분의 BREAKOUT_RECLAIM 정의는 terminal 이전으로 제한한다. 뒤에서는 terminal 이후 reclaim이 과거 Opportunity를 부활시키지 않는 Observation이라고 설명한다. 다음 예시의 기대 결과를 확정해 달라.

```text
1일: 돌파 Signal 발생
후속일: 기준선 이탈
이후: 해당 Opportunity EXPIRED 또는 INVALIDATED 확정
더 이후: 가격이 같은 frozen 돌파선 위로 회복
```

### 반드시 유지할 계약

과거 source의 EntryOpportunity는 terminal을 유지한다. 가격 회복만으로 ALLOW로 부활시키지 않는다.

### 리뷰 권고 — 아직 미확정

회복이라는 차트 사실은 계속 표시할 수 있도록 하고, 그것을 terminal Opportunity의 실행 허가와 구분하는 방식을 권한다.

다만 terminal 이후에도 원 source에 연결한 BREAKOUT_RECLAIM을 허용할지, 원 source 관찰은 종료하고 별도의 support 문맥으로 표시할지는 명시적으로 선택해 달라. “기존 source 종료”와 “차트에서 회복 사실이 없음”을 같은 뜻으로 취급하지 말아 달라.

## 8. 보완 요청 6 — 기존 Shadow와 Observation의 연결 및 연구 범위를 정해 달라

관련 원안: §14 Production 경계, §15 점수 합산 금지, §27 Research Evaluation.

### 8.1 중복 의미와 잔여 연구 진단

다음은 의미 대응의 예시이며 확정된 마이그레이션 규칙은 아니다.

| 기존 Shadow Flag | 새 vocabulary와의 연결 후보 |
|---|---|
| BREAKOUT_LEVEL_BREACH | 같은 이름의 Observation |
| BREAKOUT_LEVEL_RECLAIMED | BREAKOUT_RECLAIM |
| ORIGIN_SUPPORT_BREACH | SUPPORT_BREAK + origin support 문맥 |
| ORIGIN_SUPPORT_RECLAIMED | SUPPORT_RECLAIM + origin support 문맥 |
| PULLBACK_LOW_BREACH | 같은 이름의 Observation |
| PULLBACK_LOW_RECLAIMED | 회복 표시 방법을 별도 정의. 새 code를 임의 추가하지 않음 |
| LARGE_ADVERSE_MOVE | 기존 연구 진단으로 유지할지 명시 |
| EARLY_FAILED_BREAKOUT_CANDIDATE | 기존 연구 후보로 유지할지 명시 |
| SEVERE_PULLBACK_DETERIORATION | 기존 복합 연구 진단으로 유지할지 명시 |

같은 가격·anchor 사실을 두 detector가 따로 계산해 판정이 달라지지 않도록 공통 계산의 책임을 정해 달라. Observation 모델로 모든 Shadow 가설을 억지로 통합할 필요는 없다.

### 8.2 Risk Level과 사용자 출력

새 Observation을 몇 개 추가했다는 이유로 기존 Risk Level이 자동 변경되어서는 안 된다. 유지·대체·변경 중 어떤 정책인지 명시해 달라.

기존 Risk Level을 유지한다면 그 값이 기존 source별 Shadow 진단 범위라는 점을 표시해야 한다. 일반 RISK Observation이 존재하면서 기존 source 진단은 NORMAL인 경우에도 의미가 모순되지 않도록 설명 범위를 구분해 달라.

Risk Level을 Positive/Risk 개수의 합산으로 새로 만드는 방식은 권하지 않는다. 새로운 위험 집계 규칙을 도입하려면 별도 정책으로 다뤄야 한다.

최종 출력에는 Observation의 날짜·finality·현재/종료 상태·핵심 근거를 포함해, 과거 사건과 현재 상태가 혼동되지 않도록 해 달라. check·analyze·brief의 공통 출력 계약도 명시해 달라.

### 8.3 Research Evaluation 구현 범위

“모든 FINAL Observation을 향후 연구할 수 있어야 한다”는 요구를 다음 범위로 나눠 달라.

- 이번에 식별·날짜·설정 버전·근거 등 연구 연결에 필요한 정보만 제공하는가?
- 연구용 snapshot 기록도 확장하는가?
- 미래 5/10/20/40/60봉 return·MAE·MFE 등을 계산하는 evaluator까지 구현하는가?

현재 자동 미래 outcome evaluator는 없다. 이번에 구현한다고 해석하지 않도록 포함·제외 범위를 정해 달라. 연구용 기록을 추가하더라도 Strategy가 그 기록을 읽어야 계산되는 구조는 피해야 한다.

## 9. 원안의 조건식 오류 수정

§28 Breakout 테스트의 다음 문구는 방향이 반대다.

```text
breakout level below close → BREAKOUT_LEVEL_BREACH
```

다음과 같이 수정해 달라.

```text
FINAL close < frozen breakout level → BREAKOUT_LEVEL_BREACH
```

경계값에서 같음(=)을 이탈·회복 중 어디에 포함하는지도 일관되게 정의해 달라.

## 10. 요청하는 회신 산출물

기존 코드에 접근하지 않고도 검토할 수 있도록 다음을 포함한 수정 설계를 제공해 달라.

1. 유지할 원칙과 수정한 항목의 요약.
2. Observation 추가와 Supertrend gate 변경의 범위·검증 분리.
3. v1 code별 발생·유지·종료·재발생 및 source/anchor 의존성 표.
4. pivot 확인 시점과 Observation·snapshot 식별 계약.
5. 미정 계산식·기본값·데이터 부족 처리 목록. 새 제안값은 검증된 값과 구분.
6. 기존 Shadow Flag 대응표, Risk Level 유지 여부, 사용자 출력 예시.
7. terminal 이후 reclaim의 선택과 조건별 결과표.
8. 이번 구현 범위와 후속 연구 범위, 수용 테스트 목록.

우리 코드를 조사하라는 지시 대신, 위 현행 사실을 입력 전제로 사용해 달라. 정보가 부족한 항목은 부족한 사실과 필요한 결정을 표시하고, 미확정 권고를 기존 사용자 합의로 간주하지 말아 달라.

새 ObservationCode 추가, 기존 EntryOpportunity 임계값 변경, 실제 보유·가상 매매 상태의 Strategy 유입, Strategy DB 재도입, 기존 Technical Score의 재설계는 이번 피드백을 근거로 자동 포함하지 않는다.

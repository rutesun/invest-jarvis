# Trading Observation v1 offline calibration

실행 상태: I1/I2 수정 후 같은 protocol의 새 calibration이 정상 완료됐다. root의 의미 사례 확인과 독립 최종 artifact 리뷰가 Spec PASS / Quality Approved로 완료됐다. 승인은 순수 kernel·offline 연구 범위이며 제품 배선·통합 검증은 후속 단계다. 결함이 있던 원형 중단 run은 의사결정 근거로 사용하지 않는다.

이 연구는 Observation의 의미와 표시 기준을 검증한다. 실제 체결 성과나 전체 시장의 전략 승률을 입증하지 않으며, 제품의 V1 기본값은 유지한다. Observation은 Technical Score를 가감하거나 매수·매도 결정을 생성하지 않는다.

## 데이터와 비교 범위

로컬 CSV 20종목과 시장 비교용 SPY를 사용했다. 생존 종목의 편의 표본이므로 전체 시장으로 일반화하지 않는다. 원자료 inventory는 2014-01-02~2026-09-28이고, 사건 계산은 2025-12-31까지 절단했다. 21파일 모두 존재하며 거래소 calendar 대비 누락 session은 없다.

2014 이후 자료를 warmup으로 사용하고 사건 평가 기간은 2017~2025로 고정했다. development는 2017~2021, validation은 2022·2023·2024·2025 각각의 연도다. 기존 연구 사용 기간이므로 fresh OOS라고 부르지 않는다. 외부 provider/LLM 호출은 0회이며, 연구 CLI에서 socket 연결을 차단했다. Strategy DB와 실제 계좌는 사용하지 않았다.

EVENT는 확인일 1표본, EPISODE는 시작일 1표본이다. 연속 ACTIVE 날짜를 독립 성과 표본으로 늘리지 않는다. 미래 수익은 사건 다음 거래일 open을 기준으로 5/10/20/40/60번째 close와 고가·저가 범위를 계산한다. 같은 연도 안에서 horizon이 완성되지 않거나 가격이 누락되면 null과 이유를 남긴다.

일반 Observation은 같은 종목·연도·SPY regime·SMA150 위/아래 상태에서, 그 Observation이 없는 이전 20거래일 중 가장 가까운 날과 비교한다. 선택 과정은 미래 outcome을 사용하지 않는다. 불확실성은 ticker 단위 cluster bootstrap 2,000회(seed=21, percentile 95%)로 계산하며 comparator 재사용·horizon 중복·미매칭을 함께 공개한다.

## 결과 전 확인한 표본 한계

공통 문맥은 원자료에서 시작한 종목별 최초 cycle만 사용한다. 평가 시작일에 cycle을 새로 열어 표본을 늘리지 않았다. 14종목의 최초 cycle은 warmup 중 종료되었다.

| 고정 risk set | 원형 bug kernel 관찰 | 수정 kernel 관찰 | 선정에 미치는 영향 |
|---|---:|---:|---|
| 개별 support-test origin | 48개·6종목 | 95개·6종목 | 최소 10ticker 미달 |
| 최초 terminated cycle | 6개 | 6개 | restart는 구조상 최대 20개라 최소 50표본 불가능 |

원형 48건은 outcome을 보기 전에 protocol에 기록한 당시 관찰 사실로 보존했다. 수정 후 실제 95건은 새 label-free inventory에 별도로 남겼다. 최초 cycle과 최소 조건은 바꾸지 않았으며 normal failure·immediate failure·restart의 기본값은 `UNRESOLVED`, 예측 usefulness는 `INSUFFICIENT`로 남긴다. 비교용 중심값 normal 2회·immediate OFF와 restart A는 운영 기본값이 아니다. A~D는 동일 종료 origin에서의 기술통계로만 해석한다.

## 결과

원형에서는 누락된 FINAL 종가가 연속 failure count를 끊지 않는 문제와, 이전 reclaim 날짜가 새 failure에 남아 후속 dynamic support test를 놓치는 문제를 확인했다. 고정 risk set의 표본 자체를 누락할 수 있어 root 지시로 첫 run을 정상 중단하고 두 결함을 수정했다.

원형 run에서는 성과·요약·선정 산출물이 생성되거나 열람되지 않았다. 수정 후 support origin은 CAT18·COIN4·CRWD23·MU32·QCOM3·SHOP15의 합계 95개이며 종료일과 restart 6개는 같았다. 기존 output은 삭제하거나 덮어쓰지 않았다. 새 run은 root의 재승인 후 outcome을 실제로 계산했고, 161,101 Observation행·879 cohort행·4,041 zone행과 39후보의 결과를 저장했다.

| family | detector 표시 기준 | 예측 usefulness |
|---|---|---|
| UP/DOWN volume expansion | plateau 없어 UNRESOLVED | 모든 후보 UNRESOLVED |
| volume contraction | plateau 없어 UNRESOLVED | 0.9 후보만 SUPPORTED, 그 외 UNRESOLVED |
| support break/reclaim | buffer 0/0 ATR 잠정 선택 | UNRESOLVED |
| normal/immediate failure, restart | UNRESOLVED | INSUFFICIENT |
| zone | 표시 폭 0.5 ATR 잠정 선택 | 평가 대상 아님 |
| momentum reacceleration | SMA20_TURN 잠정 선택 | UNRESOLVED |
| momentum deceleration | 고정식 잠정 선택 | UNRESOLVED |

utility가 좋게 나온 contraction0.9로 detector를 사후 재선택하지 않았다. fixed 구조 관측에서는 LOWER_LOW만 사전 기준상 SUPPORTED, 나머지 세 종류는 UNRESOLVED였다. 결과는 이 편의 표본·기간·비교법에 한정하며 새로운 BUY/SELL gate로 쓰지 않는다. 잠정 선택의 의미 사례는 승인됐으며 제품 배선·통합 검증 전까지 활성화하지 않는다.

calibration의 source context는 chart-only anchor만 구성하고 실제 Opportunity terminal 정보를 주입하지 않았다. 따라서 `source_terminal=false`를 실제 non-terminal 확정으로 읽으면 안 된다. Task3 제품 배선의 source terminal 설명 계약과 별개다. 잠정 선택 4family의 가격·SMA·ATR·기울기·문맥·anchor·종료 조건 5분위 표는 Task2 보고서에 있으며, 미래 outcome과 분리했다.

detector 표시 기준과 예측 usefulness는 서로 독립이다. 표시 threshold는 development의 의미·경계·prefix 재현성과 인접 후보 빈도 plateau로 잠정 선택한다. 예측 usefulness가 `UNRESOLVED`여도 표시 의미가 유효하면 detector 구현과 기본 표시를 허용할 수 있다. validation 수익률을 보고 threshold를 다시 고르지 않는다.

## 재현과 후속 결정

protocol SHA256은 `8fbdd3c3d80febf75adf737f7b72a4ec655a92df80974dc6adbdba7c3d8e78af`로 유지했다. 원형 freeze manifest SHA256은 `d88143ca9d00388fea5d6aebfe882354ee02ece51442b7633347b418fbbfbfe4`, 수정 freeze manifest SHA256은 `072b1141e84a272c9394ba3fef5e3f0642b1b7a40062215f5a572ff66b68fc17`이다. 원본 4문서와 INITIAL 확정 worklog의 당시 byte snapshot, CSV별 범위·누락·hash, 실행 kernel/evaluator/script/uv.lock hash를 각각 보존했다. 의미가 바뀌면 결과를 재사용하지 않는다.

원형 구현의 전체 suite는 2,009건 통과했다. 수정 후 fresh strategy/backtest 406건, V1 baseline 21/21 MATCH와 최적화 전후 7개 family의 전체 Observation JSON·ID 동등성을 검증했다. 결과 artifact hash·동일 cohort·195개 의미 사례의 날짜분위 표집이 모두 일치했고, 표집 outcome 1,114개를 원자료로 재계산했다. 기존 warning 2건은 그대로이며 전체 suite는 최종 통합 단계에서 재검증한다. 이 단계는 순수 kernel과 offline 연구이며, adapter/Runner의 제품 배선과 source terminal 설명은 후속 작업이다. 제품 default를 바꾸려면 별도 배선·검증과 의미 사례 승인이 필요하다.

원형 중단 기록: `tmp/trading_observation_v1/calibration/`. 수정 후 완료 산출물: `tmp/trading_observation_v1/calibration-fix1/`. result manifest SHA256은 `909afd05740e04b2329a1cfc99ee723a9e701fac2c1129a630d4eb098cb06aea`다. 구현·테스트 명령과 source 변경 내역은 `.superpowers/sdd/2026-10-21-trading-observation-v1-pullback/task-2-report.md`에 기록한다.

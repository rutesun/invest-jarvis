# Trading Observation v1 검증

2026-10-21 로컬 검증 결과입니다. 원 실행·후속 동등성·수정 후 테스트를 구분하며 최종 독립 승인과 운영 정책 선정은 별도입니다.

## 목적과 정책 경계

Observation 표시를 켜거나 설정을 바꿔도 같은 매매 정책의 Signal·source·EntryOpportunity·Planner가 유지되는지 확인합니다. 이 독립성과 Pullback 정책 변경으로 의도한 차이는 별도 비교입니다. 점수 가감·Positive/Risk 합산·Observation만으로 매수/축소/청산을 만들지 않습니다.

제품 Observation은 기본 ON입니다. 구조 이탈/재탈환 buffer 0 ATR, momentum `SMA20_TURN`, 표시 zone 0.5 ATR은 제품 표시 설정이고, 거래량 확장·수축의 세 ratio는 `None`/`UNRESOLVED`라 기본 실행에서 미평가입니다. 표시 활성화·detector별 설정 선정·예측 utility·매매 정책 운영 선정은 서로 다른 상태입니다. 전체 테스트 PASS는 새 cycle/ladder 규칙의 운영 승격 근거가 아닙니다.

사용자 기본은 `SWING_W150_V2` Signal 엔진의 **Pullback parameter V1**입니다. failure/immediate/restart 운영 선정은 `UNRESOLVED`입니다. 명시 V2 실행은 아래 한 profile을 출력 확인 전에 고정한 `RESEARCH_ONLY_NOT_PRODUCTION_DEFAULT` 진단 예시이며, 최적화·운영 선정·전략 수익성 검증을 뜻하지 않습니다.

| 항목 | 고정값 |
|---|---|
| normal_failure_closes | 2 |
| support_break_buffer_atr | 0 |
| immediate_failure_volume_ratio | 1.5 |
| immediate_failure_close_location | 0.25 |
| restart_mode | A |
| 나머지 설정 | `SwingW150ParametersV2` 타입 default |
| V2 fingerprint | `3902379a9ad687f105c316ebcd9b0921bc74f94044650ac3795648d7c8b211b1` |

immediate OFF는 제품 schema가 지원하지 않아 이 예시를 동결 calibration 중심 설정과 동일하다고 부르지 않습니다. 이 profile 하나는 운영 미선정을 해소하지 않으며, 승격에는 별도 연구 protocol·표본·정책 결정이 필요합니다.

## 자료와 실행 증거

`research/trading_observation_v1/protocol.json`의 로컬 20종목·SPY와 2025-12-31까지의 입력을 사용합니다. 보존 baseline은 실제 차트 20건과 synthetic fixture 1건입니다. 현재 시장 데이터·ALAB/COHR는 수집하지 않았고 compare/cases·bounded verifier의 provider/LLM/DB/실계좌 호출은 0입니다. 이 경로는 service/recorder를 호출하지 않고 source/calibration 연구 JSONL이나 미래 evaluator 라벨을 Strategy 입력으로 읽지 않습니다. pytest의 recorder는 test별 tmp_path로 격리합니다.

기존 연구 JSONL의 작업 전체 hash가 불변이라는 뜻은 아닙니다. root의 read-only 확인에서 Task 5 당시 47줄/177,795bytes prefix는 보존됐으나 37줄이 append되어 현재 84줄/5,581,041bytes였습니다. 현재 SHA는 `4424a4cd5e381e378c807dc6022fc8ffca19ec588811985422305e365bb681de`, 보존 prefix SHA는 `ba7739dfe26f0e8f6bd574d541dab3d67de0c6283bbb1886f81f96f762691fd6`입니다. 후반 실제 종목 brief/check 기록의 작성 주체는 미확인이며, 이번 작업은 이를 삭제·복원하지 않았습니다. Task 5 실행 전후 hash 불변 증거와 본 작업의 테스트 격리·recorder 미호출 범위를 구분합니다.

- 원 baseline: `tmp/trading_observation_v1/baseline/manifest.json`, 21 product/23 artifact. 예상 집합·SHA-256 검증 후 현재 V1 replay 21 MATCH를 확인했습니다.
- 비교 실행: `tmp/trading_observation_v1/comparison/`, exit 0, 2,491.451초. `comparison-manifest.json`과 산출물 5개 hash를 확인했습니다. manifest SHA-256은 `4beeba6645ad6183c07acd77bac13816b17f80de75d23e2a2f9e4c7cd34a8e49`입니다.
- 실제 사례: `tmp/trading_observation_v1/cases/`, `cases-manifest.json`, 유형별 JSON과 prefix별 Markdown. 5유형·7prefix 재현, exit 0, 25.808초입니다.
- raw 검증 log: `tmp/trading_observation_v1/task-6-logs/`.

비교·사례 실행 script의 원래 SHA-256은 `4a76332b59bd84b4d1ad39c172d6b58df1e76a393b91369333bf96e02d4a3981`입니다. 실행 중 예상 밖 중첩 artifact의 검출 경계를 좁히는 두 줄을 보완해 현재 script는 `b09979e18464d2d999501d2f59eff94a88bd8dfafc5843ddefaaa51e6a521341`입니다. 원본 bytes와 manifest hash는 유지했습니다.

root가 승인한 `task-6-logs/post-integrity-fix-receipt.json`은 구·신 함수별 AST(실행 구조)를 비교합니다. `_verify_baseline_artifacts`와 `main`의 baseline capture 집합 계산 두 비교식 외에는 전체 AST가 같고, `src` 220개·uv.lock·protocol hash도 같습니다. 원 baseline의 21 product/23 artifact에서 구·신 preflight(계산 전 입력 검증)는 동일하게 PASS했습니다. 이 receipt는 경계 보완을 검증하며 과거 실행을 현재 script 실행으로 재표기하지 않습니다. calibration은 기존 동결 코드 hash와 결과를 그대로 유지하고 재실행하지 않았습니다.

후속 통합 리뷰에서 중간 PROVISIONAL 피벗의 FINAL history/cycle 오염을 수정하고, custom volume event에 가격 변화·실제 거래량·직전20봉 기준 거래량·ratio Evidence를 보강했습니다. 이 제품 수정은 위 script 경계 보완 receipt와 별개입니다. `task-6-logs/final-fix-equivalence-receipt.json`은 21입력·42 series·117,678봉 모두 FINAL임과 구·신 pivot 모든 필드 동등, FINAL 부분집합의 index/date identity, 허용 변경 외 module AST 동등을 확인합니다. 새 source의 실제 7prefix Runner/adapter 전체 JSON·Planner projection·공통 renderer Markdown도 원 cases와 7/7 MATCH입니다. 원 ALL_FINAL 비교를 새 source 실행으로 재표기하지 않으며 기존 calibration도 당시 source 결과로 남깁니다.

최초 미완성 compare는 중단한 원형 그대로 `comparison-incomplete-attempt1/`와 `task-6-logs/compare.log`에 보존했습니다. 최종 비교 근거로 사용하지 않습니다.

## A. 같은 정책의 Observation 독립성

V1 및 위 명시 V2 각각에서 ON/OFF를 실행하여 Signal history/current Signals, source anchors를 포함한 Opportunity 전체, 가짜 계좌 Planner 전체를 비교했습니다. 실행 설정을 설명하는 metadata는 다르므로 이를 매매 판단의 변화로 보지 않습니다.

| 비교 | 결과 |
|---|---:|
| V1 Observation ON/OFF | 21/21 MATCH |
| 명시 V2 Observation ON/OFF | 21/21 MATCH |
| 현재 V1 / 보존 baseline | 21/21 MATCH |

21입력은 실제 과거 차트 20건과 synthetic fixture 1건이며 isolation 기록은 42개입니다. 원 source에서의 비교이고, 이후 제품 수정의 ALL_FINAL 동등성은 앞의 별도 receipt로 증명했습니다.

미래 `future_winner`/return/MFE/MAE 열을 raw fixture에 넣어도 Strategy 결과가 동일함을 테스트했습니다. Backtest는 두 정책 각각에서 ON/OFF의 FINAL Signal 전체 실행 결과가 같고, 기존 FINAL-only·t+1 실제 open·미래 입력 격리·exit 우선순위 테스트를 유지합니다.

## B. V1 / 명시 V2 Pullback 차이

WATCH/reversal 건수와 날짜·가격·Evidence·source 계보·Opportunity 상태/원인·Planner 하류를 보존합니다. 버전 간 영구 Signal ID 일치는 요구하지 않고 ticker/date/code/가격/finality와 source 원인을 비교합니다. SMA150_EXIT는 날짜·가격·finality가 같아야 합니다.

실제 20종목의 전체 보존 입력 history 집계는 아래와 같습니다. 이 건수는 2017~2025 평가기간으로 추가 절단하지 않았으며, 기간 내 날짜별 차이 표와 분모가 다릅니다. synthetic fixture의 두 건수와 날짜별 차이는 모두 0입니다.

| 정책 | PULLBACK_WATCH | PULLBACK_REVERSAL_ENTRY |
|---|---:|---:|
| V1 | 1,336 | 690 |
| 명시 V2 연구 profile | 5,914 | 2,554 |

2017~2025 날짜별 차이는 12,418개 압축 행입니다. 그중 Opportunity 상태·원인이 다른 행은 6,920개, 가짜 계좌 Planner directive(수량 계획 방향)가 다른 행은 1,540개입니다. 전체 거래일 빈도나 성과율로 해석하지 않습니다. SMA150_EXIT의 날짜·가격·finality는 21입력 모두 같습니다.

| AMD 실제 거래일·종가 | V1 | 명시 V2 | 가짜 계좌 Planner |
|---|---|---|---|
| 2017-01-06, 11.3200 | 12-06 TREND_BREAKOUT source가 `EXPIRED` | 12-08 별도 Pullback source는 `EXECUTION_WATCH`(`ENTRY_WATCH`), PRIOR_BREAKOUT_LEVEL WATCH 존재 | 둘 다 7주 유지. WATCH만으로 매수하지 않음 |
| 2017-01-27, 10.6700 | 12-06 source `EXPIRED`(`ENTRY_EXPIRED`), 당일 Signal 없음 | 당일 새 PULLBACK_REVERSAL_ENTRY와 `ALLOW`(`ENTRY_WITHIN_EXTENSION`) | V1 7주 유지 / V2 risk target 100주에 맞춘 93주 매수 제안 |

수량은 고정 fake account/position의 진단 예시이며 실제 주문이 아닙니다. 뒤의 ALLOW는 새 source/window로 생겼으며 기존 EXPIRED source를 부활시킨 결과가 아닙니다. 종목별 건수는 `comparison/comparison.md`, 상세 source·Evidence·판단 원인과 계획은 `dated-policy-differences.json`에 있습니다.

`dated-policy-differences.json`은 모든 거래일의 전체 상태표가 아닙니다. 두 정책의 WATCH/현재 Signal/최신 source가 같으면 생략하며, 서로 다른 상태가 계속 같을 때 중복 날짜를 압축합니다. 다만 source 계보가 다르고 어느 한 source가 발생 후 age 0..21이면 매일 Opportunity/Planner를 평가해 상태·원인 변화를 보존합니다. WATCH Evidence의 일중 갱신만으로 행을 늘리지는 않습니다. 상태가 바뀐 날짜의 상세 Evidence는 행에 남깁니다.

종목별 기존 로그는 adapter 4회와 두 kernel replay·날짜별 Opportunity/Planner·canonical prefix hash 계산을 합친 완료 시각만 제공합니다. 각 구간의 소요시간을 분리 계측하지 않아 장기 실행을 adapter 응답 지연으로 단정할 수 없습니다. 전체 offline 연구 시간은 production latency 측정이 아닙니다.

root가 별도 측정한 AMD 3018봉 V1 adapter는 Observation OFF 2.744초 / ON 3.067초입니다. Signal은 양쪽 122개, Observation은 54→1916개, diagnostic_errors는 모두 빈 목록입니다. compare 동시 실행 중의 단일 offline 표본으로, 실제 CLI/production 지연 보장이나 반복 통계는 아닙니다.

## 과거 실제 사례 — AMD

| 유형 | 거래일·종가 | 확인한 구조 |
|---|---|---|
| healthy SMA50 WATCH | 2017-08-07, 13.4300 | SMA50 12.9774 지지 접근, 상승 기울기, low-volume 문맥 |
| ST DOWN/SMA150 WATCH | 2017-05-12, 11.2600 | SMA150 10.9887 지지 관찰, SMA50 기울기 -0.6708, Supertrend DOWN을 Evidence로 표시 |
| 1일 shakeout/reclaim | 2017-01-20 9.7500 → 01-23 9.9100 | SMA50 9.7950 아래 1회 `SOFT_BREACH` → 동적 SMA50 9.8532 `RECLAIMED`, failure latch 없음 |
| SMA150 종료/새 cycle | 2017-05-02 10.3200 → 05-12 11.2600 | SMA150 10.7910 실패로 기존 cycle TERMINATED → 두 FINAL 종가 상회 후 별도 cycle ID의 RESTART_A |
| terminal 후 reclaim | 2017-04-17, 12.7900 | 2017-02-06 source의 돌파선 12.6600 재탈환. 기존 source는 03-08 EXPIRED를 유지 |

위 다섯 유형은 모두 로컬에서 발견했습니다. 후보는 기존 FINAL kernel 한 번으로 찾고 제한된 7prefix만 실제 `StrategyRunner`(adapter 포함)와 공통 renderer로 검증했습니다. JSON에는 날짜·가격·typed Evidence·cycle/support·source별 terminal·Opportunity·가짜 계좌 Planner를, Markdown에는 실제 renderer 출력을 보존합니다. cycle 종료·WATCH·reclaim만으로 실제 매도·매수 후보를 만들지 않는 예도 확인했습니다.

이 사례의 범위는 Runner/adapter·공통 renderer까지이며 canonical service나 세 CLI의 live 실행 증거가 아닙니다. 사례용 `AnalysisStrategyResult`에 `score_history`를 주입하지 않아 최근 5거래일 Score는 `없음 또는 평가 불가`입니다. 5일 점수와 세 pipeline 배선은 별도 regression 테스트 근거와 구분합니다. root는 2017-05-12 raw CSV의 close 11.2600/low 11.08/SMA150 10.9886666775를 rolling(150)으로 별도 재계산해 MATCH를 확인했습니다.

ALAB/COHR 추가 검증은 별도 범위입니다. 두 종목과 SPY의 2014~2025 일봉 수집·상장일·누락 session 검증부터 필요하며 이번 요청 수는 0입니다.

## 테스트와 승인 경계

baseline 누락·손상·예상 밖 파일, 중첩 `foo/sources` artifact 우회를 RED/GREEN으로 재현·수정했습니다. 기존 baseline fixture/4 tests와 원본 21건은 보존했습니다.

최초 fresh full은 `1 failed, 2123 passed, 15 deselected, 2 warnings in 186.24s`입니다. 실패는 기존 runner 독립성 테스트가 새 표시 metadata까지 전체 동일하다고 요구한 계약 충돌이었으며, 실제 차이는 `observations_enabled`와 `observation_parameters` 네 값뿐이었습니다. 두 metadata를 별도 검증한 뒤 이를 제외한 전체 불변 비교를 유지하는 최소 test 수정으로 보완했습니다. 제품 source는 바꾸지 않았습니다.

초기 보완 후 focused는 **107 passed, 기존 warning 2건 in 7.38s**, full은 **2125 passed, 15 deselected, 기존 warning 2건 in 180.00s**입니다. 이는 통합 finality/Evidence 수정 전 source 결과입니다. 통합 수정은 RED 14 failed → GREEN 15 passed, 추가 경계 포함 covering **299 passed, 기존 warning 2건 in 78.68s**, 수정 후 fresh full 1회는 **2142 passed, 15 deselected, 기존 warning 2건 in 175.85s**입니다. 전체 Ruff와 변경 제품/테스트/script Python 11개 format도 통과했습니다. 경고 출처는 기존 `TechnicalResult`의 Pydantic class Config deprecation과 `pandas_ta`의 pandas copy-on-write deprecation이며 새 warning은 없습니다.

동일 reviewer의 코드 재리뷰는 I1/M1 ADDRESSED이며 evaluator/script 책임 혼합은 deferred입니다. 최종 artifact/docs 승인은 별도 gate입니다. 이 검증은 운영 V2 선정·수익성·현재 시장 자료·canonical service/세 CLI live 실행·production latency를 증명하지 않습니다.

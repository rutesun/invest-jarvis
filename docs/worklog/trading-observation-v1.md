# Worklog — trading-observation-v1

- **Branch**: feature/scorecard-strategy-position-separation
- **Started**: 2026-10-21
- **Status**: local implementation and independent review complete; uncommitted
- **Links**: [직전 설계 피드백](../references/2026-10-20-trading-observation-model-v1-review-feedback-v2.md)

---

## (2026-10-21 11:08) [Decision] 최초 ACTIVE_UP_CYCLE의 필수 조건과 선택 확인 조건 확정

- 맥락: Pullback Watch의 자격인 최초 상승 사이클 시작 조건이 미정이었다. 사용자가 필수 조건 두 개와 선택 확인 조건 세 개를 직접 확정했다.
- 후보: 가격 상승 구조의 세 확인 경로 중 하나 이상 충족 / HIGHER_LOW 등 추가 공통 필수조건 사용.
- 선택: 다음 논리로 최초 ACTIVE_UP_CYCLE을 시작한다. 현재 가격과 SMA150 방향을 필수로 확인하고, 가격 상승 구조의 확인 경로는 하나 이상 허용한다.

  ```text
  INITIAL ACTIVE_UP_CYCLE
    = (FINAL close > SMA150)
      AND (SMA150 is flat or rising)
      AND (
        confirmed HIGHER_HIGH
        OR valid price breakout
        OR existing bullish Entry Signal
      )
  ```

- 기각: SMA50 > SMA150, Supertrend UP, SMA50 slope > 0, volume expansion, HIGHER_LOW를 최초 시작의 공통 필수조건으로 추가하지 않는다.
- 적용 범위: 최초 사이클의 시작 자격이다. 그 자체로 매수 Signal·EntryOpportunity ALLOW·실제 수량을 생성하지 않는다. 종료 후 새 사이클의 restart calibration은 별도다. 최초 시작에 FINAL close를 요구한다는 결정으로 전체 Strategy를 FINAL-only로 바꾸지 않는다.
- 구현 시 명시할 세부 사항: flat/rising 판정 방법, HIGHER_HIGH·breakout의 시간적 유효 범위, valid price breakout 정의, 사용할 기존 bullish Entry Signal 종류. 사이클/WATCH를 전제로 하는 신호를 최초 시작 근거로 사용해 순환 의존을 만들지 않도록 한다.
- 조건 해석: volume expansion은 별도 공통 gate가 아니다. 선택한 기존 Entry Signal detector가 원래 요구하는 거래량 조건을 제거하라는 뜻으로 확대 해석하지 않는다.
- 구현 상태: 설계 결정 기록만 작성했다. 제품 코드·테스트·calibration은 변경하거나 실행하지 않았다.
- ADR 후보? no

## (2026-10-21 11:33) [Decision] Observation 추가와 Pullback 정책 변경의 검증 경계 유지

- 맥락: 사용자가 확정한 설계의 구현 준비를 요청했다. 기존 V2/Shadow 코드가 다수 미커밋 상태라 HEAD만으로 이번 변경 범위를 판단할 수 없다.
- 선택: 기존 dirty 파일을 보존하고 baseline 상대 비교를 사용한다. 동일 Production 설정의 Observation ON/OFF는 Signal·Opportunity·Planner 불변을 검증하고, 새 Pullback 정책의 의도한 변화는 별도 비교한다. cycle failure와 기존 SMA150_EXIT 및 실제 매도 권한은 분리한다.
- 계획: [구현 계획](../superpowers/plans/2026-10-21-trading-observation-v1-pullback.md)에 파일 책임·경계 테스트·offline calibration·리뷰 순서를 작성했다. 최초 confirmation의 세부 시점, 20종목/39후보 및 연구 판정 수치는 검토용 제안이며 사용자 확정 정책으로 취급하지 않는다.
- 확인: 현재 일반 checkout이며 새 worktree를 만들지 않았다. 기존 pivot/Shadow 테스트 23개 통과, 기존 Pydantic warning 1개. 전체 suite는 이번 단계에서 재실행하지 않았다.
- 상태: 제품 코드·테스트 구현·calibration 실행은 아직 하지 않았다. 계획 확인 후 별도 구현 에이전트를 사용하고 root가 리뷰한다. commit/push/merge는 하지 않았다.
- ADR 후보? no

## (2026-10-21 11:48) [Decision] 독립 계획 리뷰 후 별도 에이전트 순차 구현 승인

- 맥락: 사용자가 “독립 리뷰후 별도 에이전트 구현 시작해”라고 실행 순서를 지정했다.
- 선택: 계획 독립 리뷰의 지적을 반영하고, 별도 구현 에이전트가 task별로 구현하며 root가 검증·독립 리뷰를 배정한다. 구현 방식 재확인은 하지 않는다.
- 변경 전 검증: `uv run pytest -q` → 1,928 passed, 15 deselected, 기존 warning 2개, exit 0(101.67초).
- 경계: commit/push/PR/merge와 외부 금융 provider/LLM 실실행은 이번 승인에 포함하지 않는다. 실제 보유/EXIT 정책은 확정 설계를 유지한다.
- 진행 근거: `.superpowers/sdd/2026-10-21-trading-observation-v1-pullback/progress.md`.
- ADR 후보? no

## (2026-10-21 11:58) [Decision] 독립 리뷰의 구현 계약 누락 6건 보완

- 맥락: 독립 리뷰는 Critical 0건, Important 5건, Minor 1건으로 구현 전 보완을 요청했다. 기존 Deep Recovery는 SMA150 아래에서도 발생하며, 기존 parameter hash는 모든 dataclass 필드를 포함함을 코드에서 확인했다.
- 선택: 공유 타입·설정 소유를 선행 정의하고, 모든 restart에 FINAL·종료 이후·SMA150 위 조건을 명시한다. 과거 source별 frozen/terminal 문맥, family별 calibration 표본·선택 규칙, 동결 V1과 별도 V2 경로 및 실제 실행 코드 hash를 계획에 추가했다.
- 경계: 최초 cycle의 사용자 확정 조건, 기존 청산·실제 보유 권한은 유지한다. 미확정 failure/restart를 운영 기본값으로 승격하지 않는다.
- 상태: 계획 재확인 요청. 제품·테스트 구현 및 calibration은 아직 시작하지 않았다.
- ADR 후보? no

## (2026-10-21 12:00) [Decision] 독립 재리뷰 READY 후 Task 0 위임

- 근거: 최초 6건 보완 후 잔존 Critical/Important/Minor 0. Observation detector의 표시 기본값과 미래 예측 utility를 분리하고, 표시 zone 설정은 Production fingerprint에서 제외했다.
- 실행: 별도 `observation_task0` 에이전트에 dirty baseline·정확한 입력/출력 projection·TDD 검증을 배정했다. 제품정책 변경은 후속 task에서 수행한다.
- 경계: 기존 feature checkout에서 순차 작업하며 task별 독립 spec/quality 리뷰 gate를 유지한다. commit·push·merge와 외부 금융 provider 호출은 하지 않는다.
- ADR 후보? no

## (2026-10-21 12:21) [Friction] 리뷰 패키지의 baseline 테스트 파일 누락 보완

- 막힌 점: scoped snapshot에 기존 pivot 테스트가 없어 diff 생성 명령이 error를 출력했다. exit 1만 확인해 정상 diff와 구분하지 못했고 독립 리뷰어가 누락을 발견했다.
- 임시 대응: 최초 status에서 tracked-clean임을 확인한 이 파일만 기존 HEAD에서 read-only 복구하여 보완 diff를 전달했다. dirty source는 HEAD로 대체하지 않았다.
- 개선 아이디어: 이후 리뷰 패키지는 baseline 파일 존재와 error 출력을 함께 검증한다. source 보존 범위와 신규 파일 구분을 명시한다.

## (2026-10-21 12:29) [Decision] outcome 개봉 전 restart 표본 한계와 support-test origin 확정

- 맥락: 최초 종료 cycle을 ticker당 하나만 사용하는 사전 설계에서는 20종목의 restart 표본이 최대20개여서 최소50개 계약을 충족할 수 없다. 구현자가 outcome 계산 전에 이를 확인했다.
- 후보: 표본·기준 변경 / 기존 protocol 유지와 미확정 보고.
- 선택: 최초cycle-only와 최소50 기준을 유지하고 restart를 INSUFFICIENT/UNRESOLVED로 남긴다. 임의 재활성화나 기준 완화로 운영 기본값을 만들지 않는다.
- 보완: anchor 등록일과 support-test 시작일을 구분한다. 시작은 low와 anchor의 절대거리0.5ATR 첫 접촉 또는 접촉을 건너뛴 첫 FINAL 종가 이탈이다. gap-down 실패가 표본에서 빠지는 것을 방지하며, 고정 origin을 후보별 확인일로 이동하지 않는다.
- 경계: Task 2는 순수 kernel과 offline 연구 단계이며 제품 배선은 후속 task다. protocol·코드·데이터 hash 확인 전 outcome을 열지 않는다.
- ADR 후보? no

## (2026-10-21 12:49) [Friction] 기존 테스트 복구와 부정확한 cohort 계산 중단

- 막힌 점: 구현자가 기존 calibration 테스트 파일의 존재를 확인하지 않고 Add File로 편집해 선행 baseline 테스트4개를 누락했다. 별도 자기리뷰에서 발견해 predecessor의 fixture/테스트를 정확히 복구했고, 복구 후 focused40개·전체2,009개 통과(기존 warning2개)를 보고했다.
- 추가 발견: 독립 리뷰가 missing FINAL 가격의 연속이탈 count 유지와 과거 reclaimed_on 잔존 문제를 재현했다. 후자는 새로운 동적 support-test 표본을 누락할 수 있다.
- 임시 대응: 최초 calibration 실행만 중단하고 동결 protocol·hash·사전 inventory·로그를 보존한다. 최종 finding 목록을 받아 같은 구현자가 수정한 뒤 동일 protocol의 새 출력 경로에서 재동결·재실행한다. 결과를 본 뒤 후보나 최소표본 기준을 바꾸지 않는다.
- 개선 아이디어: 편집 전 기존 파일/시작 사본 대조, source 상태 전이의 반복 breach/reclaim 및 missing FINAL 경계 테스트를 필수 검증한다. 원형 inventory48개는 당시 코드로 얻은 사전 사실로 보존하고 수정 코드의 inventory를 구분한다.

## (2026-10-21 13:02) [Bug] 연속 이탈과 반복 reclaim 경계 수정·관련 테스트 검증

- 증상: FINAL reference 누락을 건너뛴 count 누적, 과거 reclaimed_on으로 인한 새 동적 test 차단을 독립 리뷰에서 재현했다.
- 근원(root cause): 미평가 봉에서 연속 count가 유지됐고, 과거 episode의 reclaim fact와 현재 episode 상태를 같은 필드 수명으로 다뤘다.
- 수정: 별도 구현자가 누락 reference에서 count를 끊고, 종료 episode·새 동적 test를 분리했다. frozen failure latch는 유지한다. 불필요한 source 계산 생략은 대상 관측 JSON/ID 동등성7개 테스트로 확인했다.
- 검증 보고: 관련 Strategy/Backtest406개 통과, 기존 warning2개와 출처 유지. 전체2,009개는 fix 전 이력이며 최종 전체 검증은 후속 단계에서 다시 한다. 13:07 독립 scoped 재리뷰에서 I1/I2 ADDRESSED·신규C0/I0·코드Quality Approved를 확인했다. Task2 전체 승인은 재실험 artifact 검증 대기다.
- 실험: root가 같은 protocol digest와 새 source/input hash를 확인하고 calibration-fix1 실행을 허용했다. 수정 후 label-free support origin95개/6ticker, restart6개이며 원형48개 자료는 보존했다. 10ticker 기준 미달이므로 운영 기본값을 임의 승격하지 않는다.
- 재발 방지 / 배운 것: missing FINAL·반복 breach/reclaim·종료 test 제외를 회귀 테스트로 고정한다. raw null0과 전체 suite PASS만으로 상태 전이 계약의 정확성을 판단하지 않는다.

## (2026-10-21 13:26) [Decision] 관찰 의미 승인과 제품 배선 시작
- 맥락: 같은 protocol의 수정 실험이 완료됐고 독립 최종 리뷰가 Spec PASS / Quality Approved,C0/I0로 판정했다. root도 지정된 대표 차트의 가격/기준선·기울기를 재계산해 의미를 확인했다.
- 후보: 미래 utility로 표시값 재선택 / 사전 의미·빈도 기준의 선택만 배선.
- 선택: support buffer0/0 ATR, 재가속SMA20_TURN, 고정 약화식과 표시zone0.5 ATR만 의미 승인으로 전달한다. volume/contraction 및 failure/restart 미선정은 유지한다. utility는 별도이며 BUY/SELL gate로 사용하지 않는다.
- 기각: contraction0.9의 utility만 보고 default를 고르는 사후 선택. 새 정책 failure/restart를 연구 중심값으로 채우는 임의 활성화.
- 후속: 별도 구현자가 Task3에서 source별 terminal 문맥·실측Evidence를 연결한다. V1 정책과 Observation ON/OFF의 Signal/Opportunity/Planner 불변을 검증한다.
- ADR 후보? no

## (2026-10-21 13:31) [Decision] 미선정 schema와 제품 표시 설정 분리
- 맥락: ObservationParameters()를 기존 SETUP 생성부도 사용하므로 dataclass 기본값 변경은 관찰 배선 외의 SETUP identity까지 바꿀 수 있다.
- 후보: schema 기본값 변경 / 승인된 제품 표시 설정 별도 주입.
- 선택: schema의 None을 유지하고 Adapter에서 승인된 표시 설정을 별도 상수/팩토리로 주입한다. 같은 정책 비교와 기존 SETUP 생성 계약을 보존한다.
- 기각: 영구 ID alias·호환 저장 계층 추가. 이번 분리는 cross-version ID 영구 보존 요구가 아니다.
- ADR 후보? no

## (2026-10-21 13:42) [Bug] Observation 제품 배선의 결측·장중·source 격리 검증
- 증상: 연구 kernel만 연결하면 결측에서 관찰을 회복으로 닫거나 PROVISIONAL source를 표시하지 못했고, 과거 source anchor 복원 실패가 다른 관찰까지 제거할 수 있었다.
- 근원(root cause): 제품 표시의 미평가/미완성 경계와 source별 실패 격리가 순수 kernel 계약만으로 완성되지 않았다.
- 수정: 별도 구현자가 결측 상태 유지·장중 preview 분리·source별 terminal/anchor 문맥과 실패 격리·발생/현재 실측Evidence를 연결했다. 완성 FINAL 계산식·임계값은 유지했다.
- 검증: 필수91/covering324통과, 기존baseline ON/OFF 각각21MATCH, Evidence 제외FINAL231record동등. 독립Spec PASS/Quality Approved,C0/I0. 기존warning2개와 미계측latency·최종full검증은 후속으로 남긴다.
- 재발 방지 / 배운 것: 같은 종목의 여러 source를 현재Opportunity 하나로 덮지 않는다. terminal 후reclaim은 차트사실만 추가하며 매매기회는 부활시키지 않는다.

## (2026-10-21 13:43) [Decision] V2 미선정 설정의 명시적 미활성 처리
- 맥락: 현재 schema는 immediate failure의 None을 미선정으로 정의하며 별도 OFF 표현은 없다. 연구 비교에서 비활성처럼 평가한 None을 제품 활성화에서 OFF로 읽으면 계약이 섞인다.
- 후보: OFF field추가 / None을OFF로간주 / 현schema보존과명시거절.
- 선택: normal/buffer/restart와 immediate pair까지 명시한 V2만 실행한다. 불완전한 명시V2는 이유있는ValueError로 거절하고, 인자생략은V1과optional미활성사유를 반환한다.
- 기각: 새OFF모드 추가와 미선정값 임의보충. 운영선정이 미완료이므로 지금 지원범위를 확장하지 않는다.
- ADR 후보? no

## (2026-10-21 13:51) [Friction] 최종 리뷰 기준 사본의 범위 누락 보완
- 막힌 점: 최초 범위압축본과 Task2 사본은 일부 선행dirty파일을 포함하지 않았다. 원본복원helper는 누락/manifest형식 불일치에서 실패했고 해당부분산출물을 성공으로 취급하지 않았다.
- 임시 대응: 실제최초status·압축본목록·각작업diff를대조했다. 압축본149개와 최초cleanHEAD317개, Task0~2에서미변경임을검증한Task3시작사본6개로472원본을새디렉터리에복원했다. 파일별hash/provenance를기록하고 사용자checkout은변경하지않았다.
- 개선 아이디어: 최초capture에서미커밋작업을포함한전체대상파일과clean파일을함께보존한다. 실패한부분사본에는유효manifest를만들지않고최종리뷰에서사용하지않는다.

## (2026-10-21 13:52) [Bug] V2 WATCH의 미완성 봉·동적 지지·origin 계보 검증
- 증상: V2 제품 배선 중 PROVISIONAL WATCH가 다음 FINAL 봉의 완료 WATCH로 남거나, 당일 Supertrend DOWN에서 전날 UP band로 reversal을 만들 수 있었다.
- 근원(root cause): 순수 support kernel의 FINAL 상태 보존과 제품 WATCH의 preview 상태·당일 동적선 자격은 서로 다른 경계였다.
- 수정: V2 preview 결과를 반환한 뒤 replay 상태를 복원하고, preview의 지지선 선택에는 당일 동적 값만 복사해 사용한다. WATCH는 선택 지지의 명시 origin과 source 계보를 보존하며 SMA50→breakout→SMA150 전환 후에도 각 reversal의 origin/low를 분리한다.
- 검증: 경계별 RED 후 Signal 테스트 51 passed. 요구 범위+Runner는 직전 231 passed이며 동결 V1 Product projection 21건이 일치했다. 최신 전체 집중 재검증과 최종 상태는 Task4 report에 기록한다.
- 재발 방지 / 배운 것: PROVISIONAL 표시와 FINAL 상태 확정, dynamic 당일 값과 WATCH origin을 분리해 검증한다. 기존 V1·SMA150_EXIT detector·운영 미선정값은 유지한다.

## (2026-10-21 14:01) [Bug] V2 reversal의 완료봉 High 참조에서 PROVISIONAL 제외
- 증상: FINAL WATCH High=122 뒤 PROVISIONAL High=130이 있으면 다음 Close=124에서 FINAL 봉만 재생한 경우와 reversal 결과가 달랐다.
- 근원(root cause): WATCH 객체 rollback 이후에도 raw frame의 미완성 High를 lookback slice가 참조했다.
- 수정: V2는 FINAL 완료봉 High만 누적하여 마지막 N봉을 참조한다. FINAL 평가와 PROVISIONAL preview가 같은 완료봉 기준을 사용하며 V1 분기는 유지했다.
- 검증: 1봉/2봉·FINAL/PROVISIONAL·과거 FINAL High의 차단 경계 8조합에서 RED 6 failed/2 passed → GREEN 8 passed. covering 241 passed/1 deselected, Ruff·diff check 통과. 기존 경고 2건과 최종 full suite는 후속 경계다.
- 재발 방지 / 배운 것: 객체 상태 복원과 데이터 참조의 finality를 함께 검증한다.

## (2026-10-21 14:05) [Decision] Observation 출력에 실제 평가 설정 전달
- 맥락: 빈 history만으로는 미발생·OFF·미선정·실패를 구분할 수 없고, 기본 설정 추정은 사용자 지정값을 잘못 표시할 수 있다.
- 후보: Runner private 조회 / 기본값 추정 / 계산 결과에 표시용 설정 동봉.
- 선택: StrategySignalBundle에 optional 활성 여부·실제 설정 payload를 추가하고 adapter가 채운다. renderer와 snapshot은 이를 소비하며 Signal fingerprint나 판단 입력에는 넣지 않는다.
- 기각: private 내부 조회와 AnalysisStrategyResult 중복 설정. source가 없는 기존 bundle의 설정은 확인 불가로 표시한다.
- ADR 후보? no

## (2026-10-21 14:05) [Decision] 신구 비교를 운영 선정과 분리
- 맥락: failure/restart 운영값이 UNRESOLVED이므로 V2를 운영 기본값처럼 실행할 수 없다.
- 후보: V2 임의 기본활성 / 비교 생략 / 출력 확인 전에 단일 진단 profile 고정.
- 선택: normal2·buffer0·immediate1.5/0.25·restartA를 명시한 연구 전용 예시로 비교한다. 기존 후보의 단순 조합이며 최적값·동결연구중심OFF·운영선정으로 주장하지 않는다.
- 기각: 비교 결과에 맞춘 profile 변경. 잘못되면 예시 차이와 사례를 재실행해야 하지만 운영 정책은 바뀌지 않는다.
- ADR 후보? no

## 실행 중 판정과 영향

아래는 SDD ledger의 `Ruling`을 사람이 읽을 수 있게 정리한 목록이다. 검증 결과와 운영 선정은 별도이며, 미확정 항목의 승격을 뜻하지 않는다.

| 판정 | 이유 | 잘못되었을 때 비용·후속 조치 |
|---|---|---|
| 현재 feature checkout에서 순차 구현 | 선행 미커밋·untracked 구현 보존 | 보존 baseline으로 이번 변경 범위를 다시 식별 |
| commit/push/merge·신규 외부 호출 없음 | 승인된 로컬 구현 범위 준수 | 통합·추가 수집은 별도 승인 필요 |
| HEAD 대신 시작 사본으로 리뷰 | HEAD에 선행 작업이 없음 | 사본 hash·변경 목록 재검증 |
| 작업 workspace 보존 | 미커밋 상태를 Git만으로 복구할 수 없음 | 보존 공간을 사용하지만 임의 삭제하지 않음 |
| 누락 interface만 보완, 최초 cycle gate 강화 금지 | 사용자 확정 조건 보존 | 연구 계약·타입 보완을 재작업 |
| 설정 mode를 제한하고 미선정은 None | schema 선언으로 운영값을 선택하지 않음 | 활성화 전 versioned schema 변경 필요 |
| 첫 cycle cohort와 최소 표본 유지 | 결과를 보고 표본 기준을 완화하지 않음 | V2 승격에 별도 확대 연구 필요 |
| touch 없이 gap 하락한 첫 FINAL breach도 support-test origin | 실패 사례가 연구에서 빠지는 것 방지 | origin 수정 후 동결·연구 재실행 |
| 첫 cycle 제한은 cycle 의존 family에 적용 | 일반·source별 Observation의 독립성 보존 | 해당 family protocol·cohort 재검증 |
| 결함 있는 원형 실험은 중단·보존하고 같은 protocol로 재실행 | 누락된 risk set으로 정책 선정 불가 | 필요 시 원형 진단 실험을 별도로 반복 |
| schema default와 제품 표시 preset 분리 | 미선정 의미와 SETUP 생성 경계 유지 | 표시 배선 수정, 영구 ID 호환 계층은 추가하지 않음 |
| 불완전 명시 V2는 거절, 기본은 V1 | immediate None은 OFF가 아니며 운영 선정 미완료 | explicit OFF를 지원하려면 별도 versioned 표현 필요 |
| 최종 리뷰 원본을 출처별 사본으로 재구성 | 최초 압축본의 일부 선행 dirty 파일 누락 | provenance·diff를 다시 구성한 후 readiness 판단 |
| 비교 B는 사전 고정 단일 연구 예시 | 미선정 V2를 운영 기본값으로 오인하지 않음 | 예시 설정 변경 시 비교·사례 재실행, 운영 영향 없음 |
| 실제 Observation 설정을 결과에 표시용으로 동봉 | OFF·미선정·미발생을 추정으로 구분하지 않음 | 표시·snapshot metadata 수정, 매매 판단 입력에는 사용하지 않음 |
| 표시 metadata는 별도 검증하고 나머지 전체 실행 결과는 불변 비교 | ON/OFF 설정 자체는 의도적으로 다르며 Product 판단은 같아야 함 | metadata 계약 재검토, Product 비교 범위는 완화하지 않음 |
| 무결성 검사만 수정한 뒤 원실행 hash와 별도 동등성 receipt 보존 | 긴 계산을 중복하지 않고 실행 코드의 출처 유지 | 허용 함수 외 AST·제품 hash가 다르면 compare/cases 재실행 |
| 최종 코드 리뷰와 offline 비교를 병행하되 최종 승인 gate는 유지 | 읽기 전용 통합 검토 중 계산 대기를 줄임 | 후속 변경은 범위 재리뷰와 source 동등성 확인 필요 |
| 최종 fixwave는 FINAL pivot 격리와 거래량 실측 보완에 한정 | 독립 재현된 새 결함과 명세상 Evidence 누락을 해결 | ALL_FINAL 동등성 근거가 부족하면 해당 검증 재실행 필요 |

## (2026-10-21 14:29) [Bug] 부분 미선정 설정과 OFF 상세 출력의 구분
- 증상: break/reclaim 중 하나만 선택된 경우 일부 Observation을 미발생으로 표시했고, OFF·진단 실패 시 상세 모드에서 알려진 실제 설정을 생략했다.
- 근원(root cause): 표시 계층이 detector의 두 설정 필수 조건과 달리 단일 설정만 검사했고, 조기 반환이 상세 설정 출력을 건너뛰었다.
- 수정: 별도 구현자가 5개 이탈·회복 code의 필수 설정을 함께 검사하고, OFF·오류·활성 확인 불가에도 알려진 설정을 상세 출력한다. 판단 로직·임계값은 변경하지 않았다.
- 검증: 대상 RED13실패/3통과→GREEN16통과, 주변92통과. 독립 재리뷰 Spec PASS/Quality Approved, C0/I0. 기존 warning2개는 후속 관리 항목으로 유지한다.
- 재발 방지 / 배운 것: 표시 계층의 미평가 판정은 실제 detector 실행 조건과 함께 검증한다.

## (2026-10-21 14:38) [Decision] 최종 회귀의 표시 계약과 실행 출처 분리
- 맥락: fresh 전체 테스트는 2,123통과/1실패였고, 실패의 재귀 diff는 ON/OFF·실제 설정 metadata 네 값뿐이었다. 독립 리뷰 중 baseline의 예상 외 nested sources 파일을 놓치는 무결성 검사 경계도 확인했다.
- 후보: Product 비교 완화 / 전체 분석 재실행 / 표시 계약만 분리하고 무결성 경계 회귀 보완.
- 선택: 별도 구현자가 표시 metadata를 별도로 assert하고 나머지 전체 결과 동등 비교를 보존한다. 무결성 검사는 최상위 sources만 제외한다. 원 compare/cases manifest는 수정하지 않고, 허용 함수 외 AST와 제품 hash가 동일한지 확인하는 별도 receipt를 붙인다.
- 기각: 원실행 source hash를 새 hash로 덮기, 표시 차이를 매매 판단 변화로 보고하기, 계산 결과가 같은지 확인 없이 실행 결과를 재사용하기.
- 후속: 수정 후 fresh 전체 테스트와 동일 독립 리뷰어의 최종 gate. compare는 진행 중이며 완료 수치를 예측해서 기록하지 않는다.
- ADR 후보? no

## (2026-10-21 14:50) [Bug] 최종 회귀의 표시 계약·artifact 검사 보완 검증
- 증상: 전체 실행 identity 테스트가 ON/OFF의 실제 표시 설정까지 동일하다고 요구했고, artifact 검사에서는 중첩 `foo/sources`의 예상 외 파일도 제외했다.
- 근원(root cause): 표시 계약과 매매 판단 불변 계약의 범위 충돌, 최상위 sources와 임의 하위 sources를 혼동한 경로 제외식이었다.
- 수정: 별도 구현자가 두 metadata를 별도 assert한 뒤 나머지 전체 identity 비교를 유지했다. 무결성 경계는 최상위 sources만 제외한다.
- 검증: 후속 focused107통과, fresh 전체2,125통과/15제외/기존경고2개/180.00초. 동일 독립 리뷰어가 I1·테스트 계약을 ADDRESSED로 판정하고 AST·source·baseline 동등성 receipt를 직접 확인했다. 최종 비교·통합 리뷰는 아직 진행 중이다.
- 재발 방지 / 배운 것: source hash가 달라진 과거 실행은 원출처로 보존하고, 변경 범위의 동등성 근거를 별도로 기록한다. 이후 제품 수정은 새 검증이 필요하다.

## (2026-10-21 14:52) [Decision] 최종 통합 리뷰의 단일 수정 범위
- 맥락: 최종 독립 리뷰는 C0/I1/M2였다. 미확정 pivot이 FINAL 구조 사건·최초 cycle을 바꾸는 결함과 거래량 사건의 실측 Evidence 누락을 재현했다.
- 후보: 전체 indicator/rolling 재설계 / 입력에서 PROVISIONAL 금지 / 신규 구조 사건의 FINAL 이력 경계와 필수 Evidence만 보완.
- 선택: 기존 구현자에게 I1/M1 단일 fixwave를 배정했다. pivot origin·확인 창·이전 관계와 원래 날짜 매핑을 검증하며, 기존 V1·EXIT·최초 cycle 조건·threshold는 유지한다. M2 evaluator/script 분할은 후속 유지보수로 남긴다.
- 기각: 미확정 입력 금지 우회, ALL_FINAL 결과를 수정본 실행으로 재표기, 전체 연구 반복. 현재 compare의 모든 입력은 FINAL이지만 수정 후 동등성 근거를 별도로 요구한다.
- 후속: RED/GREEN·covering·수정 후 fresh 전체 테스트·동일 reviewer scoped 재리뷰. 현재 전체 통합 승인은 보류다.
- ADR 후보? no

## (2026-10-21 15:02) [Bug] FINAL 구조 계산 격리와 거래량 실측 근거 보완 검증
- 증상: 중간 PROVISIONAL 고가가 이후 FINAL HH/LH와 V2 최초 cycle을 바꿨고, 거래량 확장 사건에는 ratio/threshold 외 실제 가격 변화·거래량·기준 거래량이 빠져 있었다.
- 근원(root cause): pivot 계산 입력이 raw 전체였고 확인일 finality만 검사했다. 거래량 사건은 이미 계산된 실측값을 Evidence로 전달하지 않았다.
- 수정: 공통 pivot 함수의 선택적 FINAL mask와 원 index/date 매핑을 두 신규 소비자가 공유한다. UP/DOWN 거래량 사건에 현재 제외 직전20봉 평균을 포함한 실측 Evidence를 추가한다. V1 기존 지표·EXIT 본체·정책 설정은 유지했다.
- 검증: RED14실패/1통과→GREEN15통과 및 추가2회귀, covering299/root독립17통과. 수정후fresh전체2,142통과/15제외/기존경고2개/175.85초. 21입력의 ALL_FINAL pivot 전체필드 일치와 실제7prefix의 새Runner/adapter JSON·Opportunity/Planner·renderer 원본일치를 별도 receipt로 검증했다. 독립 재리뷰·최종 비교 gate는 아직 남아 있다.
- 재발 방지 / 배운 것: 사건의 확인일뿐 아니라 원봉·확인 창·이전 관계도 확정 이력인지 확인한다. 기존 원실행은 원source/hash로 보존하며 제한된 후속 동등성 근거를 구분한다.

## (2026-10-21 15:12) [Friction] 병행 사용되는 연구 로그의 검증 시점 구분

- 막힌 점: 최종 확인에서 실제 연구 JSONL의 현재 hash가 Task5의 실행 전후 hash와 달랐다. 파일 mtime은14:44이며 이후 실제 check/brief 기록이 포함돼 있었다.
- 임시 대응: read-only 누적 SHA 검사로 기존47줄177,795bytes가 Task5 hash와 정확히 일치하고, 현재84줄5,581,041bytes는37줄 추가된 상태임을 확인했다. 원본은 보존돼 있고 작성 주체는 확인하지 않았다. 삭제·복원하지 않는다.
- 검증 경계: Task5의 당시 실행 전후 불변 근거와 전체 작업 기간 불변 주장을 구분한다. tests autouse fixture는 recorder를 tmp_path로 격리하고, 이번 compare/cases/동등성 verifier는 recorder를 호출하지 않는다. 병행 실행의 외부 호출은 이번 작업에 귀속하지 않는다.
- 개선 아이디어: 공유 진단 로그의 전체 hash 대신 검증 당시 prefix의 byte 길이·hash와 실행 범위를 함께 기록한다. 이번에 별도 저장 안전장치를 추가하지 않는다.

## (2026-10-21 15:18) [Decision] 최종 비교 결과와 운영 선정 분리

- 맥락: 원 offline compare가 exit0·2,491.451초로 완료됐다. baseline21/21, V1·명시V2의 Observation ON/OFF각21/21, 기존SMA150_EXIT21건 의미동등을 확인했다. root도 비교5개·사례14개·baseline23개 artifact hash와12,418개 날짜별 차이의 종목별합을 직접 대조했다.
- 후보: 관찰·진입 건수 증가를 운영 승격 근거로 사용 / 불변성과 정책 차이만 검증 결과로 기록.
- 선택: V1 WATCH1,336·reversal690과 명시V2 WATCH5,914·reversal2,554는 보존history의 빈도 차이로만 기록한다. 날짜별 압축행과 분모를 구분하고 수익성·우열·현재시장 성능으로 확대하지 않는다. 실패·재시작 운영값은 UNRESOLVED이고 기본은V1이다.
- 기각: 동일 연구 재선정·calibration/compare 중복 실행·원manifest의 source hash 갱신. 수정 후 ALL_FINAL 동등성 및 실제7prefix 재실행은 별도receipt로 남겼다.
- 후속: 기존 Task6·통합 독립 reviewer가 최종artifact/docs/provenance만 검토한다. 이후root의 상태 마감과 사용자보고, commit/push/merge는 실행하지 않는다.
- ADR 후보? no

## (2026-10-21 15:25) [Decision] 로컬 구현과 독립 검증 완료 판정

- 맥락: 같은 Task6 reviewer와 통합 reviewer가 최종artifact/docs/provenance gate를 모두 PASS로 마감했다. root가 최종 review 문서와 판정·실행 근거를 읽어 확인했다.
- 선택: Task0~6 완료와 `SPEC_PASS / QUALITY_APPROVED_WITH_DEFERRED_MINOR`를 기록한다. 잔여 Critical0/Important0/Minor1은 연구 evaluator/script 책임 분리이며 비차단 후속 유지보수로 남긴다. 수정후전체2,142통과·기존경고2개, 21입력 불변 비교, 실제7prefix와 최종source동결을 근거로 한다.
- 권한·검증 경계: Observation은 기본ON, 새cycle/Support Ladder는 명시V2연구경로이고 기본PullbackV1이다. failure/immediate/restart·utility·수익성·새OOS는 미확정이다. canonicalservice/세CLI live·사례5일Score·productionlatency·추가ALAB/COHR현재자료는 이번 증명에 포함하지 않았다.
- 제외항목 처리: JSONL의 작성주체와 전체무변경은 주장하지 않고 원prefix보존만 확인했다. manifest외부서명은 새기능으로 도입하지 않았다. 저장cache·보유장부·매도권한 확대는 없으며 원실행·후속receipt를 구분한다.
- 후속: 운영 전환이나 추가 연구·수집은 별도결정이다. commit/push/PR/merge·DB수정·실계좌주문은 실행하지 않았다. 미커밋 선행변경과 검증workspace는 그대로 보존한다.
- 근거: SDD `task-6-review.md`·`final-review.md`, [최종 검증](../references/2026-10-21-trading-observation-v1-validation.md). root가 plan/ledger/active-context를 완료 상태로 갱신했다.
- ADR 후보? no

## (2026-10-21 16:47) [Friction] ALAB 실제 출력으로 관찰 개선과 진입 정책 간극 재확인

- 맥락: 사용자가 개선 계기였던 ALAB 재검증을 요청했다. 실제CLI check entry exit0과 동일ALAB/SPY2y입력의V2서비스를 실행하고 보존했다. 제품설정·코드는 변경하지 않았다.
- 확인: 10/20 FINAL284.80/SMA150285.67·첫종가이탈이다. 기본V1현재WATCH없음, 명시V2연구는10/15 SMA150WATCH·ACTIVE/SOFT_BREACH1회, SupertrendDOWN별도경고·새반등Signal없음이다. 최근5일점수-65/-40/-40/-85/-85도실측했다.
- 남은 간극: 양쪽10/06breakoutsource age10·실행기준376대비-24.26%인데 Productionv1 ALLOW가유지된다. bull시장과extension상한+5%만검사하고Shadow는gate가아니기때문이다. Shadow는돌파선이탈·큰하락으로HIGH_RISK다. 새WATCH구현PASS를기존ALLOW정책개선으로설명하지않는다.
- 보조도구오류: 최초harness는제품실행·assert후feature출력에서SwingFeatureFrame의.frame경계를누락했다. 로컬진단script만수정하고보존CSV/ChartBundle/결과로socket차단offline정리를완료했다. 추가provider조회나제품수정은없다.
- 후속: 관찰개선은확인,과거ALLOW문제는미해결로사용자보고한다. 신규gate·운영V2승격은별도결정이며자동수정하지않는다. 상세와raw증거는 tmp/alab-validation-20261021.sfj1jr/report.md.

## (2026-10-21 23:33) [Bug] 명시 V2 돌파선 지지 Signal의 Backtest 호환 보완

- 증상: 실제 COIN public Backtest가 2024-11-11 눌림목 Signal에서 `Missing pullback support evidence`로 중단됐다.
- 근원(root cause): detector가 전달하는 `PRIOR_BREAKOUT_LEVEL`이 Backtest의 허용 지지 Evidence 목록에 빠져 있었다.
- 수정: 별도 구현자가 목록에 해당 종류를 추가했다. 기존 source ATR·stop 공식·손실 제한·비용·lot/R·운영 기본 V1은 유지하고 Important1의 대표 Signal 선택은 건드리지 않았다.
- 검증: positive RED2실패→Backtest61통과, root 전체2,165통과/15제외/기존경고2(190.26초). root는 원래 COIN 전체1,371봉 public 실행도 완료하고 11/11Signal→11/12시가310.04998779296875·2주를 확인했다. 별도 scoped reviewer Spec PASS/Quality 승인(C0/I0/M0), 누락·None·NaN·±Inf 거부 및 메모리 mutation 회귀 확인.
- 재발 방지 / 배운 것: 새 지지 종류는 detector 출력과 Backtest 소비를 함께 검증하며 실제 raw→Signal→T+1체결 회귀를 남긴다. failure/restart 운영 선정·수익성·새 시세수집과 구분한다. 이번 후속 수정은 미커밋이며 Important1은 미수정이다.

## (2026-10-22 10:56) [Decision] 복수 Entry 대표 선택을 공통 정책으로 통일

- 맥락: Opportunity의 history 마지막 선택과 Planner의 type 우선 선택이 달라 ALLOW여도 매수 후보가 누락됐다.
- 후보: 기존 분리 선택 유지 / 최신일·동일일 공통 우선순위 / Signal별 모든 기회를 별도 평가.
- 선택: 사용자 승인으로 최신일 우선, 동일일 과열후회복→눌림목반등→추세돌파→바닥회복을 공유한다. 대표 선택 후 평가하고 하위·과거 source로 우회하지 않는다.
- 기각: 기존 분리(소비자 불일치), 모든 기회 별도 평가(이번 수정 범위 초과). type 순위의 수익성은 미검증이다.
- 경계: Signal history·ID·source별 취소조건, 오늘 ALLOW와 exact source guard, 청산·축소 우선 및 기존 Backtest 수정은 보존한다.
- ADR 후보? no

## (2026-10-22 11:06) [Bug] 복수 Entry의 Opportunity·Planner 대표 불일치 해소

- 증상: 실제 COIN 2024-07-22의 눌림목/돌파가 함께 발생하면 ALLOW여도 Planner source guard 때문에 매수0이었다.
- 근원(root cause): Opportunity는 같은 날 history 마지막 Entry, Planner는 높은 type 순위 Entry를 선택했다.
- 수정: Strategies의 chart-only 공통 선택 함수를 공유해 최신일·동일일 합의 순서를 적용했다. 대표의 실패·종료 시 하위·과거 source로 우회하지 않으며 기존 source별 −1ATR·terminal·청산/축소·today/exact-source guard와 history/ID를 보존했다.
- 검증: 신규 RED12실패→covering199통과, root 전체2,193통과/15제외/기존경고2(191.01초). 전체 Ruff·변경Python8 format·diff·CLI help 통과. 독립 Spec PASS/Quality 승인(C0/I0/M0), 제품/테스트 hash 불변. root 실제 COIN502봉·명시 synthetic bull·테스트계좌에서 source PULLBACK·ALLOW·매수후보50주 확인. 실제 주문·새 provider 조회 없음.
- 재발 방지 / 배운 것: 모든 Signal 보존과 대표 source 선택을 분리하고 실제 adapter→Opportunity→Planner 회귀로 검증한다. frozen INTC는 source/anchor의 승인 차이만 비교 보완하고 원본 artifact/non-gate를 유지한다. 기존 Backtest 수정도 hash 보존, 두 수정은 미커밋이다.

## (2026-10-22 14:26) [Decision] 전략 관련 변경만 PR로 통합하고 이력 보존

- 맥락: 사용자가 PR 생성·독립 리뷰 후 문제 없으면 merge·main pull을 승인했다. 원격 main 이후 33개 커밋에 Notebook 관련 1개가 섞였고 로컬 main은 동등 patch의 별도 이력을 갖고 있다.
- 후보: 기존 branch 전체 publish / 관련 커밋만 별도 PR branch에 통합 / 로컬 main 이력 강제 덮어쓰기.
- 선택: 원래 feature branch를 보존하고 Notebook 커밋을 제외한 별도 PR branch를 만든다. 최종 head의 독립 리뷰와 CI가 통과하면 merge하고, 기존 main은 backup ref에 보존한 뒤 원격 main을 pull한다.
- 기각: Notebook 동반 publish(범위 밖), 강제 덮어쓰기(이력 손실 위험). 무관한 dirty/untracked는 staging·정리하지 않는다.
- 검증 보완: CI 전체 format의 기존 4파일은 기계적으로 정리하고 AST 동일성을 확인했다. 전략·보유·수량 규칙 변경은 없다.
- ADR 후보? no

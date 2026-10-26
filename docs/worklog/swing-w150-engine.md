# Worklog — swing-w150-engine

- **Branch**: feature/swing-w150-engine
- **Started**: 2026-09-30
- **Status**: in-progress
- **Links**: [구현 계획](../superpowers/plans/2026-09-30-swing-w150-engine.md) · [백테스트 결과](../backtest/results-log.md)

---

## (2026-09-30 14:21) [Decision] 재료는 tools/technical 한 곳, 해석은 pipelines
- 맥락: SWING_W150 v3 엔진화 위치를 정하다가, 백테스트 스크립트가 지표를 자체 계산하고 있고 jarvis `IndicatorCalculator`와 식이 다름을 확인(ATR: 14일 단순평균 vs pandas_ta Wilder, 슈퍼트렌드: 자체 구현 vs pandas_ta). SMA는 동일. 별도 `swing/features.py`를 두면 재료가 두 벌이 된다.
- 후보: A 지표를 jarvis 쪽으로 통일하고 백테스트 재검증 / B 백테스트 식을 별도 이름(ATR_SMA14 등)으로 재료층에 병존
- 선택: A — 원칙 "재료는 한 곳에 최대한 재사용, 재료 해석(레시피·상태)은 따로(pipelines)". ATR·슈퍼트렌드 정의가 시스템에 하나만 존재. 확정 저점(3일 지연)·구조 붕괴처럼 없는 재료만 tools/technical에 추가.
- 기각: B(같은 이름 지표의 두 정의 공존, 화면 ATR과 손절 ATR 불일치)
- 부수 발견: `src/tools/brief/`는 brief 파이프라인 전용 모델·정렬·렌더와 통신 코드(name_resolver)로, tool이 아님 → `pipelines/brief/` 이동은 별도 리팩터링 PR 후보.
- 다음: jarvis 지표로 v3를 재실행해 미사용 기간 1.02R 유지 여부 확인 → 유지 시 그 결과로 정답지 생성.
- ADR 후보? yes (재료/해석 분리 원칙)

## (2026-09-30 14:40) [Decision] jarvis 지표로 통일해도 v3 성과 유지 — 확정
- 맥락: 옵션 A 전제 확인. `src/backtest/universe_jarvis_indicators.py`로 ATR(Wilder)·슈퍼트렌드(pandas_ta)만 교체, 규칙·설정·73종목·기간은 universe_validate와 동일.
- 결과: 원본 재현 370회 1.02R(기록과 일치) / jarvis 지표 367회 1.02R, 95% 구간 [0.71,1.35], 상위10제외 0.65 동일. 기존 기간 460회 0.61R → 459회 0.61R. 전체 981건 중 진입 일치 929건, 진입·청산 일치 925건. S 0.82→0.81R, D 0.78→0.79R.
- 선택: 재료를 jarvis `IndicatorCalculator` 기준으로 통일. 정답지는 이 교체 버전(`prepare_jarvis` + 기준 `simulate`)으로 생성.
- ADR 후보? no (앞 결정의 검증)

## (2026-09-30 15:10) [Pivot] 전략은 pipelines가 아니라 별도 strategies 레이어
- 이전 접근: 해석(레시피·상태)을 `src/pipelines/swing_w150/`에 둠 → quick_check·brief가 다른 파이프라인을 호출하는 구조.
- 전환 이유: SWING_W150은 전략이고, 파이프라인은 전략을 가져다 쓰는 쪽이어야 한다(사용자 지적). 나중에 screener·backtest도 같은 전략을 쓴다.
- 새 접근: `providers → tools(재료) → strategies(전략) → pipelines → cli`. `src/strategies/swing_w150/{rules,engine,models}.py`. strategies는 tools만 import. 기존 `tools/technical/strategies/`(하루치 점수 부품)와 이름이 겹치지만 정리는 별도 PR. CLAUDE.md·AGENTS.md 아키텍처 표 갱신.

## (2026-09-30 15:10) [Decision] 한국 종목도 표시, 미검증 표기 없음
- 맥락: 백테스트는 미국 73종목만. check/brief에는 한국 종목도 들어옴.
- 후보: A 미국만 / B 한국도 "미검증" 표기 / C 한국 백테스트 먼저
- 선택: 미국·한국 모두 동일하게 표시, 미검증 표기 없음 — 사용자 결정.
- 기각: A(한국 참고 정보 없음), B(표기 불필요), C(범위 확대)
- ADR 후보? no

## (2026-09-30 15:25) [Friction] Sonnet 서브에이전트 호출 실패
- 막힌 점: 구현 위임용 Sonnet(`claude-sonnet-5-5`)이 model_not_found(404)로 즉시 종료. 부분 산출물 없음.
- 임시 대응: 사용자 승인 후 현재 세션(Opus)이 직접 구현.
- 개선 아이디어: 위임 전 사용 가능한 모델을 짧은 호출로 먼저 확인.
- 후속: 사용자 지시로 Orca 터미널(메인 체크아웃의 Claude Code 세션)에 2단계 구현을 supervised 위임(run_7ee16958f711 / task_dc34b3c49b2e). 작업 경로는 feature 워크트리 절대경로로 고정, 메인 체크아웃 수정 금지를 spec에 명시. 이 세션은 감독·골든 검증·리뷰 담당.
- 후속2: Orca 워커 터미널이 착수 직후 종료(operator_close, 변경 없음 확인) → 사용자 지시로 서브에이전트(현재 세션 모델)에 같은 spec으로 재위임.

## (2026-09-30 16:30) [Decision] 2단계 검증 + 대기 상태 보완 + 3단계 표시
- 검증: 서브에이전트 구현을 직접 재실행 — 골든 4종목(COIN 6·AMAT 12·PYPL 15·UPST 10건) 허용오차 1e-9 그대로 통과, 전체 1418 → 최종 1430 passed, ruff clean. pivots.py는 원본 confirmed_pivots와 4종목 전 봉 일치(서브에이전트 확인).
- 보완 1(대기 막힘): 오늘 종가가 이미 직전 N봉 고가 위면 규칙상 내일은 '첫 돌파'가 아니라 신호 불가 → `breakout_blocked` 필드와 "이미 X 위(첫 돌파 아님), 기준 아래로 되돌린 뒤 재돌파 필요" 문구. PYPL 2017-02-24로 고정. D 경로는 정답지에 사례가 없어 같은 로직만 적용.
- 보완 2(골든 미고정 상수): S 거래량 1.4배 경계는 정답지 기간에서 매매를 바꾸지 않아 골든이 못 잡음 → rules 단위 테스트로 경계(정확히 1.4배는 불인정) 고정.
- 3단계: `summarize(df, ticker)`(실패 시 logger.warning 후 None)를 quick_check("스윙 전략 (참고)" 섹션)·brief(항목 한 줄)에 배치. action·bucket 불변을 brief 테스트로 확인. 한국 종목은 가격 소수점 없이 천 단위 구분(`is_korean_ticker` 재사용).
- 실데이터: NVDA 보유(S) 8/28 227.11 진입·손절 199.26, 005930 대기(S) 288,000, HOOD 대기(S) 126.74.
- ADR 후보? no

## (2026-10-01 16:02) [Friction] PreToolUse hook이 worktree branch를 main으로 오인
- 막힌 점: `workdir`를 feature worktree로 지정한 `git push -u origin feature/swing-w150-engine`이 main 직접 push 금지 hook에 차단됨. 실제 worktree branch는 `feature/swing-w150-engine`, HEAD는 `4f20f57`임.
- 임시 대응: hook이 실행되는 메인 checkout의 CWD에 의존하지 않도록 `git -C <feature-worktree> push ...`로 대상 repository를 명령에 명시.
- 개선 아이디어 (스킬·훅·프롬프트): hook이 `.tool_input.workdir` 또는 `git -C` 대상에서 branch를 판정하도록 수정.

## (2026-10-01 19:00) [Decision] 측정·전략·포지션 계획을 3계층으로 분리
- 맥락: 기존 `TechnicalVerdict`는 점수 계산과 action을 결합하고, `PlaybookEngine`은 실제 보유 여부로 gate/exit를 배타 선택하며 sizing까지 수행한다. 이 구조에서는 같은 종목도 파이프라인과 보유 여부에 따라 전략 판단이 숨겨지고 전략별 성과 비교가 어렵다.
- 후보: A 기존 Playbook을 최종 action·수량 authority로 유지 / B 전략 판단과 수량 계산을 완전히 분리 / C 모든 전략 결과를 하나의 합의 action으로 즉시 병합
- 선택: B — Analysis는 가격·지표·versioned score만 산출하고, 모든 Strategy는 보유·계좌와 무관한 `entry`(`ALLOW/WATCH/BLOCK/NOT_EVALUATED`)와 `exit`(`HOLD/REDUCE/EXIT/NOT_EVALUATED`)를 동시에 반환한다. `PositionPolicy`가 선택 전략의 intent를 목표 비중으로 바꾸고, `PositionPlanner`만 실제 보유·계좌를 읽어 주문 수량을 계산한다.
- 세부: `StrategyVerdict`는 strategy id/version, ticker, as-of, entry, exit, data status, reason, optional strategy state를 가진다. target exposure·quantity·실제 holding은 제외한다. 모든 production 전략을 `StrategyRunBundle`로 check/analyze/brief에 동일 노출하고 5/10/20 거래일 episode 성과를 별도 추적한다. 초기 선택 전략은 `PLAYBOOK_V1`, SWING_W150과 기존 technical action 및 `OverheatCycleStrategy`는 병렬 shadow로 둔다.
- 기각: A(전략 판단과 계좌 의존 수량이 재결합), C(entry/exit 충돌과 전략별 근거·성과 소실). `HoldingCycleOverlay` 명칭은 실제 보유 의존으로 오해되어 `OverheatCycleStrategy`로 변경한다.
- ADR 후보? yes — ADR-0010의 Playbook 최종 판단·sizing 책임을 명시적으로 supersede해야 한다.

## (2026-10-01 19:25) [Decision] 5축 Scorecard에 구조화된 상세 근거와 최근 20거래일 Trigger를 보존
- 맥락: 단일 점수만 다음 계층에 넘기면 cRSI 과열·상단밴드 이탈 같은 중요한 원인 정보가 사라지고, 오늘 신호만 표시하면 최근 발생한 진입·위험 사건의 맥락을 놓친다.
- 후보: A 영역 점수만 전달 / B 점수와 사람이 읽는 문자열만 전달 / C 점수·metric·observation·trigger를 구조화해 전달
- 선택: C — 추세·구조·모멘텀·수급/거래량·안전도 각 영역은 `score`, `data_status`, 원본 `metrics`, 현재 상태 `observations`, 근거 `evidence`를 모두 보존한다. 기본 출력은 중요도가 높은 observation/evidence를 요약하고 상세 출력은 전체 값을 사용한다.
- Trigger: 상태와 사건을 구분한다. 예를 들어 `cRSI 과열`은 observation, `cRSI 상단밴드 하향 이탈`은 dated trigger다. 모든 production trigger는 발생일, `bars_ago`, 방향, source, 당시 값과 기준값, 현재 유효 상태를 담아 최근 20거래일(`bars_ago <= 20`)까지 전달·표시한다. 반복 상태가 아니라 전환 event만 기록하고, 무효화된 사건도 숨기지 않고 상태를 표시한다.
- 기각: A(판단 근거 소실), B(파이프라인별 문자열 재해석과 성과 추적 불가)
- ADR 후보? yes — 새 Analysis/Strategy contract의 일부로 포함한다.

## (2026-10-01 23:45) [Decision] 방향성 지표는 값·기울기·전환을 함께 전달
- 맥락: 이동평균선, cRSI, MACD처럼 시계열 방향이 중요한 지표는 현재 값만으로 상승·하락·둔화·전환을 구분할 수 없다.
- 후보: A 사람이 읽는 방향 문구만 추가 / B 공통 directional metric으로 구조화 / C 전략마다 방향을 재계산
- 선택: B — 방향성 지표는 현재값과 함께 `direction`(`RISING/FALLING/FLAT/UNKNOWN`), `delta_1d`, `slope`, `slope_lookback_bars`, `acceleration`(`ACCELERATING/DECELERATING/STABLE/UNKNOWN`)을 보존한다. 지표 특성에 맞춰 이동평균선은 21거래일 percentage slope, cRSI·MACD 계열은 1일 변화와 5거래일 slope를 기본으로 하며 계산법과 flat threshold를 versioning한다.
- 관계와 사건: MACD선/Signal선/Histogram은 각각 방향을 가지며 선간 관계(`ABOVE/BELOW`)를 별도 observation으로 둔다. 골든·데드크로스, cRSI 밴드 교차, 이동평균선 방향 전환은 최근 20거래일 Trigger로 기록한다.
- 기각: A(계산 근거와 재사용성 부족), C(파이프라인·전략별 방향 판정 불일치)
- ADR 후보? yes — Analysis contract의 directional metric 규약으로 포함한다.

## (2026-10-02 09:30) [Decision] Observation 근거 소유와 Trigger·미보유 verdict 의미 보정
- 맥락: 설계 리뷰에서 영역 수준 Evidence와 Observation의 근거가 중복될 수 있고, `TriggerStatus.CONFIRMED` 및 미보유 종목의 ExitIntent 의미가 불명확함을 확인했다.
- 후보: A 기존 flat 모델 유지 / B Observation·Trigger가 각 근거를 소유하고 상태 의미를 축소 / C 미보유 종목은 EntryIntent만 반환
- 선택: B — Observation과 Trigger가 각각 자신의 Evidence를 소유하고, ScoreDimension은 점수용 `ScoreContribution`만 가진다. Trigger status는 `ACTIVE/INVALIDATED/EXPIRED`로 제한하며 발생 사실은 `occurred_on`으로 표현한다. 미보유 여부와 무관하게 모든 StrategyVerdict는 entry·exit 두 축을 반환하고, 미보유이면 PositionPlanner의 매도 수량만 0이 된다.
- Trigger 보강: SMA20/50, SMA50/150, SMA50/200, SMA150/200 골든·데드크로스를 최근 20거래일 production Trigger에 포함한다.
- 기각: A(근거 중복과 CONFIRMED 의미 불명확), C(보유 여부가 전략 출력에 다시 개입)
- ADR 후보? yes — Analysis/Strategy contract에 반영한다.

## (2026-10-02 09:31) [Friction] 전략 성과 SQLite 영속 저장 설계 누락
- 막힌 점: spec에 5·10·20거래일 shadow 성과를 기록한다고만 쓰고 저장소, schema, idempotency, maturity 처리 경계를 정의하지 않아 실제 추적 구현이 불가능했다.
- 임시 대응: `data/db/jarvis.db` 기반 전용 SQLite store와 AnalysisRun, StrategyVerdict, TriggerEvent, StrategyEpisode, StrategyOutcome, PositionPlan schema 및 transaction 규칙을 spec에 추가했다.
- 개선 아이디어 (스킬·훅·프롬프트): 성과 추적 설계 체크리스트에 persistence 위치, identity/unique key, maturity 갱신, 재실행 중복 방지, 보존 정책을 필수 항목으로 넣는다.

## (2026-10-02 11:54) [Decision] 후행 진입은 국면별 가격 한도와 구조 유효성으로 판정
- 맥락: Trigger 당일을 놓친 사용자가 며칠 뒤 확인해도 지금 진입 가능한지, 추격을 피하고 조정을 기다려야 하는지 안내해야 한다. `% + R + ATR` 복합 기준을 별도 에이전트가 SWING_W150 Trigger 806개로 검증했으나 A안보다 per-signal expectancy를 안정적으로 개선하지 못했다.
- 후보: A 국면별 가격 한도 / B 전 국면 +5% / C `% + R + ATR` 복합 차단
- 선택: A — `EntryOpportunityPolicy V1`은 최대 20거래일 동안 강세장에서는 기준 진입가 +5% 이내 `ALLOW`, 횡보장은 `WATCH`, 하락장은 `BLOCK`으로 판정한다. 손절·구조 훼손·기간 만료는 `BLOCK`, 필수 데이터 부족은 `NOT_EVALUATED`, 다음 시가가 허용 한도를 넘으면 `WATCH`로 내린다. R·ATR 이격은 기록·출력하지만 V1 차단 조건에는 쓰지 않는다.
- 기각: B(횡보장 최근 표본의 기대값이 음수), C(체결분 성과는 높였으나 좋은 기회도 차단해 전체 Trigger 기준 기대값이 개선되지 않음)
- ADR 후보? yes — Trigger event와 지속 EntryOpportunity, 미래 데이터 차단 및 next-open gap guard 계약에 포함한다.

## (2026-10-02 14:43) [Decision] REDUCE는 현재 보유량의 50%만 남기는 축소 지시
- 맥락: 기존 Playbook은 중간 강도 매도 신호 1개를 `reduce`로 판정하지만 실제 축소 수량을 정의하지 않아 PositionPlanner가 주문량을 계산할 수 없다.
- 후보: A 현재 보유량 50% 매도 / B 현재 보유량 25% 매도 / C 목표 risk 비중까지 축소
- 선택: A — `REDUCE_ONLY_TO_POLICY_TARGET`은 현재 보유 수량의 50%를 매도한다. 목표는 항상 현재 수량 이하이며 같은 실행에서 추가매수를 만들지 않는다. 정수 수량의 반올림 규칙은 PositionPlanner 계약에서 고정한다.
- 기각: B(위험 축소 효과가 작음), C(기존 목표 비중 정보가 없으면 매도량이 0이 될 수 있고 초기 계약이 복잡해짐)
- ADR 후보? yes — PositionPolicy truth table과 Planner 수량 계약에 포함한다.

## (2026-10-02 14:51) [Pivot] 전략 이력 저장소를 SQLite에서 기존 PostgreSQL로 전환
- 이전 접근: `data/db/jarvis.db`와 Python `sqlite3` 기반의 별도 strategy history store를 설계했다.
- 전환 이유: 저장소에는 이미 `psycopg`, `STOCK_REPORT_DB_DSN`/`DATABASE_URL`, checksum migration runner를 사용하는 PostgreSQL 운영 경로가 있으며 사용자가 같은 database 사용을 요청했다.
- 새 접근: 기존 PostgreSQL database 안에 독립 `strategy_history` schema와 migration history를 두고 JSONB·DATE·TIMESTAMPTZ·FK·unique constraint를 사용한다. connection/migration 공통부는 pipeline 계층 밖 `src/storage/postgres/`로 추출하고 stock-report와 strategy history가 함께 사용한다. 기존 DSN은 호환 유지하며 `JARVIS_DB_DSN`을 우선 지원한다.

## (2026-10-02 15:00) [Decision] Analysis Trigger와 Strategy event를 분리해 PostgreSQL에 보존
- 맥락: 독립 리뷰에서 SWING stop·과열 매도·재매수가 position-independent Analysis Trigger 목록과 같은 table에 섞여 계층 경계와 event provenance가 흐려지는 문제를 확인했다.
- 후보: A 모든 event를 범용 Trigger로 유지 / B Analysis Trigger와 Strategy event를 모델·table로 분리 / C Strategy event는 verdict JSON에만 저장
- 선택: B — `TechnicalScorecard.triggers`에는 지표 기반 Analysis Trigger만 두고, 전략 state transition은 `StrategyVerdict.events`와 PostgreSQL `strategy_events`에 `strategy_run_id` FK로 저장한다. 같은 날 복수 event는 모두 보존하고 최종 verdict 우선순위는 별도로 적용한다.
- 기각: A(Analysis/Strategy 경계 훼손), C(개별 event 조회·성과 추적·FK 감사 불가)
- ADR 후보? yes

## (2026-10-02 15:00) [Pivot] next-open gap 판정을 verdict 수정에서 실행 시점 검사로 전환
- 이전 접근: T 종가 EntryOpportunity가 `ALLOW`여도 다음 시가 gap이 +5%를 넘으면 과거 verdict를 `WATCH`로 변경했다.
- 전환 이유: 확정된 T 시점 StrategyVerdict에 T+1 정보를 섞으면 시점 재현성과 immutable history가 깨진다.
- 새 접근: T 종가 verdict와 daily EntryOpportunity는 그대로 보존하고, 별도 `EntryExecutionCheck`가 실행 시각·session·market snapshot을 기준으로 매수 plan만 차단한다. daily evaluation과 execution check를 각각 PostgreSQL에 저장하며 gap 취소·policy 차단은 원 Trigger simulated cohort의 0-return으로 기록한다.

## (2026-10-02 15:06) [Decision] Strategy input identity와 daily evaluation materialization을 고정
- 맥락: PostgreSQL 재리뷰에서 run ID와 DB unique tuple이 다르고, 호출형 pipeline만으로는 EntryOpportunity의 0~20거래일 cohort가 비며, maturity worker crash recovery가 정의되지 않은 문제를 확인했다.
- 후보: A 호출된 날짜만 저장 / B 정기 materializer만 운영 / C 정기 materializer와 idempotent catch-up backfill 병행
- 선택: C — `strategy_input_hash`에 context·전략 설정·SWING checkpoint/full-history provenance를 포함하고 run ID와 DB unique identity를 같은 tuple로 맞춘다. 장 마감 materializer가 daily evaluation을 만들며 다음 실행은 누락 날짜를 prefix-only로 보충한다. 5·10·20 horizon은 child outcome row와 lease 기반 claim으로 독립 성숙시킨다.
- 기각: A(age cohort 누락), B(scheduler 중단 기간 복구 불가)
- ADR 후보? yes

## (2026-10-02 15:10) [Decision] catch-up 차집합과 maturity fencing으로 복구 경쟁을 차단
- 맥락: tail-only catch-up은 중간 날짜 누락을 복구하지 못하고, lease 만료 뒤 이전 worker가 늦게 완료하면 새 owner 결과를 덮을 수 있다.
- 후보: A 마지막 날짜 이후만 backfill / B 예상 거래일과 저장 PK의 전체 차집합 backfill, token 없는 완료 / C 전체 차집합 backfill과 claim token fencing
- 선택: C — `age_bars=0..20` 예상 거래일 전체에서 누락 PK를 계산하고, outcome 완료 update는 worker가 소유한 `claim_token`이 현재 row와 일치할 때만 허용한다. token이 바뀐 늦은 결과는 폐기한다.
- 기각: A(중간 구멍 잔존), B(lease 재claim 뒤 stale worker overwrite 가능)
- ADR 후보? no — PostgreSQL materializer·worker 구현 계약의 세부다.

## (2026-10-02 15:11) [Bug] maturity fencing을 모든 terminal update로 확대
- 증상: 성공(`matured`) update만 claim token으로 fence해 lease를 잃은 worker의 늦은 `error` update가 새 owner 결과를 덮을 수 있었다.
- 근원(root cause): terminal transition을 성공 경로 중심으로만 기술했다.
- 수정: `matured`와 `error` 모두 full primary key, `maturing` status, 현재 `claim_token`이 일치할 때만 update하고 row count 0인 stale 결과는 폐기한다.
- 재발 방지 / 배운 것: lease 기반 worker의 모든 terminal write에 동일 fencing 조건을 acceptance test로 고정한다.

## (2026-10-02 16:15) [Decision] 모든 Strategy를 ChartBundle-only 결정 함수로 고정
- 맥락: Strategy가 실제 매매장부, DB checkpoint 또는 pipeline 실행일에 의존하면 같은 차트에서도 판단이 달라지고 Analysis·Strategy·Position 경계가 다시 섞인다.
- 후보: A SWING은 checkpoint, Playbook은 실제 보유를 입력으로 유지 / B Strategy는 차트와 실제 보유를 함께 사용 / C 모든 Strategy는 ChartBundle과 version만 사용하고 실제 매매정보는 PositionPlanner로 격리
- 선택: C — 종목 OHLCV, 시장 benchmark OHLCV, 필요시 업종 benchmark OHLCV와 거래소 calendar만 Strategy 입력으로 허용한다. state·event·verdict는 차트 prefix replay의 파생 출력이며 DB는 history/cache다. 실제 보유·평균단가·계좌·체결·매매기록은 PositionPlanner만 읽는다.
- 기각: A(전략별 입력 원칙 불일치와 checkpoint 장부화), B(보유 여부에 따라 동일 차트 verdict가 달라짐)
- ADR 후보? yes

## (2026-10-02 16:15) [Pivot] 일일 materializer 의존을 on-demand chart replay로 전환
- 이전 접근: pipeline을 실행하지 않은 날짜를 별도 일일 materializer와 catch-up worker가 채워야 Strategy 상태와 EntryOpportunity가 완전해진다고 보았다.
- 전환 이유: 신호와 상태의 기준은 Jarvis 실행일이 아니라 차트 거래일이며 OHLCV 기반 전략은 현재 ChartBundle에서 과거 prefix를 재생해 누락 날짜를 복원할 수 있다.
- 새 접근: pipeline 실행 시 모든 production Strategy를 ChartBundle prefix별로 replay해 `occurred_on/as_of`를 차트 거래일로 backfill하고 `computed_at`만 실제 실행 시각으로 기록한다. DB가 비어 있어도 같은 차트면 같은 결과가 나와야 한다.

## (2026-10-02 16:58) [Decision] SWING replay와 Strategy identity의 chart-only 경계를 완결
- 맥락: 독립 리뷰에서 rolling chart 이전에 시작된 cycle, Analysis run에 결합된 Strategy ID, 실패 attempt와 episode provenance가 chart-only 재현 계약과 충돌함을 확인했다.
- 후보: A DB checkpoint·매매장부로 이전 상태 복원 / B 무제한 과거 차트를 요구 / C strategy version에 유한 replay profile과 초기 상태를 고정
- 선택: C — `SWING_W150_V1`은 평가일 기준 rolling 3년 origin, `FLAT` seed, 250-bar warm-up, coverage manifest를 versioned 계약으로 둔다. Strategy identity는 `ChartBundle + strategy_version`만 사용하고 Analysis 연결은 junction row로 분리한다. episode는 필수 anchor code/version을 가지며 Playbook V1은 승인된 gap 기준이 없어 session/data 검사만 수행한다.
- 기각: A(Strategy가 DB·실제 매매 이력에 의존), B(현재 provider 범위를 넘어선 무제한 이력이 필요하고 계산 경계가 불명확)
- ADR 후보? yes — chart-only Strategy identity와 replay profile 계약에 포함한다.

## (2026-10-02 17:29) [Bug] Scorecard 방향성·version·cRSI 상태 계약 수정 검증
- 증상: 하락 slope가 더 가팔라져도 감속으로 표시되고, top-level과 하위 계산 version이 달라질 수 있었으며, 현재 cRSI 상태 계산이 이전 봉 결측 때문에 중단됐다.
- 근원(root cause): acceleration을 signed slope 대소로 비교했고 임의 version 입력을 허용했으며, event성 Hook의 이전 봉 조건이 persistent cRSI 상태 조건에 남아 있었다.
- 수정: 동일 방향에서는 slope 절댓값으로 가속도를 판정하고 부호 전환은 `UNKNOWN`으로 고정했다. Scorecard는 V1 외 version을 거부하며, cRSI persistent state는 현재 값과 band만 요구한다.
- 재발 방지 / 배운 것: sign transition, 전체 version provenance, 이전 cRSI 결측을 회귀 테스트로 고정했다. focused 47 tests와 Ruff를 독립 재검증했다.

## (2026-10-02 17:58) [Bug] Analysis Trigger 방향과 Pocket Pivot 유효기간 계약 수정 검증
- 증상: 21거래일 SMA slope가 계속 하락인데 마지막 하루 반등만으로 `turn_up`이 발생했고, Pocket Pivot이 7일째 이미 만료되어 출력 계약과 충돌했다.
- 근원(root cause): SMA Trigger가 1일 차분을 사용했고 pattern·volume TTL을 모두 5일로 일괄 적용했다.
- 수정: SMA 방향 전환은 `t vs t-21`, 이전 방향은 `t-1 vs t-22`로 계산한다. Pocket Pivot은 10 completed-session TTL로 분리했다.
- 재발 방지 / 배운 것: 21일 하락 중 하루 반등, 21일 방향 전환 중 하루 하락, Pocket Pivot age 7/11 상태를 회귀 테스트로 고정했다. focused 38 tests와 Ruff를 독립 재검증했다.

## (2026-10-02 18:27) [Bug] SWING 최근 event와 놓친 진입 재평가 연결 검증
- 증상: SWING verdict가 오늘 event만 남기고 과거 진입 Trigger를 다음 날부터 재평가하지 않아, 놓친 신호의 현재 진입 가능성을 보여줄 수 없었다. market series가 SPY인지와 짧은 이력이 신규 상장인지도 증명할 수 없었다.
- 근원(root cause): adapter가 trace를 당일로 필터링했고 ChartBundle에 benchmark/listing provenance 필드가 없었다.
- 수정: 최근 20거래일 Strategy event를 보존하고 최신 S/D event를 0..20일 동안 매일 재평가한다. ChartBundle에 `market_ticker`, CoverageManifest에 verified `listing_first_session`을 추가했다.
- 재발 방지 / 배운 것: T+2 ALLOW/급등 WATCH, non-SPY NOT_EVALUATED, verified/unverified young listing, 최근 event 경계를 회귀 테스트로 고정했다. 관련 61 tests와 Ruff를 독립 재검증했다.

## (2026-10-02 18:46) [Bug] StrategyRunner chart-only identity와 Scorecard 경계 검증
- 증상: 같은 ChartBundle에서도 caller가 넘긴 legacy action에 따라 verdict가 달라졌고, RS 공통 거래일 부족을 실제 약세로 해석했으며 Scorecard 없는 run을 허용했다.
- 근원(root cause): Runner가 legacy adapter의 chart replay 대신 외부 verdict를 사용했고, RS helper의 0 기본값과 필수 입력 결측을 구분하지 않았으며 bundle contract를 nullable로 완화했다.
- 수정: 세 production strategy를 모두 `evaluate(bundle)`로 실행하고, RS는 최소 21개 공통 session을 요구하며, Scorecard 누락·ticker/as_of 불일치는 runner boundary에서 거부한다.
- 재발 방지 / 배운 것: 외부 legacy action 변형, 20/21 공통 session 경계, invalid Scorecard 세 경우를 회귀 테스트로 고정했다. focused 23 tests와 Ruff를 독립 재검증했다.

## (2026-10-02 19:27) [Decision] Scorecard·Strategy·Position 분리 release 검증 완료
- 맥락: 기존 점수/action과 새 5축·세 Strategy 병렬 출력, chart-only 재현, PostgreSQL history/cache를 release 문서와 전체 회귀 검증으로 마감해야 했다.
- 후보: A 실제 PostgreSQL 접속까지 완료로 간주 / B fake connection 계약과 전체 suite로 코드 변경을 마감하고 disposable PostgreSQL concurrency 검증을 deployment gate로 유지
- 선택: B — targeted 560개, pipeline/CLI 66개, 전체 1618개 test와 `src tests` Ruff를 통과했다. 실제 PostgreSQL에는 접속하지 않았으며 advisory lock·동시 insert·migration은 disposable PostgreSQL 검증 전 배포하지 않는다.
- 기각: A(현재 task에서 실제 PostgreSQL 접속 권한과 disposable 환경을 사용하지 않았으므로 운영 동시성을 검증했다고 볼 수 없음)
- ADR 후보? no — 기존 확정 설계의 release 검증과 운영 gate 기록이다.

## (2026-10-06 22:14) [Pivot] Strategy 가상 상태 추적을 Signal·Backtest 책임 분리로 전환
- 이전 접근: SWING_W150 Strategy가 rolling 3년 chart를 `FLAT`에서 replay해 가상 lifecycle, 진입가, stop, risk, R을 복원하고 이를 StrategyVerdict에 포함했다.
- 전환 이유: 모든 Strategy는 같은 ChartBundle에서 보유·매매장부와 무관하게 같은 정보를 내야 하며, 가상 position과 trade 성과는 Strategy Signal 생성이 아니라 Backtest 책임이다. 고정 horizon 성과 저장과 연속 가상 매매도 서로 다른 목적이다.
- 새 접근: Strategy는 `S_ENTRY`, `D_ENTRY`, `OVERHEAT_SELL`, `OVERHEAT_REBUY`, `SMA150_EXIT`와 0~20거래일 EntryOpportunity만 생성한다. 기존 `strategy_episodes/outcomes`는 5·10·20거래일 Signal Outcome Tracking으로 유지하고, 가상 체결·stop·partial exit·R은 Backtest가, 실제 보유·주문 수량은 PositionPlanner가 담당한다. 별도 Strategy Tracker와 ForwardTracker는 최소 범위에서 제외한다.

## (2026-10-06 22:14) [Decision] Strategy 실시간 계산에서 고정 3년 replay 요구 제거
- 맥락: rolling 3년 replay는 Strategy 내부의 가상 position을 복원하기 위해 도입됐으나, 새 책임 경계에서는 Strategy가 날짜별 Signal만 탐지한다.
- 후보: A 모든 실시간 Strategy 요청에 3년 유지 / B Signal rule lookback만 요청하고 전체 기간은 Backtest에서만 사용 / C DB checkpoint로 이전 상태 복원
- 선택: B — 실시간 Strategy는 indicator와 Signal 탐지에 필요한 versioned lookback만 사용한다. EntryOpportunity는 최대 20거래일, Signal Outcome은 이후 5·10·20거래일, Backtest는 사용자가 지정한 기간과 warm-up을 사용한다.
- 기각: A(가상 position 복원 책임이 제거된 뒤에도 불필요한 데이터 비용과 지연 유지), C(DB 상태가 Strategy 판단 입력이 되어 chart-only 결정성을 훼손)
- ADR 후보? yes — Strategy Signal, Signal Outcome, Backtest, PositionPlanner 책임 경계로 기록한다.

## (2026-10-06 22:41) [Bug] Analysis Trigger immutable 충돌 제거 검증
- 증상: 같은 거래일을 최신 현재가로 다시 계산하면 Trigger identity는 같지만 observed/reference value와 status가 달라져 PostgreSQL 저장이 `ImmutablePayloadConflictError`로 실패했다.
- 근원(root cause): 실행별 계산 결과가 아니라 최신 조회용 `analysis_trigger_events` projection에 immutable payload·동일 날짜 status 충돌 검사를 적용했다.
- 수정: Trigger projection은 같거나 최신 `status_as_of` 입력의 event payload, fingerprint, status를 갱신한다. 과거 backfill이 최신 projection을 되돌리지 않는 순서 규칙은 유지한다.
- 재발 방지 / 배운 것: 같은 날짜 payload/status 변경과 과거 backfill 두 경우를 회귀 테스트로 고정했다. strategy history 19개와 전체 1619개 test, `src tests` Ruff를 통과했다.

## (2026-10-07 11:28) [Decision] 모든 Strategy Signal에 Evidence를 필수 포함
- 맥락: Signal code만 전달하면 사용자가 왜 신호가 발생했는지 확인할 수 없고 pipeline별 설명 누락이 생길 수 있다.
- 후보: A Signal만 기본 표시 / B Signal과 핵심 Evidence를 항상 표시하고 상세 출력에 전체 Evidence 보존 / C Evidence를 renderer가 문자열로 재계산
- 선택: B — 모든 `StrategySignal`은 구조화된 Evidence를 최소 한 개 포함한다. `check`, `analyze`, `brief` 기본 출력은 Signal과 핵심 Evidence를 함께 보여주고 상세 출력과 PostgreSQL history는 전체 Evidence를 lossless하게 보존한다.
- 기각: A(판단 근거 소실), C(pipeline별 재계산으로 의미와 출력이 달라질 수 있음)
- ADR 후보? yes — Strategy Signal contract의 필수 provenance 규칙이다.

## (2026-10-07 11:57) [Pivot] Strategy Signal·Outcome 영속화를 재현 가능한 Backtest로 대체
- 이전 접근: Strategy Signal과 전체 Evidence를 PostgreSQL history에 저장하고, 5·10·20거래일 Outcome을 별도 worker가 성숙시켜 규칙별 성과를 누적했다.
- 전환 이유: 각 Strategy는 특정 차트 거래일에 발생한 Signal을 결정적으로 재현할 수 있고, Signal 발생 가격 대비 현재가 또는 지정 평가일 가격의 성과와 장기 비교는 같은 차트로 Backtest를 실행하면 계산된다. 저장 계층이 projection ordering, finality, retract, fencing, migration 복잡성을 추가한다.
- 새 접근: Strategy는 ChartBundle에서 날짜가 있는 Signal과 Evidence를 매번 계산하고, 규칙별 적절성 비교는 Signal 발생 가격 대비 평가일 가격 또는 version별 Backtest 결과로 산출한다. Strategy Signal·EntryOpportunity·Signal Outcome은 PostgreSQL을 필수 경로로 사용하지 않으며, 실제 보유와 주문 기록은 PositionPlanner 경계에만 둔다.

## (2026-10-07 17:03) [Decision] SWING 진입 Signal 이름과 EntryOpportunity 원천 참조를 명시화
- 맥락: `S_ENTRY`, `D_ENTRY`, `source_signal_code`는 약어만으로 의미를 알기 어렵고 V2에는 DB 참조용 중복 필드가 필요하지 않다.
- 후보: A 기존 약어와 id/code/date 참조 유지 / B 표시 이름만 풀어쓰기 / C V2 canonical code와 모델 필드를 의미 중심으로 변경
- 선택: C — V2는 `TREND_BREAKOUT_ENTRY`, `DEEP_RECOVERY_ENTRY`를 사용한다. EntryOpportunity는 별도 source id/code/date 대신 재평가 대상인 `entry_signal: StrategySignal | None`을 포함한다.
- 기각: A(도메인 의미가 드러나지 않음), B(내부 계약과 사용자 출력의 용어가 계속 어긋남)
- ADR 후보? no — Strategy Signal V2 출력 계약의 naming 결정이다.

## (2026-10-07 18:08) [Decision] 과열 sequence를 진입에서 분리하고 다중 지지 눌림목 Signal 추가
- 맥락: 진입 Signal을 과열의 선행조건으로 두면 Strategy가 가상 보유 cycle을 추적하는 의미가 남고, SMA50 외 중장기 지지선의 눌림목 매수 타이밍을 놓친다.
- 후보: A 진입에 종속된 과열 cycle 유지 / B 과열만 독립 / C 과열 독립과 SMA50·150·200·Supertrend 눌림목을 함께 chart-only 사건으로 계산
- 선택: C — `OVERHEAT → OVERHEAT_CORRECTION → POST_OVERHEAT_RECOVERY_ENTRY`는 실제·가상 매매와 무관한 차트 sequence다. 눌림목은 네 지지선의 0.5 ATR 이내 접근, 지지 방어, 전일 고가 돌파를 `PULLBACK_REVERSAL_ENTRY`로 만들고 겹친 지지선과 cRSI·MACD 방향을 Evidence로 보존한다.
- 기각: A(Strategy와 Backtest 상태 경계 재혼합), B(사용자가 요구한 눌림목 진입 타이밍 누락)
- ADR 후보? yes — SWING_W150 V2의 chart-only Signal inventory와 sequence 경계다.

## (2026-10-08 11:01) [Decision] 과열 자연 해소·만료와 versioned parameter preset 확정
- 맥락: SMA20을 이탈하지 않은 채 SMA50이 따라오거나 시간이 지나도 과열이 영구 유지될 수 있고, 40%·0.5 ATR 같은 magic number는 후속 검증과 조정을 어렵게 한다.
- 후보: A SMA20 이탈로만 해소 / B 자연 해소만 추가 / C correction·이격 축소·시간 만료를 함께 지원하고 모든 threshold를 parameter 객체로 주입
- 선택: C — 이격 20% 이하에서는 `OVERHEAT_RESOLVED`, 마지막 40% 이상 이격일 뒤 20거래일에는 `OVERHEAT_EXPIRED`로 해소한다. production은 frozen `SWING_W150_V2_PARAMS_V1`, Backtest는 명시적 custom parameter를 사용하며 결과에 parameter version을 포함한다.
- 기각: A(과열 상태 고착), B(높은 이격이 오래 횡보하는 경우 미해결)
- ADR 후보? yes — Strategy 결과 identity에 parameter set version을 포함하는 계약이다.

## (2026-10-08 18:09) [Decision] PositionPlanner는 장중 provisional Signal도 현재 snapshot으로 계산
- 맥락: 장중에도 매수·매도 수량을 검토할 수 있어야 하지만 미완성 daily bar를 확정 Signal이나 Backtest 체결로 취급하면 재현성이 깨진다.
- 후보: A 완료 bar의 FINAL Signal만 계산 / B PROVISIONAL도 계산하되 결과에 finality·계산시각·market snapshot hash를 고정 / C 장중 bar를 FINAL로 취급
- 선택: B — PositionPlanner는 오늘의 `current_signals`가 PROVISIONAL이어도 현재 실제 보유·계좌·가격 snapshot으로 수량을 계산한다. Backtest는 FINAL Signal만 사용한다.
- 기각: A(장중 실행 계획 부재), C(종가 전 변하는 값을 확정 사건으로 오인)
- ADR 후보? yes — Signal finality와 실행 계획 경계다.

## (2026-10-08 18:09) [Decision] Observation history와 Signal history를 별도 출력 계약으로 분리
- 맥락: `PULLBACK_WATCH`처럼 여러 날 지속되는 관찰 과정과 `PULLBACK_REVERSAL_ENTRY`처럼 한 거래일에 발생하는 사건을 같은 history로 보여주면 주문 의미와 상태 변화가 섞인다.
- 후보: A 단일 event history / B Observation과 Signal을 분리하고 각각 전체 Evidence 보존 / C 현재 상태만 표시
- 선택: B — Observation은 시작·종료·상태를 가진 episode로, Signal은 발생일이 있는 1회 사건으로 유지한다. 기본 출력은 최근 20거래일의 두 history를 나눠 보여주며 PositionPlanner와 Backtest는 Signal만 소비한다.
- 기각: A(지속 상태와 1회 사건 혼합), C(과거 전이와 신호 근거 소실)
- ADR 후보? yes — Strategy 출력 계약의 핵심 경계다.

## (2026-10-08 18:09) [Pivot] PostgreSQL strategy_history subsystem을 전체 제거
- 이전 접근: Strategy Signal·Observation·EntryOpportunity·Outcome·PositionPlan을 PostgreSQL에 저장하고 projection·maturity lifecycle을 운영했다.
- 전환 이유: 운영 적용 schema와 row가 없고 Strategy 결과는 같은 ChartBundle prefix와 versioned parameter에서 결정적으로 재계산된다. 저장이 Signal 생성과 성과 비교에 불필요한 ordering·migration·동시성 복잡성을 만들었다.
- 새 접근: `migrations/strategy_history/`, `src/storage/strategy_history/`, 관련 tests와 runtime session wiring을 삭제한다. SignalPerformance와 Backtest는 요청 시 계산하고, 공통 PostgreSQL utility와 DB 비종속 canonical hash utility는 유지한다.

## (2026-10-08 19:10) [Bug] V2 한국 benchmark와 Signal cohort 검증
- 증상: V2 EntryOpportunity가 모든 한국 종목을 `NOT_EVALUATED`로 반환했고, 다른 strategy version 또는 parameter fingerprint의 Signal도 현재 lifecycle처럼 해석했다.
- 근원(root cause): evaluator의 market gate가 미국 `SPY`만 허용했으며 active source·invalidator의 strategy/parameter identity를 검증하지 않았다.
- 수정: 미국은 `SPY`, KOSPI·6자리 KRX는 `^KS11`, KOSDAQ은 `^KQ11`을 허용했다. source와 이후 invalidator가 현재 V2 parameter cohort와 다르면 `NOT_EVALUATED`와 identity Evidence를 반환한다.
- 재발 방지 / 배운 것: KOSPI ALLOW, KOSDAQ WATCH, 6자리 KRX BLOCK, 잘못된 benchmark와 source·invalidator identity 불일치를 회귀 테스트로 고정했다. focused 60개와 전체 1706개 test, Ruff·format·diff 검사를 독립 재검증했다.

## (2026-10-08 19:26) [Bug] V2 production wiring과 공통 출력 계약 검증
- 증상: production은 legacy SWING verdict와 stateful 한 줄 요약을 사용했고 Strategy 계산마다 PostgreSQL session을 열었다. 초기 V2 renderer는 parameter fingerprint를 input hash에서 누락하고 확장률·Evidence·과열 placeholder를 잘못 표시했다.
- 근원(root cause): V1 verdict contract, persistence lifecycle, legacy renderer가 pipeline에 남아 있었고 V2 ratio/identity/Evidence 단위를 공통 renderer가 완전히 반영하지 못했다.
- 수정: production SWING을 V2 Signal bundle로 전환하고 check·analyze·brief가 현재 Observation, 두 history, 오늘 EntryOpportunity를 공통 출력한다. `strategy_history` source/test/migration/runtime wiring을 삭제하고 V2 input hash에 fingerprint를 포함했으며 확장률 percent와 핵심 Evidence를 바로 표시한다.
- 재발 방지 / 배운 것: 세 실제 formatter parity, 2y loader→runner, market unavailable V2 slot, PostgreSQL 미접속, KRX routing, 삭제 import 0건을 회귀 테스트로 고정했다. focused 92개, parity 3개, 전체 1698개 test와 Ruff·format·diff 검사를 독립 재검증했다.

## (2026-10-08 19:37) [Decision] SignalPerformance 장중 평가와 체결 기준 분리
- 맥락: Signal 발생 종가 기준 성과와 다음 실제 거래 가능 시가 기준 성과를 저장 없이 오늘 가격으로 비교하되, 장중 가격과 거래정지·provider 누락을 구분해야 했다.
- 후보: A FINAL bar만 평가 / B PROVISIONAL 현재가도 평가하고 PARTIAL 표시 / C 장중 값을 COMPLETE로 취급
- 선택: B — estimate와 executed는 별도 basis/status/reason을 유지한다. 장중 현재가는 PARTIAL, 다음 bar가 없으면 executed는 NOT_EVALUATED, 명시된 no-trade session만 거래정지 지연으로 인정한다.
- 기각: A(장중 check/analyze/brief에서 최신 성과를 숨김), C(변하는 현재가를 확정 성과로 오인), provider gap을 거래정지로 추정하는 방식(잘못된 시가 기준 생성)
- ADR 후보? yes — SignalPerformance와 Backtest finality, 가격 기준의 책임 경계다.

## (2026-10-08 19:51) [Bug] V2 Backtest causal 체결과 FINAL Signal 경계 검증
- 증상: SMA 부동소수점 오차가 정확한 risk 경계에서 수량을 5주에서 4주로 줄였고, 미래 행의 dtype·중복이 과거 Evidence 또는 실행 결과를 바꿀 수 있었다. 초기 구현은 warm-up 기간의 PROVISIONAL·identity 불일치 Signal도 결과 history에 허용했다.
- 근원(root cause): stop 계산에 indicator float 잔여 오차가 들어갔고, 기간 slice 전에 전체 frame을 검증·해석했으며, Signal validation을 체결 기간에만 적용했다.
- 수정: stop 입력을 Decimal 12자리로 정규화하고 `warmup_start~test_end`를 먼저 slice·float 정규화한 뒤 계산한다. 해당 input period의 모든 Signal에 FINAL·identity·actual bar 검증을 적용하고 `test_start` 이후만 체결한다.
- 재발 방지 / 배운 것: 미래 NaN·dtype·중복, prefix parity, warm-up PROVISIONAL/identity/missing bar, stop 우선, 5주 50% 올림, partial lot risk, 모든 fill 비용을 회귀 테스트로 고정했다. focused 50개, 관련 191개 test와 Ruff·format·diff 검사를 root가 재검증했다.

## (2026-10-08 19:51) [Decision] V2 aggregate R은 청산된 수량의 초기 risk만 사용
- 맥락: 부분청산 뒤 남아 있는 open lot risk를 realized aggregate R 분모에 포함하면 아직 실현되지 않은 position이 성과를 희석한다.
- 후보: A 원본 lot 전체 risk 포함 / B 청산된 slice의 risk만 포함 / C 현재 평가손익까지 합산
- 선택: B — `aggregate_r = closed slice realized PnL 합 / closed slice initial risk capital 합`으로 계산한다. 부분청산은 매도 수량의 risk만 closed slice로 옮기고 잔여 lot의 entry basis와 risk/share를 유지한다.
- 기각: A(미실현 risk가 실현 성과에 혼입), C(Backtest 종료일 강제평가 정책이 추가되어 현재 범위를 넘음)
- ADR 후보? yes — Backtest lot ledger와 성과 집계 계약이다.

## (2026-10-08 19:59) [Bug] PositionPlanner current Signal과 EntryOpportunity source 결합 검증
- 증상: 같은 날 여러 entry Signal이 있으면 planner가 우선순위가 높은 Signal을 고르면서, 다른 Signal을 평가한 `ALLOW` EntryOpportunity로도 매수를 승인할 수 있었다.
- 근원(root cause): 신규 매수 조건이 opportunity status와 평가일만 확인하고 `entry_signal.signal_id`를 선택된 current Signal과 대조하지 않았다.
- 수정: PositionPlanner는 current Signal 우선순위 선택 후, EntryOpportunity의 source Signal ID가 정확히 일치할 때만 `BUILD_ONLY_TO_RISK_TARGET`을 반환한다.
- 재발 방지 / 배운 것: 과거 exit 비사용, same-day exit 우선, 서로 다른 entry source 거부, matching source 승인, PROVISIONAL snapshot 고정, 5주 correction 3주 매도를 회귀 테스트로 고정했다. root 검증은 focused 103개와 pipeline·Backtest 84개, Ruff·format·diff 검사를 통과했다.

## (2026-10-08 20:06) [Decision] V2 문서의 기회·수량·성과 경계를 실제 구현에 고정
- 맥락: 기존 기능·변경 문서는 PostgreSQL history/cache와 V1 가상 보유를 현재 기능으로 설명하고, EntryOpportunity truth table은 구조 무효를 BLOCK에 섞었다.
- 후보: A 이전 설명 유지 / B 구현 inventory 추가 / C 사용자 영향과 책임 경계를 현재 V2 동작으로 갱신
- 선택: C — correction·exit은 INVALIDATED, age 20은 유효·21은 만료, 주문은 current Signal 우선순위와 정확한 ALLOW source 일치, 성과 R은 closed slice risk만 사용한다고 명시했다. Observation·Signal·성과는 저장 없이 계산하고 실제 수량과 snapshot은 PositionPlanner에만 둔다.
- 기각: A(현재 runtime과 다른 안내), B(고수준 문서 역할을 흐림)
- ADR 후보? no — 승인된 설계와 Task 4·7·8 review 결정을 문서에 반영했다.

## (2026-10-08 20:06) [Friction] Unit 검증과 실제 pipeline 결과가 다름
- 막힌 점: focused architecture 391개, 전체 1805개 test와 Ruff는 통과했지만 실제 `check NVDA`는 exit 0 안에서 SWING `ValueError: max() iterable argument is empty`를 표시했다. `analyze NVDA`는 exit 1과 `Unable to serialize unknown type: <class 'numpy.bool'>`로 종료했다.
- 임시 대응: code 변경 권한이 없는 Task 9에서는 오류 원문을 담당자에게 전달하고 실제 Signal 검증을 실패로 기록했다. `brief`도 exit 0 안에서 NVDA 포함 다수 종목에 같은 SWING 오류를 표시해 전체 gate는 실패했다. 일부 종목의 두 history·FINAL/PROVISIONAL·현재 기회 출력은 확인했다.
- 개선 아이디어 (스킬·훅·프롬프트): 실제 차트의 지지선 소실과 NumPy scalar가 포함된 출력 계약을 회귀 입력으로 확인하고, 수정 뒤 실제 세 pipeline을 다시 실행한다.

## (2026-10-08 20:20) [Bug] 실제 세 pipeline의 V2 출력 재검증
- 증상: 최초 check·brief의 지지선 소실 max-empty, analyze의 NumPy bool serialization, 영숫자 KRX 종목의 종료 후 PROVISIONAL, PositionPlan finality 표시 누락을 확인했다.
- 근원(root cause): watch의 유효 지지선이 사라지는 상태, 외부 계산의 NumPy scalar와 출력 serialization 경계, 한국 ticker 판별과 renderer metadata 전달이 실제 입력을 충분히 다루지 못했다.
- 수정: coordinator가 각 경계를 수정·focused 검증한 뒤 Task 9에서 세 명령을 다시 실행했다. 모두 exit 0이며 NVDA의 동일한 FINAL Signal·WATCH 기회·두 성과 기준, 29주 유지 계획과 FINAL 표시를 확인했다. 0167A0도 FINAL로 표시한다.
- 재발 방지 / 배운 것: 최종 architecture 411개, 전체 1825개(root), Ruff·diff-check·삭제 import 검색이 통과했다. Unit 통과와 live 성공은 따로 입증한다. 입력 부족 3개 종목과 선택적 뉴스·수급 부재, volume warning은 제한으로 남기며 최종 독립 리뷰는 coordinator가 수행한다.

## (2026-10-08 20:46) [Bug] 최종 독립 리뷰의 거래일·coverage·가격 기준 4건 수정
- 증상: 종목과 benchmark의 공동 누락은 expected 거래일에서 사라졌고, 종목 gap이 SMA150 연속 하회로 해석되어 실제 보유 5주 전량 매도를 만들었다. V2 Backtest는 미설명 누락을 거래정지처럼 건너뛰었고, 기회 당일 종가 추정도 다음 시가로 표시했다.
- 근원(root cause): 가격 관측 행이 calendar authority였고 종목 coverage가 feature·detector에 전달되지 않았다. simulator에는 expected/no-trade session 계약이 없었으며 renderer는 기준가를 단일 label로 표시했다.
- 수정: 독립 US/KRX calendar와 typed 종목 coverage로 Signal 생성·실제 매도 후보를 제한한다. 시장 chart 부재는 정상 종목 Signal과 분리하고, V2 Backtest는 독립 expected sessions와 명시적 no-trade만 허용한다. age 0/1 이상 가격 기준을 세 formatter에서 구분한다.
- 재발 방지 / 배운 것: 각 finding의 실제 RED→GREEN, architecture focused 435개·전체 1849개(15 deselected, 기존 warning 2개)와 Ruff·format·diff 검사를 확인했다. 수정 후 live는 미실행이다. 정확한 결과와 보수적 history 제한은 `review-important-fixes-report.md`에서 관리한다.

## (2026-10-08 20:46) [Decision] 미설명 종목 gap은 전체 replay를 보수적으로 제한
- 맥락: 누락을 단순히 건너뛰면 연속 종가 조건·sequence age·체결 기준의 의미가 달라진다. 현재 provider는 상장일·거래정지 metadata를 확인해 주지 않는다.
- 후보: A 관측 행을 연속 거래일로 추정 / B 전체 requested coverage를 요구 / C 임의 tolerance·누락 보정
- 선택: B — complete instrument coverage가 있어야 Signal을 계산하고, Backtest는 확인된 no-trade 선언 외 누락을 오류로 반환한다. calendar는 benchmark 응답과 독립적이다.
- 기각: A(잘못된 매도·시가 승인), C(확인되지 않은 거래정지·상장일 정책 추가)
- ADR 후보? yes — 거래일·입력 충족이 Signal과 체결의 공통 안전 경계다.

## (2026-10-08 20:47) [Friction] 전체 format 검사에서 기존 HEAD 4개 파일 불일치
- 막힌 점: 수정 Python 11개는 format PASS지만 추가 전체 `ruff format --check src tests`는 cli/main·stock_report/db·legacy_technical과 그 test 등 기존 4개 파일에서 exit 1이다. 해당 파일의 status와 diff는 모두 비어 이번 task의 변경이 아님을 확인했다.
- 임시 대응: 범위 밖 파일은 보존하고 전체 format FAIL과 변경 파일 PASS를 보고서·active context에서 분리했다. 전체 pytest 1849개와 Ruff lint·diff 검사는 통과했다.
- 개선 아이디어 (스킬·훅·프롬프트): coordinator가 기존 format debt 처리 범위를 별도 판단한다. 검증 실패를 전체 PASS로 숨기지 않는다.

## (2026-10-08 20:58) [Pivot] 정상 2y rolling 시작 경계는 한 session만 명시적으로 허용
- 이전 접근: nominal 요청 시작부터 모든 exchange session을 요구하여 첫 session 하나가 빠져도 전체 V2 Signal replay를 제한했다.
- 전환 이유: coordinator의 live NVDA/SPY 진단에서 nominal 2024-10-07~2026-10-07의 502 expected sessions와 정상 `period=2y` 501행(2024-10-08~)의 경계 차이를 확인했다. coordinator가 첫 session 1개에 한정한 허용 정책을 명시적으로 승인했다.
- 새 접근: missing이 정확히 첫 session 하나이고 이후 종료일까지 모두 연속일 때만 별도 effective_start를 사용한다. nominal request와 전체 calendar는 유지하고 시작 2개 이상·내부·끝 누락은 계속 incomplete다. 상장·거래정지를 추정하거나 Backtest의 expected/no-trade 계약을 완화하지 않는다.

## (2026-10-08 20:58) [Bug] 정상 2y boundary에서 V2 평가 복구
- 증상: root의 live `check NVDA --detail-strategy`가 exit 0이어도 정상 501행을 incomplete로 판단하여 V2 NOT_EVALUATED를 반환했다.
- 근원(root cause): nominal 기간 경계와 유효 평가 시작이 하나의 coverage start로 취급되어 정상 provider rolling 범위와 internal gap을 구분하지 못했다.
- 수정: nominal requested_start와 optional effective_start를 분리하고 complete ChartBundle의 첫 session 1개 보정·calendar equality·prefix 불변 조건을 유지했다.
- 재발 방지 / 배운 것: 실제 502/501 형태의 complete/V2 RED 4건, effective bounds RED 2건을 확인한 뒤 coverage·ChartBundle 57개와 관련 focused 238개를 통과했다. 변경 5개 Ruff·format·diff도 통과했다. 요청대로 최신 전체·live 재검증은 coordinator 범위다.

## (2026-10-08 20:52) [Friction] 실제 check 재검증의 CLI 옵션명 오인
- 막힌 점: `jarvis check NVDA --detailed-strategy`는 존재하지 않는 옵션이라 실제 pipeline 실행 전 exit 2로 종료했다.
- 임시 대응: CLI가 제시한 정식 옵션 `--detail-strategy`로 바꿔 재실행한다.
- 개선 아이디어 (스킬·훅·프롬프트): 실제 검증 명령은 이전 로그를 추측하지 말고 `--help`나 `docs/CLI_USAGE.md`의 현재 옵션을 먼저 확인한다.

## (2026-10-08 21:04) [Bug] 2y provider 시작 경계 회귀 수정과 실제 pipeline 재검증
- 증상: 독립 exchange calendar 최초 적용 후 `check NVDA`가 exit 0 안에서 SWING을 `NOT_EVALUATED`로 표시했다.
- 근원(root cause): as_of 2026-10-07의 nominal XNYS calendar는 2024-10-07부터 502개지만 `yfinance period=2y` NVDA·SPY는 2024-10-08부터 501행을 반환했다. loader가 정상적인 rolling-period 최초 1 session 경계를 중간 provider gap과 같게 차단했다.
- 수정: nominal `requested_start`와 전체 exchange sessions를 보존하고, 첫 거래일 하나만 빠진 연속 응답에 `effective_start`를 기록한다. 시작 2개 이상·중간·끝 누락은 계속 incomplete로 차단한다.
- 재발 방지 / 배운 것: live 502/501 형태와 시작 2개·중간·끝 gap을 회귀 test로 고정했다. root focused 238개, 전체 1860개, Ruff·변경 format·lock·diff가 통과했다. `check`, `analyze`, `brief --no-llm`은 모두 exit 0이고 NVDA의 2026-09-17 FINAL Signal, 14거래일, WATCH, +8.3%, 29주 유지가 일치했다.

## (2026-10-08 21:09) [Bug] 휴장일 origin prefix의 effective coverage 재설정
- 증상: 11/27 nominal 생략·11/29 effective 시작인 정상 XNYS 입력을 Thanksgiving 휴장일 11/28 origin으로 slice하면 complete ChartBundle이 ValueError를 반환했다.
- 근원(root cause): 날짜상 origin<effective 여부로 보정을 보존했지만 sliced calendar에서는 원래 생략된 11/27이 제거되어 11/29이 첫 session이었다. metadata와 calendar 순서가 맞지 않았다.
- 수정: 먼저 sliced exchange sessions를 구성하고 원래 생략 session이 그 목록에 남아 있을 때만 effective 보정을 유지한다. 없으면 origin 요청 범위에 맞춰 보정을 제거하여 COMPLETE를 유지한다. model validator와 live gap 정책은 유지한다.
- 재발 방지 / 배운 것: 실제 XNYS holiday RED 1건을 확인한 뒤 nominal·휴장·effective origin 3건을 통과했다. 직접 구성한 prefix의 model_dump/hash 일치와 미래 OHLCV 변조 불변을 검증했다. 관련 focused 241개·변경 2개 Ruff/format·diff 통과. 최신 전체·live·동일 reviewer 재검토는 coordinator 범위다.

## (2026-10-12 22:01) [Decision] Strategy 기본 출력의 판단 근거와 5일 점수 흐름 통합
- 맥락: Signal과 EntryOpportunity의 code·상태만으로는 왜 해당 결과가 나왔는지 판단하기 어렵고, 5거래일 Technical Score가 pipeline별로 분산되어 있었다.
- 후보: A `--detail-strategy`에서만 표시 / B 기본에 판단 정보를 모두 표시 / C 새로운 해석 규칙을 renderer에 추가
- 선택: B — check·analyze·brief의 공통 renderer가 기존 Evidence·임계값과 최근 5일 점수 상세를 기본 표시한다. detail은 signal ID·parameter fingerprint 같은 개발용 metadata만 추가한다.
- 기각: A(일상 판단에 필요한 근거가 숨겨짐), C(renderer가 전략 판단을 새로 만드는 책임 침범)
- ADR 후보? no — 기존 typed 결과의 표시 계약 변경이다.

## (2026-10-12 22:14) [Bug] 공통 Strategy 기본 출력에 판단 원인·5일 점수 상세 연결
- 증상: Signal·EntryOpportunity가 code와 일부 Evidence만 보여 상태 원인과 임계값을 바로 알 수 없었고, 최근 5거래일 Technical Score 상세가 공통 Strategy 출력에 없었다.
- 근원(root cause): `AnalysisStrategyResult`가 score history를 전달하지 않았고 renderer가 Evidence를 importance에 따라 생략하며 내부 영문 code message를 그대로 출력했다.
- 수정: score history·warning을 Strategy 결과에 배선했다. Signal·EntryOpportunity의 전체 Evidence·관측값·기준값과 typed 상태 원인, 5일의 점수·전일 대비·action·이유·구성·변화·이벤트·주의·진입 가능 여부를 기본 표시한다. 판단은 추가하지 않고 기존 typed Evidence를 한국어로 표현했다.
- 재발 방지 / 배운 것: check·analyze·brief 공통 출력, 불충분 차트, service 배선을 회귀 테스트로 고정했다. 전체 1,864개 test(15 deselected), focused 83개, Ruff·format·diff 검사를 통과했고 실제 `jarvis check NVDA`에서 한국어 Signal 원인, `ALLOW` +4.5% / +5.0% 임계, 5일 점수 상세를 확인했다.

## (2026-10-13 09:59) [Friction] 새 세션 인계의 터미널 준비 감지 시간 초과
- 막힌 점: 현재 체크아웃에 새 Codex 터미널을 열었으나 `orca terminal wait --for tui-idle`가 45초·60초 두 번 timeout을 반환했다. 화면은 입력 대기였지만 준비 확인이 되지 않아 해당 세션에 작업을 보내지 않았다. 원인은 확인하지 않았다.
- 임시 대응: Orca 기본 `worktree create --agent codex --prompt`로 독립 `price-volume-rule-review` 워크트리를 만들었다. `term_26ded214-0232-4fc8-b5e1-32e22c3109a7`가 인계 문서·외부 연구 메모·원본 미커밋 코드를 읽고 검토를 시작한 것을 확인했다. 작업 범위는 연구·설계이며 원본은 읽기 전용이다.
- 개선 아이디어 (스킬·훅·프롬프트): 미커밋 source 위치와 새 워크트리 기준을 프롬프트에 명시한다. 생성 성공·입력 수락·착수를 구분하고, 확인되지 않은 세션에는 중복 지시를 보내지 않는다.

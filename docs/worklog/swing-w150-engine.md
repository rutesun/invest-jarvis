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

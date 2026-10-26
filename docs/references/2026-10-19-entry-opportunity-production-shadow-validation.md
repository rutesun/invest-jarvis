# EntryOpportunity Production v1 + Shadow 검증

상태: 구현·전체 테스트·실제 차트 검증 및 xhigh 최종 전체 변경 독립 리뷰 완료(READY / Spec PASS / Quality PASS, Critical·Important·Minor 각 0건). commit/push/merge 없음.

## 운영 계약

최신 eligible source를 대표로 삼는다. 새로운 Signal은 새로운 window를 만들고, 기존 source의 종료가 실제 보유 매도를 의미하지 않는다.

| 우선 조건 | Production 결과 |
| --- | --- |
| 종목·시장 coverage/identity 부족 | NOT_EVALUATED |
| entry source 없음 | NO_RECENT_SIGNAL |
| 최초 FINAL explicit failure가 age 만료보다 먼저 또는 같은 날 발생 | INVALIDATED 유지 |
| age 20봉을 넘은 최초 FINAL session이 failure보다 먼저 발생 | EXPIRED 유지 |
| 아직 FINAL terminal이 없고 현재 PROVISIONAL failure/만료 | 잠정 INVALIDATED/EXPIRED |
| 살아 있는 source + 하락 시장 | BLOCK |
| 살아 있는 source + 강세 시장 + 실행 기준가 대비 +5% 이하 | ALLOW |
| 살아 있는 source + 나머지 시장/상단 확장 조건 | EXECUTION_WATCH (내부 WATCH 호환) |

Production v1은 adverse 하한, 3ATR, 1회 지지 이탈, reclaim 기간 실패를 신규 gate로 사용하지 않는다. 따라서 ALLOW와 CAUTION/HIGH_RISK가 동시에 나올 수 있다. ALLOW는 수익 보장이나 실제 수량 지시가 아니다.

## Shadow 경계

- breakout breach/reclaim, initial 5 bars + 3ATR adverse, origin support/low breach·reclaim·연속 이탈은 연구 진단으로만 계산한다.
- frozen anchor는 source 당시 차트에서 재구성하며, 원래 지지선과 현재 이동지지선을 구분한다.
- Strategy는 결과를 저장소에서 읽지 않는다. JSONL은 pipeline이 남기는 독립 연구 기록이다.
- 미래 5/10/20/40/60봉 성과·MAE/MFE는 후속 evaluator 책임이다.

## 실행 근거

- 변경 전: `uv run pytest -q` — 1,864 passed, 15 deselected, 기존 warning 2건, 108.01초.
- Production lifecycle·anchors: `uv run pytest tests/strategies/test_entry_opportunity.py tests/strategies/test_entry_anchors.py tests/strategies/swing_w150 -q` — root 재실행 154 passed, 기존 warning 2건, 3.34초. 독립 Task review: spec PASS / quality PASS, 수정 finding 없음.
- Shadow: 대상 55 passed, 기존 warning 2건. 독립 Task review spec PASS / quality PASS. Production 전체 결과·Signal/Observation·입력 hash의 toggle/parameter/실패 격리 검증을 포함한다.
- 제품 배선: storage + pipelines + position + backtest 대상 770 passed, 4 deselected, 기존 warning 2건. 독립 Task review spec PASS / quality PASS.
- 변경 후 전체: `uv run pytest -q` — **1,928 passed, 15 deselected**, 기존 warning 2건, 102.41초. baseline 대비 64개 테스트 추가.
- `uv run ruff check src tests`, 이번 변경 18개 Python 파일 `ruff format --check`, `git diff --check`: PASS.
- 최종 독립 리뷰(`gpt-6.1-sol`, `xhigh`): READY, Spec/Quality PASS, 수정 finding 없음. 기존 dirty baseline 대비 제품 9개·테스트 9개 파일을 검토했다. controller가 최종 source/test diff의 일치와 Ruff/format/diff 검사를 재확인했으며 검증 이후 제품·테스트 변경은 없다. 리뷰 보고서는 `.superpowers/sdd/2026-10-19-entry-opportunity-production-shadow/final-review.md`에 있다. reviewer는 suite를 중복 실행하지 않았으며 실행 결과와 정적 검토를 구분했다.
- 실제 QuickCheckPipeline + 기본 service/renderer/recorder로 ALAB·COHR·INTC·NVDA·AMD를 평가했다. 모든 ticker에서 Production errors/diagnostic_errors는 빈 목록, Shadow 비활성 결과와 Production 전체 model이 동일했다. 각각 과거 60개 거래일 prefix도 재계산해 71개 source/상태/flag 전환을 확인했다.
- 별도 `uv run jarvis check NVDA` CLI exit 0. FINAL EXPIRED, 종료일, NORMAL 위험도, Signal 근거와 5일 점수가 기본 화면에 출력됐다. 실제 기본 JSONL 파일도 생성됐다.
- analyze/brief는 공통 service·renderer를 통과하는 실행 회귀 테스트로 확인했다. 이번 검증에서 실제 외부 LLM analyze나 실제 전체 portfolio brief를 실행하지 않았다.
- 새 rule의 수익 우월성·통계적 성과를 평가하는 backtest가 아닌 제품 동작 검증이다.

## 실제 ticker / 날짜별 사례

2026-10-19 KST 조회, 미국 차트 기준 **2026-10-16 FINAL 종가**. 장중 현재가·매수 권고로 해석하지 않는다.

| Ticker | 종가 | 최신 source / 발생일 | Age | Production | 구조 위험 |
| --- | ---: | --- | ---: | --- | --- |
| ALAB | $285.82 | TREND_BREAKOUT_ENTRY / 10-06 | 8 | EXECUTION_WATCH | HIGH_RISK: 돌파선 이탈·큰 ATR 하락 |
| COHR | $232.90 | PULLBACK_REVERSAL_ENTRY / 06-30 | 76 | INVALIDATED | HIGH_RISK: 원래 지지선·조정 저점 이탈 |
| INTC | $89.85 | TREND_BREAKOUT_ENTRY / 09-21 | 19 | INVALIDATED | HIGH_RISK: 돌파선 이탈·큰 ATR 하락 |
| NVDA | $214.13 | PULLBACK_REVERSAL_ENTRY / 09-17 | 21 | EXPIRED | NORMAL |
| AMD | $528.75 | TREND_BREAKOUT_ENTRY / 09-21 | 19 | EXECUTION_WATCH | HIGH_RISK: 돌파선 이탈·큰 ATR 하락 |

ALAB/AMD는 시장 sideways 때문에 기존 EXECUTION_WATCH다. 하락폭이나 Shadow의 HIGH_RISK 때문에 Production을 내린 것이 아니다. COHR은 07-17, INTC는 10-16의 SMA150_EXIT로 무효화됐다. NVDA는 구조 위험이 없더라도 source age가 21이 되어 만료된다.

### 날짜별 계약 사례

| 사례 | 실제 차트 prefix | Production / Shadow 결과 |
| --- | --- | --- |
| 깨끗한 돌파 | NVDA 08-27 | 새 TREND_BREAKOUT_ENTRY → ALLOW + NORMAL |
| 돌파선 이탈 | NVDA 08-28 | 같은 source → ALLOW + CAUTION, BREAKOUT_LEVEL_BREACH |
| 돌파선 재탈환 | NVDA 09-03 | 같은 source → ALLOW + NORMAL, BREAKOUT_LEVEL_RECLAIMED |
| 눌림목 지지·저점 이탈 | ALAB 07-31 | 07-09 source → ALLOW + HIGH_RISK; 연구 flag가 Production 차단하지 않음 |
| 기존 explicit failure | COHR 07-31 | 07-17 SMA150_EXIT에 의해 INVALIDATED 유지 |
| 종료 이후 구조 회복 | COHR 08-07 | 지지선·저점 재탈환으로 NORMAL, Production은 INVALIDATED 유지 |
| 새 Signal | ALAB 10-05 → 10-06 | old 07-09 source EXPIRED → 새로운 돌파 source의 ALLOW + NORMAL |

### 기본 출력 발췌: ALAB

```text
SWING_W150: EXECUTION_WATCH [FINAL]
source=TREND_BREAKOUT_ENTRY, 발생일=2026-10-06, 8거래일 전
Production policy=SWING_W150_ENTRY_OPPORTUNITY_PRODUCTION_V1
Signal 기준가 389.80 / 다음 실제 시가 376.00 / 현재 종가 285.82
확장 -24.0%, 시장 sideways
Risk: HIGH_RISK [FINAL]
돌파 기준선 이탈: 관측 285.82 / 기준 377.87
Signal 당시 ATR 대비 큰 하락: 관측 285.82 / 3ATR 기준 320.881
Shadow 진단은 Production·Position Plan을 변경하지 않습니다
```

실행 원문과 재현 차트는 `.superpowers/sdd/2026-10-19-entry-opportunity-production-shadow/live/`에 보존했다. 연구 JSONL은 실제 실행일이 아닌 `evaluation_as_of` 차트 날짜로 식별하고 `recorded_at`만 계산·기록 시각이다. 과거 60일 smoke 결과는 검증 artifact이며 운영 JSONL에 자동 backfill하지 않았다.

## 변경 경계

| 파일/영역 | 책임 |
| --- | --- |
| strategies/models.py, entry_opportunity.py | source anchor/종료 metadata, 최초 FINAL terminal 및 Production version |
| strategies/entry_anchors.py | source 당시 ATR·돌파선·최초 지지선·조정 저점 재구성 |
| strategies/entry_shadow.py | 독립 연구 설정·fingerprint, 구조 진단과 마지막 FINAL 상태 |
| strategies/swing_w150/adapter.py, runner.py | optional Shadow 연결, Production과 오류 분리 |
| storage/entry_shadow.py | 보유·미래 outcome 없는 append-only 연구 snapshot |
| pipelines/strategy_analysis.py, strategy_render.py | 세 경로의 기록/비치명 오류/기본 설명 출력 |
| tests/ 9개 파일 | lifecycle·anchors·isolation·기록·세 경로 parity 및 실데이터 오염 방지 |

### 기록 소비

기본 경로 `data/research/entry-shadow.jsonl`, 환경변수 `JARVIS_ENTRY_SHADOW_LOG_PATH`. `decision_key`는 source/day/strategy·정책·parameter version을 묶으며, `snapshot_key`는 timestamp를 제외한 실제 payload를 식별한다. 반복 snapshot을 dedup한 뒤 Production/chart/anchor/Shadow finality를 구분해 FINAL을 선택한다. 다른 policy 기록은 유지한다. source 당일 execution reference는 종가 추정이며 실제 gap은 null, 이후에는 다음 실제 시가 기준이다. 자동 scheduler/과거 backfill/outcome evaluator는 없다.

## 미결 정책과 향후 평가

- WATCH deterioration gate, failure confirmation, source별 age, 별도 gap gate는 미결이다. 기존 정책 이상의 차단 규칙은 이번 구현에서 도입하지 않는다.
- Shadow 축적 기간과 건수만으로 Production 승격을 자동화하지 않는다. 후보 정의·평가 지표·표본 크기·통과 기준을 먼저 고정하고 새로운 OOS 구간에서 검증해야 한다.
- 다음 연구 시작 여부는 실제 breach/reclaim 사건 수와 source 유형·시장 국면별 분포, 충분한 20/40/60봉 forward 관측률로 판단한다. 현재 최소 표본 수는 확정하지 않았다.
- 기존 Technical Score의 Tennis Ball/Egg 점수 변경은 이번 범위 밖이다.

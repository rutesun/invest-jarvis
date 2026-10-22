# Change Record: Scorecard·Strategy·Position 분리

**Status**: In Progress
**Date**: 2026-10-21
**PRs**: -
**Type**: feat

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

기존 기술 점수, 매매 해석, 실제 주문 수량이 한 흐름에 섞여 같은 차트라도 보유 여부에 따라 의미가 달라질 수 있었다. 측정·차트 사건·실제 수량 계산을 분리하고, 재현 가능한 차트 결과를 저장 없이 다시 계산한다.

## What

1. **5축 Technical Scorecard 추가**: 추세·구조·모멘텀·수급·안전도를 각각 0~100점으로 측정하고, 방향성 metric, Observation과 Evidence, 최근 20거래일 Analysis Trigger를 함께 전달한다.
2. **Strategy 출력을 분리**: `TECHNICAL_LEGACY`·`PLAYBOOK_V1` verdict와 `SWING_W150_V2`의 Observation·Signal·EntryOpportunity를 공통 차트에서 계산한다. 실제·가상 보유, 계좌, DB row, 뉴스와 macro는 Strategy 입력이 아니다.
3. **V2 차트 sequence 추가**: 과열·조정·회복, 자연 해소·만료, 다중 지지 눌림목과 SMA150 exit을 한 번 발생하는 사건으로 추적한다. 최근 entry의 age 20은 유효하고 21부터 만료한다. source 뒤 correction·exit은 `INVALIDATED`, 하락장은 `BLOCK`으로 구분한다.
4. **PositionPlanner 경계 강화**: 오늘 Signal만 주문 후보로 쓰며 신규 매수는 우선순위로 선택한 Signal과 source가 일치하는 오늘 `ALLOW`에만 허용한다. correction은 실제 보유 50% 올림, exit은 전량 매도다. 장중 `PROVISIONAL`도 현재 snapshot으로 계산하며 finality·계산시각·snapshot hash를 반환한다.
5. **세 pipeline 공통 출력 연결**: `check`, `analyze`, `brief`가 현재 Observation, 최근 두 history, EntryOpportunity를 같은 의미로 보여준다. 기본 출력에 Signal과 EntryOpportunity의 전체 판단 Evidence·임계값, 최근 5거래일 Technical Score의 점수·변화·이벤트·주의를 포함한다. parameter fingerprint는 설정 전체를 식별하며 등록된 version의 payload 변경을 거부한다.
6. **SignalPerformance와 V2 Backtest 추가**: Signal 종가와 다음 실제 시가의 수익률을 별도 기준으로 요청 시 계산한다. 장중은 `PARTIAL`이다. V1 Golden은 유지하고 V2는 FINAL-only·T+1·stop 우선·50% correction·별도 lot·모든 fill 비용을 검증한다. aggregate R의 분모는 청산된 수량의 초기 risk다.
7. **PostgreSQL Strategy 저장 제거**: `strategy_history` code·migration·test·runtime session 연결을 삭제한다. Observation·Trigger·Signal·EntryOpportunity·성과는 차트에서 재계산하고 PositionPlan은 현재 요청에 반환한다. Stock Report PostgreSQL과 공통 utility는 유지한다.
8. **EntryOpportunity Production v2 + 독립 Shadow**: 기존 market·+5%·20봉, 최초 FINAL terminal, 최신 source/no-fallback 계약을 유지한다. `TREND_BREAKOUT_ENTRY`는 source 다음 봉부터 종가가 고정 돌파선에서 source ATR(14)의 1.0배 이상 하락하면 진입 허가를 취소한다. 동일일 explicit exit → 가격 이탈 → 만료 순서이며, 장중 이탈은 PROVISIONAL로 표시한다. 공통 출력에 가격·source 돌파선·ATR·배수·취소선을 제공한다. Shadow의 나머지 후보는 독립 진단으로 유지하며 실제 보유·수량·매도와 결합하지 않는다.
9. Trading Observation v1은 기본 ON으로 SETUP과 Positive/Risk Evidence, EVENT와 EPISODE, 피벗일과 확인일을 구분하고 source·anchor·terminal 문맥을 표시한다. 거래량 확장·수축 detector 설정은 미선정이며 미평가로 남긴다. 표시 설정은 Signal/Opportunity/Planner와 분리한다. 새 support ladder Pullback은 명시 V2 API로 구현하되 failure/restart 미선정으로 사용자 기본 Pullback parameter V1을 유지한다. offline 비교·실제 사례 명령은 보존 baseline의 예상 artifact 집합과 hash를 먼저 확인하고, 단일 연구 profile을 운영 선정과 구분해 기록한다.
10. 중간 PROVISIONAL 가격이 FINAL 구조 사건·명시 V2 INITIAL을 확정하던 경계를 수정한다. 공통 pivot 계산에서 FINAL 부분집합과 원래 날짜를 함께 보존하며 기존 V1 rolling은 유지한다. custom 거래량 확장 사건에는 가격 변화·실제 거래량·직전20봉 기준 거래량·ratio Evidence를 추가하고 기존 threshold와 기본 미선정 상태를 유지한다.
11. 복수 Entry의 대표 source를 Opportunity와 Planner가 공유한다. 최신 발생일을 우선하고 같은 날에는 과열후회복→눌림목반등→추세돌파→바닥회복 순으로 선택한다. 모든 Signal, source별 취소 조건과 exact source guard는 유지하며, 대표가 진입 불가여도 다른 source로 우회하지 않는다. 대표 선택 순서의 수익성은 별도 검증 대상이다.

## Before / After

```text
Before: 가상 보유를 재생하는 SWING 참고 표시와 PostgreSQL Strategy history/cache
After:  Observation과 날짜별 Signal, 오늘 EntryOpportunity, 두 성과 기준을 차트로 재계산
        실제 보유·계좌·가격 snapshot은 PositionPlanner에서만 사용
```

## Impact

- 기존 `total_score`, technical action, Playbook 결과와 brief ranking은 유지하며 production SWING은 V2 Signal을 사용한다.
- live 차트 입력은 2y이며 V2에는 최소 250봉이 필요하다. 미국과 한국 benchmark를 지원하고 coverage 부족은 `NOT_EVALUATED`로 표시한다.
- Strategy 관련 DB DSN과 migration은 사용하지 않는다. 이번 제거는 저장 기능 삭제이며 운영 DB의 DROP 작업은 포함하지 않는다.
- 미국·한국 거래소 calendar를 가격 응답과 분리하여 같은 날 종목·시장 데이터가 빠져도 누락을 확인한다. 미설명 종목 gap은 Signal·실제 매도 제안을 막으며, 시장 부재만으로 완전한 종목 Signal을 억제하지 않는다.
- live `2y` 응답의 첫 예상 거래일 1개 생략은 이후 날짜가 모두 연속일 때만 정상 기간 경계로 허용한다. 원래 요청·전체 calendar와 유효 평가 시작은 구분하며 시작 2개 이상·중간·끝 누락은 계속 차단한다.
- V2 Backtest는 독립 예상 거래일을 필수로 받고 확인된 no-trade만 건너뛴다. 현재 기회 기준가의 발생 당일 종가 추정과 이후 실제 시가를 구분해 표시한다.

## Compatibility and rollback

- 새 Strategy 계산이 실패하면 기존 출력은 제공하고 V2 slot에 실패 Evidence와 `NOT_EVALUATED`를 표시한다.
- V1 연구 Backtest와 Golden은 호환 기준으로 유지한다. 가상 position을 Strategy 판단에 다시 넣거나 삭제된 저장 연결을 부분적으로 되살리는 rollback은 별도 설계가 필요하다.
- 기존 단일 action과 중복 출력 제거는 병렬 비교 후 별도 결정한다. 최종 독립 리뷰와 실제 pipeline 확인이 이번 완료 gate다.

## Constraints

- 과열과 눌림목은 SWING V2의 차트 sequence이며 매매 체결·장부는 Backtest에만 속한다.
- `PositionPlan`은 주문 제안이며 실제 주문 전송과 체결 추적은 포함하지 않는다.
- 장중 finality는 현재 provider의 정규 종료 시각과 15분 buffer를 사용하며 조기 종료 metadata는 미지원이다.
- 실제 계좌 risk와 현재 가격 snapshot이 부족하면 신규 매수 수량은 `UNAVAILABLE`다. Strategy에서 가상 stop/risk를 채우지 않는다.

## Verification

2026-10-22 통합 준비: 사용자가 PR·독립 리뷰·조건부 merge·main pull을 승인했다. CI 전체 format 검사에서 기존 4파일의 포맷을 정리하고 AST(구문 구조) 동일성을 확인했다. 전체 Ruff 및 445개 Python format 검사는 통과했다. 원래 branch와 무관한 사용자 변경은 보존하고 별도 Notebook 커밋은 통합 PR에서 제외한다. PR head·최종 리뷰·CI·merge 결과는 후속 검증으로 확정한다.

2026-10-22 Important1 후속 수정: 최신 날짜·같은 날 공통 Entry 순위로 Opportunity/Planner 대표 source를 통일했다. 신규 회귀 RED12실패→covering199통과, root 전체 **2,193 passed / 15 deselected / 기존 warning2**(191.01s), 전체 Ruff·변경Python8 format·diff·CLI help 통과. 실제 COIN 두 Entry를 보존하면서 기존 source mismatch 매수0을 올바른 PULLBACK source의 매수 후보로 연결했다. INTC frozen gate는 승인된 source/anchor 차이만 허용하고 non-gate와 원본 artifact는 보존한다. 독립 수정 리뷰 Spec PASS/Quality 승인(C0/I0/M0), 이후 코드 hash 불변. 아래 원 리뷰의 두 Important는 모두 후속 수정·검증했으며 두 수정은 미커밋이다. 전체 branch 새 merge 승인·운영 V2 승격·수익성 검증을 뜻하지 않는다.

2026-10-21 Important2 후속 수정: Backtest가 명시 V2의 `PRIOR_BREAKOUT_LEVEL` 지지 Evidence를 소비하도록 보완했다. 신규 positive 회귀 2개가 기존 오류로 실패한 뒤 수정 후 Backtest 61개, root 전체 **2,165 passed / 15 deselected / 기존 warning 2건**(190.26s)을 통과했다. 원래 중단되던 COIN 전체 1,371봉도 public API에서 완료했고, 2024-11-11 실제 Signal의 11/12 시가 2주 체결을 확인했다. 수정 두 파일의 독립 리뷰는 Spec PASS / Quality 승인(C0/I0/M0)이다. 기존 손절·비용·lot/R·운영 기본값은 유지하며, 아래 전체 리뷰의 Important1은 아직 미수정이다. 이번 후속 수정은 미커밋 상태다.

누적 구현 커밋 `67d9641`의 새 전체 독립 리뷰는 **Critical 0 / Important 2 / Minor 0, 수정 필요**였다. 복수 Entry의 Opportunity/Planner source 선택 불일치와 명시 V2 돌파선 지지 Signal의 Backtest consumer 누락을 재현했다. reviewer focused 277개는 통과했으며 리뷰 당시 두 지적은 미수정이었다. [리뷰 범위·재현·다음 행동](../references/2026-10-21-committed-strategy-review.md)을 참고한다. 위 후속 수정과 아래 부분 리뷰 PASS를 구분한다.

2026-10-21 로컬 커밋 직전 root 재검증: `uv run pytest` **2,158 passed, 15 deselected, 기존 warning 2건**(179.12s), `uv run ruff check src tests scripts/research_trading_observations.py` 및 staged diff 검사 PASS. 사용자가 로컬 commit과 커밋 전체 독립 리뷰를 승인했으며, 아래 최신 -1 ATR 부분 리뷰와 별도로 전체 리뷰를 진행한다. push/merge는 범위에 포함하지 않는다.

2026-10-21 EntryOpportunity Production V2의 최종 전체 테스트는 **2,158 passed, 15 deselected, 기존 warning 2건**(184.09s)이며 focused 125개·변경 Python 6개 Ruff/format·diff 검사를 통과했다. 저장 ALAB의 실제 adapter·공통 renderer에서 고정 취소선354.89697934663843, 최초 FINAL 취소일2026-10-08(close347.04998779296875)을 확인했고, 양 parameter profile 및 Observation/Shadow ON/OFF 판정이 일치했다. 독립 최종 리뷰는 Spec PASS / Quality Approved(Critical·Important·Minor 각 0건)이며 frozen 연구 결과·Signal history·실제 보유 매도 규칙을 보존하고 commit/push/merge는 수행하지 않았다.

2026-10-21 Trading Observation v1의 수정 후 전체 테스트는 **2,142 passed, 15 deselected, 기존 warning 2건**이다. 전체 Ruff·변경 Python 11개 format을 통과했다. 원 ALL_FINAL 비교는 V1/명시 V2 각각 Observation ON/OFF 21/21 및 보존 baseline 21/21 MATCH, SMA150_EXIT 의미도 21입력에서 같다. 로컬 실제 AMD 다섯 유형·일곱 prefix는 실제 Runner/adapter와 공통 renderer로 재현했고, 후속 finality/Evidence 수정 뒤에도 전체 JSON·Planner·renderer 7/7 MATCH다. 원실행·수정 후 동등성 receipt·압축된 정책 차이와 [검증 제한](../references/2026-10-21-trading-observation-v1-validation.md)을 구분해 기록했다. 코드 재리뷰 I1/M1은 ADDRESSED이며 최종 artifact/docs 승인은 별도 gate다. 세 CLI live 실행·5일 Score history 실측·운영 V2 승격으로 확대하지 않는다.

2026-10-19 Production v1 + 독립 Shadow 추가 후 root 전체 **1,928 passed, 15 deselected**, 기존 warning 2건. src/tests Ruff·변경 18개 Python 파일 format·diff 검사 PASS. 5개 실제 ticker와 각 60거래일 prefix에서 71개 상태 전환, 별도 `check NVDA` CLI exit 0 및 JSONL 생성을 확인했다. 세 Task 독립 spec/quality review와 xhigh 최종 전체 변경 리뷰 모두 PASS이며 최종 판정은 READY(Critical·Important·Minor 각 0건)다. 검증 이후 제품·테스트 변경이 없음을 재확인했다. commit/push/merge는 수행하지 않았다. [정책표·실제 출력·기록 계약과 검증 한계](../references/2026-10-19-entry-opportunity-production-shadow-validation.md)를 참고한다. 아래 기록은 이전 구현 단계의 결과다.

2026-10-12 공통 기본 출력에 Signal·EntryOpportunity 판단 원인과 최근 5거래일 Technical Score 상세를 연결했다. 최신 전체 test는 1,864 passed, 15 deselected, 기존 warning 2건이며 Ruff·변경 파일 format·diff 검사를 통과했다. 실제 `jarvis check NVDA`에서 한국어 Signal 원인, EntryOpportunity의 +4.5% 관측값과 +5.0% 허용 상한, 5일 점수·변화·이벤트 출력을 확인했다.

Important 4건 수정 후 focused 435개·전체 1849개(15 deselected, 기존 warning 2개), Ruff·변경 파일 format·diff 검사를 통과했다. 수정 후 live는 미실행이며 독립 재검토를 기다린다. 최신 검증은 `.superpowers/sdd/2026-10-06-strategy-signal-boundary-migration/review-important-fixes-report.md`에 기록한다. 아래는 수정 전 Task 9 검증 기준이다.

추가 전체 format 검사는 기존 미변경 4개 파일에서 실패했다. 이번 수정 파일 11개는 통과했으며 범위 밖 파일은 보존했다. 정확한 경로와 결과는 최신 보고서에 기록했다.

후속 live에서 발견한 정상 `2y` 시작 경계 회귀를 TDD로 보완했다. 보완 후 focused 238개·변경 5개 Ruff/format·diff 검사가 통과했다. 위 전체 1849개는 이 보완 전 기준이며 최신 전체·live 결과는 coordinator가 재검증한다.

- 2026-10-08 최종 focused architecture suite: 411 passed, 기존 warning 2건
- 최종 전체 test(root 검증): 1825 passed, 15 deselected, 기존 warning 2건
- `uv run ruff check src tests`: passed
- `git diff --check`와 runtime·migration·test의 삭제 subsystem 검색: passed, import match 0건
- 수정 후 `check NVDA`·`analyze NVDA`·`brief`: 모두 exit 0. 동일한 FINAL 눌림목 Signal, WATCH 기회, 두 성과 기준을 확인했다. analyze·brief는 실제 29주 유지와 FINAL 계획을 표시한다.
- 최초 live 실행에서 발견한 지지선 소실·NumPy bool serialization·영숫자 KRX finality 문제는 수정 후 재실행으로 해소했다. 초기 실패 원문과 최종 결과는 Task 9 보고서에 분리해 기록했다.
- 입력이 부족한 brief 3개 종목은 `NOT_EVALUATED`이며 뉴스·수급 부재와 기존 volume ratio warning은 검증 한계로 남는다. 최종 독립 리뷰는 coordinator가 별도로 수행한다.

## Related

- 설계: `docs/superpowers/specs/2026-10-06-strategy-signal-outcome-backtest-boundary-design.md`
- 구현 계획: `docs/superpowers/plans/2026-10-06-strategy-signal-boundary-migration.md`
- ADR: 없음
- FEATURES.md: `14. Scorecard·Strategy·Position 분리`
- 후속: Production v1 + Shadow 구현·검증·독립 리뷰 완료. 후속 연구 및 commit/PR/merge는 별도 지시·승인 후 진행한다.

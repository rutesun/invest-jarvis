# Active Context — Strategy·Observation·EntryOpportunity

- 갱신: 2026-10-22 14:26 KST · Branch: feature/scorecard-strategy-position-separation · Status: 사용자 승인으로 PR·독립 리뷰·CI·조건부 merge 및 main 최신화 진행

## 목표
차트 측정·전략 해석·실제 수량 계산의 책임을 유지하고 독립 리뷰의 consumer 불일치를 해소한다.

## 진행 단계
누적 구현67d9641 → 전체 리뷰 기록6ee6352 → Important2 수정·독립 승인 → Important1 공통 선택 구현·독립 승인 → 전체2,193통과

## 지금까지
- 전체 리뷰는 C0/I2/M0였다. Important1은 같은 날 복수 Entry의 Opportunity/Planner 대표 source 선택 불일치, Important2는 새 돌파선 지지 Signal의 Backtest 소비 누락이다.
- Important2는 Backtest 허용 지지 종류에 PRIOR_BREAKOUT_LEVEL을 추가하고 정상 stop·수량, 실제 COIN raw→Signal→T+1체결, 누락·비정상 Evidence 거부 회귀로 수정했다.
- 수정 전 positive 회귀2개 실패, 수정 후 Backtest61개와 root 전체2,165개 통과(15제외·기존 경고2,190.26초). 두 수정 파일 독립 리뷰 Spec PASS/Quality 승인(C0/I0/M0), Ruff·format·diff 통과.
- root가 원래 실패한 COIN 전체1,371봉을 public API로 완료하고 2024-11-11Signal→11/12시가310.05·2주 체결을 확인했다. 새 시세·외부 API 호출 없음.
- ALAB 돌파선−source1ATR 취소 규칙은67d9641에 포함됐다. source10/6 취소선354.90, 최초 FINAL 취소10/8이며 회복해도 old opportunity는 부활하지 않는다.
- Important1은 사용자 승인으로 최신 Entry 날짜 우선·동일일 과열후회복→눌림목반등→추세돌파→바닥회복을 공유하도록 수정했다. 모든 Signal/ID와 source별 취소·today/exact-source guard·청산/축소 우선은 유지한다. 대표가 허용되지 않아도 다른 source로 우회하지 않는다.
- 신규 회귀 RED12실패→covering199통과. 실제 COIN 2024-07-22의 두 Entry는 그대로이며, 충분한 가상 계좌·명시 synthetic bull benchmark에서 source PULLBACK·ALLOW·매수후보50주로 연결됨을 root가 재확인했다. 실제 주문은 없다.
- 최신 root 전체 `uv run pytest`: 2,193 passed / 15 deselected / 기존 경고2(191.01초). 전체 Ruff·변경Python8 format·diff·CLI help 통과. Important1 독립 리뷰 Spec PASS/Quality 승인(C0/I0/M0), 이후 제품/테스트 hash 불변. 기존 Backtest 수정 hash도 유지했다.
- frozen product 21개 중 INTC 1개만 대표 source가 바뀌었다. history·non-gate 전체 비교와 source/anchor의 좁은 기대값 비교를 유지하고 원본 artifact는 보존했다.

## 핵심 결정
- Strategy는 chart-only이며 보유/DB 장부를 읽지 않는다. 실제 수량은 PositionPlanner, 가상 실행·stop·lot/R은 Backtest의 책임이다.
- Observation 기본ON, 기본 Pullback V1 유지. 새 cycle/support ladder는 명시 V2 연구 경로이며 failure/restart 운영 선정은 UNRESOLVED다.
- INITIAL은 FINAL close>SMA150·SMA150 flat/rising과 confirmed HH/유효돌파/기존 bullish Entry 중 하나다. SMA50 정배열·Supertrend UP·거래량·HL은 공통 필수가 아니다.
- Opportunity 취소는 실제 보유의 자동 매도를 뜻하지 않는다. 모든 Signal을 기록하되 대표 선택과 매수 source guard는 일치해야 한다.

## 다음 행동
1. 사용자가 PR 생성·리뷰 후 문제 없으면 merge·main pull을 승인했다. 원래 branch를 보존하고 별도 Notebook 커밋은 제외한 통합 PR을 만든다.
2. PR 최종 head의 독립 리뷰·CI를 확인한 뒤 merge한다. 기존 main의 중복 cherry-pick 이력은 backup ref에 보존하고 원격 main과 일치시킨다.
3. CI 전체 format의 기존 4파일은 의미 변경 없이 정리했으며 AST 동일성을 확인했다. 새 provider/live 조회·실제 주문은 범위 밖이다.

## 함정 · 미결
- 무관한 .serena/.codex 설정·notebook 문서·대용량 tmp·ignored .superpowers 자료를 정리하지 않는다.
- 과거 연구 artifact와 당시 source/hash를 보존한다. 이번 호환 수정은 운영 V2 승격·수익성 검증이나 별도 연구 재선정이 아니다.

## 참조
1. `docs/references/2026-10-21-committed-strategy-review.md` — 원 리뷰와 후속 수정 상태
2. `docs/changes/scorecard-strategy-position-separation.md` — 변경 범위·검증 이력
3. `docs/worklog/trading-observation-v1.md` — 결정·버그 검증 기록

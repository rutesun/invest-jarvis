# Active Context — notebook-notion-sync

- 갱신: 2026-10-26 18:47 · Branch: feature/notebook-notion-sync · Status: PR 생성·머지 검증 진행 중

## 목표
Notion에는 읽기용 본문을 표시하고 원본 Markdown은 로컬에 보존합니다.

## 지금까지
- 10-22: 신규35개 업로드. 기존83개 legacy 보존.
- 10-26: 전체118개 스캔 후35개 page의 Raw Markdown 보관 block35개 제거.
- 읽기용 본문·pageID/URL·schema·원본 보존,35개 v2 hash 검증 완료.
- Default view(table)의 Content Hash/Key/Source Path/출처는 이미 숨김. 속성 유지.
- 자동 원문 부록을 제거하고 notebook-v2 사용. 작성된 코드 예시 유지.
- jarvis-notebook 스킬에 원문 부록 미생성·읽기용 본문 보존·목록 열 숨김 및 schema 유지 규칙 반영. 스킬 형식 검증 PASS.
- 최신 main 병합 완료. 독립 리뷰에서 발견한 식별자·URL 내부 밑줄과 C# 제목 손실 수정, 관련154 tests PASS·재리뷰 Critical/Important 0건.
- 관련148 tests/Ruff PASS. 전체1554 passed/24 failed/15 deselected; 환경실패는 worklog 참조.

## 핵심 결정
- 원문은 로컬에만 보존합니다. 동기화 속성은 목록에서 숨기고 schema에는 유지합니다.
- 기존83개 legacy의 본문·분류 migration은 미실행입니다.

## 다음 행동
1. Notion 본문·목록 표시 확인.
2. 현재 로컬124개/remote118개. 신규6개는 별도 범위에서 검색근거·schema 보완 후 검토.
3. 정리한35개는 UNCHANGED입니다. v1 manifest를 재사용하지 않습니다.

## 함정 · 하지 말 것
원본 수정/source-missing 자동archive/PDF업로드 금지 유지. 10-26 사용자 요청으로 PR 생성·머지 진행 중. 개인자료 Git 제외·0600.

## 참조
1. docs/handoff/notebook-notion-sync.md
2. docs/worklog/notebook-notion-sync.md
3. data/notebook-notion/verification-remove-raw-2026-10-26.json

## 이전 main 작업 상태 (PR #63 병합 이력)

### Strategy·Observation·EntryOpportunity

- 갱신: 2026-10-22 14:40 KST · Branch: feature/scorecard-strategy-position-pr-20261022 · Status: PR #63 최종 로컬 검증·독립 리뷰 승인, GitHub CI 통과 후 merge

## 목표
차트 측정·전략 해석·실제 수량 계산의 책임을 유지하고 독립 리뷰의 consumer 불일치를 해소한다.

## 진행 단계
누적 구현 → 대표 Entry·Backtest 호환 수정 → PR #63 → CI 이식성·coverage 수정 → 전체2,197통과·독립 리뷰 C0/I0/M0

## 지금까지
- [PR #63](https://github.com/rutesun/invest-jarvis/pull/63)을 생성했다. 원래 branch와 로컬 main 이력을 보존하고 별도 Notebook 커밋은 제외했다. 통합 head c71639f에서 로컬 전체 2,193개와 Ruff/전체 format은 통과했으나 GitHub Linux CI는 개인 Downloads의 외부 스펙 경로에 의존하는 연구 테스트 2개가 실패했다.
- 같은 head의 새 전체 독립 리뷰 C0/I1/M1을 모두 수정했다. 테스트 전용 authority fixture로 개인 경로 의존성을 분리하고, 명시된 불완전 coverage에서 Observation을 생성하지 않도록 했다. 실제 연구 protocol·과거 artifact·strict freeze 검증·coverage 없는 독립 연구 동작은 보존한다.
- 수정 후 root 전체 `uv run pytest`: 2,197 passed / 15 deselected / 기존 경고2(191.32초). 전체 Ruff·445개 format·diff PASS. 관련87개 회귀와 외부 문서 미존재·거래소 세션 누락의 RED/GREEN을 확인했다. 같은 전체 PR reviewer의 재리뷰는 Spec PASS/Quality 승인(C0/I0/M0)이다. 이후 제품 변경은 없으며 GitHub CI와 실제 merge 상태는 [PR #63](https://github.com/rutesun/invest-jarvis/pull/63)이 기준이다.
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
1. 수정 head를 publish하고 GitHub lint/test가 모두 성공했는지 확인한다. frozen 연구 protocol과 과거 artifact는 변경하지 않는다.
2. 검토한 정확한 head를 지정해 PR #63을 merge한다. 기존 main의 중복 cherry-pick 이력은 backup ref에 보존하고 원격 main을 pull한 뒤 merge commit과 일치하는지 확인한다.
3. CI 전체 format의 기존 4파일은 의미 변경 없이 정리했으며 AST 동일성을 확인했다. 새 provider/live 조회·실제 주문은 범위 밖이다.

## 함정 · 미결
- 무관한 .serena/.codex 설정·notebook 문서·대용량 tmp·ignored .superpowers 자료를 정리하지 않는다.
- 과거 연구 artifact와 당시 source/hash를 보존한다. 이번 호환 수정은 운영 V2 승격·수익성 검증이나 별도 연구 재선정이 아니다.

## 참조
1. `docs/references/2026-10-21-committed-strategy-review.md` — 원 리뷰와 후속 수정 상태
2. `docs/changes/scorecard-strategy-position-separation.md` — 변경 범위·검증 이력
3. `docs/worklog/trading-observation-v1.md` — 결정·버그 검증 기록

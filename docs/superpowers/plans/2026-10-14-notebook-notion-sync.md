# Notebook Notion Sync Implementation Plan

> 실행: superpowers:executing-plans와 test-driven-development를 적용합니다. 사용자의 2026-10-14 지시로 로컬 구현·검증을 연속 진행하며 commit과 외부 쓰기는 생략합니다.

**Goal:** 원본을 수정하지 않고 항목별 변경과 실제 적용 범위를 검토할 수 있는 지속 동기화를 구현합니다.
**Architecture:** parser → renderer → remote snapshot/plan → 승인 manifest 기반 create-verify-swap. journal로 불확실한 쓰기를 차단하고 read-back으로 실제 내용을 검증합니다.
**Tech Stack:** Python, uv, httpx, Typer, pytest.
**Spec:** `docs/superpowers/specs/2026-10-02-notebook-notion-sync-design.md`

## Global Constraints
- 원본 `/Users/al03229901/Develop/My/invest-jarvis/notebook`은 읽기 전용입니다.
- 대상 Database `eee67e454ce4478b9f1749e8e92a1b42`, API `2025-09-03`.
- 이번 실행은 schema/page/archive/PDF 쓰기와 commit/push/PR을 하지 않습니다.
- 기존 Key `{type}/{date}#{title}`를 유지합니다. legacy와 orphan은 자동 적용하지 않습니다.
- Source Path/rich_text, Content Hash/rich_text, PDF 원문/url을 제안하며 현재 schema를 자동 수정하지 않습니다.
- 적용 명령은 검토 manifest와 독립 journal을 요구합니다. 기본 CLI는 읽기 전용입니다.

## Review Focus
- 코드 fence 안의 H2/H3를 항목으로 오인하지 않아야 합니다.
- 긴 한글·emoji·URL과 100개 초과 block/child를 잘라 버리지 않아야 합니다.
- Notion에서 사람이 바꾼 본문이나 schema가 stale manifest로 덮이지 않아야 합니다.
- create/append/archive 응답 유실은 재시도 중복을 만들지 않아야 합니다.
- 새 page 간 순환 wikilink는 할당한 page ID를 통해 연결하고 hash가 ID에 종속되지 않아야 합니다.

## Task 1: Parser와 lossless renderer
Files: `src/tools/notebook/{models,parser,markdown}.py`, `tests/tools/notebook/`.
Interfaces: `parse_notebook_dir(Path) -> list[NotebookEntry]`; `render_markdown(str, resolver) -> list[dict]`.
- [x] fixture로 기존 Key, fence, date 오류, duplicate, 제외 문서 및 원문 보존 테스트를 먼저 작성하고 실패를 확인합니다.
- [x] Markdown link, callout, nested list, wikilink, table, code를 구현합니다. 미지원 문법은 literal로 보존합니다.
- [x] rich_text 2,000자와 block 100개 제한을 확인합니다. 원문은 별도의 raw Markdown code block으로도 보존합니다.
- [x] `uv run pytest tests/tools/notebook` 통과를 확인합니다.

## Task 2: Remote-aware plan
Files: `src/integrations/notebook_notion/{remote,plan}.py`, `tests/integrations/test_notebook_notion.py`.
Interfaces: `Remote.snapshot(database_id) -> dict`; `build_plan(entries, snapshot) -> dict`.
- [x] pagination, schema drift, duplicate, legacy, unchanged와 dry-run zero-write 테스트를 먼저 작성합니다.
- [x] GET와 query POST만 허용하는 read-only client를 구현합니다. token과 본문을 manifest에 기록하지 않습니다.
- [x] schema/local/remote fingerprints, 변경 hash, 적용 대상 목록과 schema 제안을 JSON으로 저장합니다.
- [x] 로컬 fixture 및 현재 remote 재조회로 검증합니다.

## Task 3: Apply와 recovery (fake API로만 실행)
Files: `src/integrations/notebook_notion/apply.py`, 같은 integration test.
Interfaces: `apply_plan(remote, entries, manifest, journal_path) -> dict`.
- [x] create/append/read-back/archive 실패와 stale manifest 차단 테스트를 먼저 작성합니다.
- [x] page ID 2-pass 할당, batch append, normalized read-back, 검증 후 archive를 구현합니다.
- [x] append 응답 유실은 실제 prefix와 비교해 복구합니다. create 응답 유실은 수동 reconcile을 요구합니다.
- [x] journal atomic write와 단일 실행 lock을 구현합니다. legacy migration과 orphan archive는 일반 적용에서 제외합니다.

## Task 4: CLI와 인계
Files: `src/cli/notebook.py`, `src/cli/main.py`, CLI/FEATURES/changes/worklog/handoff/active-context.
- [x] CLI 기본 dry-run, offline 및 잘못된 apply 조합을 검증합니다.
- [x] 전체 `uv run pytest`, scoped ruff, CLI help, 읽기 전용 live plan을 실행합니다.
- [x] 실제 schema 제안과 private manifest 위치를 문서화합니다. 개인 본문/secret은 문서와 로그에서 제외합니다.
- [x] 독립 reviewer로 전체 변경을 확인하고 중요한 지적을 수정합니다.

## 실행 기록
- Pre-flight: parser의 entry/renderer 인터페이스를 plan/apply가 공유합니다. hash는 logical wikilink로 계산하고 실제 page ID는 apply 시 치환합니다.
- Ruling: 기존 설계의 승인 대기 문구는 이번 사용자의 로컬 구현 지시로 대체합니다. 외부 적용 승인은 포함하지 않습니다.
- Ruling: 본문 무손실을 보장하기 위해 보기용 변환과 별도로 원본 Markdown code block을 보존합니다. 따라서 지원하지 않는 문법도 복구 가능합니다.

- Task 1–4 완료: 관련 68 passed, scoped Ruff/check-format PASS, CLI help/offline/live dry-run 확인.
- 독립 리뷰: 중요 지적 6개를 regression RED→GREEN으로 수정 후 추가 Critical/Important 없음.
- 전체 suite: 1480 passed / 18 failed / 15 deselected. 기존 HEAD에서 11개 환경 실패 재현, 외부 금융 API DNS 실패 7개. 세부 근거는 worklog 참조.
- Ruling: 새 코드 경로와 개인 원본의 이름이 모두 notebook이어서 기존 broad gitignore가 코드를 숨겼습니다. /notebook/으로 범위를 root 원본에 한정했습니다. pycache와 private data는 기존 규칙으로 계속 제외됩니다.
- 외부 적용은 미실행이며 현재 manifest에는 SCHEMA_CHANGE_REQUIRED blocker가 있습니다.


## 2026-10-22 후속: 종목별 묶음
사용자 승인: 삼성전자 관련 문서를 같은 종목으로 묶고 업로드 없이 검증합니다. 새 속성을 만들지 않고 기존 `종목`을 정확히 채웁니다.

- [x] 재현: 국내 이름이 테마로 빠지는 오류, 이름/코드 중복, ETF 제목 잘림을 RED 테스트로 고정합니다.
- [x] 정적 국내 회사명·확인된 코드 별칭만 통일합니다. 미등록 문자열을 무리하게 추정하거나 외부 resolver를 호출하지 않습니다.
- [x] offline/remote-aware manifest에 `stock_groups`를 추가하고 legacy 포함 예정 분류를 검증합니다.
- [x] 최신 원본/remote 재조회, 원본 hash 불변, 117개 raw 복원, scoped 75 tests/Ruff, 전체 suite와 독립 리뷰를 수행합니다.
- [x] schema 제안·신규 34개 manifest·1개 시험 후보와 문서를 갱신합니다. 실제 쓰기는 없습니다.

제약: 이 사전은 전체 시장을 다루지 않습니다. 기존 미국 ticker와 6자리 코드 처리 및 미등록 매매 제목 첫 단어 fallback은 호환 유지합니다. 예를 들어 아마존/AMZN은 아직 통합하지 않습니다. 삼성전자 본문·제목 언급만 있는 16개는 자동 지정하지 않고 private verification의 검토 후보 목록으로 남깁니다.


## 2026-10-22 후속 정정: API 기반 종목 분류
사용자가 수동 대응표를 거부하고 검색 API 사용을 지시했습니다. 위 정적 45이름/8코드 구현과 그 수치를 현재 API 분류 검증으로 사용하지 않습니다.

- [x] Naver 검색 raw→StockIdentity 골든 테스트와 runtime boundary 검증을 추가합니다. 국가/시장/code로 식별하며 KOSDAQ을 KOSPI로 가정하지 않습니다.
- [x] parser를 raw 후보 추출로 전환하고 company whitelist를 제거합니다. API 결과로 종목을 확정하고 모호한 이름·short ticker 충돌·부분 ETF 매칭은 검토합니다.
- [x] 검색 근거 cache v2/30일·증분 저장·offline 재현·frozen manifest apply와 만료 resume 복구를 검증합니다.
- [x] 리뷰의 소문자 충돌·부분 ETF·만료 복구·cache형식 우회를 RED→GREEN으로 수정합니다.
- [x] 공개 종목 샘플의 실제 검색/종류 API 응답을 확인하고 fixture/부분 미리보기로 보존합니다.
- [x] 사용자 명시 승인 후 기존542개 검색어 조회 완료. 500개 성공 뒤 nullable nation 응답 중단을 회귀 수정하고 증분 cache로42개만 재개했습니다. 승인 시점117항목 기준 최신 remote-aware manifest/schema proposal/trial을 생성했습니다. 작업 중 추가된 새1항목은 제외하고 SOURCE_SCOPE_CHANGED로 적용을 차단합니다.
- [ ] 실제 schema/page/PDF 적용: 여전히 금지입니다.

## 2026-10-26 사용자 표시 정책 갱신
이전 raw 부록 복원 계획은 이력입니다. 사용자 지시로 원본은 로컬에서만 보존하고 Notion 자동 Raw Markdown 부록을 제거합니다. 작성된 코드예시는 유지하고 notebook-v2 projection/hash를 사용합니다. 실제 정리는 pageID와 읽기용 본문을 보존하는 in-place 작업으로 진행하며 hash갱신전 일치를 확인합니다. 목록4속성은 숨기되schema에서삭제하지않습니다. 최신결과는handoff와worklog를따릅니다.

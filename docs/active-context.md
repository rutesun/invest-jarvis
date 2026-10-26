# Active Context — notebook-notion-sync

- 갱신: 2026-10-26 18:29 · Branch: feature/notebook-notion-sync · Status: Notion 본문·목록 정리 및 notebook 스킬 반영 완료

## 목표
Notion에는 읽기용 본문을 표시하고 원본 Markdown은 로컬에 보존합니다.

## 지금까지
- 10-22: 신규35개 업로드. 기존83개 legacy 보존.
- 10-26: 전체118개 스캔 후35개 page의 Raw Markdown 보관 block35개 제거.
- 읽기용 본문·pageID/URL·schema·원본 보존,35개 v2 hash 검증 완료.
- Default view(table)의 Content Hash/Key/Source Path/출처는 이미 숨김. 속성 유지.
- 자동 원문 부록을 제거하고 notebook-v2 사용. 작성된 코드 예시 유지.
- jarvis-notebook 스킬에 원문 부록 미생성·읽기용 본문 보존·목록 열 숨김 및 schema 유지 규칙 반영. 스킬 형식 검증 PASS.
- 관련148 tests/Ruff PASS. 전체1554 passed/24 failed/15 deselected; 환경실패는 worklog 참조.

## 핵심 결정
- 원문은 로컬에만 보존합니다. 동기화 속성은 목록에서 숨기고 schema에는 유지합니다.
- 기존83개 legacy의 본문·분류 migration은 미실행입니다.

## 다음 행동
1. Notion 본문·목록 표시 확인.
2. 현재 로컬124개/remote118개. 신규6개는 별도 범위에서 검색근거·schema 보완 후 검토.
3. 정리한35개는 UNCHANGED입니다. v1 manifest를 재사용하지 않습니다.

## 함정 · 하지 말 것
원본 수정/source-missing 자동archive/PDF업로드/commit·push·PR 금지 유지. 개인자료 Git 제외·0600.

## 참조
1. docs/handoff/notebook-notion-sync.md
2. docs/worklog/notebook-notion-sync.md
3. data/notebook-notion/verification-remove-raw-2026-10-26.json

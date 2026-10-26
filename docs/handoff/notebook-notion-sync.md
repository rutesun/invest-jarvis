# Handoff — notebook-notion-sync

- 갱신: 2026-10-26 18:18 · Branch: feature/notebook-notion-sync · Status: 원문 부록 제거·목록 숨김 확인 완료

## 목표
로컬 투자 노트를 원본으로 유지하며 Notion에는 항목별 읽기용 본문을 제공합니다. 종목은 검색 API 근거로 묶습니다.

## 지금까지
- 10-22 사용자 승인으로3속성 추가와 신규35개 업로드·read-back 완료. 기존83개 legacy는 본문·분류 미갱신입니다.
- 10-26 사용자 지시로 전체118개를 스캔하고35개 page의 Raw Markdown 보관 block35개만 제거했습니다. 읽기용 본문·작성된 코드 예시·pageID/URL·schema·로컬 원본은 유지됐습니다. page 생성·교체·archive 없이 보관 block만 제거했습니다.
- 35개 hash를 notebook-v2로 갱신해 재조회에서도 UNCHANGED입니다. 자동 원문 부록은 다시 붙이지 않으며 v1 manifest는 재적용하지 않습니다.
- DB에는 Default view(table)한개입니다. Content Hash/Key/Source Path/출처는 이미 visible:false였고 최종 조회로 확인했습니다. 속성 삭제나 view 쓰기는 없었습니다.
- 현재 로컬124개/remote118개:83 LEGACY_UNVERIFIED/35 UNCHANGED/6 CREATE_CANDIDATE. 새6개는 이번 정리 범위 밖이며 schema·검색근거 보완이 필요합니다.
- 관련148 tests/Ruff PASS. 전체1554 passed/24 failed/15 deselected/2 warnings. 기존18개 환경실패 외 embedding6개가 tiktoken 공개 encoding 다운로드 DNS 제한으로 실패했습니다. 이름별 근거는 worklog에 있습니다.
- 원본/PDF/commit/push/PR 미수행. 기존.serena SHA256은40e17269250fbd4577bbe35991cde1c44010aa9d1aad5a37e1fcfabc1c49d091로 유지됐습니다.

## 최신 근거
`data/notebook-notion/` 개인자료는 Git 제외·0600입니다.
- verification-remove-raw-2026-10-26.json:제거35개·본문/주소/원본 보존·숨김 검증.
- journal-remove-raw-2026-10-26.json:35개 DONE, 제거 block ID와 본문 fingerprint.
- plan-remove-raw-2026-10-26.json:118개 스캔과 제거 대상.
- review-after-raw-removal-2026-10-26.json:현재124항목의 hash 계획. 신규6개 적용 차단.
- views-cleanup-before-2026-10-26.json / view-cleanup-after-2026-10-26.json:목록 숨김 근거.
- source-remove-raw-before-2026-10-26.json:원본 byte hash 기준.
- 10-22 review-live-final 등 v1 자료는 당시 이력이며 현재 적용하지 않습니다.

## 미결 · 다음 결정
새6개 업로드와 기존83개 legacy migration은 별도 범위로 검토합니다. schema options 요청100개 제한과 누락삭제 규칙을 지키며 전체 목록을 잘라 PATCH하지 않습니다.

## 다음 행동
우선 Notion 표시를 확인합니다. 후속 동기화 요청 시 현재 source/schema를 다시 읽고 신규6개의 검색근거와 schema를 보완한 새 manifest를 만듭니다.

```bash
MPLCONFIGDIR=/tmp/notebook-notion-mpl uv run --cache-dir /tmp/notebook-notion-uv-cache jarvis notebook sync \
  --notebook-dir /Users/al03229901/Develop/My/invest-jarvis/notebook \
  --stock-cache data/notebook-notion/stock-search-cache.json \
  --manifest data/notebook-notion/review-v2-next.json
```

## 참조 (읽기 순서)
1. [worklog](../worklog/notebook-notion-sync.md) — 승인·실행·테스트 근거
2. [CLI](../CLI_USAGE.md#notebook-sync---투자-notebook-지속-동기화) — v2 표시 정책·경계
3. [변경 기록](../changes/notebook-notion-sync.md)

## 함정 · 하지 말 것
- 원본 수정/source-missing 자동archive/PDF업로드/commit·push·PR 금지 유지.
- 원문 부록을 다시 붙이거나 v1 manifest를 적용하지 않습니다. 동기화 속성은 삭제하지 않습니다.
- 전체 로컬 stock_groups와 실제 갱신한35개 remote 분류를 구분합니다.

# Change Record: 투자 notebook 지속 동기화

**Status**: Draft
**Date**: 2026-10-22
**PRs**: 없음 (commit/push/PR 미실행)
**Type**: feat

> 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

## Why

기존 report uploader는 notebook 항목을 처리하지 못하고, 과거 변환은 긴 본문과 링크 보존에 한계가 있었습니다. 2026-10-22 최신 재조회에서 원본118개 중 remote83개에는 hash가 없고35개가 미수집이었습니다. 원본을 보존하며 변경과 적용 범위를 검토할 수 있도록 전용 경로를 추가했습니다.

## What

1. 월별 항목 parser와 기존 Key를 유지하는 page projection을 추가했습니다. 원본 Markdown은 로컬 notebook에 보존하고 Notion에는 읽기용 본문만 표시합니다. 10-26 사용자 지시로 자동 원문 부록을 제거했습니다.
2. remote-aware manifest와 schema 제안을 추가했습니다. legacy·orphan·duplicate를 분리하고 schema 및 option의 암묵적 변경도 차단합니다.
3. staging page·2-pass wikilink·read-back·journal recovery를 구현했습니다. 이전 page는 새 본문 검증 후에만 archive하며, target 변경의 참조 page도 RELINK 후보에 명시합니다.
4. Naver 검색 API 응답으로 종목명·코드를 연결합니다. 수동 대응표를 제거하고 raw metadata 추출과 API 분류를 분리했습니다. 검색 근거·증분 cache·충돌/모호성 검토와 전체 로컬 항목의 stock_groups를 제공합니다.
5. CLI 기본값을 읽기 전용으로 두고 apply에 검토 manifest와 journal을 요구합니다. 원본 변경·remote 변경·동시 실행을 사전에 차단합니다.

## Before / After

```
Before: notebook sync 명령 없음; 지속 변경 감지·복구 경로 없음
After: 항목별 dry-run·변경감지·검토manifest·read-back·부분실패복구 지원
```

## Impact

`jarvis notebook sync`를 추가했습니다. 상세 사용법은 [CLI 안내](../CLI_USAGE.md#notebook-sync---투자-notebook-지속-동기화)를 참조합니다. 최소 property와 필요한 select/multi-select option을 검토·적용한 뒤 새 manifest가 필요합니다.

## Constraints

- 2026-10-22 사용자의 실제 업데이트 지시 후 schema3속성을 추가하고 삼성전자 시험page1개의 업로드·read-back·journal 복구를 완료했습니다. 신규34개와 시험page의링크갱신1개도 완료해 최종 신규35개/전체118개입니다. 기존83legacy는 유지합니다.
- 개인 원본과 `.serena/project.yml` 기존 변경을 보존했습니다. 원본 본문과 secret은 문서·로그에 기록하지 않았습니다.
- legacy migration·orphan archive·PDF 업로드는 지원하지 않습니다.
- 전체 suite의 기존 환경 실패는 [검증 기록](../worklog/notebook-notion-sync.md)에 분리했습니다.

10-22 사용자 승인 후 542개 검색어의 실제 조회를 완료했습니다. 결과는 resolved 168 / not_found 324 / ambiguous 50입니다. 승인 당시 117개 항목을 기준으로 삼성전자14개·SK하이닉스11개, 신규34개와 기존83 legacy를 분리했습니다. 관련141 tests와 Ruff PASS; 전체1553 passed/18 failed(기존 동일 실패)/15 deselected입니다. nationCode:null 후보를 UNKNOWN으로 보존하는 실제 응답 회귀를 추가했습니다. 이 결과는 실제 업데이트 전의 역사적snapshot입니다. 이후 사용자의 실제 업데이트 지시로 최신118항목의manifest를 재생성하고schema차단을 해소했습니다.

## 실제 API 호환 보완

- 선택값의 대소문자·앞뒤 공백을 무시하는 Notion 동작을 schema 및 read-back 비교에 반영했습니다.
- 같은 링크·서식의 인접 text 병합과 paragraph의 빈 icon 기본값을 허용합니다. 본문이 같으면 검증을 통과합니다. 다른 내용·링크·서식은 차단합니다. 10-22까지 v1 직렬화를 유지했으며 10-26 부록 제거부터 notebook-v2로 갱신했습니다.
- schema options 요청의100개제한과 누락삭제 규칙을 CLI 문서에 명시했습니다. 직접 전체PATCH를 분할하지 않고 승인된 신규option만 임시page로 준비해 기존option을 보존했습니다. 이 준비는 자동CLI기능이 아닙니다.
- 관련147 tests/Ruff PASS. 전체1559 passed/18 failed/15 deselected로 기존동일18개환경실패가 남습니다. 상세이름과로그는worklog를 참조합니다.

## 실제 반영 결과

최종active118개이며 신규35개의속성·전체본문read-back을완료했습니다. 기존83개와로컬원본전체파일을보존했고Key중복은없습니다. 최종hash기준계획은35UNCHANGED/83LEGACY_UNVERIFIED/선택0/blocker0입니다. 신규중삼성전자4개를같은종목으로지정했습니다.

## Related

- [설계](../superpowers/specs/2026-10-02-notebook-notion-sync-design.md)
- [구현 계획](../superpowers/plans/2026-10-14-notebook-notion-sync.md)
- [적용 검토·다음 단계](../handoff/notebook-notion-sync.md)
- ADR은 외부 적용과 정책 채택 검토 후 확정합니다.

## 2026-10-26 본문·목록 정리

사용자 지시로35개 page의 자동 Raw Markdown 보관 block35개를 제거했습니다. 읽기용 본문·주소·schema·로컬 원본을 보존했고 notebook-v2 hash로 갱신했습니다. 목록의 Content Hash/Key/Source Path/출처는 기존 숨김 상태를 재확인했습니다. 관련148 tests/Ruff 통과, 전체1554 passed/24 failed/15 deselected이며 환경실패 상세는 worklog에 있습니다. 그동안 추가된 로컬6개 기록은 이번 정리에 포함하지 않았습니다.

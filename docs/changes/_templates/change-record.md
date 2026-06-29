# Change Record: {기능명}

**Status**: Draft | In Progress | Merged
**Date**: {YYYY-MM-DD}
**PRs**: #{PR 번호}
**Type**: feat | fix | refactor | docs | perf

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

{왜 이 변경이 필요했는지. 현재 문제와 동기. 가능하면 데이터·수치 포함. 1-3문장.}

## What

{번호 목록. 각 항목은 "무엇을 + 왜 그렇게 설계했나"를 함께 서술. ADR이 있으면 `(→ ADR-NNNN)` 인라인 참조.}

1. **{변경명}**: {구현 내용 + 이 접근을 선택한 이유 또는 기각한 대안}

## Before / After

{핵심 변경에서 달라진 부분을 before/after로 대비. 코드·출력·설계 모두 가능. 없으면 섹션 생략.}

```
Before: {이전 동작 또는 코드}
After:  {이후 동작 또는 코드}
```

## Impact

{사용자·운영 관점에서 체감 가능한 변화. CLI 출력 변화, 마이그레이션 필요 여부, 환경 변수 추가 등.
없으면 섹션 생략.}

## Constraints

{무엇을 의도적으로 안 했는지, 변경에서 지킨 불변 조건, 기각된 대안과 이유. 없으면 섹션 생략.}

- {예: "X 기능은 Y 이유로 이번 범위에서 제외. 후속 Z에서 다룬다."}

## Related

- 설계: {spec/plan 경로 또는 "없음"}
- ADR: {관련 ADR 또는 "없음"}
- FEATURES.md: {업데이트한 섹션 또는 "해당 없음"}
- 후속: {다음 PR/태스크 또는 "없음"}

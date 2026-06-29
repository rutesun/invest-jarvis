---
description: 현재 브랜치 변경을 분석해 docs/changes/ change record 초안 생성
argument-hint: "[PR번호] (선택)"
allowed-tools: Bash(git diff:*), Bash(git log:*), Bash(git rev-parse:*), Read, Write, Edit
---

현재 feature 브랜치의 변경을 분석해 `docs/changes/` change record 초안을 작성하라.

## 입력 컨텍스트

변경 요약:
!`git diff main...HEAD --stat`

커밋 로그:
!`git log main...HEAD --format='- %s%n%b'`

상세 diff가 필요하면 `git diff main...HEAD -- <path>`로 직접 확인하라.

## 작성 규칙

1. 포맷은 `docs/changes/_templates/change-record.md`를 엄격히 따른다. 먼저 Read로 템플릿을 확인하라.
2. 섹션별 작성 지침:
   - **Why**: 변경 동기. diff/커밋에서 확인되는 문제·수치를 포함. 추측 금지.
   - **What**: 번호 목록. 각 항목은 "무엇을 했고 + 왜 그렇게 설계했나". 파일 나열이 아니라 결정 단위로 묶는다.
   - **Before / After**: 핵심 변경의 코드·출력·계약 대비. diff에서 실제로 확인되는 것만.
   - **Impact**: 사용자·운영 체감 변화(CLI 출력, 환경변수, 마이그레이션). 없으면 섹션 생략.
   - **Constraints**: 의도적으로 안 한 것, 불변 조건, 기각된 대안. 커밋의 "deferred/보류/제외/후속" 단서를 활용.
   - **Related**: spec/plan 경로, ADR, 후속 태스크.
3. diff에 근거가 없는 내용은 지어내지 않는다. 불명확하면 `{확인 필요}`로 표시한다.
4. Type은 커밋 prefix(feat/fix/refactor/docs/perf)에서 추론한다.
5. Date는 오늘 날짜. PRs는 인자 `$1`이 있으면 `#$1`, 없으면 `{PR번호}`로 둔다.

## 출력

1. 변경 핵심을 나타내는 kebab-case 파일명으로 `docs/changes/{name}.md`를 Write.
2. `docs/changes/INDEX.md` 표 맨 위(최신순)에 행을 추가.
3. 작성 후 사용자에게 검토를 요청한다. 특히 `{확인 필요}`로 표시한 항목을 명시한다.

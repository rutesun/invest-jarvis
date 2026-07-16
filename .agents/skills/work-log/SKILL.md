---
name: work-log
description: 현재 브랜치 작업 일지 docs/worklog/topic.md에 타임스탬프 엔트리(Decision/Bug/Friction/Pivot)를 추가한다. 설계 결정 확정, 버그 수정 검증, 도구 부재로 막힘, 접근 전환 시점에 호출.
---

# Work Log

작업 중의 결정·버그수정·마찰·방향전환을 `docs/worklog/<topic>.md`에 시간순으로 기록한다.
change-record/ADR의 1차 재료다. 파일 헤더·엔트리 포맷은 아래 템플릿을 그대로 쓴다.

입력 형식: `<type> <한 줄 요지>` (`type`: `decision` | `bug` | `friction` | `pivot`)

## 언제 호출하나 (트리거)

- 설계 결정이 확정된 직후 → `decision`
- 버그 수정이 검증된 후 → `bug`
- 도구 부재로 막히거나 맥락을 잘못 잡았을 때 → `friction`
- 접근을 폐기·전환할 때 → `pivot`

## 절차

1. 날짜·시간과 브랜치를 구한다:
   - `date '+%Y-%m-%d %H:%M'`
   - `git rev-parse --abbrev-ref HEAD`
2. 대상 파일 `docs/worklog/<topic>.md`를 정한다. `<topic>`은 작업 주제 kebab-case
   (브랜치명을 그대로 쓰지 않는다). 같은 작업의 후속 엔트리는 같은 파일에 append한다.
3. 파일이 없으면 아래 "파일 헤더" 블록으로 새로 만든다
   (`Branch`/`Started`/`Status`/`Links` 채움).
4. 인자 `type`에 맞는 엔트리 블록을 파일 끝에 append한다 (아래 포맷).
5. 최근 대화 맥락에서 각 필드를 채운다. **맥락에 근거 없는 내용은 지어내지 않고
   `{확인 필요}`로 표시**한다.
6. 작성 후 한 줄로 무엇을 어디에 기록했는지 보고한다.

## 파일 헤더 (새 파일일 때만)

새 `docs/worklog/<topic>.md`를 만들 때 파일 맨 위에 아래 블록을 쓴다.
값은 절차 1에서 구한 브랜치·날짜로 채우고, 링크가 없으면 `Links` 줄은 생략한다.

````markdown
# Worklog — <topic>

- **Branch**: <git rev-parse --abbrev-ref HEAD 결과 (미초기화면 "(git 미초기화)")>
- **Started**: <YYYY-MM-DD>
- **Status**: in-progress
- **Links**: [관련 설계 문서](상대경로) · [이슈](url)

---
````

## 엔트리 포맷

기존 파일에는 헤더를 다시 쓰지 않고, 파일 끝에 엔트리 블록만 append한다.

````markdown
## (YYYY-MM-DD HH:MM) [Decision] 제목
- 맥락: 왜 이 결정이 필요했나
- 후보: A / B / C
- 선택: 고른 것 — 이유
- 기각: A(이유), C(이유)
- ADR 후보? yes/no

## (YYYY-MM-DD HH:MM) [Bug] 제목
- 증상:
- 근원(root cause):
- 수정:
- 재발 방지 / 배운 것:

## (YYYY-MM-DD HH:MM) [Friction] 제목
- 막힌 점:
- 임시 대응:
- 개선 아이디어 (스킬·훅·프롬프트):

## (YYYY-MM-DD HH:MM) [Pivot] 제목
- 이전 접근:
- 전환 이유:
- 새 접근:
````

## 안 하는 것

- 슬래시 커맨드·CLI 경로는 만들지 않는다(현재 범위 밖).
- 강제 훅으로 호출을 강제하지 않는다. 누락은 감수한다.

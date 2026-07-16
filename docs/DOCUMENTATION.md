# Documentation Guide

> 이 문서는 invest-jarvis 저장소의 문서 생성/업데이트 원칙의 기준 문서입니다.
> 문서 관련 규칙을 바꾸려면 이 문서를 먼저 업데이트합니다.

---

## 1. 목적

문서는 다음 세 가지를 분리해서 관리한다.

1. 현재 프로젝트가 무엇을 지원하는지 설명
2. 어떤 설계 탐색과 브레인스토밍이 있었는지 보관
3. 어떤 PR/머지로 무엇이 바뀌었는지 기록

같은 내용을 여러 문서에 반복해서 적지 않는다.

---

## 2. 문서 역할

| 문서 | 역할 | 질문 |
|------|------|------|
| `docs/FEATURES.md` | 현재 프로젝트가 지원하는 기능 설명 | "지금 이 프로젝트는 무엇을 할 수 있나?" |
| `docs/superpowers/specs/` | 브레인스토밍/설계 탐색 결과 보관 | "무엇을 만들려고 고민했고 어떤 설계를 검토했나?" |
| `docs/worklog/` | 작업 중 결정·버그·마찰·전환의 시간순 일지 | "작업 중 그 순간 무슨 판단을 했고 어디서 막혔나?" |
| `docs/changes/` | PR 또는 머지 단위 변경 기록 | "이번 변경에서 실제로 무엇이 들어갔나?" |
| `docs/adr/` | 중요한 아키텍처 의사결정 기록 | "왜 이 구조/방식을 선택했나?" |
| `docs/CLI_USAGE.md` | CLI 명령 사용법 | "어떻게 실행하나?" |
| `docs/ARCHITECTURE.md` | 코드 구조와 데이터 흐름 설명 | "코드는 어떤 구조로 동작하나?" |

---

## 3. 생성 원칙

### 3.1 기존 문서 우선

- 먼저 기존 문서를 업데이트할 수 있는지 확인한다.
- 새 문서는 기존 문서에 자연스럽게 들어가기 어려울 때만 만든다.
- 같은 주제의 문서를 여러 개 만들지 않는다.

### 3.2 현재 상태와 변경 이력을 분리

- 현재 상태 설명은 `docs/FEATURES.md`에 쓴다.
- 변경 이력은 `docs/changes/`에 쓴다.
- 설계 탐색 내용은 `docs/superpowers/specs/`에 둔다.
- 설계 문서를 현재 상태 문서처럼 취급하지 않는다.

### 3.3 구현 상세는 plan으로

- 코드 레벨 구현 순서, 태스크 분해, 실험 로그는 `docs/superpowers/plans/`가 담당한다.
- 사람이 빠르게 이해해야 하는 문서에는 구현 상세를 과도하게 넣지 않는다.

### 3.4 한 문서 한 책임

- 문서 하나는 하나의 질문에 답해야 한다.
- `FEATURES.md`에 PR 히스토리를 길게 적지 않는다.
- `docs/changes/`에 현재 전체 기능 설명을 복제하지 않는다.
- `docs/superpowers/specs/`에 이미 확정된 운영 규칙을 다시 쓰지 않는다.

### 3.5 코드와 같은 커밋

- 기능/동작이 바뀌는 PR이면 관련 문서도 같은 커밋 또는 같은 PR에 포함한다.
- 문서가 코드보다 늦게 따라오지 않게 한다.

---

## 4. 언제 어떤 문서를 업데이트할지

| 상황 | 액션 |
|------|------|
| 작업 중 결정/버그수정/마찰/방향전환이 발생함 | `work-log` 스킬로 `docs/worklog/<topic>.md`에 기록 |
| 새로운 기능/동작이 사용자 관점에서 추가됨 | `docs/FEATURES.md` 업데이트 |
| PR에서 의미 있는 변경 범위를 남겨야 함 | `docs/changes/{name}.md` 생성 또는 업데이트 |
| 구현 전에 설계 탐색/브레인스토밍이 필요함 | `docs/superpowers/specs/...` 생성 또는 업데이트 |
| 아키텍처적으로 중요한 선택이 있었음 | `docs/adr/NNNN-제목.md` 추가 |
| CLI 명령/옵션이 바뀜 | `docs/CLI_USAGE.md` 업데이트 |
| 구조/레이어/흐름이 바뀜 | `docs/ARCHITECTURE.md` 업데이트 |
| 개발 프로세스/문서 규칙이 바뀜 | 이 문서와 `docs/DEVELOPMENT.md` 업데이트 |

---

## 4.5 `docs/worklog` 사용 원칙

`docs/worklog/`는 작업 *중* 실시간으로 남기는 시간순 일지다. change-record/ADR이 끝나고 정제한 결과라면, worklog는 그 순간의 원재료다.

- 기록 주체는 에이전트다. `work-log` 스킬을 체크포인트(결정 확정·버그수정 검증·막힘·접근 전환)에서 호출한다.
- 파일 단위는 주제(topic) kebab-case. 브랜치는 헤더에 적는다.
- 엔트리 타입은 `Decision` / `Bug` / `Friction` / `Pivot` 4종.
- 소비 방향: `Decision`은 ADR 후보, `Friction`/`Pivot`은 harness 개선 소스, 전체는 change-record의 Why/What/Constraints 근거.
- 강제 훅은 두지 않는다. 누락은 스킬 기반의 트레이드오프로 감수한다.

---

## 5. `docs/changes` 사용 원칙

`docs/changes/`는 머지 단위 변경 기록이다.

다음 중 하나라도 해당하면 작성하는 것이 좋다.

- 새 기능이 추가됐다
- 기존 기능의 동작이나 사용자 해석이 바뀌었다
- 하나의 PR이 여러 파일에 걸친 의미 있는 변경을 담고 있다
- 나중에 "이 변경이 왜 들어갔는지" 추적할 가능성이 높다

굳이 만들지 않아도 되는 경우:

- 오탈자 수정만 있는 PR
- 내부 리팩터링만 있고 사용자 관점 동작 변화가 없는 경우
- 테스트만 추가했고 기능/동작 설명이 달라지지 않는 경우

권장 흐름:

1. 작업 초반 `Draft`로 초안 생성
2. 구현 중 범위와 체크리스트 갱신
3. 머지 직전/직후 `Merged`로 마감
4. 현재 상태 변화가 있으면 `docs/FEATURES.md`도 함께 업데이트

### 파일 포맷

템플릿: `docs/changes/_templates/change-record.md`

헤더 필드:
- `Status`: Draft | In Progress | Merged
- `Date`: 머지일, ISO 8601 (`YYYY-MM-DD`)
- `PRs`: PR 번호
- `Type`: feat | fix | refactor | docs | perf

`Changes` 섹션은 다음 카테고리로 분류한다 (해당 없는 항목 생략):

| 카테고리 | 의미 |
|---------|------|
| **Added** | 새 기능/동작 추가 |
| **Changed** | 기존 동작 변경 (사용자 해석이 달라지는 것) |
| **Fixed** | 버그 수정 |
| **Removed** | 기능/동작 제거 |
| **Breaking** | 하위 호환을 깨는 변경 — 있으면 반드시 명시 |

각 항목은 동사로 시작한다. 커밋 로그를 그대로 옮기지 않는다.

### 인덱스 유지

`docs/changes/INDEX.md`를 단일 진입점으로 운영한다. change record를 새로 추가하거나 상태가 바뀌면 INDEX도 함께 업데이트한다.

### 초안 생성

빈 템플릿을 수동으로 채우지 말고 `/change-record`로 초안을 생성한다. 현재 브랜치의 diff·커밋 로그를 분석해 Why/What/Before·After/Impact/Constraints를 채운 초안을 만든다. 생성 후 사람이 검토·보정한다.

---

## 6. ADR 운영 원칙

`docs/adr/`는 중요한 아키텍처 의사결정을 남기는 문서다.

- **기본 원칙**: brainstorming 결과와 ADR을 같은 문서로 취급하지 않는다.
- **brainstorming 완료 시점**: ADR을 바로 확정하지 않고, 설계 문서(`docs/superpowers/specs/...`)에 ADR 후보를 식별한다.
- **구현 계획 단계**: 후보 결정이 실제 구현 범위인지 다시 확인한다.
- **작성 시점**: `docs/FEATURES.md`가 바뀌는 PR 중, 아키텍처적으로 중요한 결정이 실제로 채택되었을 때
- **위치**: `docs/adr/NNNN-제목.md`
- **번호 정책**: 번호는 순차 증가, append-only
- **템플릿**: `docs/adr/0000-template.md`
- **수정 원칙**: 수락된 ADR 본문은 뒤집지 않는다. 결정이 바뀌면 새 ADR을 추가하고 기존 ADR에 대체 관계만 표시한다.

권장 흐름:

1. brainstorming 문서에 `ADR Candidates` 또는 `Architecture Decisions` 섹션 기록
2. writing-plans 또는 구현 시작 전, 후보가 실제 구현 대상인지 확인
3. 머지 직전/직후 채택된 결정만 ADR로 확정

---

## 7. 강제 방식

문서 누락이 반복되어(기능 PR 다수가 `docs/changes/` 기록 없이 머지됨) 아래 자동화를 도입했다.
생성·유도·차단 3계층으로, 작성 비용을 낮춘 뒤 누락만 게이트로 막는다.

**생성 (마찰 제거)**

- `/change-record` (`.claude/commands/change-record.md`): 현재 브랜치 diff·커밋 로그를 분석해
  템플릿에 맞는 change record 초안을 생성한다. 작성 비용을 낮춰 강제가 실제로 작동하게 만드는 것이 목적.

**유도 (세션 종료 시)**

- Stop hook (`.claude/hooks/check-docs.sh`): feature 브랜치에서 `src/` 변경이 있는데
  `docs/changes/` 기록이 없으면 에이전트에게 작성을 유도한다. `stop_hook_active`로 한 번만 막는다.

**차단 (push 시)**

- pre-push (`scripts/check-features-doc.sh`): `src/` 변경 PR을 LLM이 기능 변경으로 판정하면
  `docs/FEATURES.md`와 `docs/changes/`가 둘 다 있어야 push가 통과한다.

brainstorming 단계까지 막지는 않는다. 게이트는 세션 종료 시점과 push 시점에만 둔다.

---

## 8. 작성 원칙

- 짧고 명확하게 쓴다.
- "왜", "무엇", "어디가 기준 문서인지"가 바로 보여야 한다.
- 예시보다 규칙을 우선한다.
- 문서 간 링크는 실제 독자가 따라갈 가치가 있을 때만 추가한다.
- 제목은 검색 가능하고 구체적으로 쓴다.
- 문서 이름은 역할이 드러나게 짓는다.

---

## 9. 템플릿과 기준

- `docs/changes/` 템플릿: `docs/changes/_templates/change-record.md`
- `docs/adr/` 템플릿: `docs/adr/0000-template.md`
- 현재 기능 기준 문서: `docs/FEATURES.md`
- 문서 생성/업데이트 규칙 변경 시 기준 문서: `docs/DOCUMENTATION.md`

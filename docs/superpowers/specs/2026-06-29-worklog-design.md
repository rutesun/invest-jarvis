# Worklog (작업 일지) 설계

**Date**: 2026-06-29
**Status**: Approved (design)
**관련**: `docs/DOCUMENTATION.md`, `.claude/commands/change-record.md`, `docs/adr/`

> 이 문서는 설계 탐색 결과(spec)다. 확정 운영 규칙은 구현 시 `docs/DOCUMENTATION.md`·`CLAUDE.md`에 반영한다.

---

## 1. 목적

작업 중 발생하는 **결정·버그수정·마찰·방향전환**을 그 순간 날것으로 기록해, 나중에
ADR과 harness engineering(에이전트 도구·스킬·훅·프롬프트 개선)의 1차 재료로 쓴다.

해결하려는 문제: 기존 문서는 모두 **정제된 결과·회고**만 담아서, "그 순간 왜 그걸 골랐나",
"어디서 헤맸나" 같은 생생한 맥락이 소실된다.

## 2. 기존 체계와의 관계

| 문서 | 시점 | 출처 | 위치 |
|------|------|------|------|
| **worklog** (신규) | 작업 *중* (실시간) | 대화 맥락 | `docs/worklog/` |
| `change-record` | 브랜치 *끝* | git diff 재구성 | `docs/changes/` |
| ADR | 결정 확정 후 | 정제된 판단 | `docs/adr/` |
| spec | 구현 *전* | 브레인스토밍 | `docs/superpowers/specs/` |
| plan | 구현 *전* | 태스크 분해 | `docs/superpowers/plans/` |

worklog는 위 어디에도 안 들어가는 시간순 일지다. 소비 방향:

- worklog의 **Decision** → 아키텍처급이면 ADR로 승격
- worklog의 **Friction/Pivot** → 모아서 스킬·훅·프롬프트 개선 소스
- worklog 전체 → 브랜치 종료 시 `change-record`의 Why/What/Constraints 1차 근거

## 3. 파일 포맷

위치: `docs/worklog/<topic-slug>.md` (git 커밋). 파일명은 **주제 kebab-case**.
브랜치명을 파일명으로 쓰지 않는다(worktree 브랜치명이 `claude/musing-...`처럼 무의미할 수 있음).
브랜치는 헤더에 기록한다. 첫 엔트리를 남길 때 주제 slug를 정한다.

```markdown
# Worklog: <주제>

**Branch**: <branch> · **Started**: YYYY-MM-DD · **Status**: Active | Wrapped
**Links**: spec/plan 경로, PR

---

## (YYYY-MM-DD HH:MM) [Decision] <제목>
- 맥락: 왜 이 결정이 필요했나
- 후보: A / B / C
- 선택: B — 이유
- 기각: A(이유), C(이유)
- ADR 후보? yes/no

## (YYYY-MM-DD HH:MM) [Bug] <제목>
- 증상:
- 근원(root cause):
- 수정:
- 재발 방지 / 배운 것:

## (YYYY-MM-DD HH:MM) [Friction] <제목>
- 막힌 점:
- 임시 대응:
- 개선 아이디어 (스킬·훅·프롬프트):

## (YYYY-MM-DD HH:MM) [Pivot] <제목>
- 이전 접근:
- 전환 이유:
- 새 접근:
```

엔트리 타입은 4종: `Decision`, `Bug`, `Friction`, `Pivot`. 각 엔트리는 시간 스탬프로 시작.

## 4. 기록 주체와 트리거

- **기록 주체**: 에이전트(Claude)가 체크포인트에서 `work-log` 스킬을 호출해 자동 기록.
- **트리거 규칙** (CLAUDE.md / AGENTS.md에 명시, 훅 아님 — `DOCUMENTATION.md §7` 철학 준수):
  - AskUserQuestion 등으로 **설계 결정이 확정된 직후** → `[Decision]`
  - **버그 수정이 검증된 후**(테스트 통과 등) → `[Bug]`
  - **도구 부재로 막히거나** 맥락을 잘못 잡았을 때 → `[Friction]`
  - **접근을 폐기·전환**할 때 → `[Pivot]`
- 누락 위험은 감수한다(스킬 기반의 트레이드오프). 자동 강제 훅은 도입하지 않는다.

## 5. 아티팩트

| 아티팩트 | 위치 | 역할 |
|----------|------|------|
| 스킬 | `.claude/skills/work-log/SKILL.md` | 에이전트가 Skill 도구로 호출. 타입별 템플릿·작성 규칙 |
| 템플릿 | `docs/worklog/_templates/worklog.md` | 파일 헤더 + 4개 엔트리 스니펫 |
| 기록물 | `docs/worklog/<topic>.md` | 실제 일지 (커밋) |

`work-log` 스킬 동작:
1. 인자로 엔트리 타입 + 한 줄 요지를 받는다 (예: `decision 동기화 방식`).
2. 현재 날짜·시간, 현재 브랜치를 구한다.
3. 대상 `docs/worklog/<topic>.md`가 없으면 헤더와 함께 생성한다.
4. 최근 대화 맥락에서 해당 타입의 필드를 채워 엔트리를 append한다.
5. 맥락에 근거 없는 내용은 지어내지 않고 `{확인 필요}`로 표시한다.

## 6. 검증

자동 테스트 대상이 아니다. 이 브랜치 자체에서 dogfooding(직접 써보며 검증):
- 4개 타입 엔트리를 실제로 한 번씩 남겨본다.
- 남긴 엔트리가 `change-record`/ADR로 매끄럽게 정제되는지 확인한다.

## 7. ADR 후보

- 없음. 이번 변경은 문서·프로세스 컨벤션이라 아키텍처 결정(ADR)에 해당하지 않는다.
  단, `DOCUMENTATION.md`의 문서 역할 표에 worklog 행을 추가하는 운영 규칙 변경은 동반한다.

## 8. 부수 변경

- `CLAUDE.md` 스킬 규칙("Simple CLI wrappers only")에 **프로세스 스킬 예외** 한 줄 추가.
- `CLAUDE.md` / `AGENTS.md`에 worklog 트리거 규칙 추가.
- `docs/DOCUMENTATION.md` 문서 역할 표·생성 원칙에 worklog 반영.

## 9. 의도적으로 안 하는 것 (YAGNI)

- 슬래시 커맨드(`/work-log`) 수동 경로: 처음엔 만들지 않는다. 자동 기록만으로 부족하면 추가.
- 엔트리를 검증·쿼리하는 CLI(`jarvis worklog`): 포맷이 검증된 후 harness 도구로 별도 검토.
- 강제 훅: 누락이 반복돼 실제 비용이 될 때만 재검토.

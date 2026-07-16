# Worklog — worklog-tooling

- **Branch**: claude/musing-taussig-6c7a0c
- **Started**: 2026-06-29
- **Status**: in-progress
- **Links**: [spec](../superpowers/specs/2026-06-29-worklog-design.md) · [plan](../superpowers/plans/2026-06-29-worklog.md)

---

## (2026-06-29 16:35) [Decision] 기록 방식 = 스킬 기반
- 맥락: working 로그를 어떤 자동화 수준으로 남길지 정해야 나머지 설계가 따라옴
- 후보: 수동 컨벤션 / 스킬 기반 / 훅 자동 캡처
- 선택: 스킬 기반 — "왜 골랐나" 의미 정보는 에이전트가 직접 써야 잘 남고, 트리거가 명시적이라 파싱·집계가 쉬움
- 기각: 수동 컨벤션(포맷·빈도 들쭉날쭉, 누락), 훅 자동 캡처(노이즈 과다, 의미 정보 자동 포착 불가, 구현 복잡)
- ADR 후보? no (프로세스 컨벤션)

## (2026-06-29 16:42) [Decision] 로그 단위 = 브랜치/주제
- 맥락: 두 소비처(ADR·harness)가 데이터를 꺼내는 방식을 좌우
- 후보: 브랜치/주제 단위 / 날짜 단위 / 단일 롤링+태그
- 선택: 브랜치/주제 단위 — 기존 specs/plans/changes와 정렬 일관, PR·ADR 핸드오프가 자연스러움
- 기각: 날짜 단위(주제 섞임), 롤링 파일(탐색성·머지 충돌)
- ADR 후보? no

## (2026-06-29 16:50) [Decision] 호출 주체 = 에이전트 자동 + CLAUDE.md 트리거
- 맥락: 스킬 기반은 누가 언제 호출하느냐가 관건
- 후보: 에이전트 자동(Skill 도구) / 유저 수동(/work-log 슬래시 커맨드)
- 선택: 에이전트 자동 + CLAUDE.md/AGENTS.md 트리거 규칙 — "제가 호출" 의도에 부합, DOCUMENTATION.md §7의 훅보다 체크리스트 철학과 일치
- 기각: 슬래시 커맨드 단독(에이전트가 자동으로 못 남김)
- ADR 후보? no

## (2026-06-29 16:55) [Bug] AskUserQuestion 호출이 JSON 파싱 실패
- 증상: AskUserQuestion 호출 시 "questions type expected as array but provided as string" InputValidationError
- 근원(root cause): 마지막 옵션 description 끝의 잘못된 이스케이프(`\.`)가 JSON 인자 파싱을 깨뜨림
- 수정: 해당 이스케이프 제거 후 동일 인자로 재호출 → 정상
- 재발 방지 / 배운 것: 옵션 텍스트에 백슬래시 이스케이프를 넣지 않는다. 한글 설명문 끝 구두점 주의.

## (2026-06-29 17:05) [Friction] change-record 위치 탐색에 헤맴
- 막힌 점: change-record 패턴을 맞추려 `.claude/skills/`에서 찾았으나 없음. find로 여러 번 탐색 후 실제로는 슬래시 커맨드(`.claude/commands/change-record.md`)임을 확인
- 임시 대응: `find / -iname '*change-record*'`로 전역 탐색해 위치 특정
- 개선 아이디어: 스킬 vs 슬래시 커맨드 vs CLI 래퍼의 위치 규약을 한 곳(CLAUDE.md 또는 DOCUMENTATION.md)에 명시하면 탐색 비용 감소

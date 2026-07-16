# Worklog — jarvis-lilys

- **Branch**: feature/jarvis-lilys-worklog
- **Started**: 2026-07-15
- **Status**: in-progress

---

## (2026-07-15 14:57) [Decision] Lily 요약 추출을 독립 스킬로 분리
- 맥락: Lily digest URL은 SPA와 공개 note API를 거쳐야 해서 매번 수동으로 API 경로를 찾는 비용이 있었다.
- 후보: jarvis-notebook에 fetch 절차 추가 / 독립 jarvis-lilys 스킬 생성
- 선택: 독립 jarvis-lilys 스킬 생성 — 본문 추출 책임과 노트 기록 책임을 분리할 수 있다.
- 기각: jarvis-notebook에 통합(기록 스킬이 외부 서비스 추출 로직까지 갖게 됨)
- ADR 후보? no

## (2026-07-16 14:53) [Decision] 단순 CLI 스킬 설명 한도를 40줄로 완화
- 맥락: 20줄 제한은 실행 명령만 남기기에는 충분했지만, API 성격·출력물·후속 기록 흐름을 설명하기에는 부족했다.
- 후보: 20줄 유지 / 40줄 완화 / 프로세스 스킬만 예외 처리
- 선택: 40줄 완화 — 간단한 CLI 스킬도 사용 조건과 실패 시 확인점을 담을 수 있다.
- 기각: 20줄 유지(스킬 설명이 지나치게 얇아짐), 프로세스 스킬만 예외 처리(이번 문제를 해결하지 못함)
- ADR 후보? no

## (2026-07-16 15:00) [Pivot] main 직접 변경을 feature 브랜치 커밋으로 이동
- 이전 접근: local main에 worklog 관련 커밋과 Lily 스킬 변경이 섞여 있었다.
- 전환 이유: main에는 worklog 실험 커밋을 남기지 않고, 관련 변경을 feature 브랜치의 단일 커밋으로 관리하기 위해서다.
- 새 접근: `feature/jarvis-lilys-worklog`를 `origin/main` 기준으로 만들고 worklog/Lily 관련 파일만 stage해 한 커밋으로 묶는다.

## (2026-07-16 15:28) [Bug] SEC cache 테스트 날짜 의존 실패
- 증상: PR #49의 `test` check에서 `tests/tools/test_disclosure.py::test_sec_fetcher_uses_cache`가 빈 결과를 반환해 실패했다.
- 근원(root cause): 테스트가 현재 날짜를 고정하지 않아, 2026-07-16 기준 fixture 공시가 90일 cutoff 밖으로 밀렸다.
- 수정: cache 경로 테스트도 다른 SEC 테스트와 동일하게 `src.tools.disclosure.datetime.now()`를 2026-06-20으로 고정했다.
- 재발 방지 / 배운 것: 날짜 필터가 있는 테스트는 캐시 경로 여부와 무관하게 시간 고정을 일관되게 적용한다.

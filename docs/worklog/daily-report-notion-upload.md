# Worklog — daily-report-notion-upload

- **Branch**: feature/jarvis-lilys-worklog
- **Started**: 2026-07-16
- **Status**: in-progress

---

## (2026-07-16 15:06) [Bug] Notion Markdown 변환기 해시태그 무한 루프 수정
- 증상: `daily_2026-07-06.md` Notion 업로드가 페이지 생성 전 단계에서 응답 없이 멈춤.
- 근원(root cause): `_markdown_to_blocks`가 `#KB금융 #신한지주`처럼 `#`로 시작하지만 Markdown heading은 아닌 줄을 paragraph로 소비하지 않아 index가 증가하지 않음.
- 수정: paragraph 수집 중단 조건을 `#` 전체가 아니라 실제 heading marker(`# `, `## `, `### `)로 좁힘.
- 재발 방지 / 배운 것: 해시태그 줄 회귀 테스트를 추가했고, 실제 07-06 리포트 변환이 즉시 완료됨을 확인.

## (2026-07-16 15:06) [Bug] Daily Report category alias 누락 보강
- 증상: 2026-07-08 리포트 생성 중 LLM이 `전기전자`, `철강금속` category를 반복 반환해 map stage 검증 실패.
- 근원(root cause): `CATEGORY_ALIASES`가 실제 LLM 출력 변형 일부를 정규 `IssueCategory`로 매핑하지 못함.
- 수정: `전기전자`는 `반도체`, `철강금속`은 `소재/화학`으로 정규화.
- 재발 방지 / 배운 것: 실제 실패 category를 재현하는 `MappedIssue` 회귀 테스트를 추가.

## (2026-07-16 15:06) [Bug] 종목명이 category로 들어온 케이스 정규화
- 증상: 2026-07-08 재실행 중 LLM이 `현대백화점`을 category로 반환해 map stage 검증 실패.
- 근원(root cause): category 필드에 업종 대신 대표 종목명이 들어오는 변형을 alias가 흡수하지 못함.
- 수정: `현대백화점`을 `유통/소비재`로 정규화.
- 재발 방지 / 배운 것: 종목명 category 변형을 재현하는 회귀 테스트를 추가.

## (2026-07-16 15:06) [Bug] 우주·철강·광산 category alias 보강
- 증상: 2026-07-09 리포트 생성 중 `우주개발`, `철강/소재`, `광산/에너지` category가 검증 실패.
- 근원(root cause): LLM이 허용 category보다 세분화된 업종명을 반환했으나 alias 맵에 해당 변형이 없었음.
- 수정: `우주개발`은 `방산`, `철강/소재`는 `소재/화학`, `광산/에너지`는 `에너지`로 정규화.
- 재발 방지 / 배운 것: 실제 실패 값을 기반으로 alias 회귀 테스트를 추가.

## (2026-07-27 16:45) [Bug] report upload 날짜 필터·파일명 파싱·중복 업로드 수정
- 증상: `jarvis report upload 2026-07-20 --type daily`가 15개 파일을 업로드 시도 — help("종료 날짜 미지정 시 시작 날짜만")와 달리 시작 날짜 이후 전부 대상이 되고, `daily_v2_*.md`는 date가 `v2_2026-06-19`로 추출돼 Notion Date 검증 실패 8건 발생. 같은 명령 재실행 시 중복 페이지 생성.
- 근원(root cause): (1) end_date 미지정 시 상한 없음, (2) 파일명 prefix strip 방식 날짜 추출이 v2/AB 변형을 처리 못 하고 문자열 비교 필터를 통과, (3) upload_report_from_file에 기존 페이지 확인 없이 항상 create.
- 수정: end_date 미지정 시 start_date로 고정. `extract_report_date()`가 정규식으로 `daily_/daily_v2_/screen-` + 날짜 형식만 허용(AB 변형 제외). 업로드 전 같은 Type·Date 페이지를 `_archive_existing_report_pages()`로 아카이브해 재업로드를 교체 의미로 변경 (notion-client 3.0 data_sources.query 사용).
- 재발 방지 / 배운 것: extract_report_date 파라미터라이즈 테스트 + archive 헬퍼 mock 테스트 추가. 실제 재업로드로 07-20 페이지가 1개 유지됨을 확인.

## (2026-07-27 17:20) [Bug] 코드리뷰에서 발견된 Notion 업로드 결함 2건 수정
- 증상: (1) `_markdown_to_blocks`가 표 형식이 아닌 `|` 시작 줄(다음 줄이 `|`가 아닌 경우)에서 여전히 무한 루프 — 해시태그 수정과 동일한 "소비되지 않는 줄" 버그 클래스. (2) 재업로드 시 기존 페이지를 먼저 아카이브한 뒤 페이지 생성을 시도해, 생성 실패(429 등) 시 기존 리포트가 유실됨.
- 근원(root cause): (1) 문단 수집 루프가 소비하지 못하는 줄에서 index가 전진하지 않는 구조적 문제 — 특정 접두사만 고치는 것으로는 부족. (2) archive-before-create 순서에 롤백 없음.
- 수정: (1) 문단 분기에 진행 보장(어떤 분기도 소비 못 한 줄은 단독 문단으로 소비) + `_HEADING_PREFIXES` 상수로 heading 분기와 중단 조건 동기화. (2) 기존 페이지 id를 미리 조회하고 새 페이지 업로드 성공 후에만 아카이브하도록 순서 변경. notion-client 하한도 3.0.0으로 상향(data_sources.query 의존 명시).
- 재발 방지 / 배운 것: `|` 줄 회귀 테스트 2건, create 실패 시 기존 페이지 보존 테스트 추가. 특수 케이스 수정 시 같은 버그 클래스의 다른 입력을 반드시 찾아볼 것.

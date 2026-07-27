# Worklog — daily-report-strict-schema-regression

- **Branch**: main
- **Started**: 2026-07-27
- **Status**: in-progress

---

## (2026-07-27 15:30) [Bug] shuffle stage ThemeMapping이 OpenAI strict structured output에서 400 에러
- 증상: `jarvis report daily`의 shuffle stage에서 모든 카테고리가 `Error code: 400 — Invalid schema for response_format 'ThemeMapping'`으로 실패. fallback(원본 테마 그대로)으로 진행돼 테마 정규화가 전부 무력화됨. wrapup은 `KeyInsightsList`(list) 사용이라 영향 없음.
- 근원(root cause): PR #52에서 daily 스테이지 LLM이 Anthropic haiku → OpenAI gpt-5.6-luna로 전환됨. Anthropic은 tool calling 방식이라 `dict[str, list[str]]` 필드를 허용했지만, langchain-openai는 gpt-5.x에서 strict json_schema 방식을 쓰고 OpenAI strict 모드는 자유형 dict(`additionalProperties`가 스키마인 object)를 거부한다. 마지막 정상 리포트(07-15)가 PR #52 병합(07-27) 전이라 회귀가 드러나지 않았음.
- 수정: `ThemeMapping.mapping: dict[str, list[str]]` → `groups: list[ThemeGroup]`(normalized/originals) 구조로 변경, `as_dict()`로 기존 dict 인터페이스 유지. shuffle 프롬프트의 출력 예시 2곳도 새 형태로 갱신.
- 재발 방지 / 배운 것: `tests/pipelines/daily_report/test_models.py`에 strict 스키마 계약 테스트 추가 — `invoke_llm_with_retry`에 들어가는 4개 출력 모델(MappedIssueList/ThemeMapping/ThemeAnalysis/KeyInsightsList) 전체에 대해 "properties 없는 object 금지"를 검증. provider 전환은 structured output 방식(json_schema vs tool calling)까지 바꾸므로 dict 필드 호환성을 함께 점검해야 한다. `CategoryInsightsList.insights`도 dict 필드지만 현재 LLM 호출에 미사용 — 사용 시 같은 문제 발생 예정.

## (2026-07-27 17:20) [Bug] 코드리뷰 후속: as_dict 중복 정규화명 유실 + 계약 테스트 walker 공용화
- 증상: LLM이 같은 normalized 이름의 그룹을 중복 반환하면 `ThemeMapping.as_dict()`가 last-wins로 앞 그룹의 originals를 유실. 또한 새로 작성한 스키마 walker가 기존 `tests/pipelines/stock_report/test_synthesis_schema_strict.py`의 더 강한 walker(list[Any], additionalProperties 서브스키마, oneOf/allOf까지 검출)를 중복 구현.
- 수정: as_dict를 setdefault+extend 병합으로 변경. walker를 `tests/harness/strict_schema.py`로 추출해 stock_report·daily_report 계약 테스트가 공유.
- 재발 방지 / 배운 것: 계약 테스트를 새로 만들기 전에 같은 버그 클래스를 막는 기존 가드를 먼저 검색할 것 (commit 94f55e4가 동일한 400 회귀를 이미 겪었음).

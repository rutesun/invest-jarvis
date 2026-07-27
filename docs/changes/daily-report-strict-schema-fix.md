# Change Record: Daily Report OpenAI strict schema 회귀 수정

**Status**: Draft
**Date**: 2026-07-27
**PRs**: #53
**Type**: fix

> 이 문서는 PR/머지 단위 변경 기록입니다. 현재 기능 상태는 `docs/FEATURES.md`를 기준으로 봅니다.

---

## Why

PR #52에서 daily 스테이지 LLM이 Anthropic haiku(tool calling)에서 OpenAI gpt-5.6-luna(strict json_schema)로 전환되면서, 자유형 dict 필드인 `ThemeMapping.mapping: dict[str, list[str]]`이 OpenAI에서 400 에러(`Invalid schema for response_format 'ThemeMapping'`)로 거부됐다. shuffle stage가 카테고리 전체에서 3회 재시도 후 fallback(원본 테마 그대로)으로 진행돼 테마 정규화가 완전히 무력화된 상태였다. 마지막 정상 리포트(07-15)가 PR #52 병합 전이라 회귀가 드러나지 않았다.

## What

1. **ThemeMapping을 strict 호환 구조로 변경**: `mapping: dict[str, list[str]]` → `groups: list[ThemeGroup]`(normalized/originals). OpenAI strict structured output은 자유형 dict(object without properties)를 지원하지 않으므로 그룹 배열로 표현. 기존 호출부의 dict 계약은 `as_dict()` 메서드로 유지해 shuffle_stage 변경을 1줄로 최소화. 공용 헬퍼 `invoke_llm_with_retry`를 `method="function_calling"`으로 전환하는 대안은 모든 파이프라인의 structured output 방식을 바꾸는 광역 변경이라 기각.
2. **shuffle 프롬프트 예시 갱신**: `SHUFFLE_SYSTEM_PROMPT_V2`의 출력 예시 2곳을 dict 형태에서 `{"groups": [...]}` 형태로 변경해 스키마와 예시의 불일치 제거.
3. **strict 스키마 계약 테스트 추가**: `invoke_llm_with_retry`에 전달되는 구조화 출력 모델 4종(MappedIssueList/ThemeMapping/ThemeAnalysis/KeyInsightsList) 전체에 대해 "properties 없는 object 금지"를 검증하는 파라미터라이즈 테스트. provider 전환 시 dict 필드 회귀를 테스트 단계에서 잡는다.
4. **map stage 카테고리 alias 6종 추가**: LLM이 생성하는 비정규 카테고리(전기전자→반도체, 철강금속·철강/소재→소재/화학, 광산/에너지→에너지, 우주개발→방산, 현대백화점→유통/소비재)를 정규 카테고리로 흡수.
5. **test_models.py 기존 테스트 복원**: 이전 세션에서 alias 테스트를 추가하면서 의도치 않게 삭제된 기존 모델 검증 테스트 약 260줄(MacroSnapshot 검증, MappedIssue themes 제약, ThemeAnalysis 검증 등)을 HEAD에서 복원해 병합.
6. **Notion 마크다운 변환기 해시태그 무한 루프 수정**: `_markdown_to_blocks`의 문단 수집 중단 조건을 `#` 전체에서 실제 heading marker(`# `, `## `, `### `)로 좁힘. `#특징업종` 같은 해시태그 줄이 소비되지 않아 index가 멈추던 버그. 해시태그 줄 회귀 테스트 포함.
7. **`jarvis report upload` 버그 3종 수정**: (1) 종료 날짜 미지정 시 help대로 시작 날짜 하루만 대상, (2) 파일명 날짜 추출을 prefix strip에서 정규식(`extract_report_date`)으로 바꿔 `daily_v2_*`는 정상 날짜로, AB 테스트 변형은 제외, (3) 업로드 전 같은 Type·Date의 기존 페이지를 아카이브(`_archive_existing_report_pages`, notion-client 3.0 `data_sources.query`)해 재업로드를 교체 의미로 변경.

## Before / After

```
Before: ThemeMapping.mapping: dict[str, list[str]]
        → OpenAI strict json_schema 400 거부 → 전 카테고리 fallback, 테마 정규화 무력화
After:  ThemeMapping.groups: list[ThemeGroup] + as_dict()
        → strict 스키마 통과, 테마 정규화 정상 동작
```

## Impact

- `jarvis report daily` 사용자 체감: 스키마 오류 로그(카테고리당 3회 재시도) 제거, 유사 테마가 다시 통합됨. 2026-07-16~26 리포트 11건을 이 수정으로 생성해 검증 완료.
- `jarvis report upload <date>`: 시작 날짜 이후 전체가 아니라 해당 날짜만 업로드. 재실행해도 Notion 페이지가 중복 생성되지 않고 교체됨(기존 페이지는 휴지통으로). 07-16~26 리포트 11건 업로드로 검증 완료.
- 마이그레이션·환경 변수 변경 없음.

## Constraints

- `CategoryInsightsList.insights`도 동일한 dict 필드지만 현재 LLM 호출에 미사용이라 이번 범위에서 제외. LLM 호출에 사용하게 되면 같은 구조 변경이 필요하다(계약 테스트 대상에 추가할 것).
- `invoke_llm_with_retry`의 structured output 방식(json_schema)은 변경하지 않음 — strict 스키마의 출력 보장을 유지.

## Related

- 설계: docs/worklog/daily-report-strict-schema-regression.md
- ADR: 없음
- FEATURES.md: 해당 없음 (동작 회귀 수정, 기능 계약 변경 없음)
- 후속: 없음

# Category Field 실행 플랜

**Date**: 2026-04-17
**Spec**: `docs/superpowers/specs/2026-04-17-category-field-design.md`
**Branch**: feature/prompt-evaluation

---

## 개요

`MappedIssue`에 `category` 필드를 추가하여 클러스터링 키(시스템용)와 테마(내러티브용)를 분리합니다.

---

## Task 1: 데이터 모델 변경

**파일**: `src/pipelines/daily_report/models.py`

1. `IssueCategory` Literal 타입 정의 (18개 카테고리)
2. `MappedIssue.category` 필드 추가
3. `ShuffleResult` 구조 변경: `category_groups: Dict[str, Dict[str, List[MappedIssue]]]`
4. `NewsItem.category` 필드 추가

**의존성**: 없음 (최초 변경)

---

## Task 2: Map Stage 프롬프트 업데이트

**파일**: `src/pipelines/daily_report/prompts.py`

1. `MAP_SYSTEM_PROMPT_V4` 신규 추가 (카테고리 선택 지침 포함)
2. `MAP_SYSTEM_PROMPT` 포인터를 V4로 변경

**의존성**: Task 1 완료 후

---

## Task 3: Shuffle Stage 로직 재작성

**파일**: `src/pipelines/daily_report/stages/shuffle_stage.py`

1. 1단계: 결정론적 카테고리 그룹핑 (LLM 불필요)
   ```python
   category_buckets: Dict[str, List[MappedIssue]] = {}
   for issue in issues:
       category_buckets.setdefault(issue.category, []).append(issue)
   ```
2. 2단계: 카테고리 내 테마 정규화 (LLM, 병렬)

**의존성**: Task 1 완료 필수

---

## Task 4: Reduce Stage 로직 변경

**파일**: `src/pipelines/daily_report/stages/reduce_stage.py`

1. `category_groups` 구조 순회
2. `NewsItem` 생성 시 `category` 포함

**의존성**: Task 1, Task 3 완료 필수

---

## Task 5: Pipeline 통합 업데이트

**파일**: `src/pipelines/daily_report/pipeline.py`

1. Shuffle → Reduce 연결을 `category_groups`로 변경
2. 로그 메시지 업데이트

**의존성**: Task 3, Task 4 완료 필수

---

## Task 6: 평가 메트릭 추가

**파일**: 
- `evaluations/metrics.py`
- `tests/evaluations/test_metrics.py`

1. `category_accuracy` 함수 추가
2. `RULE_BASED_METRICS`에 등록
3. 테스트 케이스 추가

**의존성**: Task 1 완료 후 (병렬 가능)

---

## Task 7: 테스트 케이스 데이터셋 업데이트

**파일**: `evaluations/datasets/test_cases.json`

각 케이스에 `expected_category` 필드 추가:

| case_id | expected_category |
|---------|-------------------|
| case_001 | `["자동차", "AI/소프트웨어"]` |
| case_002 | `"반도체"` |
| case_003 | `["매크로", "K-푸드", "AI/소프트웨어"]` |
| case_004 | `"AI/소프트웨어"` |
| case_005 | `"에너지"` |
| case_csv_003 | `"방산"` |
| case_csv_004 | `"반도체"` |
| case_csv_005 | `"매크로"` |
| case_csv_006 | `"이차전지"` |

**의존성**: 없음 (병렬 가능)

---

## Task 8: Fixture 재생성

**파일**: `tests/pipelines/daily_report/fixtures/stage_outputs/`

```bash
uv run python -m src.pipelines.daily_report.stages.map_stage 2026-04-14
uv run python -m src.pipelines.daily_report.stages.shuffle_stage 2026-04-14
uv run python -m src.pipelines.daily_report.stages.reduce_stage 2026-04-14
```

**의존성**: Task 1~5 모두 완료 필수

---

## 실행 순서

```
Task 1 (models.py)
     │
     ├─────────────────┬────────────────┐
     v                 v                v
Task 2 (prompts)   Task 6 (metrics)  Task 7 (test_cases)
     │                 │
     v                 v
Task 3 (shuffle_stage)
     │
     v
Task 4 (reduce_stage)
     │
     v
Task 5 (pipeline)
     │
     v
Task 8 (fixtures)
```

---

## 커밋 전략

1. **Commit 1**: Task 1 - 데이터 모델 변경
2. **Commit 2**: Task 2 + Task 6 + Task 7 - 프롬프트/메트릭/데이터셋
3. **Commit 3**: Task 3 + Task 4 + Task 5 - 스테이지 로직
4. **Commit 4**: Task 8 - Fixture 재생성 및 테스트 통과

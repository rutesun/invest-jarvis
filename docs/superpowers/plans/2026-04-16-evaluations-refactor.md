# Evaluations Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `evaluations/` 디렉토리의 버그 3건과 설계 문제 3건을 수정한다.

**Architecture:** `metrics.py`를 단일 진실 소스로 만들고, `langsmith_eval.py`는 그 함수들을 래핑만 한다. `_issues_to_text`와 `ThemeMatchResult`는 `metrics.py`에만 존재한다.

**Tech Stack:** Python, Pydantic v2, LangChain, pytest (uv run pytest)

---

## 수정 대상 요약

| 번호 | 유형 | 위치 | 내용 |
|------|------|------|------|
| 1 | 버그 | `evaluate_map.py:73` | 짧은 입력에도 `...` 항상 출력 |
| 2 | 버그 | `metrics.py:150-152` | `keyword_coverage` 키워드 이중 검색 |
| 3 | 기능 누락 | `metrics.py`, `evaluate_map.py` | `must_split` 필드 미평가 |
| 4 | 중복 | `metrics.py`, `langsmith_eval.py` | `_issues_to_text` 중복 정의 |
| 5 | 불일치 | `metrics.py`, `langsmith_eval.py` | `ThemeMatchResult` 스키마 불일치 |
| 6 | 중복 | `langsmith_eval.py` | 평가자 함수가 metrics.py 로직 재구현 |

---

## 파일 구조

```
evaluations/
├── metrics.py          # 수정: 버그 2건 수정, must_split 추가, ThemeMatchResult 통합
├── evaluate_map.py     # 수정: 버그 1건 수정
└── langsmith_eval.py   # 수정: _issues_to_text 제거, 평가자 재구현 제거, ThemeMatchResult 제거

tests/
└── evaluations/
    ├── __init__.py     # 신규
    └── test_metrics.py # 신규: metrics.py 단위 테스트
```

---

## Task 1: 테스트 파일 초기 셋업

**Files:**
- Create: `tests/evaluations/__init__.py`
- Create: `tests/evaluations/test_metrics.py`

- [ ] **Step 1: `__init__.py` 생성**

```python
# tests/evaluations/__init__.py
```

- [ ] **Step 2: 테스트 파일 생성 — 헬퍼 픽스처 작성**

```python
# tests/evaluations/test_metrics.py
"""evaluations/metrics.py 단위 테스트."""

import pytest
from src.pipelines.daily_report.models import MappedIssue
from evaluations.metrics import (
    split_accuracy,
    number_preservation,
    company_preservation,
    keyword_coverage,
    must_split_check,
    theme_relevance,
    _issues_to_text,
    RULE_BASED_METRICS,
)


def make_issue(
    title="테스트 이슈",
    summary="요약",
    themes=None,
    keywords=None,
    impact="영향",
) -> MappedIssue:
    return MappedIssue(
        title=title,
        summary=summary,
        themes=themes or ["테마1"],
        keywords=keywords or ["키워드1"],
        impact=impact,
    )
```

- [ ] **Step 3: 테스트 실행하여 import 오류 확인**

```bash
uv run pytest tests/evaluations/test_metrics.py -v
```

Expected: `ImportError: cannot import name 'must_split_check'` — `must_split_check`가 아직 없으므로 실패해야 정상.

---

## Task 2: `keyword_coverage` 이중 검색 버그 수정

**Files:**
- Modify: `evaluations/metrics.py:140-155`
- Modify: `tests/evaluations/test_metrics.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/evaluations/test_metrics.py`에 추가:

```python
def test_keyword_coverage_no_double_count():
    """키워드가 이중으로 검색되지 않아야 함 (회귀 방지용)."""
    # 키워드가 issues.keywords에만 존재하는 경우
    issue = make_issue(keywords=["HBM", "삼성"])
    expected = {"expected_keywords": ["HBM", "삼성", "없는키워드"]}
    score = keyword_coverage([issue], expected)
    # 2/3 = 0.666...
    assert abs(score - 2 / 3) < 0.01


def test_keyword_coverage_full_match():
    issue = make_issue(title="HBM 뉴스", summary="삼성 HBM", keywords=["HBM"])
    expected = {"expected_keywords": ["HBM", "삼성"]}
    score = keyword_coverage([issue], expected)
    assert score == 1.0


def test_keyword_coverage_empty_expected():
    score = keyword_coverage([make_issue()], {"expected_keywords": []})
    assert score == 1.0
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/evaluations/test_metrics.py::test_keyword_coverage_no_double_count -v
```

Expected: FAIL (ImportError, `must_split_check` 미존재로 import 전체 실패)

- [ ] **Step 3: `metrics.py`의 `keyword_coverage` 수정**

`evaluations/metrics.py`의 `keyword_coverage` 함수를 아래로 교체:

```python
def keyword_coverage(
    issues: List[MappedIssue],
    expected: Dict[str, Any],
) -> float:
    """키워드 커버리지: 예상 키워드 중 출력에 포함된 비율."""
    expected_keywords = expected.get("expected_keywords", [])
    if not expected_keywords:
        return 1.0

    # _issues_to_text에 이미 keywords가 포함됨 — 중복 없이 단일 검색
    all_text = _issues_to_text(issues)

    covered = sum(1 for kw in expected_keywords if kw in all_text)
    return covered / len(expected_keywords)
```

---

## Task 3: `must_split_check` 메트릭 추가

**Files:**
- Modify: `evaluations/metrics.py`
- Modify: `evaluations/evaluate_map.py`
- Modify: `tests/evaluations/test_metrics.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/evaluations/test_metrics.py`에 추가:

```python
def test_must_split_check_pass_when_split_required():
    """must_split=True이고 이슈가 2개 이상이면 1.0."""
    issues = [make_issue("이슈1"), make_issue("이슈2")]
    score = must_split_check(issues, {"must_split": True, "num_issues_min": 2})
    assert score == 1.0


def test_must_split_check_fail_when_not_split():
    """must_split=True인데 이슈가 1개면 0.0."""
    score = must_split_check([make_issue()], {"must_split": True, "num_issues_min": 2})
    assert score == 0.0


def test_must_split_check_not_required():
    """must_split=False이면 이슈 개수에 관계없이 1.0."""
    score = must_split_check([make_issue()], {"must_split": False, "num_issues_min": 1})
    assert score == 1.0


def test_must_split_check_missing_field():
    """must_split 필드가 없으면 1.0 (선택적 필드)."""
    score = must_split_check([make_issue()], {})
    assert score == 1.0
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/evaluations/test_metrics.py -k "must_split" -v
```

Expected: FAIL (ImportError)

- [ ] **Step 3: `metrics.py`에 `must_split_check` 함수 추가**

`evaluations/metrics.py`의 `keyword_coverage` 함수 다음에 추가:

```python
def must_split_check(
    issues: List[MappedIssue],
    expected: Dict[str, Any],
) -> float:
    """분리 필요 여부 충족 검사.

    must_split=True인 경우 이슈가 num_issues_min 이상으로 분리됐는지 확인.
    must_split=False이거나 필드가 없으면 항상 1.0.
    """
    if not expected.get("must_split", False):
        return 1.0

    min_expected = expected.get("num_issues_min", 2)
    return 1.0 if len(issues) >= min_expected else 0.0
```

- [ ] **Step 4: `RULE_BASED_METRICS` 딕셔너리에 추가**

`evaluations/metrics.py`의 `RULE_BASED_METRICS`를 아래로 교체:

```python
RULE_BASED_METRICS = {
    "split_accuracy": split_accuracy,
    "must_split_check": must_split_check,
    "number_preservation": number_preservation,
    "company_preservation": company_preservation,
    "theme_relevance": theme_relevance,
    "keyword_coverage": keyword_coverage,
}
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```bash
uv run pytest tests/evaluations/test_metrics.py -v
```

Expected: 아직 ImportError — Task 5에서 `_issues_to_text` export 확인 후 해결됨.

---

## Task 4: 짧은 입력의 `...` 출력 버그 수정

**Files:**
- Modify: `evaluations/evaluate_map.py:73`

- [ ] **Step 1: `evaluate_map.py` 수정**

`evaluations/evaluate_map.py`의 73번째 줄 교체:

```python
# 수정 전
print(f"Input: {input_text[:80]}...")

# 수정 후
suffix = "..." if len(input_text) > 80 else ""
print(f"Input: {input_text[:80]}{suffix}")
```

- [ ] **Step 2: 커밋**

```bash
git add evaluations/evaluate_map.py
git commit -m "fix(eval): 짧은 입력에 ... 항상 붙는 버그 수정"
```

---

## Task 5: `_issues_to_text` 중복 제거

**Files:**
- Modify: `evaluations/langsmith_eval.py:83-92` (함수 제거, import 추가)

- [ ] **Step 1: `langsmith_eval.py` 상단 import 수정**

`evaluations/langsmith_eval.py`의 import 블록에 추가:

```python
from evaluations.metrics import (
    split_accuracy as _split_accuracy,
    number_preservation as _number_preservation,
    company_preservation as _company_preservation,
    keyword_coverage as _keyword_coverage,
    must_split_check as _must_split_check,
    _issues_to_text,
)
```

- [ ] **Step 2: `langsmith_eval.py`의 `_issues_to_text` 함수 삭제**

`evaluations/langsmith_eval.py`에서 아래 블록 전체 삭제:

```python
def _issues_to_text(issues: List[MappedIssue]) -> str:
    """이슈 리스트를 단일 텍스트로 변환."""
    parts = []
    for issue in issues:
        parts.append(issue.title)
        parts.append(issue.summary)
        parts.append(issue.impact)
        parts.extend(issue.themes)
        parts.extend(issue.keywords)
    return " ".join(parts)
```

- [ ] **Step 3: 실행하여 동작 확인 (import 에러 없는지)**

```bash
uv run python -c "from evaluations.langsmith_eval import run_map_stage_for_eval; print('OK')"
```

Expected: `OK`

---

## Task 6: `ThemeMatchResult` 통합 및 LangSmith 평가자 재구현

**Files:**
- Modify: `evaluations/langsmith_eval.py` — 로컬 `ThemeMatchResult` 삭제, 평가자 함수 재작성

- [ ] **Step 1: `langsmith_eval.py`의 `ThemeMatchResult` 로컬 정의 삭제**

`theme_relevance_llm` 함수 내부의 로컬 `ThemeMatchResult` 클래스 정의 삭제:

```python
# 삭제 대상 (함수 내부에 있음)
class ThemeMatchResult(BaseModel):
    score: float = Field(description="매칭 점수 (0.0 ~ 1.0)", ge=0.0, le=1.0)
    reasoning: str = Field(description="판단 근거")
```

- [ ] **Step 2: `langsmith_eval.py` import에 `ThemeMatchResult` 추가**

이미 추가된 metrics import에 `ThemeMatchResult` 포함:

```python
from evaluations.metrics import (
    split_accuracy as _split_accuracy,
    number_preservation as _number_preservation,
    company_preservation as _company_preservation,
    keyword_coverage as _keyword_coverage,
    must_split_check as _must_split_check,
    _issues_to_text,
    ThemeMatchResult,
)
```

- [ ] **Step 3: LangSmith 규칙 기반 평가자들을 metrics.py 함수를 호출하는 래퍼로 교체**

`evaluations/langsmith_eval.py`의 `split_accuracy`, `number_preservation`, `company_preservation`, `keyword_coverage` 함수들을 아래로 교체:

```python
def split_accuracy(run: Run, example: Example) -> Dict:
    """이슈 분리 정확도."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _split_accuracy(issues, example.outputs or {})
    return {"key": "split_accuracy", "score": score}


def must_split_check(run: Run, example: Example) -> Dict:
    """분리 필요 여부 충족 검사."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _must_split_check(issues, example.outputs or {})
    return {"key": "must_split_check", "score": score}


def number_preservation(run: Run, example: Example) -> Dict:
    """숫자 보존율."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _number_preservation(issues, example.outputs or {})
    return {"key": "number_preservation", "score": score}


def company_preservation(run: Run, example: Example) -> Dict:
    """기업명 보존율."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _company_preservation(issues, example.outputs or {})
    return {"key": "company_preservation", "score": score}


def keyword_coverage(run: Run, example: Example) -> Dict:
    """키워드 커버리지."""
    issues = [MappedIssue(**i) for i in (run.outputs or {}).get("issues", [])]
    score = _keyword_coverage(issues, example.outputs or {})
    return {"key": "keyword_coverage", "score": score}
```

- [ ] **Step 4: `run_evaluation`의 evaluators 리스트에 `must_split_check` 추가**

`evaluations/langsmith_eval.py`의 `run_evaluation` 함수 내 evaluators 리스트 교체:

```python
results = evaluate(
    run_map_stage_for_eval,
    data=DATASET_NAME,
    evaluators=[
        split_accuracy,
        must_split_check,
        number_preservation,
        company_preservation,
        keyword_coverage,
        theme_relevance_llm,
    ],
    experiment_prefix=experiment_prefix,
)
```

- [ ] **Step 5: `theme_relevance_llm`의 `ThemeMatchResult` 사용 확인**

`langsmith_eval.py`의 `theme_relevance_llm` 함수가 이제 `metrics.py`에서 import된 `ThemeMatchResult`를 사용하므로, 함수 내부의 `result.score`와 `result.reasoning` 참조를 `result.score`와 `result.matches`로 수정:

```python
    try:
        llm_with_output = llm.with_structured_output(ThemeMatchResult)
        result = llm_with_output.invoke(messages)
        # ThemeMatchResult.matches의 첫 번째 항목에서 reasoning 추출
        reasoning = result.matches[0].get("reason", "") if result.matches else ""
        return {
            "key": "theme_relevance",
            "score": result.score,
            "comment": reasoning,
        }
    except Exception as e:
        print(f"⚠️  LLM 테마 평가 실패: {e}")
        return {"key": "theme_relevance", "score": 0.5}
```

---

## Task 7: 전체 테스트 통과 확인 및 커밋

- [ ] **Step 1: import 오류 없는지 확인**

```bash
uv run python -c "from evaluations.metrics import RULE_BASED_METRICS; print(list(RULE_BASED_METRICS.keys()))"
```

Expected:
```
['split_accuracy', 'must_split_check', 'number_preservation', 'company_preservation', 'theme_relevance', 'keyword_coverage']
```

- [ ] **Step 2: 전체 단위 테스트 실행**

```bash
uv run pytest tests/evaluations/ -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 3: 기존 테스트 회귀 확인**

```bash
uv run pytest tests/ -v --ignore=tests/integration -q
```

Expected: 기존 테스트 모두 PASS (새 테스트 포함)

- [ ] **Step 4: 최종 커밋**

```bash
git add evaluations/metrics.py evaluations/evaluate_map.py evaluations/langsmith_eval.py tests/evaluations/
git commit -m "refactor(eval): metrics.py를 단일 소스로 통합, must_split 메트릭 추가"
```

---

## 검증 체크리스트

- [ ] `must_split_check`가 `RULE_BASED_METRICS`에 포함됨
- [ ] `_issues_to_text`가 `metrics.py`에만 정의됨
- [ ] `ThemeMatchResult`가 `metrics.py`에만 정의됨
- [ ] `langsmith_eval.py`의 평가자 함수들이 `metrics.py` 함수를 호출함
- [ ] `keyword_coverage`가 키워드를 한 번만 검색함
- [ ] 짧은 입력에 `...`이 붙지 않음
- [ ] 모든 테스트 PASS

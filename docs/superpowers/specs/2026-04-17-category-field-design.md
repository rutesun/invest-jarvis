# MappedIssue Category Field Design

**Date**: 2026-04-17
**Branch**: feature/prompt-evaluation
**Status**: Approved

---

## 배경 및 목적

현재 `MappedIssue.themes`가 두 가지 역할을 동시에 수행한다:

1. **클러스터링 키** (시스템용) — Shuffle stage가 LLM으로 정규화해 이슈를 그룹핑
2. **내러티브 태그** (사용자용) — 리포트에 "투자 가치 있는 테마" 문구로 노출

이 이중 역할이 구조적 긴장을 만든다. 클러스터링에 유리한 표현(안정적·반복적)과 내러티브에 유리한 표현(구체적·맥락 의존적)이 충돌하며, Shuffle stage의 LLM 테마 정규화가 불안정해진다.

**해결**: `category` 필드를 고정 Literal 타입으로 추가해 클러스터링을 담당하게 하고, `themes`는 순수 내러티브 역할로 분리한다.

---

## 카테고리 목록 (확정)

```python
IssueCategory = Literal[
    # 기술/제조
    "반도체", "디스플레이", "이차전지", "소재/화학",
    # 산업
    "자동차", "조선/중공업", "방산",
    # 소프트웨어/서비스
    "AI/소프트웨어", "통신",
    # 헬스케어
    "바이오/제약",
    # 소비
    "유통/소비재", "K-푸드",
    # 에너지/인프라
    "에너지", "건설/부동산",
    # 금융/거시
    "금융/보험", "매크로", "정책/규제",
    # 기타
    "기타",
]
```

총 18개. LLM이 Pydantic `Literal` 제약으로 이 목록 중 하나를 선택하도록 강제된다.

---

## 변경된 데이터 모델

### `MappedIssue` (`src/pipelines/daily_report/models.py`)

```python
class MappedIssue(BaseModel):
    category: IssueCategory          # ← 신규: 고정 카테고리 (클러스터링 키)
    title: str                       # 내러티브 제목 (사용자 노출)
    summary: str                     # 숫자·팩트 중심 요약
    themes: List[str]                # 내러티브 태그, max 3 (사용자 노출)
    impact: str                      # 시장 시사점
    keywords: List[str]              # 종목명·기술용어 (검색 쿼리용)
    sentiment: Literal["bull", "bear", "neutral"]
    source_ids: List[str]
```

### `ShuffleResult` (`src/pipelines/daily_report/models.py`)

2단계 구조로 변경. Pydantic 모델 불필요 (LLM이 직접 생성하지 않음):

```python
class ShuffleResult(BaseModel):
    category_groups: Dict[str, Dict[str, List[MappedIssue]]]
    # { "반도체": { "HBM 수요 급등": [issue1, issue2], "레거시 재고": [issue3] } }
```

`canonical_themes`(원본→정규화 매핑)는 제거. Reduce stage가 정규화 테마명(`category_groups`의 키)만 사용하므로 불필요.

### `NewsItem` (`src/pipelines/daily_report/models.py`)

```python
class NewsItem(BaseModel):
    category: IssueCategory          # ← 신규: 출처 카테고리 (정렬·필터링용)
    theme: str                       # 정규화된 테마명
    emoji: str
    summary: str
    impact: str
    stocks: List[StockDetail]
```

---

## 파이프라인 변경

### Map Stage (`stages/map_stage.py`)

변경 없음. `MappedIssueList` 구조화 출력에 `category` 필드가 포함되므로 LLM이 자동으로 채운다.

**프롬프트 변경** (`prompts.py`): `MAP_SYSTEM_PROMPT`에 category 선택 지침 추가.

```
**카테고리 선택 (category)**:
아래 18개 중 이슈를 가장 잘 대표하는 하나를 선택하세요.
반도체 | 디스플레이 | 이차전지 | 소재/화학 | 자동차 | 조선/중공업 | 방산 |
AI/소프트웨어 | 통신 | 바이오/제약 | 유통/소비재 | K-푸드 |
에너지 | 건설/부동산 | 금융/보험 | 매크로 | 정책/규제 | 기타

- category는 섹터 분류 (시스템용): 반드시 위 목록 중 하나만 사용
- themes는 투자 내러티브 (사용자용): 자유롭게 구체적으로 작성
  - 예) category: "반도체", themes: ["HBM 선단공정 전환 가속", "DRAM 업사이클"]
```

### Shuffle Stage (`stages/shuffle_stage.py`)

**1단계: 결정론적 카테고리 그룹핑 (LLM 불필요)**

```python
category_buckets: Dict[str, List[MappedIssue]] = {}
for issue in issues:
    category_buckets.setdefault(issue.category, []).append(issue)
```

**2단계: 카테고리 내 테마 정규화 (LLM, 병렬)**

각 `(category, issues)` 쌍에 대해 기존 테마 정규화 로직 적용. 카테고리 범위 내에서만 정규화하므로 맥락이 줄어 정확도 향상 기대.

```python
tasks = [
    _normalize_themes(category, cat_issues, date)
    for category, cat_issues in category_buckets.items()
]
results = await asyncio.gather(*tasks)
```

LLM 호출 횟수: `1회(전체)` → `카테고리 수만큼(병렬)`. 각 호출의 토큰 수는 줄어 전체 레이턴시 유사하거나 개선.

### Reduce Stage (`stages/reduce_stage.py`)

`ShuffleResult.category_groups`를 순회:

```python
for category, theme_map in shuffle_result.category_groups.items():
    for theme, issues in theme_map.items():
        news_item = await _generate_news_item(category, theme, issues)
```

`NewsItem`에 `category` 포함해 반환. 최종 `DailyReport.news`는 카테고리 기준으로 정렬 가능.

---

## 평가 (Evaluations)

### 신규 메트릭 (`evaluations/metrics.py`)

```python
def category_accuracy(
    issues: List[MappedIssue],
    expected: Dict[str, Any],
) -> float:
    """카테고리 정확도: 예상 카테고리와 실제 카테고리 일치 여부."""
    expected_category = expected.get("expected_category")
    if not expected_category:
        return 1.0
    actual_categories = [issue.category for issue in issues]
    matched = sum(1 for c in actual_categories if c == expected_category)
    return min(matched / max(len(actual_categories), 1), 1.0)
```

### 테스트 케이스 업데이트 (`evaluations/datasets/test_cases.json`)

각 케이스에 `expected_category` 필드 추가:

| case_id | expected_category |
|---------|-------------------|
| case_001 (테슬라/오라클) | `"자동차"`, `"AI/소프트웨어"` (2개 이슈) |
| case_002 (삼성 HBM) | `"반도체"` |
| case_003 (소매판매/라면/양자컴퓨터) | `"매크로"`, `"K-푸드"`, `"AI/소프트웨어"` |
| case_004 (양자보안 관련주) | `"AI/소프트웨어"` |
| case_005 (ESS 설치량) | `"에너지"` |

---

## 영향 받는 파일

| 파일 | 변경 유형 |
|------|-----------|
| `src/pipelines/daily_report/models.py` | `IssueCategory` 추가, `MappedIssue.category` 추가, `ShuffleResult` 구조 변경, `NewsItem.category` 추가 |
| `src/pipelines/daily_report/prompts.py` | `MAP_SYSTEM_PROMPT_V4` 추가 (category 선택 지침) |
| `src/pipelines/daily_report/stages/shuffle_stage.py` | 2단계 그룹핑 로직으로 재작성 |
| `src/pipelines/daily_report/stages/reduce_stage.py` | `category_groups` 순회, `NewsItem.category` 전달 |
| `evaluations/metrics.py` | `category_accuracy` 추가, `RULE_BASED_METRICS` 업데이트 |
| `evaluations/datasets/test_cases.json` | `expected_category` 필드 추가 |
| `tests/evaluations/test_metrics.py` | `category_accuracy` 테스트 추가 |
| `tests/pipelines/daily_report/` | Shuffle/Reduce 관련 테스트 픽스처 업데이트 |

---

## 비고: 마이그레이션 영향 없음

- 기존 저장된 `map_*.json` 픽스처는 `category` 필드가 없어 로딩 시 Pydantic 오류 발생 → 픽스처 재생성 필요
- LangSmith에 기록된 과거 실험 결과는 영향 없음 (read-only)

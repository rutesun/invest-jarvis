"""Map stage 평가 메트릭."""

from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from src.pipelines.daily_report.models import MappedIssue


class ThemeMatchResult(BaseModel):
    """LLM 테마 매칭 결과."""

    matches: list[dict[str, Any]] = Field(
        description="각 예상 테마별 매칭 결과 [{expected, matched, reason}]"
    )
    score: float = Field(description="전체 매칭 점수 (0.0 ~ 1.0)", ge=0.0, le=1.0)


def split_accuracy(
    issues: list[MappedIssue],
    expected: dict[str, Any],
) -> float:
    """이슈 분리 정확도: 예상 범위 내 개수인지."""
    actual_count = len(issues)
    min_expected = expected.get("num_issues_min", 1)
    max_expected = expected.get("num_issues_max", 1)
    return 1.0 if min_expected <= actual_count <= max_expected else 0.0


def number_preservation(
    issues: list[MappedIssue],
    expected: dict[str, Any],
) -> float:
    """숫자 보존율: 원문 숫자가 출력에 포함되었는지.

    경계 검증: "5.6%"가 "25.6%"에서 매칭되지 않도록
    숫자 앞에 다른 숫자가 없어야 매칭으로 인정.
    """
    import re

    expected_numbers = expected.get("must_preserve_numbers", [])
    if not expected_numbers:
        return 1.0

    output_text = _issues_to_text(issues)
    preserved = 0
    for n in expected_numbers:
        # 숫자 앞에 다른 숫자가 없어야 매칭 (negative lookbehind)
        # 예: "5.6%"는 "25.6%"에서 매칭 안됨, " 5.6%"나 문장 시작에서는 매칭됨
        pattern = r"(?<![0-9])" + re.escape(n)
        if re.search(pattern, output_text):
            preserved += 1
    return preserved / len(expected_numbers)


def company_preservation(
    issues: list[MappedIssue],
    expected: dict[str, Any],
) -> float:
    """기업명 보존율: 원문 기업명이 출력에 포함되었는지."""
    expected_companies = expected.get("must_preserve_companies", [])
    if not expected_companies:
        return 1.0

    output_text = _issues_to_text(issues)
    preserved = sum(1 for c in expected_companies if c in output_text)
    return preserved / len(expected_companies)


def theme_relevance(
    issues: list[MappedIssue],
    expected: dict[str, Any],
) -> float:
    """테마 적절성: 예상 테마와 실제 테마의 의미적 유사도.

    단순 포함 검사 (부분 문자열 매칭). Fallback용.
    """
    expected_themes = expected.get("expected_themes", [])
    if not expected_themes:
        return 1.0

    actual_themes = [theme for issue in issues for theme in issue.themes]
    actual_themes_text = " ".join(actual_themes)

    matched = 0
    for exp_theme in expected_themes:
        # 부분 문자열 매칭 (예: "전기차" in "전기차 수요 둔화")
        keywords = exp_theme.split()
        if any(kw in actual_themes_text for kw in keywords):
            matched += 1

    return matched / len(expected_themes)


def theme_relevance_llm(
    issues: list[MappedIssue],
    expected: dict[str, Any],
    llm=None,
) -> tuple[float, list[dict]]:
    """LLM-as-Judge로 테마 의미적 유사도 평가.

    Returns:
        (score, match_details) - 점수와 상세 매칭 결과
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.pipelines.daily_report.prompts import THEME_JUDGE_SYSTEM_PROMPT

    expected_themes = expected.get("expected_themes", [])
    if not expected_themes:
        return 1.0, []

    actual_themes = [theme for issue in issues for theme in issue.themes]
    if not actual_themes:
        return 0.0, [
            {"expected": t, "matched": False, "reason": "출력 테마 없음"} for t in expected_themes
        ]

    # LLM 생성 (없으면 기본값)
    if llm is None:
        from src.llm.provider import LLMProvider

        llm = LLMProvider.create(
            provider="anthropic",
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            temperature=0,
        )

    user_prompt = f"""예상 테마: {expected_themes}
실제 테마: {actual_themes}

각 예상 테마가 실제 테마 중 하나와 의미적으로 일치하는지 판단하세요."""

    messages = [
        SystemMessage(content=THEME_JUDGE_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    try:
        llm_with_output = llm.with_structured_output(ThemeMatchResult)
        result = llm_with_output.invoke(messages)
        return result.score, result.matches
    except Exception as e:
        print(f"⚠️  LLM 테마 평가 실패: {e}, fallback to rule-based")
        return theme_relevance(issues, expected), []


def keyword_coverage(
    issues: list[MappedIssue],
    expected: dict[str, Any],
) -> float:
    """키워드 커버리지: 예상 키워드 중 출력에 포함된 비율."""
    expected_keywords = expected.get("expected_keywords", [])
    if not expected_keywords:
        return 1.0

    # _issues_to_text에 이미 keywords가 포함됨 — 중복 없이 단일 검색
    all_text = _issues_to_text(issues)

    covered = sum(1 for kw in expected_keywords if kw in all_text)
    return covered / len(expected_keywords)


def must_split_check(
    issues: list[MappedIssue],
    expected: dict[str, Any],
) -> float:
    """분리 필요 여부 충족 검사.

    must_split=True인 경우 이슈가 num_issues_min 이상으로 분리됐는지 확인.
    must_split=False이거나 필드가 없으면 항상 1.0.
    """
    if not expected.get("must_split", False):
        return 1.0

    min_expected = expected.get("num_issues_min", 2)
    return 1.0 if len(issues) >= min_expected else 0.0


def category_accuracy(
    issues: list[MappedIssue],
    expected: dict[str, Any],
) -> float:
    """카테고리 정확도: 예상 카테고리와 실제 카테고리 일치 여부.

    Counter 기반 Jaccard 유사도 사용:
    - intersection: 각 카테고리별 min(expected, actual) 합
    - union: 각 카테고리별 max(expected, actual) 합
    - score = intersection / union
    """
    expected_category = expected.get("expected_category")
    if not expected_category:
        return 1.0

    if not issues:
        return 0.0

    actual_categories = [issue.category for issue in issues]

    # expected_category가 리스트인 경우 (복수 이슈)
    if isinstance(expected_category, list):
        expected_counter = Counter(expected_category)
        actual_counter = Counter(actual_categories)

        # 모든 카테고리 키
        all_categories = set(expected_counter.keys()) | set(actual_counter.keys())

        # intersection: 각 카테고리별 min
        intersection = sum(
            min(expected_counter.get(cat, 0), actual_counter.get(cat, 0)) for cat in all_categories
        )
        # union: 각 카테고리별 max
        union = sum(
            max(expected_counter.get(cat, 0), actual_counter.get(cat, 0)) for cat in all_categories
        )
        return intersection / union if union > 0 else 1.0

    # 단일 카테고리인 경우
    matched = sum(1 for c in actual_categories if c == expected_category)
    return matched / len(actual_categories)


def _issues_to_text(issues: list[MappedIssue]) -> str:
    """이슈 리스트를 단일 텍스트로 변환."""
    parts = []
    for issue in issues:
        parts.append(issue.title)
        parts.append(issue.summary)
        parts.append(issue.impact)
        parts.extend(issue.themes)
    return " ".join(parts)


# 규칙 기반 메트릭
RULE_BASED_METRICS = {
    "split_accuracy": split_accuracy,
    "must_split_check": must_split_check,
    "number_preservation": number_preservation,
    "company_preservation": company_preservation,
    "theme_relevance": theme_relevance,
    "keyword_coverage": keyword_coverage,
    "category_accuracy": category_accuracy,
}


def evaluate_all(
    issues: list[MappedIssue],
    expected: dict[str, Any],
    use_llm_judge: bool = False,
    llm=None,
) -> dict[str, Any]:
    """모든 메트릭 계산.

    Args:
        issues: 평가할 이슈 리스트
        expected: 예상 값 딕셔너리
        use_llm_judge: LLM-as-Judge 사용 여부
        llm: 사용할 LLM 인스턴스 (None이면 자동 생성)

    Returns:
        메트릭 결과 딕셔너리
    """
    results = {}

    # 규칙 기반 메트릭
    for name, fn in RULE_BASED_METRICS.items():
        if name == "theme_relevance" and use_llm_judge:
            continue  # LLM 버전으로 대체
        results[name] = fn(issues, expected)

    # LLM-as-Judge 메트릭
    if use_llm_judge:
        score, details = theme_relevance_llm(issues, expected, llm)
        results["theme_relevance"] = score
        results["theme_relevance_details"] = details

    return results

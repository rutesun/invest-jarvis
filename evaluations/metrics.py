"""Map stage 평가 메트릭."""

from typing import List, Dict, Any
from pydantic import BaseModel, Field
from src.pipelines.daily_report.models import MappedIssue


class ThemeMatchResult(BaseModel):
    """LLM 테마 매칭 결과."""

    matches: List[Dict[str, Any]] = Field(
        description="각 예상 테마별 매칭 결과 [{expected, matched, reason}]"
    )
    score: float = Field(description="전체 매칭 점수 (0.0 ~ 1.0)", ge=0.0, le=1.0)


def split_accuracy(
    issues: List[MappedIssue],
    expected: Dict[str, Any],
) -> float:
    """이슈 분리 정확도: 예상 범위 내 개수인지."""
    actual_count = len(issues)
    min_expected = expected.get("num_issues_min", 1)
    max_expected = expected.get("num_issues_max", 1)
    return 1.0 if min_expected <= actual_count <= max_expected else 0.0


def number_preservation(
    issues: List[MappedIssue],
    expected: Dict[str, Any],
) -> float:
    """숫자 보존율: 원문 숫자가 출력에 포함되었는지."""
    expected_numbers = expected.get("must_preserve_numbers", [])
    if not expected_numbers:
        return 1.0

    output_text = _issues_to_text(issues)
    preserved = sum(1 for n in expected_numbers if n in output_text)
    return preserved / len(expected_numbers)


def company_preservation(
    issues: List[MappedIssue],
    expected: Dict[str, Any],
) -> float:
    """기업명 보존율: 원문 기업명이 출력에 포함되었는지."""
    expected_companies = expected.get("must_preserve_companies", [])
    if not expected_companies:
        return 1.0

    output_text = _issues_to_text(issues)
    preserved = sum(1 for c in expected_companies if c in output_text)
    return preserved / len(expected_companies)


def theme_relevance(
    issues: List[MappedIssue],
    expected: Dict[str, Any],
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
    issues: List[MappedIssue],
    expected: Dict[str, Any],
    llm=None,
) -> tuple[float, List[Dict]]:
    """LLM-as-Judge로 테마 의미적 유사도 평가.

    Returns:
        (score, match_details) - 점수와 상세 매칭 결과
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    expected_themes = expected.get("expected_themes", [])
    if not expected_themes:
        return 1.0, []

    actual_themes = [theme for issue in issues for theme in issue.themes]
    if not actual_themes:
        return 0.0, [{"expected": t, "matched": False, "reason": "출력 테마 없음"} for t in expected_themes]

    # LLM 생성 (없으면 기본값)
    if llm is None:
        from src.llm.provider import LLMProvider
        llm = LLMProvider.create(
            provider="anthropic",
            model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            temperature=0,
        )

    system_prompt = """당신은 테마 매칭 평가자입니다.
예상 테마와 실제 테마가 의미적으로 일치하는지 판단하세요.

규칙:
- 정확히 같은 단어가 아니어도 의미가 같으면 매칭됨
- 예: "양자보안" ≈ "Post-Quantum Cryptography" ≈ "양자암호"
- 예: "전기차 수요 둔화" ≈ "EV 시장 성장 둔화"
- 부분적으로 관련있는 것은 매칭 아님

JSON 형식으로 응답하세요."""

    user_prompt = f"""예상 테마: {expected_themes}
실제 테마: {actual_themes}

각 예상 테마가 실제 테마 중 하나와 의미적으로 일치하는지 판단하세요."""

    messages = [
        SystemMessage(content=system_prompt),
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
    issues: List[MappedIssue],
    expected: Dict[str, Any],
) -> float:
    """키워드 커버리지: 예상 키워드 중 출력에 포함된 비율."""
    expected_keywords = expected.get("expected_keywords", [])
    if not expected_keywords:
        return 1.0

    # keywords 필드 + summary + title에서 검색
    output_text = _issues_to_text(issues)
    actual_keywords = [kw for issue in issues for kw in issue.keywords]
    all_text = output_text + " " + " ".join(actual_keywords)

    covered = sum(1 for kw in expected_keywords if kw in all_text)
    return covered / len(expected_keywords)


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


# 규칙 기반 메트릭
RULE_BASED_METRICS = {
    "split_accuracy": split_accuracy,
    "number_preservation": number_preservation,
    "company_preservation": company_preservation,
    "theme_relevance": theme_relevance,
    "keyword_coverage": keyword_coverage,
}


def evaluate_all(
    issues: List[MappedIssue],
    expected: Dict[str, Any],
    use_llm_judge: bool = False,
    llm=None,
) -> Dict[str, Any]:
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

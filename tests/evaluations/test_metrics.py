"""evaluations/metrics.py 단위 테스트."""

from evaluations.metrics import (
    RULE_BASED_METRICS,
    company_preservation,
    keyword_coverage,
    must_split_check,
    number_preservation,
    split_accuracy,
)
from src.pipelines.daily_report.models import MappedIssue


def make_issue(
    title="테스트 이슈",
    summary="요약",
    category="기타",
    themes=None,
    keywords=None,
    impact="영향",
    sentiment="neutral",
    source_ids=None,
) -> MappedIssue:
    return MappedIssue(
        title=title,
        summary=summary,
        category=category,
        themes=themes or ["테마1"],
        keywords=keywords or ["키워드1"],
        impact=impact,
        sentiment=sentiment,
        source_ids=source_ids or ["test_001"],
    )


# ============================================================
# split_accuracy
# ============================================================


def test_split_accuracy_exact_match():
    issues = [make_issue(), make_issue()]
    score = split_accuracy(issues, {"num_issues_min": 2, "num_issues_max": 2})
    assert score == 1.0


def test_split_accuracy_within_range():
    issues = [make_issue(), make_issue()]
    score = split_accuracy(issues, {"num_issues_min": 1, "num_issues_max": 3})
    assert score == 1.0


def test_split_accuracy_too_few():
    score = split_accuracy([make_issue()], {"num_issues_min": 2, "num_issues_max": 3})
    assert score == 0.0


def test_split_accuracy_too_many():
    issues = [make_issue(), make_issue(), make_issue()]
    score = split_accuracy(issues, {"num_issues_min": 1, "num_issues_max": 2})
    assert score == 0.0


# ============================================================
# must_split_check
# ============================================================


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


# ============================================================
# number_preservation
# ============================================================


def test_number_preservation_all_preserved():
    issue = make_issue(summary="테슬라 5.6% 급락, 인력 10% 감축")
    score = number_preservation([issue], {"must_preserve_numbers": ["5.6%", "10%"]})
    assert score == 1.0


def test_number_preservation_partial():
    issue = make_issue(summary="테슬라 5.6% 급락")
    score = number_preservation([issue], {"must_preserve_numbers": ["5.6%", "10%"]})
    assert abs(score - 0.5) < 0.01


def test_number_preservation_empty_expected():
    score = number_preservation([make_issue()], {"must_preserve_numbers": []})
    assert score == 1.0


# ============================================================
# company_preservation
# ============================================================


def test_company_preservation_all_preserved():
    issue = make_issue(title="테슬라 오라클 뉴스", summary="블룸에너지 계약")
    score = company_preservation(
        [issue], {"must_preserve_companies": ["테슬라", "오라클", "블룸에너지"]}
    )
    assert score == 1.0


def test_company_preservation_partial():
    issue = make_issue(title="테슬라 뉴스")
    score = company_preservation([issue], {"must_preserve_companies": ["테슬라", "오라클"]})
    assert abs(score - 0.5) < 0.01


# ============================================================
# keyword_coverage — 이중 검색 없는지 확인
# ============================================================


def test_keyword_coverage_no_double_count():
    """키워드가 issues.keywords에만 존재하는 경우 이중 검색 없이 정확히 계산."""
    issue = make_issue(keywords=["HBM", "삼성"])
    expected = {"expected_keywords": ["HBM", "삼성", "없는키워드"]}
    score = keyword_coverage([issue], expected)
    assert abs(score - 2 / 3) < 0.01


def test_keyword_coverage_full_match():
    issue = make_issue(title="HBM 뉴스", summary="삼성 HBM", keywords=["HBM"])
    score = keyword_coverage([issue], {"expected_keywords": ["HBM", "삼성"]})
    assert score == 1.0


def test_keyword_coverage_empty_expected():
    score = keyword_coverage([make_issue()], {"expected_keywords": []})
    assert score == 1.0


# ============================================================
# RULE_BASED_METRICS 포함 여부
# ============================================================


def test_rule_based_metrics_contains_must_split():
    assert "must_split_check" in RULE_BASED_METRICS


def test_rule_based_metrics_all_keys():
    expected_keys = {
        "split_accuracy",
        "must_split_check",
        "number_preservation",
        "company_preservation",
        "theme_relevance",
        "keyword_coverage",
        "category_accuracy",
    }
    assert expected_keys == set(RULE_BASED_METRICS.keys())

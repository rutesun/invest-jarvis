from src.tools.filing.concepts import (
    SEC_CONCEPT_CHAINS,
    resolve_dart_metric,
    resolve_sec_metric,
)


def test_sec_revenue_primary_tag():
    """RevenueFromContract... 태그가 있으면 revenue로 매핑."""
    facts = {"RevenueFromContractWithCustomerExcludingAssessedTax": 416_200_000_000}
    result = resolve_sec_metric("revenue", facts)
    assert result == 416_200_000_000


def test_sec_revenue_fallback():
    """Primary 태그 없으면 Revenues fallback."""
    facts = {"Revenues": 215_900_000_000}
    result = resolve_sec_metric("revenue", facts)
    assert result == 215_900_000_000


def test_sec_revenue_not_found():
    """모든 fallback 실패 시 None."""
    facts = {"SomeOtherTag": 999}
    result = resolve_sec_metric("revenue", facts)
    assert result is None


def test_sec_operating_income():
    facts = {"OperatingIncomeLoss": 133_100_000_000}
    result = resolve_sec_metric("operating_income", facts)
    assert result == 133_100_000_000


def test_sec_unknown_metric():
    """정의되지 않은 metric 요청 시 None."""
    facts = {}
    result = resolve_sec_metric("unknown_metric", facts)
    assert result is None


def test_dart_revenue():
    result = resolve_dart_metric("매출액")
    assert result == "revenue"


def test_dart_operating_income():
    result = resolve_dart_metric("영업이익")
    assert result == "operating_income"


def test_dart_unknown():
    result = resolve_dart_metric("알수없는계정")
    assert result is None


def test_sec_concept_chains_has_all_required():
    required = ["revenue", "operating_income", "net_income", "shares_outstanding"]
    for key in required:
        assert key in SEC_CONCEPT_CHAINS, f"{key} missing from SEC_CONCEPT_CHAINS"

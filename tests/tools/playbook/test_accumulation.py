from src.tools.playbook.models import AccumulationResult


def test_accumulation_result_model():
    r = AccumulationResult(
        accumulation_days=14, distribution_days=8, accumulation_ratio=0.636, window=25
    )
    assert r.accumulation_days == 14
    assert r.distribution_days == 8
    assert abs(r.accumulation_ratio - 0.636) < 1e-6
    assert r.is_accumulating is True  # ratio > 0.5

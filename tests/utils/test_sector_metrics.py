from src.utils.sector_metrics import SectorMetrics


def test_get_priority_metrics_technology():
    """Technology 섹터의 우선순위 지표 반환 테스트"""
    result = SectorMetrics.get_priority_metrics("Technology")

    assert isinstance(result, list)
    assert len(result) > 0
    assert "peg_ratio" in result
    assert "ps_ratio" in result


def test_get_priority_metrics_none():
    """섹터가 None일 때 DEFAULT 반환 테스트"""
    result = SectorMetrics.get_priority_metrics(None)

    assert isinstance(result, list)
    assert len(result) > 0
    assert result == SectorMetrics.DEFAULT

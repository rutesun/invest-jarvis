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


def test_get_priority_metrics_financials():
    """Financials 섹터 매핑 테스트"""
    result = SectorMetrics.get_priority_metrics("Financials")

    assert "roe" in result
    assert "roa" in result
    assert "pb_ratio" in result


def test_get_priority_metrics_fuzzy_match():
    """퍼지 매칭 테스트 - 'Information Technology'도 매칭"""
    result = SectorMetrics.get_priority_metrics("Information Technology")

    assert "peg_ratio" in result
    assert "ps_ratio" in result


def test_get_priority_metrics_unknown():
    """인식되지 않는 섹터는 DEFAULT 반환"""
    result = SectorMetrics.get_priority_metrics("Unknown Sector")

    assert result == SectorMetrics.DEFAULT

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


def test_all_sectors_have_mappings():
    """10개 섹터 모두 매핑되었는지 검증"""
    sectors = [
        "Technology",
        "Financials",
        "Consumer Cyclical",
        "Consumer Defensive",
        "Healthcare",
        "Industrials",
        "Energy",
        "Real Estate",
        "Utilities",
        "Communication Services",
    ]

    for sector in sectors:
        result = SectorMetrics.get_priority_metrics(sector)
        assert result is not None
        assert len(result) > 0
        assert result != SectorMetrics.DEFAULT, f"{sector} should have specific mapping"


def test_case_insensitive_matching():
    """대소문자 구분 없이 매칭되는지 테스트"""
    assert SectorMetrics.get_priority_metrics("TECHNOLOGY") == SectorMetrics.TECHNOLOGY
    assert SectorMetrics.get_priority_metrics("technology") == SectorMetrics.TECHNOLOGY
    assert SectorMetrics.get_priority_metrics("TechNOLogy") == SectorMetrics.TECHNOLOGY


def test_partial_sector_name_matching():
    """부분 매칭 테스트"""
    # "Information Technology"도 매칭되어야 함
    assert SectorMetrics.get_priority_metrics("Information Technology") == SectorMetrics.TECHNOLOGY

    # "Financial Services"도 매칭되어야 함
    assert SectorMetrics.get_priority_metrics("Financial Services") == SectorMetrics.FINANCIALS


def test_empty_string_returns_default():
    """빈 문자열은 DEFAULT 반환"""
    assert SectorMetrics.get_priority_metrics("") == SectorMetrics.DEFAULT

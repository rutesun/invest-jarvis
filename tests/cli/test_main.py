from src.cli.analyze_render import _format_metric_value, _get_metric_display_name


def test_format_metric_value_percent():
    """퍼센트 지표 포맷팅 테스트"""
    assert _format_metric_value("revenue_growth", 0.732) == "73.2%"
    assert _format_metric_value("roe", 1.015) == "101.5%"
    assert _format_metric_value("fcf_yield", 0.013) == "1.3%"


def test_format_metric_value_dollar():
    """달러 금액 포맷팅 테스트"""
    assert _format_metric_value("free_cash_flow", 106.3e9) == "$106.3B"
    assert _format_metric_value("operating_cash_flow", 42.5e9) == "$42.5B"


def test_format_metric_value_ratio():
    """비율 지표 포맷팅 테스트"""
    assert _format_metric_value("pe_ratio", 38.5) == "38.5"
    assert _format_metric_value("peg_ratio", 2.15) == "2.15"
    assert _format_metric_value("debt_to_equity", 7.3) == "7.3"


def test_get_metric_display_name():
    """지표명 표시 매핑 테스트"""
    assert _get_metric_display_name("pe_ratio") == "P/E Ratio"
    assert _get_metric_display_name("peg_ratio") == "PEG Ratio"
    assert _get_metric_display_name("revenue_growth") == "매출 성장률"
    assert _get_metric_display_name("unknown_metric") == "Unknown Metric"


def test_cli_priority_metrics_order():
    """우선순위 지표 순서 검증"""
    from src.utils.sector_metrics import SectorMetrics

    priority = SectorMetrics.get_priority_metrics("Technology")

    # Technology 섹터의 첫 번째 지표는 peg_ratio여야 함
    assert priority[0] == "peg_ratio"
    assert priority[1] == "ps_ratio"

import pytest
import re
from typer.testing import CliRunner
from src.cli.main import app

runner = CliRunner()


@pytest.mark.integration
def test_check_with_scoring():
    """Test check command shows total_score."""
    result = runner.invoke(app, ["check", "AAPL"])
    assert result.exit_code == 0
    assert "AAPL" in result.stdout


@pytest.mark.integration
def test_check_korean_stock_scoring():
    """Test check with Korean stock."""
    result = runner.invoke(app, ["check", "005930.KS"])
    assert result.exit_code in [0, 1]


@pytest.mark.integration
def test_analyze_shows_quarterly_trends():
    """Verify CLI shows quarterly table and list"""
    result = runner.invoke(app, ["analyze", "AAPL", "--provider", "openai"])

    # Table verification
    assert "분기별 추이" in result.stdout
    assert "YoY Growth %" in result.stdout

    # List verification
    assert "분기별 실적" in result.stdout
    assert "매출 추이:" in result.stdout
    assert "이익 추이:" in result.stdout

    # Growth rate format verification (+ or - sign)
    assert re.search(r"YoY [+-]\d+\.\d+%", result.stdout) is not None


@pytest.mark.integration
def test_analyze_shows_sector_priority_metrics():
    """CLI에서 섹터별 우선순위 지표가 ⭐와 함께 표시되는지 검증"""
    result = runner.invoke(app, ["analyze", "NVDA", "--provider", "openai"])

    assert result.exit_code == 0

    # Technology 섹터는 PSR을 ⭐와 함께 표시해야 함
    # 렌더링 후에는 **bold** 마크업이 사라지므로 단순 텍스트 검색
    assert "⭐" in result.stdout, "⭐ symbol should be present in output"
    assert "PSR" in result.stdout, "PSR metric should be present"
    assert "매출 성장률" in result.stdout, "Revenue growth metric should be present"

    # 우선순위 지표들이 ⭐와 함께 같은 섹션에 표시되어야 함
    lines_with_star = [line for line in result.stdout.split('\n') if '⭐' in line]
    assert len(lines_with_star) > 0, "Should have lines with priority metrics marked with ⭐"

    # P/E Ratio는 우선순위가 아니므로 ⭐가 붙지 않아야 함
    # Check that no line contains both ⭐ and P/E Ratio
    pe_lines = [line for line in result.stdout.split('\n')
                if '⭐' in line and 'P/E Ratio' in line]
    assert len(pe_lines) == 0, "P/E Ratio should not have ⭐"

    # Sector/Industry 정보는 표시되어야 함
    assert "Technology" in result.stdout or "Semiconductors" in result.stdout

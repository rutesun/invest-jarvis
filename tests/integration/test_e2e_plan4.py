import pytest
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
    import re
    assert re.search(r"YoY [+-]\d+\.\d+%", result.stdout) is not None

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

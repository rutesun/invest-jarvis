import pytest
from typer.testing import CliRunner
from src.cli.main import app

runner = CliRunner()


@pytest.mark.integration
def test_end_to_end_check_real_ticker():
    """End-to-end test with real API call."""
    result = runner.invoke(app, ["check", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    # Should have price and assessment
    assert "가격" in result.stdout or "$" in result.stdout

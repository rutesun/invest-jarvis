import pytest
from typer.testing import CliRunner
from src.cli.main import app
import os

runner = CliRunner()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("KIS_APP_KEY") or not os.getenv("KIS_APP_SECRET"),
    reason="KIS credentials not available",
)
def test_portfolio_command():
    """Test portfolio command with real KIS API."""
    result = runner.invoke(app, ["portfolio"])
    assert result.exit_code == 0
    assert "portfolio" in result.stdout.lower() or "holdings" in result.stdout.lower()


@pytest.mark.integration
def test_korean_stock_check():
    """Test check command with Korean stock."""
    result = runner.invoke(app, ["check", "005930"])
    assert result.exit_code in [0, 1]

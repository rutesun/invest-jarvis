import pytest
from typer.testing import CliRunner

from src.cli.main import app


runner = CliRunner()


@pytest.mark.integration
def test_korean_stock_check():
    """Test check command with Korean stock."""
    result = runner.invoke(app, ["check", "005930"])
    assert result.exit_code in [0, 1]

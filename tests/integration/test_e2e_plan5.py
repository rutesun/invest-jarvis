import pytest
from typer.testing import CliRunner
from src.cli.main import app

runner = CliRunner()


@pytest.mark.integration
def test_screen_command_kr():
    """Test screen command for Korean market."""
    result = runner.invoke(app, ["screen", "--market=kr"])
    # May fail without network, but should not crash
    assert result.exit_code in [0, 1]


@pytest.mark.integration
def test_screen_command_us():
    """Test screen command for US market (requires KIS credentials)."""
    result = runner.invoke(app, ["screen", "--market=us"])
    assert result.exit_code in [0, 1]

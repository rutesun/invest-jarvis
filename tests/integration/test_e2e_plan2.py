import os

import pytest
from typer.testing import CliRunner

from src.cli.main import app


runner = CliRunner()


@pytest.mark.integration
def test_analyze_command_integration():
    """Integration test for analyze command (requires API key)."""
    provider = "openai"
    api_key_env = "OPENAI_API_KEY"

    if not os.getenv(api_key_env):
        pytest.skip(f"{api_key_env} not set")

    result = runner.invoke(app, ["analyze", "AAPL", "--provider", provider])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    assert "Technical Analysis" in result.stdout
    assert "News Analysis" in result.stdout or "Deep Dive Analysis" in result.stdout


@pytest.mark.integration
def test_report_command_integration():
    """Integration test for report command (requires API key)."""
    provider = "openai"
    api_key_env = "OPENAI_API_KEY"

    if not os.getenv(api_key_env):
        pytest.skip(f"{api_key_env} not set")

    result = runner.invoke(app, ["report", "--tickers", "AAPL,MSFT", "--provider", provider])

    assert result.exit_code == 0
    assert "Daily Market Report" in result.stdout
    assert "Macro Snapshot" in result.stdout
    assert "AAPL" in result.stdout
    assert "MSFT" in result.stdout


@pytest.mark.integration
def test_analyze_with_anthropic():
    """Integration test for analyze command with Anthropic (requires API key)."""
    provider = "anthropic"
    api_key_env = "ANTHROPIC_API_KEY"

    if not os.getenv(api_key_env):
        pytest.skip(f"{api_key_env} not set")

    result = runner.invoke(app, ["analyze", "AAPL", "--provider", provider])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    assert "Technical Analysis" in result.stdout

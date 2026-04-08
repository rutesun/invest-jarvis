import pytest
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock
from src.cli.main import app

runner = CliRunner()


def test_cli_check_command():
    mock_result = {
        "ticker": "AAPL",
        "success": True,
        "price": 178.50,
        "change_pct": 2.5,
        "assessment": "매수",
        "confidence": 75.0,
        "signals": ["골든크로스"],
        "warnings": [],
        "indicators": {"sma_20": 175.0, "sma_50": 170.0, "rsi": 58.3, "adx": 28.0},
        "strategies": [],
    }

    with patch("src.cli.main.run_quick_check", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_result
        result = runner.invoke(app, ["check", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    assert "178.50" in result.stdout


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout

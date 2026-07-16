from typer.testing import CliRunner

from src.cli.main import app


runner = CliRunner()


def test_brief_command_registered():
    result = runner.invoke(app, ["brief", "--help"])
    assert result.exit_code == 0
    assert "brief" in result.output.lower() or "브리핑" in result.output

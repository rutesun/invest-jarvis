# tests/core/test_models.py
from src.core.models import ToolResult


def test_tool_result_success():
    result = ToolResult(success=True, data={"price": 150.0})
    assert result.success is True
    assert result.data == {"price": 150.0}
    assert result.error is None


def test_tool_result_failure():
    result = ToolResult(success=False, data=None, error="API error")
    assert result.success is False
    assert result.error == "API error"

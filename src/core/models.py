# src/core/models.py
from typing import Any
from pydantic import BaseModel


class ToolResult(BaseModel):
    """Tool execution result."""
    success: bool
    data: Any
    error: str | None = None

# src/core/interfaces.py
from abc import ABC, abstractmethod
import pandas as pd
from src.core.models import ToolResult


class BaseTool(ABC):
    """Abstract base class for all analysis tools."""
    name: str
    description: str

    @abstractmethod
    async def execute(self, ticker: str, **kwargs) -> ToolResult:
        """Execute the tool and return result."""
        pass


class BaseProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    async def get_price_history(self, ticker: str, period: str) -> pd.DataFrame:
        """Get historical price data."""
        pass

    @abstractmethod
    async def get_quote(self, ticker: str) -> dict:
        """Get current quote."""
        pass

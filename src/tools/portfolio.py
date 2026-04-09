from src.core.interfaces import BaseTool
from src.core.models import ToolResult
from src.providers.kis import KISProvider


class PortfolioTool(BaseTool):
    """Portfolio analysis tool."""

    name = "portfolio"
    description = "포트폴리오 잔고 및 보유 종목 조회"

    def __init__(self, provider: KISProvider):
        self.provider = provider

    async def execute(self, **kwargs) -> ToolResult:
        """Get portfolio balance and positions."""
        try:
            balance = await self.provider.get_balance()
            return ToolResult(success=True, data=balance)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

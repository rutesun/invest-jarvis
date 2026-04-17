from datetime import datetime
from pydantic import BaseModel
import yfinance as yf
from src.core.interfaces import BaseTool
from src.core.models import ToolResult


class TickerMacroSnapshot(BaseModel):
    """Macro indicators snapshot for ticker analysis."""

    timestamp: datetime

    vix: float
    vix_change: float

    fear_greed: int
    fear_greed_label: str

    wti: float
    wti_change: float

    us_10y: float
    us_2y: float
    yield_spread: float

    dxy: float
    dxy_change: float


class MacroTool(BaseTool):
    """Macro indicators tool."""

    name = "macro"
    description = "Macro indicators (VIX, Fear & Greed, WTI, Yields, DXY)"

    def _get_fear_greed_label(self, value: int) -> str:
        """Get Fear & Greed label from value."""
        if value <= 25:
            return "Extreme Fear"
        elif value <= 45:
            return "Fear"
        elif value <= 55:
            return "Neutral"
        elif value <= 75:
            return "Greed"
        else:
            return "Extreme Greed"

    def _calculate_fear_greed(self, vix: float, market_momentum: float) -> int:
        """Calculate approximate Fear & Greed index."""
        vix_normalized = max(0, min(100, (50 - vix) * 2))
        momentum_normalized = max(0, min(100, (market_momentum + 5) * 10))
        fear_greed = int((vix_normalized * 0.6 + momentum_normalized * 0.4))
        return max(0, min(100, fear_greed))

    async def execute(self, **kwargs) -> ToolResult:
        """Execute macro indicators tool."""
        try:
            tickers = {
                "vix": "^VIX",
                "wti": "CL=F",
                "us_10y": "^TNX",
                "us_2y": "^IRX",
                "dxy": "DX-Y.NYB",
                "spy": "SPY",
            }

            data = {}
            for key, symbol in tickers.items():
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                if hist.empty:
                    return ToolResult(
                        success=False,
                        data=None,
                        error=f"No data found for {symbol}",
                    )

                current = hist["Close"].iloc[-1]
                previous = hist["Close"].iloc[-2] if len(hist) >= 2 else current
                change = current - previous

                data[key] = {"current": float(current), "change": float(change)}

            spy_momentum = (
                (data["spy"]["current"] - hist["Close"].iloc[0]) / hist["Close"].iloc[0] * 100
            )
            fear_greed = self._calculate_fear_greed(
                data["vix"]["current"], spy_momentum
            )
            fear_greed_label = self._get_fear_greed_label(fear_greed)

            yield_spread = data["us_10y"]["current"] - data["us_2y"]["current"]

            snapshot = TickerMacroSnapshot(
                timestamp=datetime.now(),
                vix=data["vix"]["current"],
                vix_change=data["vix"]["change"],
                fear_greed=fear_greed,
                fear_greed_label=fear_greed_label,
                wti=data["wti"]["current"],
                wti_change=data["wti"]["change"],
                us_10y=data["us_10y"]["current"],
                us_2y=data["us_2y"]["current"],
                yield_spread=yield_spread,
                dxy=data["dxy"]["current"],
                dxy_change=data["dxy"]["change"],
            )

            return ToolResult(success=True, data=snapshot)

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


__all__ = ["MacroTool", "TickerMacroSnapshot"]

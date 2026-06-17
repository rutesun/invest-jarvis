import pandas as pd

from src.providers.yfinance_provider import YFinanceProvider


def index_symbol_for(ticker: str) -> str:
    """종목 티커 → 비교 시장지수 심볼."""
    if ticker.endswith(".KS"):
        return "^KS11"
    if ticker.endswith(".KQ"):
        return "^KQ11"
    code = ticker.replace(".KS", "").replace(".KQ", "")
    if code.isdigit() and len(code) == 6:
        return "^KS11"  # 시장 불명 6자리 → 코스피 기본 (KOSDAQ는 .KQ로 구분)
    return "^GSPC"  # 미국/기타


class IndexProvider:
    """시장지수 OHLCV fetch (yfinance). RS·시장환경 모듈에 DataFrame 주입용."""

    def __init__(self, yf_provider: YFinanceProvider | None = None):
        self._yf = yf_provider or YFinanceProvider()

    async def get_index_history(self, ticker: str, period: str = "2y") -> tuple[str, pd.DataFrame]:
        """종목에 맞는 지수의 OHLCV를 반환. (index_symbol, df)."""
        symbol = index_symbol_for(ticker)
        df = await self._yf.get_price_history(symbol, period)
        return symbol, df

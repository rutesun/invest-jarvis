from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from src.providers.kis import KISProvider
from src.providers.kis_wrapper import KISProviderWrapper
from src.providers.yfinance_provider import YFinanceProvider


TICKERS = {
    "033100.KQ": Path("tests/fixtures/technical/structure_zones/033100.KQ.csv"),
    "066970.KQ": Path("tests/fixtures/technical/structure_zones/066970.KQ.csv"),
    "ALAB": Path("tests/fixtures/technical/structure_zones/ALAB.csv"),
}


def _is_korean_ticker(ticker: str) -> bool:
    return ticker.endswith((".KS", ".KQ"))


async def main() -> None:
    load_dotenv()

    yf_provider = YFinanceProvider()
    kis_wrapper = None
    kis_key = os.getenv("KIS_APP_KEY")
    kis_secret = os.getenv("KIS_APP_SECRET")
    if kis_key and kis_secret:
        kis_wrapper = KISProviderWrapper(KISProvider(app_key=kis_key, app_secret=kis_secret))

    for ticker, output_path in TICKERS.items():
        provider = (
            kis_wrapper if _is_korean_ticker(ticker) and kis_wrapper is not None else yf_provider
        )
        df = await provider.get_price_history(ticker, period="3y")
        if df.empty:
            raise RuntimeError(f"No price history returned for {ticker}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        export_df.index.name = "Date"
        export_df.to_csv(output_path)
        print(f"saved {ticker} -> {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

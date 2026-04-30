# src/tools/filing/parser.py
"""Unified filing parser that handles both SEC (US) and DART (KR) markets."""

import logging
import os
from collections.abc import AsyncGenerator

from langchain_core.language_models import BaseChatModel

from src.tools.filing.dart_parser import DARTFilingParser
from src.tools.filing.models import FilingFacts
from src.tools.filing.sec_parser import SECFilingParser


logger = logging.getLogger(__name__)


class FilingParser:
    """Unified parser for SEC (US) and DART (KR) filing data."""

    def __init__(self, llm: BaseChatModel | None = None) -> None:
        self.llm = llm
        self._sec_parser = SECFilingParser(llm=llm)

        # DART parser requires API key
        dart_api_key = os.getenv("OPENDART_API_KEY")
        self._dart_parser = DARTFilingParser(dart_api_key, llm=llm) if dart_api_key else None

    async def parse(self, ticker: str) -> FilingFacts | None:
        """Parse filing data for the given ticker.

        Automatically detects market (US vs KR) and routes to appropriate parser.

        Args:
            ticker: Stock ticker (e.g., "AAPL", "NVDA", "005930")

        Returns:
            FilingFacts object with financial data and insights, or None if parsing failed
        """
        try:
            if self._is_korean_ticker(ticker):
                return await self._parse_korean_stock(ticker)
            else:
                return await self._parse_us_stock(ticker)
        except Exception:
            logger.exception("Filing parse failed for %s", ticker)
            return None

    async def _parse_us_stock(self, ticker: str) -> FilingFacts | None:
        """Parse SEC filing data for US stocks."""
        return await self._sec_parser.parse(ticker)

    async def _parse_korean_stock(self, ticker: str) -> FilingFacts | None:
        """Parse DART filing data for Korean stocks."""
        if not self._dart_parser:
            logger.warning(
                "DART API key not available - skipping Korean filing data for %s", ticker
            )
            return None

        # Korean ticker format: 6-digit code (e.g., "005930")
        if len(ticker) == 6 and ticker.isdigit():
            stock_code = ticker
            corp_code = self._get_corp_code(stock_code)
            if corp_code:
                # Try recent years starting from 2023
                for year in ["2024", "2023", "2025"]:
                    result = await self._dart_parser.parse(
                        stock_code=stock_code,
                        corp_code=corp_code,
                        bsns_year=year,
                        reprt_code="11011",  # Annual report
                    )
                    if result:
                        return result

        logger.warning("Invalid Korean ticker format: %s", ticker)
        return None

    def _is_korean_ticker(self, ticker: str) -> bool:
        """Check if ticker is Korean stock (6-digit numeric code)."""
        return len(ticker) == 6 and ticker.isdigit()

    def _get_corp_code(self, stock_code: str) -> str | None:
        """Get DART corporation code for Korean stock code.

        This is a simplified mapping. In production, you'd want to use
        the DART corp_code API or maintain a comprehensive mapping table.
        """
        # Known mappings for major Korean stocks
        corp_code_mapping = {
            "005930": "00126380",  # Samsung Electronics
            "000660": "00164779",  # SK Hynix
            "035420": "00167781",  # NAVER
            "005380": "00126186",  # Hyundai Motor
            "051910": "00164779",  # LG Chem
            "006400": "00164386",  # Samsung SDI
            "003670": "00164470",  # Posco Holdings
            "028260": "00164779",  # Samsung C&T
            "009150": "00164386",  # Samsung Electro-Mechanics
            "034730": "00167865",  # SK
        }

        return corp_code_mapping.get(stock_code)

    async def list_available_filings(
        self, ticker: str, limit: int = 5
    ) -> AsyncGenerator[str, None]:
        """List recent available filings for a ticker.

        Useful for debugging and verification.

        Args:
            ticker: Stock ticker
            limit: Maximum number of filings to list

        Yields:
            Filing descriptions (e.g., "10-K filed 2024-02-21", "사업보고서 2025")
        """
        try:
            if self._is_korean_ticker(ticker) and self._dart_parser:
                stock_code = ticker
                corp_code = self._get_corp_code(stock_code)
                if corp_code:
                    # For DART, we typically have annual reports
                    for year in range(2025, 2022, -1):  # 2025, 2024, 2023
                        yield f"사업보고서 {year}"
                        if limit <= 0:
                            break
                        limit -= 1
            else:
                # For SEC, we'd need to implement a filing list API call
                # For now, just indicate the latest 10-K is available
                yield "Latest 10-K available"

        except Exception:
            logger.exception("Failed to list filings for %s", ticker)

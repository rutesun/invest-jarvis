"""ticker → 종목명 조회 — yfinance get_quote 결과를 영속 캐시(180일)에 저장.

종목명은 거의 바뀌지 않으므로, 매 brief 실행마다 느린 get_quote(yfinance .info는
종목당 1~2초)를 반복하지 않도록 ticker를 키로 캐싱한다. 조회 실패 시 None을
반환하고, 렌더러가 종목코드로 graceful fallback 한다.

KR 종목은 yfinance 심볼에 시장 접미사가 필요하다(.KS=KOSPI, .KQ=KOSDAQ). 어느
시장인지 사전 정보가 없으므로 .KS → .KQ 순으로 시도해 이름이 잡히는 첫 심볼을
쓴다. (KIS 시세 응답은 종목명 필드가 비어 있고, 한글명을 주는 상품기본조회
tr_id는 앱키 미승인이라 US·KR 모두 yfinance로 통일한다.)
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.interfaces import BaseProvider
from src.providers.ticker_cache import UserMappingCache
from src.providers.yfinance_provider import YFinanceProvider
from src.tools.disclosure import extract_kr_code, is_korean_ticker


logger = logging.getLogger(__name__)

# yfinance는 잘못된 시장 접미사(예: KOSDAQ 종목의 .KS)에 대해 예외 대신
# quoteType='MUTUALFUND'인 fuzzy 검색 결과(쓰레기 shortName)를 반환한다.
# 실제 상장 종목/ETF만 통과시켜 오염된 이름을 걸러낸다.
_VALID_QUOTE_TYPES = {"EQUITY", "ETF"}


def _default_cache_path() -> Path:
    return Path.home() / ".cache/invest-jarvis/ticker_names.yaml"


class TickerNameResolver:
    """yfinance get_quote로 종목명을 얻고 원본 ticker 키로 캐싱한다.

    UserMappingCache를 재사용하되 전용 캐시 파일을 써서 name→ticker 해석 캐시와
    분리한다. 캐시 엔트리는 query=ticker, display_name=종목명 으로 저장한다.
    """

    def __init__(
        self,
        cache: UserMappingCache | None = None,
        provider: BaseProvider | None = None,
    ):
        self.cache = cache or UserMappingCache(_default_cache_path())
        self.provider = provider or YFinanceProvider()

    async def resolve(self, ticker: str) -> str | None:
        """ticker의 종목명을 반환. 캐시 우선, 없으면 yfinance 조회 후 캐싱."""
        cached = self.cache.get(ticker)
        if cached and cached.display_name:
            self.cache.update_usage(ticker)
            return cached.display_name

        name = await self._fetch(ticker)
        if name:
            self.cache.save(ticker, ticker, name)
        return name

    async def _fetch(self, ticker: str) -> str | None:
        for symbol in _yf_symbols(ticker):
            try:
                quote = await self.provider.get_quote(symbol)
            except Exception as e:  # noqa: BLE001 — 이름 조회 실패는 치명적이지 않음
                logger.debug("종목명 조회 실패 %s: %s", symbol, e)
                continue
            quote = quote or {}
            name = quote.get("name") or None
            if name and quote.get("quote_type") in _VALID_QUOTE_TYPES:
                return name
        return None


def _yf_symbols(ticker: str) -> list[str]:
    """yfinance 조회용 심볼 후보 — KR은 시장 접미사(.KS→.KQ) 순 시도."""
    if is_korean_ticker(ticker):
        code = extract_kr_code(ticker)
        return [f"{code}.KS", f"{code}.KQ"]
    return [ticker]

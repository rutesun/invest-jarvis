"""TickerNameResolver — 캐시 우선 조회 + yfinance fallback + KR 접미사 시도."""

import pytest

from src.providers.ticker_cache import UserMappingCache
from src.tools.brief.name_resolver import TickerNameResolver


class _StubProvider:
    """symbol → (name, quote_type) 매핑을 흉내내는 가짜 provider.

    quotes 값은 name 문자열이거나 (name, quote_type) 튜플. 호출 심볼을 기록한다.
    """

    def __init__(self, quotes: dict[str, object], raise_symbols: set[str] | None = None):
        self._quotes = quotes
        self._raise = raise_symbols or set()
        self.calls: list[str] = []

    async def get_quote(self, ticker: str) -> dict:
        self.calls.append(ticker)
        if ticker in self._raise:
            raise RuntimeError("boom")
        entry = self._quotes.get(ticker)
        if isinstance(entry, tuple):
            name, qtype = entry
        else:
            name, qtype = entry, "EQUITY"
        return {"name": name, "quote_type": qtype}

    async def get_price_history(self, ticker, period="1y"):  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
def cache(tmp_path):
    return UserMappingCache(tmp_path / "names.yaml")


@pytest.mark.asyncio
async def test_resolve_us_fetches_and_caches(cache):
    provider = _StubProvider({"NVDA": "NVIDIA Corporation"})
    resolver = TickerNameResolver(cache=cache, provider=provider)

    assert await resolver.resolve("NVDA") == "NVIDIA Corporation"
    assert provider.calls == ["NVDA"]


@pytest.mark.asyncio
async def test_resolve_cache_hit_skips_provider(cache):
    provider = _StubProvider({"NVDA": "NVIDIA Corporation"})
    resolver = TickerNameResolver(cache=cache, provider=provider)

    await resolver.resolve("NVDA")
    name = await resolver.resolve("NVDA")

    assert name == "NVIDIA Corporation"
    assert provider.calls == ["NVDA"]  # 두 번째는 캐시 히트 → provider 미호출


@pytest.mark.asyncio
async def test_resolve_kr_kospi_uses_ks_suffix(cache):
    provider = _StubProvider({"005930.KS": "SamsungElec"})
    resolver = TickerNameResolver(cache=cache, provider=provider)

    assert await resolver.resolve("005930") == "SamsungElec"
    assert provider.calls == ["005930.KS"]  # .KS에서 바로 잡히면 .KQ 미시도


@pytest.mark.asyncio
async def test_resolve_kr_kosdaq_falls_back_to_kq(cache):
    provider = _StubProvider({"123330.KQ": "Genic"})  # .KS는 이름 없음
    resolver = TickerNameResolver(cache=cache, provider=provider)

    assert await resolver.resolve("123330") == "Genic"
    assert provider.calls == ["123330.KS", "123330.KQ"]


@pytest.mark.asyncio
async def test_resolve_kr_rejects_mutualfund_junk_and_falls_back(cache):
    """KOSDAQ 종목의 .KS는 quoteType=MUTUALFUND 쓰레기 → 거부하고 .KQ 사용."""
    provider = _StubProvider(
        {
            "123330.KS": ("123330.KS,0P0000TSEP,27050", "MUTUALFUND"),
            "123330.KQ": ("Genic", "EQUITY"),
        }
    )
    resolver = TickerNameResolver(cache=cache, provider=provider)

    assert await resolver.resolve("123330") == "Genic"
    assert provider.calls == ["123330.KS", "123330.KQ"]


@pytest.mark.asyncio
async def test_resolve_accepts_etf_quote_type(cache):
    provider = _StubProvider({"487240.KS": ("KODEX AI Electric Power Core Fa", "ETF")})
    resolver = TickerNameResolver(cache=cache, provider=provider)

    assert await resolver.resolve("487240") == "KODEX AI Electric Power Core Fa"


@pytest.mark.asyncio
async def test_resolve_returns_none_on_provider_error(cache):
    provider = _StubProvider({}, raise_symbols={"XYZ"})
    resolver = TickerNameResolver(cache=cache, provider=provider)

    assert await resolver.resolve("XYZ") is None


@pytest.mark.asyncio
async def test_resolve_returns_none_when_name_missing(cache):
    provider = _StubProvider({})
    resolver = TickerNameResolver(cache=cache, provider=provider)

    assert await resolver.resolve("XYZ") is None

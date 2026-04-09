from src.tools.screener.models import UniverseStock
from src.providers.naver import NaverProvider
from src.providers.kis import KISProvider
from src.providers.yfinance_provider import YFinanceProvider


class UniverseBuilder:
    """Build universe of stocks from multiple sources."""

    def __init__(
        self,
        naver_provider: NaverProvider,
        kis_provider: KISProvider | None,
        yf_provider: YFinanceProvider,
    ):
        self.naver = naver_provider
        self.kis = kis_provider
        self.yf = yf_provider

    async def build(self, market: str = "all") -> list[UniverseStock]:
        """Build universe for given market."""
        stocks: dict[str, UniverseStock] = {}

        if market in ("kr", "all"):
            await self._build_kr(stocks)

        if market in ("us", "all"):
            await self._build_us(stocks)

        return list(stocks.values())

    async def _build_kr(self, stocks: dict[str, UniverseStock]) -> None:
        """Build Korean market universe."""
        # 1. Themes
        try:
            themes = await self.naver.get_themes(top_n=10)
            for theme in themes:
                for s in theme.get("stocks", []):
                    code = s["code"]
                    self._merge(stocks, code, UniverseStock(
                        ticker=code,
                        name=s["name"],
                        market=s["market"],
                        sources=["theme"],
                        theme=theme["name"],
                        theme_change_rate=theme["change_rate"],
                    ))
        except Exception:
            pass

        # 2. Volume ranking
        try:
            volume_stocks = await self.naver.get_volume_ranking(top_n=30)
            for s in volume_stocks:
                self._merge(stocks, s["code"], UniverseStock(
                    ticker=s["code"],
                    name=s["name"],
                    market=s["market"],
                    sources=["volume_rank"],
                    price=s.get("price"),
                    change_pct=s.get("change_pct"),
                ))
        except Exception:
            pass

        # 3. Rise ranking
        try:
            rise_stocks = await self.naver.get_rise_ranking(top_n=30)
            for s in rise_stocks:
                self._merge(stocks, s["code"], UniverseStock(
                    ticker=s["code"],
                    name=s["name"],
                    market=s["market"],
                    sources=["rise_rank"],
                    price=s.get("price"),
                    change_pct=s.get("change_pct"),
                ))
        except Exception:
            pass

        # 4. KIS investor ranking
        if self.kis:
            try:
                for inv_type in ["foreign", "institution"]:
                    ranking = await self.kis.get_investor_ranking(investor_type=inv_type, top_n=30)
                    for s in ranking:
                        self._merge(stocks, s["ticker"], UniverseStock(
                            ticker=s["ticker"],
                            name=s["name"],
                            market="KOSPI",
                            sources=["kis_rank"],
                        ))
            except Exception:
                pass

    async def _build_us(self, stocks: dict[str, UniverseStock]) -> None:
        """Build US market universe."""
        if not self.kis:
            return

        for exchange in ["NAS", "NYS"]:
            # Rise ranking
            try:
                rise = await self.kis.get_us_ranking_updown(exchange=exchange, direction="up", top_n=30)
                for s in rise:
                    self._merge(stocks, s["ticker"], UniverseStock(
                        ticker=s["ticker"],
                        name=s["name"],
                        market=exchange,
                        sources=["rise_rank"],
                        price=s.get("price"),
                        change_pct=s.get("change_pct"),
                    ))
            except Exception:
                pass

            # Volume ranking
            try:
                volume = await self.kis.get_us_ranking_volume(exchange=exchange, top_n=30)
                for s in volume:
                    self._merge(stocks, s["ticker"], UniverseStock(
                        ticker=s["ticker"],
                        name=s["name"],
                        market=exchange,
                        sources=["volume_rank"],
                        price=s.get("price"),
                    ))
            except Exception:
                pass

    def _merge(self, stocks: dict[str, UniverseStock], key: str, new: UniverseStock) -> None:
        """Merge stock into universe, accumulating sources."""
        if key in stocks:
            existing = stocks[key]
            for source in new.sources:
                if source not in existing.sources:
                    existing.sources.append(source)
            if new.theme and not existing.theme:
                existing.theme = new.theme
                existing.theme_change_rate = new.theme_change_rate
            if new.price and not existing.price:
                existing.price = new.price
                existing.change_pct = new.change_pct
        else:
            stocks[key] = new

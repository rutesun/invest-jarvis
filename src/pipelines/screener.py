from datetime import datetime
from pathlib import Path
from typing import Any

from src.tools.screener.universe import UniverseBuilder
from src.tools.screener.evidence import EvidenceCollector
from src.tools.screener.models import ScreenerEvidence
from src.tools.news import NewsTool


class ScreenerPipeline:
    """Market screener pipeline: universe → score → themes → news."""

    def __init__(
        self,
        universe_builder: UniverseBuilder,
        evidence_collector: EvidenceCollector,
        news_tool: NewsTool,
    ):
        self.universe_builder = universe_builder
        self.evidence_collector = evidence_collector
        self.news_tool = news_tool

    async def run(self, market: str = "all") -> dict[str, Any]:
        """Run screener pipeline.

        Args:
            market: Market to screen ("all", "kr", "us")

        Returns:
            Dictionary with market results including leaders, themes, and news
        """
        # 1. Get Naver themes (KR only)
        naver_themes = []
        if market in ("all", "kr"):
            try:
                naver = self.universe_builder.naver
                naver_themes = await naver.get_themes(top_n=20)
            except Exception:
                pass

        # 2. Universe
        universe = await self.universe_builder.build(market)

        # 3. Evidence + Score
        scored = await self.evidence_collector.collect_and_score(universe)

        # 4. Theme aggregation
        theme_ranking = self._aggregate_themes(scored)

        # 5. News for top 10
        top_stocks = scored[:10]
        news = await self._fetch_news_for_top(top_stocks)

        return {
            "market": market,
            "timestamp": datetime.now(),
            "leaders": scored[:50],
            "naver_themes": naver_themes,
            "themes": theme_ranking[:10],
            "news": news,
            "total_universe_size": len(universe),
        }

    def _format_net(self, value: int) -> str:
        """Format net buy quantity with sign and unit.

        Args:
            value: Net buy quantity (positive for buy, negative for sell)

        Returns:
            Formatted string (e.g., "+1.2M", "-300K", "-")
        """
        if value == 0:
            return "-"

        abs_val = abs(value)
        sign = "+" if value > 0 else ""

        if abs_val >= 1_000_000:
            return f"{sign}{value / 1_000_000:.1f}M"
        elif abs_val >= 1_000:
            return f"{sign}{value // 1_000}K"
        else:
            return f"{sign}{value}"

    def _aggregate_themes(self, scored: list[ScreenerEvidence]) -> list[dict]:
        """Aggregate themes from scored stocks.
        
        Args:
            scored: List of ScreenerEvidence objects sorted by momentum
            
        Returns:
            List of theme dictionaries sorted by average momentum
        """
        themes: dict[str, dict] = {}
        for item in scored:
            theme = item.stock.theme
            if not theme:
                continue
            if theme not in themes:
                themes[theme] = {
                    "name": theme,
                    "change_rate": item.stock.theme_change_rate,
                    "stock_count": 0,
                    "top_stocks": [],
                    "momentum_sum": 0.0,
                }
            themes[theme]["stock_count"] += 1
            themes[theme]["momentum_sum"] += item.momentum_total
            if len(themes[theme]["top_stocks"]) < 3:
                themes[theme]["top_stocks"].append(item.stock.name)

        result = list(themes.values())
        for t in result:
            t["avg_momentum"] = t["momentum_sum"] / t["stock_count"] if t["stock_count"] > 0 else 0
        result.sort(key=lambda x: x["avg_momentum"], reverse=True)
        return result

    async def _fetch_news_for_top(self, top_stocks: list[ScreenerEvidence]) -> dict[str, list]:
        """Fetch news for top stocks.
        
        Args:
            top_stocks: List of top ScreenerEvidence objects
            
        Returns:
            Dictionary mapping stock names to news articles
        """
        news: dict[str, list] = {}
        for item in top_stocks:
            ticker = item.stock.ticker
            # For Korean stocks, yfinance needs .KS suffix
            yf_ticker = f"{ticker}.KS" if item.stock.market in ("KOSPI", "KOSDAQ") else ticker
            try:
                result = await self.news_tool.execute(yf_ticker, limit=3)
                if result.success and result.data:
                    news[item.stock.name] = [
                        {"title": a.title, "published": a.published}
                        for a in result.data
                    ]
            except Exception:
                pass
        return news

    def format_output(self, result: dict[str, Any]) -> str:
        """Format screener result as markdown.
        
        Args:
            result: Dictionary from run() containing leaders, themes, news
            
        Returns:
            Markdown formatted string
        """
        ts = result["timestamp"].strftime("%Y-%m-%d")
        lines = [
            f"# Market Screener ({ts})",
            "",
        ]

        # Naver Themes (raw from Naver API)
        naver_themes = result.get("naver_themes", [])
        if naver_themes:
            lines.append("## 상위 테마 (네이버)")
            lines.append("| # | 테마명 | 등락률 |")
            lines.append("|---|--------|--------|")
            for i, t in enumerate(naver_themes, 1):
                lines.append(f"| {i} | {t['name']} | {t['change_rate']:+.2f}% |")
            lines.append("")

        # Themes (aggregated from scored stocks)
        themes = result.get("themes", [])
        if themes:
            lines.append("## 주도 테마 TOP 10 (집계)")
            lines.append("| # | 테마 | 등락률 | 종목수 | 주요 종목 |")
            lines.append("|---|------|--------|--------|-----------|")
            for i, t in enumerate(themes, 1):
                stocks_str = ", ".join(t["top_stocks"])
                rate = t.get("change_rate") or 0
                lines.append(f"| {i} | {t['name']} | {rate:+.1f}% | {t['stock_count']} | {stocks_str} |")
            lines.append("")

        # Leaders - separate KR and US
        leaders = result.get("leaders", [])
        if leaders:
            # Separate KR and US stocks
            kr_leaders = [item for item in leaders if item.stock.market in ("KOSPI", "KOSDAQ")]
            us_leaders = [item for item in leaders if item.stock.market not in ("KOSPI", "KOSDAQ")]

            # Korean stocks
            if kr_leaders:
                lines.append("## 주도주 TOP 50 (한국)")
                lines.append("| # | 종목 | 시장 | 모멘텀 | 당일외인 | 당일기관 | 당일프로 | 10일외인 | 10일기관 | 10일프로 | 거래량 | 소스 |")
                lines.append("|---|------|------|--------|----------|----------|----------|----------|----------|----------|--------|------|")
                for item in kr_leaders:
                    s = item.stock
                    sources_str = ",".join(s.sources)
                    # Daily net buy (most recent day)
                    daily_f = self._format_net(item.daily_foreign)
                    daily_i = self._format_net(item.daily_institution)
                    daily_p = self._format_net(item.daily_program)
                    # 10-day aggregated: "7/10 (+15.3M)"
                    ten_f = f"{item.foreign_days_count}/10 ({self._format_net(item.foreign_net)})"
                    ten_i = f"{item.institution_days_count}/10 ({self._format_net(item.institution_net)})"
                    ten_p = f"{item.program_days_count}/10 ({self._format_net(item.program_net)})"
                    lines.append(
                        f"| {item.rank} | {s.name} | {s.market} | "
                        f"{item.momentum_total:.0f} | {daily_f} | {daily_i} | {daily_p} | "
                        f"{ten_f} | {ten_i} | {ten_p} | {item.vol_ratio:.1f}x | {sources_str} |"
                    )
                lines.append("")

            # US stocks
            if us_leaders:
                lines.append("## 주도주 TOP 50 (미국)")
                lines.append("| # | 종목 | 시장 | 모멘텀 | 거래량 | 소스 |")
                lines.append("|---|------|------|--------|--------|------|")
                for item in us_leaders:
                    s = item.stock
                    sources_str = ",".join(s.sources)
                    lines.append(
                        f"| {item.rank} | {s.name} | {s.market} | "
                        f"{item.momentum_total:.0f} | {item.vol_ratio:.1f}x | {sources_str} |"
                    )
                lines.append("")

        # News
        news = result.get("news", {})
        if news:
            lines.append("## 상위 종목 뉴스")
            for name, articles in news.items():
                lines.append(f"### {name}")
                for a in articles:
                    lines.append(f"- {a['title']} ({a['published']})")
                lines.append("")

        return "\n".join(lines)

    def save_report(self, result: dict[str, Any]) -> Path:
        """Save report to markdown file.
        
        Args:
            result: Dictionary from run() containing screener results
            
        Returns:
            Path to saved report file
        """
        timestamp = result["timestamp"]
        dir_path = Path("reports") / timestamp.strftime("%Y-%m")
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"screen-{timestamp.strftime('%Y-%m-%d')}.md"
        file_path.write_text(self.format_output(result))
        return file_path

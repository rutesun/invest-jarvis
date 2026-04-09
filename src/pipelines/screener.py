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
        # 1. Universe
        universe = await self.universe_builder.build(market)

        # 2. Evidence + Score
        scored = await self.evidence_collector.collect_and_score(universe)

        # 3. Theme aggregation
        theme_ranking = self._aggregate_themes(scored)

        # 4. News for top 10
        top_stocks = scored[:10]
        news = await self._fetch_news_for_top(top_stocks)

        return {
            "market": market,
            "timestamp": datetime.now(),
            "leaders": scored[:20],
            "themes": theme_ranking[:10],
            "news": news,
            "total_universe_size": len(universe),
        }

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

        # Themes
        themes = result.get("themes", [])
        if themes:
            lines.append("## 주도 테마 TOP 10")
            lines.append("| # | 테마 | 등락률 | 종목수 | 주요 종목 |")
            lines.append("|---|------|--------|--------|-----------|")
            for i, t in enumerate(themes, 1):
                stocks_str = ", ".join(t["top_stocks"])
                rate = t.get("change_rate") or 0
                lines.append(f"| {i} | {t['name']} | {rate:+.1f}% | {t['stock_count']} | {stocks_str} |")
            lines.append("")

        # Leaders
        leaders = result.get("leaders", [])
        if leaders:
            lines.append("## 주도주 TOP 20")
            lines.append("| # | 종목 | 시장 | 모멘텀 | 수급 | 거래량 | 소스 |")
            lines.append("|---|------|------|--------|------|--------|------|")
            for item in leaders:
                s = item.stock
                sources_str = ",".join(s.sources)
                acc = f"{item.accumulation_score:.0f}" if item.accumulation_score > 0 else "-"
                lines.append(
                    f"| {item.rank} | {s.name} | {s.market} | "
                    f"{item.momentum_total:.0f} | {acc} | {item.vol_ratio:.1f}x | {sources_str} |"
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

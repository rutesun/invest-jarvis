from datetime import datetime
from pathlib import Path
from typing import Any

from src.tools.news import NewsTool
from src.tools.screener.evidence import EvidenceCollector
from src.tools.screener.models import ScreenerEvidence
from src.tools.screener.universe import UniverseBuilder


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

    async def run(self, market: str = "all", turnaround_only: bool = False) -> dict[str, Any]:
        """Run screener pipeline.

        Args:
            market: Market to screen ("all", "kr", "us")
            turnaround_only: True면 턴어라운드 후보 발굴에 집중(리더 표 생략)

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

        # Debug: log universe stats
        kr_count = sum(1 for s in universe if s.market in ("KOSPI", "KOSDAQ"))
        us_count = sum(1 for s in universe if s.market not in ("KOSPI", "KOSDAQ"))
        import logging

        logging.info(f"Universe: total={len(universe)}, KR={kr_count}, US={us_count}")

        # 3. Evidence + Score
        scored = await self.evidence_collector.collect_and_score(universe)

        # 4. Theme aggregation
        theme_ranking = self._aggregate_themes(scored)

        # 5. Separate KR and US stocks
        kr_scored = [item for item in scored if item.stock.market in ("KOSPI", "KOSDAQ")]
        us_scored = [item for item in scored if item.stock.market not in ("KOSPI", "KOSDAQ")]

        # 5b. 턴어라운드 발굴 후보 (마커 수 → 총점 순)
        turnaround_candidates = sorted(
            (item for item in scored if item.turnaround_candidate),
            key=lambda x: (x.turnaround_score, x.total_score),
            reverse=True,
        )[:30]

        # 6. News for top 10 (KR only)
        top_stocks = kr_scored[:10]
        news = await self._fetch_news_for_top(top_stocks)

        return {
            "market": market,
            "timestamp": datetime.now(),
            "kr_leaders": kr_scored[:50],
            "us_leaders": us_scored[:50],
            "turnaround_candidates": turnaround_candidates,
            "turnaround_only": turnaround_only,
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
                        {"title": a.title, "published": a.published} for a in result.data
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
                lines.append(
                    f"| {i} | {t['name']} | {rate:+.1f}% | {t['stock_count']} | {stocks_str} |"
                )
            lines.append("")

        # 턴어라운드 발굴 후보 (예측 알파 아님 — 기사·시장 판단은 사용자 몫)
        candidates = result.get("turnaround_candidates", [])
        if candidates:
            lines.append("## 턴어라운드 발굴 후보")
            lines.append("> 예측 신호 아님. 후보 표면화용 — 기사·시장 상황은 직접 판단하세요.")
            lines.append("| # | 종목 | 시장 | 스코어 | 마커 | check확인 |")
            lines.append("|---|------|------|--------|------|-----------|")
            for i, item in enumerate(candidates, 1):
                s = item.stock
                markers = " · ".join(item.turnaround_markers)
                confirmed = "확인" if item.turnaround_confirmed else "미확인"
                lines.append(
                    f"| {i} | {s.name} | {s.market} | {item.turnaround_score}/4 | "
                    f"{markers} | {confirmed} |"
                )
            lines.append("")

        # turnaround_only 모드면 리더 표는 생략(발굴에 집중)
        if result.get("turnaround_only"):
            return "\n".join(lines)

        # Leaders - separate KR and US
        kr_leaders = result.get("kr_leaders", [])
        us_leaders = result.get("us_leaders", [])

        # Korean stocks
        if kr_leaders:
            lines.append("## 주도주 TOP 50 (한국)")
            lines.append(
                "| # | 종목 | 시장 | 모멘텀 | 당일외인 | 당일기관 | 당일프로 | 10일외인 | 10일기관 | 10일프로 | 거래량 | 소스 |"
            )
            lines.append(
                "|---|------|------|--------|----------|----------|----------|----------|----------|----------|--------|------|"
            )
            for i, item in enumerate(kr_leaders, 1):
                s = item.stock
                sources_str = ",".join(s.sources)
                # Daily net buy (most recent day)
                daily_f = self._format_net(item.daily_foreign)
                daily_i = self._format_net(item.daily_institution)
                daily_p = self._format_net(item.daily_program)
                # 10-day aggregated: "7/10 (+15.3M)"
                ten_f = f"{item.foreign_days_count}/10 ({self._format_net(item.foreign_net)})"
                ten_i = (
                    f"{item.institution_days_count}/10 ({self._format_net(item.institution_net)})"
                )
                ten_p = f"{item.program_days_count}/10 ({self._format_net(item.program_net)})"
                lines.append(
                    f"| {i} | {s.name} | {s.market} | "
                    f"{item.momentum_total:.0f} | {daily_f} | {daily_i} | {daily_p} | "
                    f"{ten_f} | {ten_i} | {ten_p} | {item.vol_ratio:.1f}x | {sources_str} |"
                )
            lines.append("")

        # US stocks
        if us_leaders:
            lines.append("## 주도주 TOP 50 (미국)")
            lines.append("| # | 티커 | 종목명 | 시장 | 모멘텀 | 거래량 | 소스 |")
            lines.append("|---|------|--------|------|--------|--------|------|")
            for i, item in enumerate(us_leaders, 1):
                s = item.stock
                sources_str = ",".join(s.sources)
                lines.append(
                    f"| {i} | {s.ticker} | {s.name} | {s.market} | "
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

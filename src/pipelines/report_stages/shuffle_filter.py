# src/pipelines/report_stages/shuffle_filter.py
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel

from src.llm.daily_report_models import (
    IssueExtract,
    ShuffleResult,
    StockDetail,
    Theme,
)
from src.llm.daily_report_analyzer import merge_themes_llm

logger = logging.getLogger(__name__)


def _detect_market(ticker: str) -> str:
    """한국 티커 감지 (6자리 숫자 또는 A+6자리 숫자)"""
    if ticker.isdigit() and len(ticker) == 6:
        return "KR"
    if len(ticker) == 7 and ticker.startswith("A") and ticker[1:].isdigit():
        return "KR"
    return "US"


@dataclass
class ShuffleStage:
    ticker_resolver: object
    merge_llm: BaseChatModel
    known_themes: list[str]
    top_n: int = 7

    async def run(
        self,
        issues: list[IssueExtract],
        kr_flow: list[dict],
        momentum: list[dict],
    ) -> ShuffleResult:
        raw_theme_names = list({issue.theme for issue in issues})
        new_themes = [t for t in raw_theme_names if t not in self.known_themes]
        theme_mapping: dict[str, str] = {}
        if new_themes:
            known_str = "\n".join(f"- {t}" for t in self.known_themes)
            new_str = "\n".join(f"- {t}" for t in new_themes)
            theme_mapping = await merge_themes_llm(self.merge_llm, known_str, new_str)

        all_raw_tickers: set[str] = set()
        for issue in issues:
            all_raw_tickers.update(issue.tickers)

        ticker_map: dict[str, str] = {}
        for raw in all_raw_tickers:
            try:
                resolution = await self.ticker_resolver.resolve(raw)
                ticker_map[raw] = resolution.resolved_ticker
            except Exception as e:
                logger.warning("티커 변환 실패 %s: %s", raw, e)
                ticker_map[raw] = raw

        theme_issues: dict[str, list[IssueExtract]] = defaultdict(list)
        for issue in issues:
            normalized = theme_mapping.get(issue.theme, issue.theme)
            theme_issues[normalized].append(issue)

        stock_details: dict[str, dict] = defaultdict(lambda: {
            "mention_count": 0, "summaries": [], "source": "telegram",
        })
        for theme_name, theme_issue_list in theme_issues.items():
            for issue in theme_issue_list:
                for raw_ticker in issue.tickers:
                    resolved = ticker_map.get(raw_ticker, raw_ticker)
                    stock_details[resolved]["mention_count"] += 1
                    stock_details[resolved]["summaries"].append(issue.summary)

        themes: list[Theme] = []
        for theme_name, theme_issue_list in theme_issues.items():
            sentiment_counts = Counter(i.sentiment for i in theme_issue_list)
            dominant_sentiment = sentiment_counts.most_common(1)[0][0]

            theme_tickers: dict[str, int] = Counter()
            for issue in theme_issue_list:
                for raw_ticker in issue.tickers:
                    resolved = ticker_map.get(raw_ticker, raw_ticker)
                    theme_tickers[resolved] += 1

            sorted_tickers = [t for t, _ in theme_tickers.most_common()]
            summaries = [i.summary for i in theme_issue_list]
            narrative = summaries[0] if summaries else ""

            themes.append(Theme(
                name=theme_name,
                narrative=narrative,
                sentiment=dominant_sentiment,
                mention_count=len(theme_issue_list),
                stocks=sorted_tickers,
            ))

        kr_flow_map = {item["ticker"]: item for item in kr_flow}
        momentum_map = {item["ticker"]: item for item in momentum}

        final_details: dict[str, StockDetail] = {}
        all_tickers = set(stock_details.keys())

        for ticker in all_tickers:
            info = stock_details[ticker]
            market = _detect_market(ticker)
            flow_score = None
            volume_score = None
            source = "telegram"

            if ticker in kr_flow_map:
                flow_data = kr_flow_map[ticker]
                flow_score = float(flow_data.get("foreign_net", 0)) + float(flow_data.get("inst_net", 0))
                source = "both"

            if ticker in momentum_map:
                mom_data = momentum_map[ticker]
                volume_score = float(mom_data.get("change_pct", 0)) + float(mom_data.get("volume_ratio", 0))
                source = "both"

            final_details[ticker] = StockDetail(
                ticker=ticker,
                market=market,
                mention_count=info["mention_count"],
                flow_score=flow_score,
                volume_score=volume_score,
                source=source,
                summaries=info["summaries"],
            )

        market_only_tickers: list[str] = []
        for ticker in set(kr_flow_map.keys()) | set(momentum_map.keys()):
            if ticker not in all_tickers:
                market = _detect_market(ticker)
                flow_data = kr_flow_map.get(ticker, {})
                mom_data = momentum_map.get(ticker, {})
                flow_score = None
                volume_score = None
                if flow_data:
                    flow_score = float(flow_data.get("foreign_net", 0)) + float(flow_data.get("inst_net", 0))
                if mom_data:
                    volume_score = float(mom_data.get("change_pct", 0)) + float(mom_data.get("volume_ratio", 0))

                final_details[ticker] = StockDetail(
                    ticker=ticker, market=market, mention_count=0,
                    flow_score=flow_score, volume_score=volume_score,
                    source="market_data", summaries=[],
                )
                market_only_tickers.append(ticker)

        if market_only_tickers:
            themes.append(Theme(
                name="기타 수급 특징주",
                narrative="텔레그램 미언급이나 수급/거래량 이상 감지",
                sentiment="neutral",
                mention_count=0,
                stocks=market_only_tickers,
            ))

        themes.sort(key=lambda t: t.mention_count, reverse=True)
        themes = themes[: self.top_n]

        return ShuffleResult(themes=themes, stock_details=final_details)

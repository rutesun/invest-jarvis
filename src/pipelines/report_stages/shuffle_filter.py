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
        logger.info("[Stage 3: Shuffle] 시작 - %d개 이슈, %d개 KR 수급, %d개 US 모멘텀",
                    len(issues), len(kr_flow), len(momentum))

        raw_theme_names = list({issue.theme for issue in issues})
        logger.info("[Shuffle] Step 1: 테마 병합 - 기존 %d개, 원본 %d개",
                    len(self.known_themes), len(raw_theme_names))

        new_themes = [t for t in raw_theme_names if t not in self.known_themes]
        theme_mapping: dict[str, str] = {}
        if new_themes:
            logger.info("[Shuffle] 새 테마 %d개 발견, LLM 병합 시작", len(new_themes))
            known_str = "\n".join(f"- {t}" for t in self.known_themes)
            new_str = "\n".join(f"- {t}" for t in new_themes)
            theme_mapping = await merge_themes_llm(self.merge_llm, known_str, new_str)
            logger.debug("[Shuffle] 테마 매핑: %s", theme_mapping)
        else:
            logger.info("[Shuffle] 새 테마 없음, 병합 스킵")

        logger.info("[Shuffle] Step 2: 티커 정규화 시작")
        all_raw_tickers: set[str] = set()
        for issue in issues:
            all_raw_tickers.update(issue.tickers)

        logger.info("[Shuffle] %d개 고유 티커 발견, 정규화 진행", len(all_raw_tickers))
        ticker_map: dict[str, str] = {}
        for raw in all_raw_tickers:
            try:
                resolution = await self.ticker_resolver.resolve(raw)
                ticker_map[raw] = resolution.resolved_ticker
                logger.debug("[Shuffle] 티커 변환: %s → %s", raw, resolution.resolved_ticker)
            except Exception as e:
                logger.warning("[Shuffle] 티커 변환 실패 %s: %s", raw, e)
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

        logger.info("[Shuffle] Step 3: 시장 데이터 보강 완료 - %d개 종목 상세 정보",
                    len(final_details))

        themes.sort(key=lambda t: t.mention_count, reverse=True)
        logger.info("[Shuffle] Step 4: 상위 %d개 테마 선별 (전체 %d개)",
                    min(self.top_n, len(themes)), len(themes))
        themes = themes[: self.top_n]

        logger.info("[Stage 3: Shuffle] 완료 - %d개 테마, %d개 종목",
                    len(themes), len(final_details))
        for i, theme in enumerate(themes[:3], 1):
            logger.debug("[Shuffle] Top %d: %s (%d회 언급, %d개 종목)",
                        i, theme.name, theme.mention_count, len(theme.stocks))

        return ShuffleResult(themes=themes, stock_details=final_details)

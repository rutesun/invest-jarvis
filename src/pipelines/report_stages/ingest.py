# src/pipelines/report_stages/ingest.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from src.llm.daily_report_models import IngestResult
from src.tools.macro import MacroTool
from src.tools.news import NewsTool

logger = logging.getLogger(__name__)

MARKET_NEWS_QUERIES = ["SPY", "QQQ", "KOSPI", "나스닥", "S&P 500"]


@dataclass
class IngestStage:
    macro_tool: MacroTool
    news_tool: NewsTool
    kis_provider: Any
    telegram_loader: Any

    async def run(self) -> IngestResult:
        telegram_task = asyncio.to_thread(self.telegram_loader.load)
        macro_task = self._fetch_macro()
        news_task = self._fetch_market_news()
        kr_flow_task = self._fetch_kr_flow()
        momentum_task = self._fetch_momentum()

        results = await asyncio.gather(
            telegram_task, macro_task, news_task, kr_flow_task, momentum_task,
            return_exceptions=True,
        )

        telegram_messages = results[0] if not isinstance(results[0], Exception) else []
        macro_snapshot = results[1] if not isinstance(results[1], Exception) else {}
        market_news = results[2] if not isinstance(results[2], Exception) else []
        kr_flow = results[3] if not isinstance(results[3], Exception) else []
        momentum = results[4] if not isinstance(results[4], Exception) else []

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning("수집 소스 %d 실패: %s", i, r)

        return IngestResult(
            telegram_messages=telegram_messages,
            macro_snapshot=macro_snapshot,
            market_news=market_news,
            kr_flow=kr_flow,
            momentum=momentum,
        )

    async def _fetch_macro(self) -> dict:
        result = await self.macro_tool.execute()
        if not result.success:
            return {}
        snap = result.data
        return {
            "vix": snap.vix, "vix_change": snap.vix_change,
            "fear_greed": snap.fear_greed, "fear_greed_label": snap.fear_greed_label,
            "wti": snap.wti, "wti_change": snap.wti_change,
            "us_10y": snap.us_10y, "us_2y": snap.us_2y,
            "yield_spread": snap.yield_spread,
            "dxy": snap.dxy, "dxy_change": snap.dxy_change,
        }

    async def _fetch_market_news(self) -> list[dict]:
        all_news: list[dict] = []
        for query in MARKET_NEWS_QUERIES:
            try:
                result = await self.news_tool.execute(ticker=query, limit=5)
                if result.success and result.data:
                    for article in result.data:
                        all_news.append({
                            "title": article.title,
                            "summary": article.summary,
                            "source": query,
                            "url": article.url,
                        })
            except Exception as e:
                logger.warning("%s 뉴스 수집 실패: %s", query, e)
        return all_news

    async def _fetch_kr_flow(self) -> list[dict]:
        try:
            foreign = await self.kis_provider.get_investor_ranking(
                investor_type="foreign", top_n=30,
            )
            institution = await self.kis_provider.get_investor_ranking(
                investor_type="institution", top_n=30,
            )
            merged: dict[str, dict] = {}
            for item in foreign:
                merged[item["ticker"]] = {
                    "ticker": item["ticker"],
                    "name": item["name"],
                    "foreign_net": item.get("net_buy_amount", 0),
                    "inst_net": 0,
                }
            for item in institution:
                key = item["ticker"]
                if key in merged:
                    merged[key]["inst_net"] = item.get("net_buy_amount", 0)
                else:
                    merged[key] = {
                        "ticker": key,
                        "name": item["name"],
                        "foreign_net": 0,
                        "inst_net": item.get("net_buy_amount", 0),
                    }
            return list(merged.values())
        except Exception as e:
            logger.warning("KR 수급 수집 실패: %s", e)
            return []

    async def _fetch_momentum(self) -> list[dict]:
        try:
            results: list[dict] = []
            seen: set[str] = set()
            for exchange in ("NAS", "NYS"):
                updown = await self.kis_provider.get_us_ranking_updown(
                    exchange=exchange, direction="up", top_n=30,
                )
                for item in updown:
                    if item["ticker"] not in seen:
                        results.append({
                            "ticker": item["ticker"],
                            "name": item.get("name", ""),
                            "price": item.get("price", 0),
                            "change_pct": item.get("change_pct", 0),
                            "volume_ratio": 0,
                            "exchange": item.get("exchange", exchange),
                        })
                        seen.add(item["ticker"])
                volume = await self.kis_provider.get_us_ranking_volume(
                    exchange=exchange, top_n=30,
                )
                for item in volume:
                    if item["ticker"] not in seen:
                        results.append({
                            "ticker": item["ticker"],
                            "name": item.get("name", ""),
                            "price": item.get("price", 0),
                            "change_pct": 0,
                            "volume_ratio": 0,
                            "exchange": item.get("exchange", exchange),
                        })
                        seen.add(item["ticker"])
            return results
        except Exception as e:
            logger.warning("US 모멘텀 수집 실패: %s", e)
            return []

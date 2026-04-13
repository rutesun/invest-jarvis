# src/pipelines/report_stages/catalyst.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool

from src.llm.daily_report_models import ShuffleResult, StockCatalyst
from src.llm.prompts.daily_report import DailyReportPrompts

logger = logging.getLogger(__name__)


@dataclass
class CatalystStage:
    llm: BaseChatModel
    news_tool: object
    ticker_resolver: object
    stocks_per_theme: int = 3

    async def run(self, shuffle_result: ShuffleResult) -> list[StockCatalyst]:
        logger.info("[Stage 4: Catalyst] 시작 - %d개 테마 처리", len(shuffle_result.themes))

        themes_for_prompt = []
        total_stocks = 0
        for theme in shuffle_result.themes:
            top_stocks = theme.stocks[: self.stocks_per_theme]
            total_stocks += len(top_stocks)
            stock_infos = []
            for ticker in top_stocks:
                detail = shuffle_result.stock_details.get(ticker)
                stock_infos.append({
                    "ticker": ticker,
                    "summaries": detail.summaries if detail else [],
                    "flow_score": detail.flow_score if detail else None,
                    "volume_score": detail.volume_score if detail else None,
                })
            themes_for_prompt.append({
                "name": theme.name,
                "narrative": theme.narrative,
                "stocks": stock_infos,
            })
            logger.debug("[Catalyst] 테마 '%s': 상위 %d개 종목 선별",
                        theme.name, len(top_stocks))

        logger.info("[Catalyst] LLM tool calling 시작 - %d개 종목 뉴스 검색", total_stocks)
        themes_json = json.dumps(themes_for_prompt, ensure_ascii=False, indent=2)
        catalysts = await self._run_agent(themes_json, shuffle_result.stock_details)

        logger.info("[Stage 4: Catalyst] 완료 - %d개 종목 촉매 분석", len(catalysts))
        return catalysts

    async def _run_agent(self, themes_json: str, stock_details: dict) -> list[StockCatalyst]:
        news_tool_ref = self.news_tool
        ticker_resolver_ref = self.ticker_resolver

        @tool
        async def search_news(query: str) -> str:
            """주식 티커 또는 키워드로 최근 뉴스를 검색합니다."""
            result = await news_tool_ref.execute(ticker=query, limit=5)
            if not result.success or not result.data:
                return f"{query}에 대한 뉴스가 없습니다"
            return "\n".join(
                f"- {a.title}: {a.summary}" for a in result.data[:5]
            )

        @tool
        async def resolve_ticker(name: str) -> str:
            """회사명을 주식 티커 심볼로 변환합니다."""
            result = await ticker_resolver_ref.resolve(name)
            return f"{name} → {result.resolved_ticker}"

        prompt = DailyReportPrompts.catalyst(themes_json)

        llm_with_tools = self.llm.bind_tools([search_news, resolve_ticker])
        structured = llm_with_tools.with_structured_output(list[StockCatalyst])

        result = await structured.ainvoke(
            prompt,
            config={
                "run_name": "catalyst_analysis",
                "metadata": {"stage": "catalyst"},
            },
        )
        return result

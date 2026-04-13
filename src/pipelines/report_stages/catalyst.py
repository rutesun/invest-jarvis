# src/pipelines/report_stages/catalyst.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List
from pydantic import BaseModel

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from src.llm.daily_report_models import ShuffleResult, StockCatalyst
from src.llm.prompts.daily_report import DailyReportPrompts

logger = logging.getLogger(__name__)


class CatalystListResult(BaseModel):
    """Wrapper for list of catalysts to work with structured output."""
    catalysts: List[StockCatalyst]


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

        tools = [search_news, resolve_ticker]

        # 1. 툴을 실행할 에이전트 프롬프트 구성
        prompt_text = DailyReportPrompts.catalyst(themes_json)
        agent_prompt = ChatPromptTemplate.from_messages([
            ("system", "당신은 증권 리포트를 작성하기 위해 데이터를 조사하는 전문 연구원입니다. 도구를 적절히 사용하여 각 테마 및 주도주에 필요한 최신 뉴스 등 추가 정보를 수집하고 분석하세요."),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        # 2. 에이전트 실행기(AgentExecutor) 구성
        agent = create_tool_calling_agent(self.llm, tools, agent_prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        # 3. 에이전트 루프 실행하여 외부 조사 후 결과 텍스트 획득
        agent_result = await agent_executor.ainvoke(
            {"input": prompt_text},
            config={
                "run_name": "catalyst_analysis_agent",
                "metadata": {"stage": "catalyst"},
            },
        )

        # 4. 조사된 내용 기반으로 최종 Pydantic 데이터 구조 파싱
        structured_parser = self.llm.with_structured_output(CatalystListResult)
        parse_prompt = ChatPromptTemplate.from_messages([
            ("system", "다음은 시장 이슈 관련 조사 데이터입니다. 이 내용을 바탕으로 요구하는 데이터 구조(CatalystListResult) 모델에 맞게 정보를 정확하게 추출하여 JSON 형식으로 응답하세요."),
            ("human", "{text}")
        ])
        
        chain = parse_prompt | structured_parser
        
        parsed_result = await chain.ainvoke(
            {"text": agent_result["output"]},
            config={
                 "run_name": "catalyst_analysis_parse",
                 "metadata": {"stage": "catalyst"},
            }
        )
        
        return parsed_result.catalysts if parsed_result else []

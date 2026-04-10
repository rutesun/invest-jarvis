import json
import logging
import re
from ddgs import DDGS
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from src.providers.ticker_models import TickerNotFoundError

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a financial ticker resolution assistant. Find the exact stock exchange ticker symbol for a given company name or query.

Use the duckduckgo_search tool to look up the company's stock ticker.

Rules:
- Korean KOSPI stocks use .KS suffix (e.g., 005930.KS for Samsung Electronics)
- Korean KOSDAQ stocks use .KQ suffix (e.g., 035720.KQ for Kakao)
- US stocks use plain symbol without suffix (e.g., AAPL, RKLB)
- Return ONLY valid exchange-listed tickers

For Korean companies:
- Search using Korean company name + "종목코드" or "주식 코드"
- The 6-digit code is the stock code (e.g., 009150 for Samsung Electro-Mechanics)
- Determine KOSPI (.KS) vs KOSDAQ (.KQ) from search results (look for 코스피/코스닥 indicators)
- If market is unclear, prefer .KS for large-cap companies and .KQ for smaller ones

After finding the ticker, respond with ONLY this JSON (no other text):
{"ticker": "SYMBOL", "display_name": "Full Company Name"}"""


def _has_korean(text: str) -> bool:
    return bool(re.search(r'[\uAC00-\uD7A3]', text))


@tool
def duckduckgo_search(query: str) -> str:
    """Search DuckDuckGo for stock ticker information. Returns top 5 results."""
    ddgs = DDGS()
    region = "kr-kr" if _has_korean(query) else None
    logger.debug("DuckDuckGo search: %r (region=%s)", query, region)
    results = ddgs.text(query, region=region, max_results=5)
    if not results:
        return "No results found."
    output = "\n".join(f"- {r['title']}: {r['body']}" for r in results)
    logger.debug("Search results:\n%s", output[:500])
    return output


class LLMTickerAgent:
    """GPT-4o + DuckDuckGo Tool Calling Loop으로 회사명을 티커로 해결한다."""

    MAX_ITERATIONS = 3

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for LLMTickerAgent")
        self.llm = ChatOpenAI(model=model, api_key=api_key, temperature=0)

    async def resolve(self, query: str) -> tuple[str, str]:
        """
        회사명/쿼리를 (ticker, display_name) 튜플로 해결한다.
        해결 실패 시 TickerNotFoundError 발생.
        """
        logger.debug("LLMTickerAgent resolving: %s", query)
        llm_with_tools = self.llm.bind_tools([duckduckgo_search])

        if _has_korean(query):
            human_content = f"Find the Korean stock ticker (종목코드) for: {query}\nSearch for '{query} 종목코드' or '{query} 주식 코드' to find the 6-digit code and whether it's on KOSPI (코스피) or KOSDAQ (코스닥)."
        else:
            human_content = f"Find the stock ticker for: {query}"

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]

        for iteration in range(self.MAX_ITERATIONS):
            logger.debug("Iteration %d/%d", iteration + 1, self.MAX_ITERATIONS)
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            if not response.tool_calls:
                logger.debug("LLM response (no tool calls): %s", response.content)
                try:
                    result = json.loads(response.content)
                    ticker = result.get("ticker")
                    display_name = result.get("display_name")
                    if not ticker or not isinstance(ticker, str) or ticker.lower() == "null":
                        raise TickerNotFoundError(f"LLM returned null ticker for: {query}")
                    logger.debug("Resolved %s → %s (%s)", query, ticker, display_name)
                    return ticker, display_name
                except (json.JSONDecodeError, KeyError):
                    raise TickerNotFoundError(f"Could not resolve: {query}")

            for tool_call in response.tool_calls:
                logger.debug("Tool call: %s(%s)", tool_call["name"], tool_call["args"])
                tool_result = duckduckgo_search.invoke({"query": tool_call["args"]["query"]})
                messages.append(ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_call["id"],
                ))

        raise TickerNotFoundError(f"Could not resolve after {self.MAX_ITERATIONS} iterations: {query}")

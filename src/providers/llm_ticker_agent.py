import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from duckduckgo_search import DDGS
from src.providers.ticker_models import TickerNotFoundError

_SYSTEM_PROMPT = """You are a financial ticker resolution assistant. Find the exact stock exchange ticker symbol for a given company name or query.

Use the duckduckgo_search tool to look up the company's stock ticker.

Rules:
- Korean KOSPI stocks use .KS suffix (e.g., 005930.KS for Samsung Electronics)
- Korean KOSDAQ stocks use .KQ suffix (e.g., 035720.KQ for Kakao)
- US stocks use plain symbol without suffix (e.g., AAPL, RKLB)
- Return ONLY valid exchange-listed tickers

After finding the ticker, respond with ONLY this JSON (no other text):
{"ticker": "SYMBOL", "display_name": "Full Company Name"}"""


@tool
def duckduckgo_search(query: str) -> str:
    """Search DuckDuckGo for stock ticker information. Returns top 5 results."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    if not results:
        return "No results found."
    return "\n".join(f"- {r['title']}: {r['body']}" for r in results)


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
        llm_with_tools = self.llm.bind_tools([duckduckgo_search])
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"Find the stock ticker for: {query}"),
        ]

        for _ in range(self.MAX_ITERATIONS):
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            if not response.tool_calls:
                try:
                    result = json.loads(response.content)
                    return result["ticker"], result["display_name"]
                except (json.JSONDecodeError, KeyError):
                    raise TickerNotFoundError(f"Could not resolve: {query}")

            for tool_call in response.tool_calls:
                tool_result = duckduckgo_search.invoke({"query": tool_call["args"]["query"]})
                messages.append(ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_call["id"],
                ))

        raise TickerNotFoundError(f"Could not resolve after {self.MAX_ITERATIONS} iterations: {query}")

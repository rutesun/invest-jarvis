from pydantic import BaseModel
import yfinance as yf
from src.core.interfaces import BaseTool
from src.core.models import ToolResult


class NewsArticle(BaseModel):
    """News article model."""

    title: str
    published: str
    summary: str
    url: str | None = None


class NewsTool(BaseTool):
    """News aggregation tool."""

    name = "news"
    description = "Fetch recent news for a ticker"

    async def execute(self, ticker: str, limit: int = 10, **kwargs) -> ToolResult:
        """Execute news tool."""
        try:
            stock = yf.Ticker(ticker)
            news_items = stock.news

            if not news_items:
                return ToolResult(success=True, data=[])

            articles = []
            for item in news_items:
                title = item.get("title", "")
                if not title:
                    continue

                published = item.get("providerPublishTime", "")
                if isinstance(published, int):
                    from datetime import datetime
                    published = datetime.fromtimestamp(published).isoformat()

                article = NewsArticle(
                    title=title,
                    published=str(published),
                    summary=item.get("summary", "") or title,
                    url=item.get("link"),
                )
                articles.append(article)

                if len(articles) >= limit:
                    break

            return ToolResult(success=True, data=articles)

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

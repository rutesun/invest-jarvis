import logging
from pydantic import BaseModel
import yfinance as yf
from src.core.interfaces import BaseTool
from src.core.models import ToolResult

logger = logging.getLogger(__name__)


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
            logger.debug("Fetching news for %s (limit=%d)", ticker, limit)
            stock = yf.Ticker(ticker)
            news_items = stock.news

            if not news_items:
                logger.debug("No news found for %s", ticker)
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

            logger.debug("Fetched %d articles for %s", len(articles), ticker)
            return ToolResult(success=True, data=articles)

        except Exception as e:
            logger.debug("News fetch error for %s: %s", ticker, e)
            return ToolResult(success=False, data=None, error=str(e))

from datetime import datetime
from types import SimpleNamespace

import pytest

from src.tools import news
from src.tools.news import NewsArticle, NewsTool


@pytest.fixture
def synthetic_news(monkeypatch):
    """Synthetic legacy-shaped input, not a captured yfinance API contract."""
    news_by_ticker = {
        "AAPL": [
            {},
            {"title": ""},
            {
                "title": "First Apple article",
                "providerPublishTime": 1704067200,
                "summary": "First summary",
                "link": "https://example.com/apple/1",
            },
            {
                "title": "Second Apple article",
                "providerPublishTime": "2024-01-02T09:30:00",
                "summary": "",
            },
            {"title": "Third Apple article"},
            {"title": "Fourth Apple article", "summary": None},
        ],
        "MSFT": [
            {
                "title": "Microsoft announces new product",
                "providerPublishTime": "2024-01-02T10:30:00",
                "summary": "Microsoft product summary",
                "link": "https://example.com/microsoft/1",
            }
        ],
        "INVALID_TICKER_XYZ123": [],
    }
    monkeypatch.setattr(
        news.yf, "Ticker", lambda ticker: SimpleNamespace(news=news_by_ticker[ticker])
    )


def test_news_article_model():
    article = NewsArticle(
        title="Apple announces new product",
        published=datetime.now().isoformat(),
        summary="Apple has announced a new product line.",
        url="https://example.com/article",
    )
    assert article.title == "Apple announces new product"
    assert article.url == "https://example.com/article"
    assert article.summary is not None


@pytest.mark.asyncio
async def test_news_tool_execute(synthetic_news):
    tool = NewsTool()
    result = await tool.execute(ticker="AAPL")

    assert result.success is True
    assert result.error is None
    assert isinstance(result.data, list)
    assert all(isinstance(article, NewsArticle) for article in result.data)
    assert [article.title for article in result.data] == [
        "First Apple article",
        "Second Apple article",
        "Third Apple article",
        "Fourth Apple article",
    ]


@pytest.mark.asyncio
async def test_news_tool_invalid_ticker(synthetic_news):
    tool = NewsTool()
    result = await tool.execute(ticker="INVALID_TICKER_XYZ123")

    assert result.success is True
    assert result.data == []
    assert result.error is None


@pytest.mark.asyncio
async def test_news_tool_limit(synthetic_news):
    tool = NewsTool()
    result = await tool.execute(ticker="AAPL", limit=3)

    assert result.success is True
    assert [article.title for article in result.data] == [
        "First Apple article",
        "Second Apple article",
        "Third Apple article",
    ]


@pytest.mark.asyncio
async def test_news_article_fields(synthetic_news):
    tool = NewsTool()
    result = await tool.execute(ticker="MSFT")

    assert result.success is True
    assert len(result.data) == 1
    assert result.data[0].model_dump() == {
        "title": "Microsoft announces new product",
        "published": "2024-01-02T10:30:00",
        "summary": "Microsoft product summary",
        "url": "https://example.com/microsoft/1",
    }


@pytest.mark.asyncio
async def test_news_tool_converts_integer_timestamp(synthetic_news):
    result = await NewsTool().execute(ticker="AAPL")

    assert result.success is True
    # The production contract uses local time; this assertion is timezone independent.
    assert datetime.fromisoformat(result.data[0].published).timestamp() == 1704067200


@pytest.mark.asyncio
async def test_news_tool_article_fallbacks(synthetic_news):
    result = await NewsTool().execute(ticker="AAPL")

    assert result.success is True
    assert [article.summary for article in result.data] == [
        "First summary",
        "Second Apple article",
        "Third Apple article",
        "Fourth Apple article",
    ]
    assert result.data[0].url == "https://example.com/apple/1"
    assert [article.url for article in result.data[1:]] == [None, None, None]
    assert result.data[2].published == ""


@pytest.mark.asyncio
async def test_news_tool_provider_error(monkeypatch):
    class FailingTicker:
        @property
        def news(self):
            raise RuntimeError("synthetic news provider failure")

    monkeypatch.setattr(news.yf, "Ticker", lambda ticker: FailingTicker())
    result = await NewsTool().execute(ticker="AAPL")

    assert result.success is False
    assert result.data is None
    assert result.error == "synthetic news provider failure"

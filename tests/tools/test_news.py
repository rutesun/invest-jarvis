import pytest
from datetime import datetime
from src.tools.news import NewsTool, NewsArticle


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
async def test_news_tool_execute():
    tool = NewsTool()
    result = await tool.execute(ticker="AAPL")

    assert result.success is True
    assert result.data is not None
    assert isinstance(result.data, list)

    if len(result.data) > 0:
        article = result.data[0]
        assert isinstance(article, NewsArticle)
        assert article.title is not None
        assert article.published is not None


@pytest.mark.asyncio
async def test_news_tool_invalid_ticker():
    tool = NewsTool()
    result = await tool.execute(ticker="INVALID_TICKER_XYZ123")

    assert result.success is True
    assert isinstance(result.data, list)
    assert len(result.data) == 0


@pytest.mark.asyncio
async def test_news_tool_limit():
    tool = NewsTool()
    result = await tool.execute(ticker="AAPL", limit=3)

    assert result.success is True
    assert isinstance(result.data, list)
    assert len(result.data) <= 3


@pytest.mark.asyncio
async def test_news_article_fields():
    tool = NewsTool()
    result = await tool.execute(ticker="MSFT")

    assert result.success is True

    if len(result.data) > 0:
        article = result.data[0]
        assert hasattr(article, "title")
        assert hasattr(article, "published")
        assert hasattr(article, "summary")
        assert hasattr(article, "url")
        assert article.title != ""
        assert article.published != ""

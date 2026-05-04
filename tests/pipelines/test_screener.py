from unittest.mock import AsyncMock

import pytest

from src.core.models import ToolResult
from src.pipelines.screener import ScreenerPipeline
from src.tools.news import NewsArticle
from src.tools.screener.models import ScreenerEvidence, UniverseStock


@pytest.fixture
def mock_universe_builder():
    builder = AsyncMock()
    builder.build.return_value = [
        UniverseStock(
            ticker="005930",
            name="삼성전자",
            market="KOSPI",
            sources=["theme"],
            theme="AI/반도체",
            theme_change_rate=3.2,
        ),
        UniverseStock(ticker="NVDA", name="NVIDIA", market="NAS", sources=["rise_rank"]),
    ]
    return builder


@pytest.fixture
def mock_evidence_collector():
    collector = AsyncMock()
    collector.collect_and_score.return_value = [
        ScreenerEvidence(
            stock=UniverseStock(
                ticker="005930",
                name="삼성전자",
                market="KOSPI",
                sources=["theme"],
                theme="AI/반도체",
                theme_change_rate=3.2,
            ),
            accumulation_score=12.0,
            up_days=7,
            volume_burst_score=5.0,
            source_diversity_bonus=4.0,
            momentum_total=47.0,
            total_score=21.0,
            vol_ratio=3.5,
            rank=1,
        ),
        ScreenerEvidence(
            stock=UniverseStock(ticker="NVDA", name="NVIDIA", market="NAS", sources=["rise_rank"]),
            accumulation_score=0.0,
            up_days=6,
            volume_burst_score=3.0,
            source_diversity_bonus=0.0,
            momentum_total=37.0,
            total_score=3.0,
            vol_ratio=2.0,
            rank=2,
        ),
    ]
    return collector


@pytest.fixture
def mock_news_tool():
    tool = AsyncMock()
    tool.execute.return_value = ToolResult(
        success=True,
        data=[
            NewsArticle(
                title="HBM 수주", published="2026-04-09", summary="확대", url="https://example.com"
            )
        ],
    )
    return tool


@pytest.mark.asyncio
async def test_screener_pipeline_run(
    mock_universe_builder, mock_evidence_collector, mock_news_tool
):
    pipeline = ScreenerPipeline(
        universe_builder=mock_universe_builder,
        evidence_collector=mock_evidence_collector,
        news_tool=mock_news_tool,
    )
    result = await pipeline.run(market="all")

    assert result["market"] == "all"
    assert len(result.get("kr_leaders", []) + result.get("us_leaders", [])) == 2
    assert len(result["themes"]) >= 1
    assert result["themes"][0]["name"] == "AI/반도체"
    assert "news" in result


@pytest.mark.asyncio
async def test_screener_pipeline_format(
    mock_universe_builder, mock_evidence_collector, mock_news_tool
):
    pipeline = ScreenerPipeline(
        universe_builder=mock_universe_builder,
        evidence_collector=mock_evidence_collector,
        news_tool=mock_news_tool,
    )
    result = await pipeline.run(market="all")
    output = pipeline.format_output(result)

    assert "주도 테마" in output
    assert "주도주" in output
    assert "삼성전자" in output


@pytest.mark.asyncio
async def test_screener_pipeline_theme_aggregation(
    mock_universe_builder, mock_evidence_collector, mock_news_tool
):
    """Test theme aggregation with multiple themes."""
    # Setup evidence with multiple themes
    mock_evidence_collector.collect_and_score.return_value = [
        ScreenerEvidence(
            stock=UniverseStock(
                ticker="005930",
                name="삼성전자",
                market="KOSPI",
                sources=["theme"],
                theme="AI/반도체",
                theme_change_rate=3.2,
            ),
            accumulation_score=12.0,
            momentum_total=47.0,
            total_score=21.0,
            vol_ratio=3.5,
            rank=1,
        ),
        ScreenerEvidence(
            stock=UniverseStock(
                ticker="000660",
                name="SK하이닉스",
                market="KOSPI",
                sources=["theme"],
                theme="AI/반도체",
                theme_change_rate=3.2,
            ),
            accumulation_score=8.0,
            momentum_total=35.0,
            total_score=15.0,
            vol_ratio=2.5,
            rank=2,
        ),
        ScreenerEvidence(
            stock=UniverseStock(
                ticker="370330",
                name="현대차",
                market="KOSPI",
                sources=["theme"],
                theme="전기차",
                theme_change_rate=1.5,
            ),
            accumulation_score=5.0,
            momentum_total=25.0,
            total_score=10.0,
            vol_ratio=1.8,
            rank=3,
        ),
    ]

    pipeline = ScreenerPipeline(
        universe_builder=mock_universe_builder,
        evidence_collector=mock_evidence_collector,
        news_tool=mock_news_tool,
    )
    result = await pipeline.run(market="all")

    assert len(result["themes"]) == 2
    assert result["themes"][0]["name"] == "AI/반도체"
    assert result["themes"][0]["stock_count"] == 2
    assert result["themes"][1]["name"] == "전기차"
    assert result["themes"][1]["stock_count"] == 1


@pytest.mark.asyncio
async def test_screener_pipeline_format_output(
    mock_universe_builder, mock_evidence_collector, mock_news_tool
):
    """Test format_output produces valid markdown."""
    mock_evidence_collector.collect_and_score.return_value = [
        ScreenerEvidence(
            stock=UniverseStock(
                ticker="005930", name="삼성전자", market="KOSPI", sources=["theme", "rise_rank"]
            ),
            accumulation_score=12.0,
            momentum_total=47.0,
            total_score=21.0,
            vol_ratio=3.5,
            rank=1,
        ),
    ]

    pipeline = ScreenerPipeline(
        universe_builder=mock_universe_builder,
        evidence_collector=mock_evidence_collector,
        news_tool=mock_news_tool,
    )
    result = await pipeline.run(market="all")
    output = pipeline.format_output(result)

    # Check markdown structure
    assert "# Market Screener" in output
    assert "## 주도주 TOP 50" in output
    assert "삼성전자" in output
    assert "KOSPI" in output
    assert "47" in output  # momentum_total


@pytest.mark.asyncio
async def test_screener_pipeline_save_report(
    mock_universe_builder, mock_evidence_collector, mock_news_tool, tmp_path
):
    """Test save_report creates file with correct path."""
    import os

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        pipeline = ScreenerPipeline(
            universe_builder=mock_universe_builder,
            evidence_collector=mock_evidence_collector,
            news_tool=mock_news_tool,
        )
        result = await pipeline.run(market="all")
        saved_path = pipeline.save_report(result)

        # Check path structure
        assert saved_path.exists()
        assert "reports" in str(saved_path)
        # Check year-month pattern (e.g., "2026-04" or "2026-05")
        import re

        assert re.search(r"202\d-\d{2}", str(saved_path))
        assert "screen-" in saved_path.name
        assert saved_path.name.endswith(".md")

        # Check content
        content = saved_path.read_text()
        assert "# Market Screener" in content
        assert "주도 테마" in content
    finally:
        os.chdir(original_cwd)

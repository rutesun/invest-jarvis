# tests/pipelines/report_stages/test_synthesize.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pipelines.report_stages.synthesize import SynthesizeStage
from src.llm.daily_report_models import (
    IngestResult, ShuffleResult, Theme, StockDetail,
    StockCatalyst, DailyReport,
)


@pytest.fixture
def sample_ingest():
    return IngestResult(
        telegram_messages=[],
        macro_snapshot={"vix": 18.2, "fear_greed": 62, "dxy": 104.2},
        market_news=[{"title": "SPY up", "summary": "Market rises", "source": "SPY", "url": ""}],
        kr_flow=[],
        momentum=[],
    )


@pytest.fixture
def sample_shuffle():
    return ShuffleResult(
        themes=[Theme(name="AI", narrative="AI boom", sentiment="bull",
                      mention_count=10, stocks=["NVDA"])],
        stock_details={"NVDA": StockDetail(
            ticker="NVDA", market="US", mention_count=5,
            flow_score=None, volume_score=3.2, source="telegram",
            summaries=["NVDA 실적 호조"],
        )},
    )


@pytest.fixture
def sample_catalysts():
    return [
        StockCatalyst(ticker="NVDA", themes=["AI"],
                      news=["New chip"], catalyst_summary="차세대 칩"),
    ]


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=DailyReport(
        date="2026-04-13",
        market_pulse="VIX 18.2 | 리스크온",
        narrative_and_themes="AI 인프라 투자 확대",
        featured_analysis="NVDA: 차세대 칩 발표",
    ))
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.asyncio
async def test_synthesize_returns_daily_report(
    sample_ingest, sample_shuffle, sample_catalysts, mock_llm,
):
    stage = SynthesizeStage(llm=mock_llm)
    report = await stage.run(sample_ingest, sample_shuffle, sample_catalysts)

    assert isinstance(report, DailyReport)
    assert report.date == "2026-04-13"
    assert "VIX" in report.market_pulse

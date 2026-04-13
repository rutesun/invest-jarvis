# tests/pipelines/report_stages/test_catalyst.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pipelines.report_stages.catalyst import CatalystStage
from src.llm.daily_report_models import (
    ShuffleResult, Theme, StockDetail, StockCatalyst,
)


@pytest.fixture
def sample_shuffle_result():
    themes = [
        Theme(name="CPO/광통신", narrative="CPO 수요 증가", sentiment="bull",
              mention_count=5, stocks=["NVDA", "LITE", "A058400"]),
        Theme(name="AI 반도체", narrative="AI 칩 수요", sentiment="bull",
              mention_count=3, stocks=["NVDA", "000660"]),
    ]
    stock_details = {
        "NVDA": StockDetail(ticker="NVDA", market="US", mention_count=5,
                            flow_score=None, volume_score=3.2, source="both",
                            summaries=["NVDA 실적 호조", "AI 칩 수요 폭발"]),
        "LITE": StockDetail(ticker="LITE", market="US", mention_count=3,
                            flow_score=None, volume_score=2.1, source="telegram",
                            summaries=["광트랜시버 수주"]),
        "A058400": StockDetail(ticker="A058400", market="KR", mention_count=2,
                               flow_score=350.0, volume_score=None, source="both",
                               summaries=["코위버 CPO 모듈"]),
        "000660": StockDetail(ticker="000660", market="KR", mention_count=2,
                              flow_score=500.0, volume_score=None, source="telegram",
                              summaries=["HBM 수요"]),
    }
    return ShuffleResult(themes=themes, stock_details=stock_details)


@pytest.fixture
def mock_catalyst_llm():
    """tool-calling 에이전트가 StockCatalyst 리스트를 반환하는 것을 시뮬레이션하는 mock."""
    llm = AsyncMock()
    llm.return_value = [
        StockCatalyst(
            ticker="NVDA", themes=["CPO/광통신", "AI 반도체"],
            news=["NVDA new chip announced"], catalyst_summary="차세대 칩 발표",
        ),
        StockCatalyst(
            ticker="LITE", themes=["CPO/광통신"],
            news=["Lumentum Q2 guidance up"], catalyst_summary="가이던스 상향",
        ),
    ]
    return llm


@pytest.mark.asyncio
async def test_catalyst_stage_returns_catalysts(sample_shuffle_result, mock_catalyst_llm):
    stage = CatalystStage(
        llm=mock_catalyst_llm,
        news_tool=AsyncMock(),
        ticker_resolver=AsyncMock(),
        stocks_per_theme=2,
    )
    stage._run_agent = mock_catalyst_llm

    catalysts = await stage.run(sample_shuffle_result)
    assert len(catalysts) >= 1
    assert all(isinstance(c, StockCatalyst) for c in catalysts)


@pytest.mark.asyncio
async def test_catalyst_stage_limits_stocks_per_theme(sample_shuffle_result):
    called_tickers: list[str] = []

    async def mock_agent(themes_json: str, stock_details: dict) -> list[StockCatalyst]:
        import json
        data = json.loads(themes_json)
        for theme in data:
            for stock in theme["stocks"]:
                called_tickers.append(stock["ticker"])
        return []

    stage = CatalystStage(
        llm=AsyncMock(),
        news_tool=AsyncMock(),
        ticker_resolver=AsyncMock(),
        stocks_per_theme=2,
    )
    stage._run_agent = mock_agent
    await stage.run(sample_shuffle_result)

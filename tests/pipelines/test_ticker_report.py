import pytest
from unittest.mock import AsyncMock
from datetime import datetime
from src.pipelines.ticker_report import TickerReportPipeline
from src.tools.macro import MacroTool, TickerMacroSnapshot
from src.tools.technical.tool import TechnicalAnalysisTool
from src.tools.technical.models import TechnicalResult, IndicatorSnapshot, StrategyResult
from src.core.models import ToolResult


@pytest.fixture
def mock_macro_tool():
    tool = AsyncMock(spec=MacroTool)
    macro_snapshot = TickerMacroSnapshot(
        timestamp=datetime.now(),
        vix=15.5,
        vix_change=-0.5,
        fear_greed=65,
        fear_greed_label="Greed",
        wti=75.5,
        wti_change=1.2,
        us_10y=4.2,
        us_2y=4.5,
        yield_spread=-0.3,
        dxy=103.5,
        dxy_change=0.2,
    )
    tool.execute.return_value = ToolResult(success=True, data=macro_snapshot)
    return tool


@pytest.fixture
def mock_technical_tool():
    tool = AsyncMock(spec=TechnicalAnalysisTool)

    def create_technical_result(ticker: str):
        snapshot = IndicatorSnapshot(
            price=178.50 if ticker == "AAPL" else 450.00,
            change_pct=2.5 if ticker == "AAPL" else -1.2,
            sma_20=175.0,
            sma_50=170.0,
            rsi=58.3,
        )
        return TechnicalResult(
            ticker=ticker,
            timestamp=datetime.now(),
            snapshot=snapshot,
            indicators=snapshot,
            components={},
            total_score=75,
            strategies=[
                StrategyResult(
                    name="trend",
                    status="강세" if ticker == "AAPL" else "약세",
                    confidence=75.0,
                    signals=["골든크로스" if ticker == "AAPL" else "데드크로스"],
                    evidence=["20일선 > 50일선"],
                    metrics={"sma_20": 175.0},
                )
            ],
            overall_assessment="매수" if ticker == "AAPL" else "매도",
            confidence_score=75.0,
            key_insights=["골든크로스 발생"],
            warnings=[],
        )

    async def execute_mock(ticker: str):
        return ToolResult(success=True, data=create_technical_result(ticker))

    tool.execute.side_effect = execute_mock
    return tool


@pytest.fixture
def mock_llm():
    """Mock LangChain chat model."""
    return AsyncMock()


@pytest.mark.asyncio
async def test_daily_report_pipeline_success(
    mock_macro_tool, mock_technical_tool, mock_llm
):
    pipeline = TickerReportPipeline(
        macro_tool=mock_macro_tool,
        technical_tool=mock_technical_tool,
        llm=mock_llm,
    )

    result = await pipeline.run(tickers=["AAPL", "MSFT"])

    assert "date" in result
    assert "macro" in result
    assert "tickers" in result

    assert result["macro"].vix == 15.5
    assert result["macro"].fear_greed == 65
    assert len(result["tickers"]) == 2

    assert result["tickers"][0]["ticker"] == "AAPL"
    assert result["tickers"][0]["technical"].ticker == "AAPL"
    assert result["tickers"][1]["ticker"] == "MSFT"
    assert result["tickers"][1]["technical"].ticker == "MSFT"

    mock_macro_tool.execute.assert_called_once()
    assert mock_technical_tool.execute.call_count == 2


@pytest.mark.asyncio
async def test_daily_report_pipeline_macro_failure(
    mock_macro_tool, mock_technical_tool, mock_llm
):
    mock_macro_tool.execute.return_value = ToolResult(
        success=False, data=None, error="Failed to fetch macro data"
    )

    pipeline = TickerReportPipeline(
        macro_tool=mock_macro_tool,
        technical_tool=mock_technical_tool,
        llm=mock_llm,
    )

    with pytest.raises(RuntimeError, match="Macro snapshot failed"):
        await pipeline.run(tickers=["AAPL"])


@pytest.mark.asyncio
async def test_daily_report_pipeline_technical_failure(
    mock_macro_tool, mock_technical_tool, mock_llm
):
    async def execute_mock_with_failure(ticker: str):
        if ticker == "AAPL":
            return ToolResult(
                success=False, data=None, error="Failed to fetch AAPL data"
            )
        snapshot = IndicatorSnapshot(price=450.0, change_pct=-1.2)
        return ToolResult(
            success=True,
            data=TechnicalResult(
                ticker=ticker,
                timestamp=datetime.now(),
                snapshot=snapshot,
                indicators=snapshot,
                components={},
                total_score=50,
                strategies=[],
                overall_assessment="중립",
                confidence_score=50.0,
                key_insights=[],
                warnings=[],
            ),
        )

    mock_technical_tool.execute.side_effect = execute_mock_with_failure

    pipeline = TickerReportPipeline(
        macro_tool=mock_macro_tool,
        technical_tool=mock_technical_tool,
        llm=mock_llm,
    )

    result = await pipeline.run(tickers=["AAPL", "MSFT"])

    assert len(result["tickers"]) == 2
    assert result["tickers"][0]["ticker"] == "AAPL"
    assert result["tickers"][0]["technical"] is None
    assert result["tickers"][0]["error"] == "Failed to fetch AAPL data"
    assert result["tickers"][1]["ticker"] == "MSFT"
    assert result["tickers"][1]["technical"] is not None


@pytest.mark.asyncio
async def test_daily_report_pipeline_empty_tickers(
    mock_macro_tool, mock_technical_tool, mock_llm
):
    pipeline = TickerReportPipeline(
        macro_tool=mock_macro_tool,
        technical_tool=mock_technical_tool,
        llm=mock_llm,
    )

    result = await pipeline.run(tickers=[])

    assert "date" in result
    assert "macro" in result
    assert "tickers" in result
    assert len(result["tickers"]) == 0
    mock_technical_tool.execute.assert_not_called()

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock
from datetime import datetime
from src.cli.main import app
from src.tools.macro import MacroSnapshot
from src.tools.technical.models import TechnicalResult, IndicatorSnapshot
from src.llm.models import TechnicalSummaryOutput, NewsAnalysisOutput

runner = CliRunner()


def test_cli_check_command():
    mock_result = {
        "ticker": "AAPL",
        "success": True,
        "price": 178.50,
        "change_pct": 2.5,
        "assessment": "매수",
        "confidence": 75.0,
        "signals": ["골든크로스"],
        "warnings": [],
        "indicators": {"sma_20": 175.0, "sma_50": 170.0, "rsi": 58.3, "adx": 28.0},
        "strategies": [],
        "total_score": 75,
    }

    with patch("src.cli.main.run_quick_check", new_callable=AsyncMock) as mock_run, \
         patch("src.cli.main.resolve_ticker", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = "AAPL"
        mock_run.return_value = mock_result
        result = runner.invoke(app, ["check", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    assert "178.50" in result.stdout


def test_cli_analyze_command():
    mock_snapshot = IndicatorSnapshot(
        price=178.50,
        change_pct=2.5,
        sma_20=175.0,
        sma_50=170.0,
        rsi=58.3,
    )
    mock_technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=mock_snapshot,
        indicators=mock_snapshot,
        components={},
        total_score=75,
        strategies=[],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["골든크로스"],
        warnings=[],
    )
    mock_tech_summary = TechnicalSummaryOutput(
        summary="기술적 분석 요약",
        key_insights=["인사이트 1"],
        recommendation="매수",
        confidence=0.75,
        rationale="근거",
    )
    mock_news_analysis = NewsAnalysisOutput(
        sentiment="긍정",
        confidence=0.8,
        key_themes=["테마1"],
        summary="뉴스 요약",
        impact_assessment="영향 평가",
    )

    mock_result = {
        "ticker": "AAPL",
        "technical": mock_technical,
        "technical_summary": mock_tech_summary,
        "news": [],
        "news_analysis": mock_news_analysis,
    }

    with patch("src.cli.main.run_deep_dive", new_callable=AsyncMock) as mock_run, \
         patch("src.cli.main.resolve_ticker", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = "AAPL"
        mock_run.return_value = mock_result
        result = runner.invoke(app, ["analyze", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    assert "178.50" in result.stdout


def test_cli_report_command():
    from src.llm.daily_report_models import DailyReport

    mock_report = DailyReport(
        date="2026-04-13",
        market_pulse="시장은 안정적인 분위기입니다.",
        narrative_and_themes="테크 주도의 상승세가 이어지고 있습니다.",
        featured_analysis="NVDA가 AI 수요로 강세를 보이고 있습니다.",
    )

    with patch("src.cli.main.create_daily_report_pipeline") as mock_create:
        mock_pipeline = AsyncMock()
        mock_pipeline.run = AsyncMock(return_value=mock_report)
        mock_create.return_value = mock_pipeline
        result = runner.invoke(app, ["report"])

    assert result.exit_code == 0
    assert "2026-04-13" in result.stdout or "시장은 안정적인 분위기" in result.stdout


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.3.0" in result.stdout

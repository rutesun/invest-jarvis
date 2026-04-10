import pytest
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock
from datetime import datetime
from src.cli.main import app, _render_quarterly_table
from src.tools.macro import MacroSnapshot
from src.tools.technical.models import TechnicalResult, IndicatorSnapshot
from src.llm.models import TechnicalSummaryOutput, NewsAnalysisOutput
from src.tools.fundamental import QuarterlyData

runner = CliRunner()


def test_cli_check_command():
    mock_result = {
        "ticker": "AAPL",
        "success": True,
        "price": 178.50,
        "change_pct": 2.5,
        "total_score": 45,
        "assessment": "매수",
        "confidence": 75.0,
        "signals": ["골든크로스"],
        "warnings": [],
        "indicators": {"sma_20": 175.0, "sma_50": 170.0, "rsi": 58.3, "adx": 28.0},
        "components": [],
    }

    with patch("src.cli.main.run_quick_check", new_callable=AsyncMock) as mock_run:
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
    mock_components = {
        "minervini": {"score": 20, "signals": ["골든크로스"], "evidence": [], "metrics": {}},
        "velocity": {"score": 10, "signals": [], "evidence": [], "metrics": {}},
        "crsi": {"score": 5, "signals": [], "evidence": [], "metrics": {}},
        "volume": {"score": 5, "signals": [], "evidence": [], "metrics": {}},
        "patterns": {"score": 5, "signals": [], "evidence": [], "metrics": {}},
    }
    mock_technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=mock_snapshot,
        components=mock_components,
        total_score=45,
        indicators=mock_snapshot,
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

    with patch("src.cli.main.run_deep_dive", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_result
        result = runner.invoke(app, ["analyze", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    assert "178.50" in result.stdout


def test_cli_report_command():
    mock_macro = MacroSnapshot(
        timestamp=datetime.now(),
        vix=15.5,
        vix_change=-0.5,
        fear_greed=65,
        fear_greed_label="Greed",
        wti=75.0,
        wti_change=1.0,
        us_10y=4.5,
        us_2y=4.2,
        yield_spread=0.3,
        dxy=103.5,
        dxy_change=0.2,
    )

    mock_snapshot = IndicatorSnapshot(
        price=178.50,
        change_pct=2.5,
        sma_20=175.0,
        sma_50=170.0,
        rsi=58.3,
    )
    mock_components = {
        "minervini": {"score": 20, "signals": ["골든크로스"], "evidence": [], "metrics": {}},
        "velocity": {"score": 10, "signals": [], "evidence": [], "metrics": {}},
        "crsi": {"score": 5, "signals": [], "evidence": [], "metrics": {}},
        "volume": {"score": 5, "signals": [], "evidence": [], "metrics": {}},
        "patterns": {"score": 5, "signals": [], "evidence": [], "metrics": {}},
    }
    mock_technical = TechnicalResult(
        ticker="AAPL",
        timestamp=datetime.now(),
        snapshot=mock_snapshot,
        components=mock_components,
        total_score=45,
        indicators=mock_snapshot,
        strategies=[],
        overall_assessment="매수",
        confidence_score=75.0,
        key_insights=["골든크로스"],
        warnings=[],
    )

    mock_result = {
        "date": datetime.now(),
        "macro": mock_macro,
        "tickers": [
            {
                "ticker": "AAPL",
                "technical": mock_technical,
                "error": None,
            }
        ],
    }

    with patch("src.cli.main.run_daily_report", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_result
        result = runner.invoke(app, ["report", "--tickers", "AAPL"])

    assert result.exit_code == 0
    assert "Daily Market Report" in result.stdout
    assert "Macro Snapshot" in result.stdout


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.3.0" in result.stdout


def test_render_quarterly_table_with_full_data():
    """Test rendering with complete quarterly data"""
    data = [
        QuarterlyData(
            period="2026-Q1",
            revenue=143e9,
            earnings=36e9,
            revenue_yoy=0.15,
            revenue_qoq=0.40,
            earnings_yoy=0.18,
            earnings_qoq=0.35,
        ),
        QuarterlyData(
            period="2025-Q4",
            revenue=102e9,
            earnings=28e9,
            revenue_yoy=0.08,
            revenue_qoq=0.09,
            earnings_yoy=0.12,
            earnings_qoq=0.17,
        ),
    ]
    result = _render_quarterly_table(data)
    assert "Revenue" in result
    assert "YoY Growth %" in result
    assert "QoQ Growth %" in result
    assert "Earnings" in result
    assert "2026-Q1" in result
    assert "2025-Q4" in result
    assert "$143.00B" in result
    assert "$102.00B" in result
    assert "$36.00B" in result
    assert "$28.00B" in result


def test_render_quarterly_table_with_none_values():
    """Test rendering with None values (verify N/A appears instead of crashing)"""
    data = [
        QuarterlyData(
            period="2026-Q1",
            revenue=143e9,
            earnings=None,
            revenue_yoy=0.15,
            revenue_qoq=None,
            earnings_yoy=None,
            earnings_qoq=None,
        ),
        QuarterlyData(
            period="2025-Q4",
            revenue=None,
            earnings=28e9,
            revenue_yoy=None,
            revenue_qoq=0.09,
            earnings_yoy=0.12,
            earnings_qoq=None,
        ),
    ]
    result = _render_quarterly_table(data)
    assert "N/A" in result
    assert "Revenue" in result
    assert "Earnings" in result
    assert "2026-Q1" in result
    assert "2025-Q4" in result


def test_render_quarterly_table_color_coding():
    """Test color coding (verify green for positive growth, red for negative)"""
    data = [
        QuarterlyData(
            period="2026-Q1",
            revenue=143e9,
            earnings=36e9,
            revenue_yoy=0.15,
            revenue_qoq=-0.05,
            earnings_yoy=-0.10,
            earnings_qoq=0.20,
        ),
    ]
    result = _render_quarterly_table(data)
    # ANSI color codes: \x1b[32m = green, \x1b[31m = red
    assert "\x1b[32m" in result  # Green color code present
    assert "\x1b[31m" in result  # Red color code present
    assert "+15.00%" in result
    assert "-5.00%" in result
    assert "-10.00%" in result
    assert "+20.00%" in result


def test_render_quarterly_table_with_empty_list():
    """Test with empty list (verify empty string returned)"""
    result = _render_quarterly_table([])
    assert result == ""


def test_render_quarterly_table_with_none_input():
    """Test with None input (verify empty string returned)"""
    result = _render_quarterly_table(None)
    assert result == ""

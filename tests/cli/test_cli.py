from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app, run_deep_dive
from src.llm.models import ActionableSignalOutput, NewsAnalysisOutput, TechnicalSummaryOutput
from src.pipelines.analyze_decision import AnalyzeScenario, FactorAssessment
from src.tools.macro import TickerMacroSnapshot
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult


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

    with (
        patch("src.cli.main.run_quick_check", new_callable=AsyncMock) as mock_run,
        patch("src.cli.main.resolve_ticker", new_callable=AsyncMock) as mock_resolve,
    ):
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
        "factor_assessments": [
            FactorAssessment(
                factor_type="technical",
                role="주도",
                freshness_score=4,
                magnitude_score=4,
                actionability_score=3,
                total_score=11,
                summary="20일선 위 유지",
                role_reason="추세가 현재 액션과 직접 연결됨",
                evidence=["20일선 > 50일선"],
            )
        ],
        "scenarios": [
            AnalyzeScenario(
                name="기본 시나리오",
                trigger_price_levels=["20일선 유지"],
                confirming_factors=["거래량 유지"],
                invalidation_conditions=["20일선 종가 이탈"],
                expected_path="눌림 후 재상승",
                recommended_action="조정 구간 접근",
            )
        ],
        "news": [],
        "news_analysis": mock_news_analysis,
        "actionable_signal": ActionableSignalOutput(
            action="매수",
            timing="지금",
            signal_strength=8,
            headline="매수",
            primary_reason="골든크로스",
            supporting_reasons=[],
            risks=[],
            confidence=0.75,
        ),
    }

    with (
        patch("src.cli.main.run_deep_dive", new_callable=AsyncMock) as mock_run,
        patch("src.cli.main.resolve_ticker", new_callable=AsyncMock) as mock_resolve,
    ):
        mock_resolve.return_value = "AAPL"
        mock_run.return_value = mock_result
        result = runner.invoke(app, ["analyze", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    assert "178.50" in result.stdout
    assert "Summary" in result.stdout  # 플랜 A 레이아웃
    assert "가격" in result.stdout
    assert "판단 요약" not in result.stdout  # 플랜 A에서 제거됨
    # actionable_signal 패널은 플랜 B Task 10에서 제거 예정 — 현재는 있어도 무방


def test_cli_report_command():
    mock_macro = TickerMacroSnapshot(
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
        result = runner.invoke(app, ["report", "ticker", "--tickers", "AAPL"])

    assert result.exit_code == 0
    assert "Daily Market Report" in result.stdout
    assert "Macro Snapshot" in result.stdout


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.3.0" in result.stdout


@pytest.mark.asyncio
async def test_run_deep_dive_korean_stock_without_kis_credentials_uses_yfinance(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("KIS_APP_KEY", raising=False)
    monkeypatch.delenv("KIS_APP_SECRET", raising=False)
    monkeypatch.delenv("OPENDART_API_KEY", raising=False)

    expected = {"ticker": "066970.KQ", "success": True}
    mock_pipeline = AsyncMock()
    mock_pipeline.run = AsyncMock(return_value=expected)

    with (
        patch("src.cli.main.resolve_ticker", new=AsyncMock(return_value="066970.KQ")),
        patch("src.cli.main.YFinanceProvider", return_value=object()) as mock_yfinance_provider,
        patch("src.cli.main.TechnicalScorer", return_value=object()),
        patch("src.cli.main.TechnicalAnalysisTool", return_value=object()),
        patch("src.cli.main.FundamentalTool", return_value=object()) as mock_fundamental_tool,
        patch("src.cli.main.NewsTool", return_value=object()),
        patch("src.cli.main.LLMProvider.create", return_value=object()),
        patch("src.tools.disclosure.SECDisclosureFetcher", return_value=object()),
        patch("src.tools.disclosure.DARTDisclosureFetcher", return_value=object()),
        patch("src.tools.disclosure.DisclosureTool", return_value=object()),
        patch("src.tools.flow.FlowTool", return_value=object()),
        patch("src.cli.main.DeepDivePipeline", return_value=mock_pipeline),
    ):
        result = await run_deep_dive("엘앤에프", "openai")

    assert result == expected
    mock_yfinance_provider.assert_called_once()
    mock_fundamental_tool.assert_called_once_with(kis_provider=None)

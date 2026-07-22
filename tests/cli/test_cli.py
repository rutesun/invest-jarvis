from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app, run_deep_dive, run_quick_check, run_quick_checks
from src.llm.models import IntegratedExplanationOutput, NewsAnalysisOutput, TechnicalSummaryOutput
from src.pipelines.analyze_decision import AnalyzeDecisionSummary, AnalyzeScenario, FactorAssessment
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

    with patch("src.cli.main.run_quick_checks", new=AsyncMock(return_value=[mock_result])):
        result = runner.invoke(app, ["check", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL" in result.stdout
    assert "178.50" in result.stdout


@pytest.mark.asyncio
async def test_run_quick_check_never_constructs_macro():
    with (
        patch("src.cli.main.resolve_ticker", new=AsyncMock(return_value="AAPL")),
        patch("src.cli.main.YFinanceProvider"),
        patch("src.cli.main.TechnicalScorer"),
        patch("src.cli.main.TechnicalAnalysisTool"),
        patch("src.cli.main.QuickCheckPipeline") as pipeline_cls,
        patch("src.cli.main.MacroTool") as macro_cls,
    ):
        pipeline_cls.return_value.run = AsyncMock(
            return_value={"success": True, "ticker": "AAPL"}
        )
        result = await run_quick_check("AAPL")

    macro_cls.assert_not_called()
    assert result["ticker"] == "AAPL"


def test_check_output_never_displays_macro():
    success = {
        "ticker": "AAPL",
        "success": True,
        "price": 178.5,
        "change_pct": 1.2,
        "total_score": 42,
        "component_raw_total": 42,
        "adjusted_score": 35,
        "technical_verdict": None,
        "score_history": [],
        "score_history_warning": None,
        "assessment": "관망",
        "confidence": 0,
        "signals": [],
        "warnings": [],
        "indicators": {
            "sma_20": 175.0,
            "sma_50": 170.0,
            "sma_100": 165.0,
            "sma_100_slope_pct": 0.2,
            "sma_150": 160.0,
            "sma_200": 155.0,
            "sma_200_slope_pct": -0.1,
            "rsi": 55.0,
            "adx": 20.0,
            "crsi": 50.0,
        },
        "components": [],
    }
    with patch(
        "src.cli.main.run_quick_checks",
        new=AsyncMock(return_value=[success]),
    ):
        result = runner.invoke(app, ["check", "AAPL"])

    assert result.exit_code == 0
    assert "AAPL Quick Check" in result.stdout
    assert "Macro" not in result.stdout


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
        "decision_summary": AnalyzeDecisionSummary(
            leader="technical",
            core_variables=["20일선 위 유지", "거래량 유지"],
            action="관망",
            timing="조정_대기",
            action_sentence="조정 확인 후 접근이 유리",
        ),
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
        "integrated_explanation": IntegratedExplanationOutput(
            decision_explanation="규칙이 확정한 관망 판단 해설",
            rationale=["기술적: 추세 유지"],
            risks=["과열 부담"],
            monitoring_points=["20일선 유지 여부"],
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
    assert "판단 요약" in result.stdout
    assert "주도 팩터" in result.stdout
    assert "가격" in result.stdout
    assert "조정 대기" in result.stdout
    assert "실행 가능한 투자 시그널" not in result.stdout
    assert "종합 해설" in result.stdout
    assert "규칙이 확정한 관망 판단 해설" in result.stdout


@pytest.mark.asyncio
async def test_run_quick_checks_isolates_failures_and_preserves_input_order():
    success_aapl = {"success": True, "ticker": "AAPL"}
    success_msft = {"success": True, "ticker": "MSFT"}

    with patch(
        "src.cli.main.run_quick_check",
        new=AsyncMock(
            side_effect=[
                success_aapl,
                RuntimeError("resolver down"),
                success_msft,
            ]
        ),
    ) as quick_check:
        results = await run_quick_checks(["AAPL", "INVALID", "MSFT"])

    assert results == [
        success_aapl,
        {
            "success": False,
            "ticker": "INVALID",
            "error": "resolver down",
        },
        success_msft,
    ]
    assert [call.args[0] for call in quick_check.await_args_list] == [
        "AAPL",
        "INVALID",
        "MSFT",
    ]


def test_check_accepts_multiple_tickers():
    results = [
        {"success": True, "ticker": "AAPL", "price": 100.0, "change_pct": 1.0},
        {"success": True, "ticker": "MSFT", "price": 200.0, "change_pct": -1.0},
    ]
    with (
        patch("src.cli.main.run_quick_checks", new=AsyncMock(return_value=results)),
        patch(
            "src.pipelines.quick_check.QuickCheckPipeline.format_output",
            side_effect=["AAPL result", "MSFT result"],
        ),
    ):
        result = runner.invoke(app, ["check", "AAPL", "MSFT"])

    assert result.exit_code == 0
    assert "AAPL result" in result.stdout
    assert "MSFT result" in result.stdout


def test_check_reports_all_results_then_exits_nonzero_on_partial_failure():
    results = [
        {"success": True, "ticker": "AAPL", "price": 100.0, "change_pct": 1.0},
        {"success": False, "ticker": "INVALID", "error": "No data"},
    ]
    with (
        patch("src.cli.main.run_quick_checks", new=AsyncMock(return_value=results)),
        patch(
            "src.pipelines.quick_check.QuickCheckPipeline.format_output",
            return_value="AAPL result",
        ),
    ):
        result = runner.invoke(app, ["check", "AAPL", "INVALID"])

    assert result.exit_code == 1
    assert "AAPL result" in result.stdout
    assert "INVALID" in result.stdout
    assert "No data" in result.stdout


def test_report_ticker_command_is_removed():
    result = runner.invoke(app, ["report", "ticker"])
    assert result.exit_code != 0
    assert "No such command" in result.stderr


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
        patch("src.cli.main.MacroTool") as mock_macro_tool,
        patch(
            "src.cli.main.DeepDivePipeline", return_value=mock_pipeline
        ) as mock_pipeline_cls,
    ):
        result = await run_deep_dive("엘앤에프", "openai")

    assert result == expected
    mock_yfinance_provider.assert_called_once()
    mock_fundamental_tool.assert_called_once_with(kis_provider=None)
    mock_macro_tool.assert_called_once_with()
    assert mock_pipeline_cls.call_args.kwargs["macro_tool"] is mock_macro_tool.return_value

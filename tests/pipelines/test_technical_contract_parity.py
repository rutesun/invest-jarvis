from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.core.models import ToolResult
from src.llm.models import IntegratedExplanationOutput, TechnicalSummaryOutput
from src.pipelines.brief import BriefPipeline
from src.pipelines.deep_dive import DeepDivePipeline
from src.pipelines.quick_check import QuickCheckPipeline
from src.pipelines.strategy_analysis import AnalysisStrategyService, ChartBundleLoader
from src.storage.canonical import canonical_bytes
from src.strategies.models import EntryOpportunityStatus, StructureStatus
from src.tools.playbook.holdings import HoldingEntry, HoldingsConfig
from src.tools.playbook.models import (
    ExitVerdict,
    MarketRegimeResult,
    PlaybookVerdict,
    RelativeStrengthResult,
)
from src.tools.technical.models import StructureLevelsPayloadV2, TechnicalResult
from src.tools.technical.scorecard_models import DataStatus
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.tool import TechnicalAnalysisTool


class SnapshotProvider:
    def __init__(self, history: pd.DataFrame):
        self.history = history

    async def get_price_history(self, ticker: str, period: str) -> pd.DataFrame:
        return self.history.copy(deep=True)


@pytest.fixture
def ohlcv_snapshot() -> pd.DataFrame:
    periods = 800
    dates = pd.date_range("2023-01-02", periods=periods, freq="B")
    trend = np.linspace(100.0, 180.0, periods)
    cycle = np.sin(np.linspace(0.0, 16.0, periods)) * 4.0
    close = trend + cycle
    return pd.DataFrame(
        {
            "Open": close - 0.7,
            "High": close + 1.5,
            "Low": close - 1.5,
            "Close": close,
            "Volume": 1_000_000 + (np.arange(periods) % 20) * 10_000,
        },
        index=dates,
    )


def _technical_tool(history: pd.DataFrame) -> TechnicalAnalysisTool:
    return TechnicalAnalysisTool(
        provider=SnapshotProvider(history),
        scorer=TechnicalScorer(),
    )


def _canonical_projection(result: TechnicalResult) -> dict[str, Any]:
    return {
        "components": result.components,
        "component_raw_total": result.component_raw_total,
        "adjusted_score": result.adjusted_score,
        "technical_verdict": result.technical_verdict.model_dump(),
        "score_history": [point.model_dump() for point in result.score_history],
        "aggregation_trace": [entry.model_dump() for entry in result.aggregation_trace],
    }


def _brief_verdict(ticker: str) -> PlaybookVerdict:
    return PlaybookVerdict(
        ticker=ticker,
        holding=True,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=1.0,
            outperform_6m=1.0,
            rp_slope_4w=0.1,
            index_symbol="^GSPC",
        ),
        sector_strength=None,
        canslim=None,
        gate=None,
        position_plan=None,
        exit_verdict=ExitVerdict(
            action="hold",
            signals=[],
            current_r=None,
            trailing_stop=None,
            detail="test",
        ),
        headline="test",
    )


@pytest.mark.asyncio
async def test_technical_contract_is_identical_across_check_analyze_and_brief(
    ohlcv_snapshot: pd.DataFrame,
    tmp_path,
    monkeypatch,
):
    log_path = tmp_path / "consumer-decisions.jsonl"
    monkeypatch.setenv("JARVIS_ENTRY_SHADOW_LOG_PATH", str(log_path))
    strategy_service = AnalysisStrategyService(
        chart_loader=ChartBundleLoader(market_provider=SnapshotProvider(ohlcv_snapshot))
    )
    check_pipeline = QuickCheckPipeline(
        _technical_tool(ohlcv_snapshot), strategy_service=strategy_service
    )
    check_result = await check_pipeline.run("AAPL")

    news_tool = MagicMock()
    news_tool.execute = AsyncMock(return_value=ToolResult(success=True, data=[]))
    deep_pipeline = DeepDivePipeline(
        technical_tool=_technical_tool(ohlcv_snapshot),
        news_tool=news_tool,
        llm=MagicMock(),
        pattern_engine=MagicMock(detect=MagicMock(return_value={})),
        structure_zone_detector=MagicMock(detect=MagicMock(return_value=MagicMock())),
        level_payload_composer=MagicMock(
            return_value=SimpleNamespace(
                structure_levels=StructureLevelsPayloadV2(
                    summary_label="no_clear_structure",
                    headline="명확한 구조 없음",
                    why="parity 테스트 기본값",
                ),
                execution_levels=[],
                structure_summary=None,
                execution_summary=None,
            )
        ),
        structure_presentation_adapter=MagicMock(
            return_value=SimpleNamespace(
                llm_context="",
                structure_summary=None,
                execution_summary=None,
            )
        ),
        strategy_service=strategy_service,
    )
    deep_pipeline._generate_technical_summary = AsyncMock(
        return_value=TechnicalSummaryOutput(
            summary="test",
            key_insights=[],
            recommendation="중립",
            confidence=0.5,
            rationale="test",
        )
    )
    config = HoldingsConfig(
        krw_capital=None,
        krw_risk_pct=None,
        usd_capital=None,
        usd_risk_pct=None,
        holdings=[
            HoldingEntry(
                ticker="AAPL", quantity=1, avg_price=100.0, stop_price=None, currency="USD"
            )
        ],
    )

    with (
        patch(
            "src.pipelines.deep_dive.analyzer.generate_integrated_explanation",
            new=AsyncMock(
                return_value=IntegratedExplanationOutput(
                    decision_explanation="test",
                    rationale=[],
                    risks=[],
                    monitoring_points=[],
                )
            ),
        ),
        patch("src.pipelines.deep_dive.render_technical_chart", return_value=None),
        patch("src.pipelines.deep_dive.load_holdings", return_value=config),
    ):
        analyze_result = await deep_pipeline.run("AAPL")

    macro_tool = MagicMock()
    macro_tool.execute = AsyncMock(return_value=ToolResult(success=True, data=None))
    brief_playbook = MagicMock()
    brief_playbook.evaluate = AsyncMock(side_effect=lambda *, ticker, **_: _brief_verdict(ticker))
    brief_news = MagicMock()
    brief_news.execute = AsyncMock(return_value=ToolResult(success=True, data=[]))
    brief_disclosure = MagicMock()
    brief_disclosure.execute = AsyncMock(return_value=ToolResult(success=True, data=[]))
    brief_pipeline = BriefPipeline(
        technical_tools={
            "KR": _technical_tool(ohlcv_snapshot),
            "US": _technical_tool(ohlcv_snapshot),
        },
        playbook_engine=brief_playbook,
        macro_tool=macro_tool,
        news_tool=brief_news,
        disclosure_tool=brief_disclosure,
        flow_tool=None,
        strategy_service=strategy_service,
    )
    brief_result = await brief_pipeline.run(config)
    changed_position_result = await brief_pipeline.run(
        HoldingsConfig(
            krw_capital=None,
            krw_risk_pct=None,
            usd_capital=10_000,
            usd_risk_pct=0.02,
            holdings=[
                HoldingEntry(
                    ticker="AAPL",
                    quantity=7,
                    avg_price=120.0,
                    stop_price=None,
                    currency="USD",
                )
            ],
        )
    )
    brief_playbook_call = brief_playbook.evaluate.await_args

    snapshots = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [row["pipeline"] for row in snapshots] == ["check", "analyze", "brief", "brief"]
    assert len({row["decision_key"] for row in snapshots}) == 1
    assert snapshots[2]["snapshot_key"] == snapshots[3]["snapshot_key"]

    assert _canonical_projection(analyze_result["technical"]) == _canonical_projection(
        brief_playbook_call.kwargs["technical_result"]
    )
    assert {
        "components": {item["name"]: item["score"] for item in check_result["components"]},
        "component_raw_total": check_result["component_raw_total"],
        "adjusted_score": check_result["adjusted_score"],
        "technical_verdict": check_result["technical_verdict"],
        "score_history": check_result["score_history"],
        "aggregation_trace": check_result["aggregation_trace"],
    } == {
        "components": {
            name: component["score"]
            for name, component in analyze_result["technical"].components.items()
        },
        "component_raw_total": analyze_result["technical"].component_raw_total,
        "adjusted_score": analyze_result["technical"].adjusted_score,
        "technical_verdict": analyze_result["technical"].technical_verdict.model_dump(),
        "score_history": [
            point.model_dump() for point in analyze_result["technical"].score_history
        ],
        "aggregation_trace": [
            entry.model_dump() for entry in analyze_result["technical"].aggregation_trace
        ],
    }
    check_run = check_result["strategy_run"]
    analyze_run = analyze_result["strategy_run"]
    brief_run = brief_result["items"][0].strategy_run
    assert check_run is not None and analyze_run is not None and brief_run is not None
    assert canonical_bytes(check_run.scorecard) == canonical_bytes(analyze_run.scorecard)
    assert canonical_bytes(check_run.scorecard) == canonical_bytes(brief_run.scorecard)
    assert canonical_bytes(check_run.verdicts) == canonical_bytes(analyze_run.verdicts)
    assert canonical_bytes(check_run.verdicts) == canonical_bytes(brief_run.verdicts)
    assert analyze_result["strategy_analysis"].position_plan.current_quantity == 1
    assert brief_result["items"][0].strategy_analysis.position_plan.current_quantity == 1
    changed_item = changed_position_result["items"][0]
    assert canonical_bytes(brief_run.scorecard) == canonical_bytes(
        changed_item.strategy_run.scorecard
    )
    assert canonical_bytes(brief_run.verdicts) == canonical_bytes(
        changed_item.strategy_run.verdicts
    )
    assert changed_item.strategy_analysis.position_plan.current_quantity == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "empty"])
async def test_market_bundle_failure_keeps_all_strategy_slots_and_legacy_result(
    ohlcv_snapshot, failure
):
    class FailingMarketProvider:
        async def get_price_history(self, ticker, period):
            if failure == "empty":
                return pd.DataFrame()
            raise TimeoutError("market chart timed out")

    pipeline = QuickCheckPipeline(
        _technical_tool(ohlcv_snapshot),
        strategy_service=AnalysisStrategyService(
            chart_loader=ChartBundleLoader(market_provider=FailingMarketProvider())
        ),
    )
    result = await pipeline.run("AAPL")

    assert result["success"] is True
    assert result["total_score"] is not None
    assert result["scorecard"] is not None
    assert result["strategy_run"] is not None
    assert [verdict.strategy_id for verdict in result["strategy_run"].verdicts] == [
        "TECHNICAL_LEGACY",
        "PLAYBOOK_V1",
    ]
    run = result["strategy_run"]
    assert run.data_status is DataStatus.INSUFFICIENT_DATA
    assert len(run.signal_bundles) == 1
    signals = run.signal_bundles[0]
    assert signals.strategy_id == "SWING_W150"
    assert signals.strategy_version == "SWING_W150_V2"
    assert signals.as_of == result["scorecard"].as_of
    opportunity = signals.entry_opportunity
    assert opportunity.status is EntryOpportunityStatus.NOT_EVALUATED
    assert opportunity.evaluation_as_of == signals.as_of
    assert opportunity.market_regime is None
    assert opportunity.structure_status is StructureStatus.UNKNOWN
    assert [item.code for item in opportunity.evidence] == ["CHART_OR_MARKET_INCOMPLETE"]
    assert result["strategy_run"].verdicts[1].entry.intent.value == "not_evaluated"
    output = pipeline.format_output(result)
    assert "Market chart unavailable" in output
    assert "SWING_W150: NOT_EVALUATED" in output
    assert "종목 또는 benchmark 차트 불충분" in output
    assert result["strategy_analysis"].exchange_sessions[-1] == result["scorecard"].as_of

    legacy_result = await QuickCheckPipeline(_technical_tool(ohlcv_snapshot)).run("AAPL")
    assert canonical_bytes(result["scorecard"]) == canonical_bytes(legacy_result["scorecard"])
    for key in ("total_score", "component_raw_total", "adjusted_score", "technical_verdict"):
        assert result[key] == legacy_result[key]

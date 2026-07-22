from __future__ import annotations

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
from src.tools.playbook.holdings import HoldingEntry, HoldingsConfig
from src.tools.playbook.models import (
    ExitVerdict,
    MarketRegimeResult,
    PlaybookVerdict,
    RelativeStrengthResult,
)
from src.tools.technical.models import StructureLevelsPayloadV2, TechnicalResult
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
        market_regime=MarketRegimeResult(
            regime="상승", allow_new_buy=True, index_symbol="^GSPC"
        ),
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
):
    check_pipeline = QuickCheckPipeline(_technical_tool(ohlcv_snapshot))
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
        technical_tools={"KR": _technical_tool(ohlcv_snapshot), "US": _technical_tool(ohlcv_snapshot)},
        playbook_engine=brief_playbook,
        macro_tool=macro_tool,
        news_tool=brief_news,
        disclosure_tool=brief_disclosure,
        flow_tool=None,
    )
    config = HoldingsConfig(
        krw_capital=None,
        krw_risk_pct=None,
        usd_capital=None,
        usd_risk_pct=None,
        holdings=[
            HoldingEntry(
                ticker="AAPL",
                quantity=1,
                avg_price=100.0,
                stop_price=None,
                currency="USD",
            )
        ],
    )
    await brief_pipeline.run(config)
    brief_playbook_call = brief_playbook.evaluate.await_args

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

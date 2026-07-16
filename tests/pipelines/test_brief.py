"""BriefPipeline 조립 테스트 — 전 도구 목, 부분 실패 격리·LLM fallback 검증."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import ToolResult
from src.pipelines.brief import BriefPipeline
from src.tools.brief.models import BUCKET_LIQUIDATE, BUCKET_REJECTED
from src.tools.macro import TickerMacroSnapshot
from src.tools.playbook.holdings import HoldingEntry, HoldingsConfig, WatchEntry
from src.tools.playbook.models import (
    ExitVerdict,
    GateCheck,
    GateResult,
    MarketRegimeResult,
    PlaybookVerdict,
    RelativeStrengthResult,
)
from src.tools.technical.models import IndicatorSnapshot, TechnicalResult


def _technical(ticker: str, price: float = 100.0, change_pct: float = 1.0) -> TechnicalResult:
    return TechnicalResult(
        ticker=ticker,
        timestamp=datetime(2026, 7, 14),
        snapshot=IndicatorSnapshot(price=price, change_pct=change_pct),
        components={},
    )


def _verdict_holding(ticker: str, action: str = "liquidate") -> PlaybookVerdict:
    return PlaybookVerdict(
        ticker=ticker,
        holding=True,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=1.0, outperform_6m=1.0, rp_slope_4w=0.1, index_symbol="^GSPC"
        ),
        sector_strength=None,
        canslim=None,
        gate=None,
        position_plan=None,
        exit_verdict=ExitVerdict(
            action=action, signals=[], current_r=None, trailing_stop=None, detail="테스트"
        ),
        headline="",
    )


def _verdict_watch(ticker: str, met: dict[str, bool]) -> PlaybookVerdict:
    checklist = [
        GateCheck(name=n, required=True, met=met[n], reason=f"{n}") for n in ("A", "B", "C", "E")
    ]
    passed = all(met.values())
    return PlaybookVerdict(
        ticker=ticker,
        holding=False,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=1.0, outperform_6m=1.0, rp_slope_4w=0.1, index_symbol="^GSPC"
        ),
        sector_strength=None,
        canslim=None,
        gate=GateResult(
            passed=passed,
            checklist=checklist,
            quality_grade="A" if passed else None,
            veto_reason=None if passed else "E: 미충족",
        ),
        position_plan=None,
        exit_verdict=None,
        headline="",
    )


def _config() -> HoldingsConfig:
    return HoldingsConfig(
        krw_capital=None,
        krw_risk_pct=None,
        usd_capital=None,
        usd_risk_pct=None,
        holdings=[
            HoldingEntry(
                ticker="AAPL", quantity=5, avg_price=150.0, stop_price=None, currency="USD"
            )
        ],
        watchlist=[WatchEntry(ticker="NVDA", note=None, currency="USD")],
    )


def _pipeline(engine, tech_us=None, llm=None) -> BriefPipeline:
    macro_tool = MagicMock()
    macro_tool.execute = AsyncMock(
        return_value=ToolResult(
            success=True,
            data=TickerMacroSnapshot(
                timestamp=datetime(2026, 7, 14),
                vix=14.0,
                vix_change=0.1,
                fear_greed=60,
                fear_greed_label="Greed",
                wti=70.0,
                wti_change=0.0,
                us_10y=4.1,
                us_2y=4.0,
                yield_spread=0.1,
                dxy=104.0,
                dxy_change=0.0,
            ),
        )
    )
    if tech_us is None:
        tech_us = MagicMock()
        tech_us.execute = AsyncMock(
            side_effect=lambda ticker, **kw: ToolResult(success=True, data=_technical(ticker))
        )
    news_tool = MagicMock()
    news_tool.execute = AsyncMock(return_value=ToolResult(success=True, data=[]))
    disclosure_tool = MagicMock()
    disclosure_tool.execute = AsyncMock(return_value=ToolResult(success=True, data=[]))
    flow_tool = MagicMock()
    flow_tool.execute = AsyncMock(return_value=ToolResult(success=False, data=None, error="no kis"))
    return BriefPipeline(
        technical_tools={"KR": tech_us, "US": tech_us},
        playbook_engine=engine,
        macro_tool=macro_tool,
        news_tool=news_tool,
        disclosure_tool=disclosure_tool,
        flow_tool=flow_tool,
        llm=llm,
    )


@pytest.mark.asyncio
async def test_run_all_targets_included_and_ranked():
    engine = MagicMock()

    async def _eval(*, ticker, holding, **kw):
        if holding is not None:
            return _verdict_holding(ticker, action="liquidate")
        return _verdict_watch(ticker, {"A": True, "B": False, "C": False, "E": False})

    engine.evaluate = AsyncMock(side_effect=_eval)
    pipeline = _pipeline(engine)

    result = await pipeline.run(_config())

    assert {i.ticker for i in result["items"]} == {"AAPL", "NVDA"}
    assert result["items"][0].ticker == "AAPL"  # 청산(버킷1) > 거부(버킷6)
    assert result["items"][0].bucket == BUCKET_LIQUIDATE
    assert result["items"][1].bucket == BUCKET_REJECTED
    assert result["macro"] is not None


@pytest.mark.asyncio
async def test_run_isolates_per_ticker_failure():
    """한 종목 기술분석 실패가 나머지 종목을 막지 않는다."""
    engine = MagicMock()
    engine.evaluate = AsyncMock(
        side_effect=lambda *, ticker, holding, **kw: (
            _verdict_holding(ticker, "hold")
            if holding
            else _verdict_watch(ticker, {"A": True, "B": True, "C": True, "E": True})
        )
    )
    tech = MagicMock()

    async def _tech(ticker, **kw):
        if ticker == "AAPL":
            return ToolResult(success=False, data=None, error="timeout")
        return ToolResult(success=True, data=_technical(ticker))

    tech.execute = AsyncMock(side_effect=_tech)
    pipeline = _pipeline(engine, tech_us=tech)

    result = await pipeline.run(_config())

    by_ticker = {i.ticker: i for i in result["items"]}
    assert by_ticker["AAPL"].action == "error"
    assert "timeout" in by_ticker["AAPL"].error
    assert by_ticker["NVDA"].action == "eligible"


@pytest.mark.asyncio
async def test_run_macro_failure_does_not_block():
    engine = MagicMock()
    engine.evaluate = AsyncMock(
        side_effect=lambda *, ticker, holding, **kw: (
            _verdict_holding(ticker, "hold")
            if holding
            else _verdict_watch(ticker, {"A": True, "B": True, "C": True, "E": True})
        )
    )
    pipeline = _pipeline(engine)
    pipeline.macro_tool.execute = AsyncMock(
        return_value=ToolResult(success=False, data=None, error="down")
    )

    result = await pipeline.run(_config())

    assert result["macro"] is None
    assert len(result["items"]) == 2


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_rule_text():
    """LLM 실패 시 narrative 없이 완성 — 규칙 원문 fallback (스펙 §7)."""
    engine = MagicMock()
    engine.evaluate = AsyncMock(
        side_effect=lambda *, ticker, holding, **kw: (
            _verdict_holding(ticker, "hold")
            if holding
            else _verdict_watch(ticker, {"A": True, "B": True, "C": True, "E": True})
        )
    )
    failing_llm = MagicMock()
    failing_llm.with_structured_output.side_effect = RuntimeError("LLM down")
    pipeline = _pipeline(engine, llm=failing_llm)

    result = await pipeline.run(_config())

    assert all(i.narrative is None for i in result["items"])
    md = pipeline.format_output(result)
    assert "NVDA" in md and "AAPL" in md


@pytest.mark.asyncio
async def test_empty_config_returns_empty_items():
    engine = MagicMock()
    pipeline = _pipeline(engine)
    config = HoldingsConfig(
        krw_capital=None, krw_risk_pct=None, usd_capital=None, usd_risk_pct=None
    )
    result = await pipeline.run(config)
    assert result["items"] == []
    engine.evaluate.assert_not_called()

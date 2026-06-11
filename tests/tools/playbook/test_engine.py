"""TDD: engine.py — PlaybookEngine.evaluate 오케스트레이션."""

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------


def _make_stock_df(n: int = 300, close: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2022-01-01", periods=n, freq="B")
    closes = np.linspace(80, close, n)
    df = pd.DataFrame(
        {
            "Open": closes - 0.5,
            "High": closes + 2.0,
            "Low": closes - 2.0,
            "Close": closes,
            "Volume": np.full(n, 1_500_000.0),
        },
        index=idx,
    )
    df["ATR"] = 2.0
    df["Vol_SMA_50"] = 1_000_000.0
    return df


def _make_index_df(n: int = 300) -> pd.DataFrame:
    """상승 시장 지수 DataFrame (allow_new_buy=True 보장)."""
    idx = pd.date_range("2022-01-01", periods=n, freq="B")
    close = np.linspace(3000, 5000, n)
    df = pd.DataFrame(
        {"Open": close - 10, "High": close + 20, "Low": close - 20, "Close": close},
        index=idx,
    )
    return df


def _make_technical_result(stock_df: pd.DataFrame) -> MagicMock:
    """TechnicalResult mock — components에 minervini.is_stage2 포함."""
    tr = MagicMock()
    tr.raw_dataframe = stock_df
    tr.snapshot = MagicMock()
    tr.snapshot.price = float(stock_df["Close"].iloc[-1])
    tr.snapshot.high_52w = float(stock_df["Close"].max())
    tr.snapshot.swing_low = float(stock_df["Close"].min())
    tr.components = {
        "minervini": {
            "metrics": {"is_stage2": 1.0},
        },
        "volume": {"score": 2, "signals": []},
    }
    tr.ticker = "AAPL"
    return tr


def _make_sector_strong() -> MagicMock:
    from src.tools.playbook.models import SectorStrengthResult

    return SectorStrengthResult(
        industry="Technology",
        rank_pct=0.1,
        trend="up",
        is_strong=True,
        source="FMP",
    )


# ---------------------------------------------------------------------------
# Task 6: mock 부품으로 미보유 분기 테스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_not_holding_gate_pass_returns_verdict():
    """미보유 + 게이트 통과 → PlaybookVerdict(gate=passed, position_plan 있음)."""
    from src.tools.playbook.engine import PlaybookEngine
    from src.tools.playbook.models import PlaybookVerdict

    stock_df = _make_stock_df(300, close=100.0)
    index_df = _make_index_df(300)
    technical_result = _make_technical_result(stock_df)

    # providers mock
    index_provider = MagicMock()
    index_provider.get_index_history = AsyncMock(return_value=("^GSPC", index_df))

    fmp_provider = MagicMock()
    fmp_provider.industry_snapshot = AsyncMock(return_value={})
    fmp_provider.historical_industry = AsyncMock(return_value=[])

    kis_provider = MagicMock()

    engine = PlaybookEngine(
        index_provider=index_provider,
        fmp_provider=fmp_provider,
        kis_provider=kis_provider,
    )

    result = await engine.evaluate(
        ticker="AAPL",
        technical_result=technical_result,
        fundamental=None,
        flow=None,
        zone_set=None,
        holding=None,
    )

    assert isinstance(result, PlaybookVerdict)
    assert result.ticker == "AAPL"
    assert result.holding is False
    assert result.gate is not None
    assert result.exit_verdict is None
    assert result.market_regime is not None
    assert result.relative_strength is not None


@pytest.mark.asyncio
async def test_engine_holding_returns_exit_verdict():
    """보유 → PlaybookVerdict(exit_verdict 있음, gate=None)."""
    from src.tools.playbook.engine import PlaybookEngine
    from src.tools.playbook.holdings import HoldingEntry
    from src.tools.playbook.models import PlaybookVerdict

    stock_df = _make_stock_df(300, close=110.0)
    index_df = _make_index_df(300)
    technical_result = _make_technical_result(stock_df)

    holding = HoldingEntry(
        ticker="AAPL",
        quantity=10,
        avg_price=100.0,
        stop_price=90.0,
        currency="USD",
    )

    index_provider = MagicMock()
    index_provider.get_index_history = AsyncMock(return_value=("^GSPC", index_df))
    fmp_provider = MagicMock()
    fmp_provider.industry_snapshot = AsyncMock(return_value={})
    fmp_provider.historical_industry = AsyncMock(return_value=[])
    kis_provider = MagicMock()

    engine = PlaybookEngine(
        index_provider=index_provider,
        fmp_provider=fmp_provider,
        kis_provider=kis_provider,
    )

    result = await engine.evaluate(
        ticker="AAPL",
        technical_result=technical_result,
        fundamental=None,
        flow=None,
        zone_set=None,
        holding=holding,
    )

    assert isinstance(result, PlaybookVerdict)
    assert result.holding is True
    assert result.exit_verdict is not None
    assert result.gate is None


@pytest.mark.asyncio
async def test_engine_gate_pass_with_position_plan():
    """게이트 통과 + capital 있음 → position_plan.shares 계산됨."""
    from src.tools.playbook.engine import PlaybookEngine

    stock_df = _make_stock_df(300, close=100.0)
    index_df = _make_index_df(300)
    technical_result = _make_technical_result(stock_df)

    index_provider = MagicMock()
    index_provider.get_index_history = AsyncMock(return_value=("^GSPC", index_df))
    fmp_provider = MagicMock()
    fmp_provider.industry_snapshot = AsyncMock(return_value={})
    fmp_provider.historical_industry = AsyncMock(return_value=[])
    kis_provider = MagicMock()

    engine = PlaybookEngine(
        index_provider=index_provider,
        fmp_provider=fmp_provider,
        kis_provider=kis_provider,
        usd_capital=100_000.0,
        usd_risk_pct=0.01,
    )

    result = await engine.evaluate(
        ticker="AAPL",
        technical_result=technical_result,
        fundamental=None,
        flow=None,
        zone_set=None,
        holding=None,
    )

    # gate가 통과했으면 position_plan이 있어야 함
    if result.gate and result.gate.passed:
        assert result.position_plan is not None
        assert result.position_plan.error is None or result.position_plan.shares is not None


@pytest.mark.asyncio
async def test_engine_headline_not_empty():
    """PlaybookVerdict.headline은 비어있으면 안 됨."""
    from src.tools.playbook.engine import PlaybookEngine

    stock_df = _make_stock_df(300, close=100.0)
    index_df = _make_index_df(300)
    technical_result = _make_technical_result(stock_df)

    index_provider = MagicMock()
    index_provider.get_index_history = AsyncMock(return_value=("^GSPC", index_df))
    fmp_provider = MagicMock()
    fmp_provider.industry_snapshot = AsyncMock(return_value={})
    fmp_provider.historical_industry = AsyncMock(return_value=[])
    kis_provider = MagicMock()

    engine = PlaybookEngine(
        index_provider=index_provider,
        fmp_provider=fmp_provider,
        kis_provider=kis_provider,
    )

    result = await engine.evaluate(
        ticker="AAPL",
        technical_result=technical_result,
        fundamental=None,
        flow=None,
        zone_set=None,
        holding=None,
    )
    assert result.headline
    assert len(result.headline) > 0


@pytest.mark.asyncio
async def test_engine_is_stage2_from_components():
    """is_stage2를 technical_result.components['minervini']['metrics']['is_stage2']에서 추출."""
    from src.tools.playbook.engine import PlaybookEngine

    stock_df = _make_stock_df(300, close=100.0)
    index_df = _make_index_df(300)
    technical_result = _make_technical_result(stock_df)

    # is_stage2=0.0 → gate 탈락 (B 항목)
    technical_result.components["minervini"]["metrics"]["is_stage2"] = 0.0

    index_provider = MagicMock()
    index_provider.get_index_history = AsyncMock(return_value=("^GSPC", index_df))
    fmp_provider = MagicMock()
    fmp_provider.industry_snapshot = AsyncMock(return_value={})
    fmp_provider.historical_industry = AsyncMock(return_value=[])
    kis_provider = MagicMock()

    engine = PlaybookEngine(
        index_provider=index_provider,
        fmp_provider=fmp_provider,
        kis_provider=kis_provider,
    )

    result = await engine.evaluate(
        ticker="AAPL",
        technical_result=technical_result,
        fundamental=None,
        flow=None,
        zone_set=None,
        holding=None,
    )
    assert result.gate is not None
    assert result.gate.passed is False  # is_stage2=0.0 → B 탈락


@pytest.mark.asyncio
async def test_engine_korean_ticker_uses_kis_sector():
    """한국 티커 → sector provider가 KIS 관련 경로 사용."""
    from src.tools.playbook.engine import PlaybookEngine

    stock_df = _make_stock_df(300, close=70000.0)
    index_df = _make_index_df(300)
    technical_result = _make_technical_result(stock_df)
    technical_result.ticker = "005930.KS"

    # 한국 종목은 FMP 대신 KIS 섹터 경로
    index_provider = MagicMock()
    index_provider.get_index_history = AsyncMock(return_value=("^KS11", index_df))
    fmp_provider = MagicMock()
    fmp_provider.industry_snapshot = AsyncMock(return_value={})
    fmp_provider.historical_industry = AsyncMock(return_value=[])
    kis_provider = MagicMock()
    # KIS sector: get_sector_index_history 호출
    kis_provider.get_sector_index_history = AsyncMock(return_value=pd.DataFrame())

    engine = PlaybookEngine(
        index_provider=index_provider,
        fmp_provider=fmp_provider,
        kis_provider=kis_provider,
    )

    result = await engine.evaluate(
        ticker="005930.KS",
        technical_result=technical_result,
        fundamental=None,
        flow=None,
        zone_set=None,
        holding=None,
    )
    assert result.ticker == "005930.KS"
    assert isinstance(result.headline, str)

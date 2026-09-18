import logging
from unittest.mock import AsyncMock

import numpy as np
import pandas as pd
import pytest

from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.tool import TechnicalAnalysisTool


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    close = 100 + np.arange(100) * 0.5
    provider.get_price_history.return_value = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": [1000000] * 100,
        },
        index=dates,
    )
    return provider


@pytest.fixture
def scorer():
    return TechnicalScorer()


@pytest.mark.asyncio
async def test_technical_tool_execute(mock_provider, scorer):
    tool = TechnicalAnalysisTool(provider=mock_provider, scorer=scorer)
    result = await tool.execute("AAPL")

    assert result.success is True
    assert result.data is not None
    assert result.data.ticker == "AAPL"
    assert result.data.components is not None
    assert len(result.data.components) > 0


@pytest.mark.asyncio
async def test_technical_tool_uses_canonical_three_year_period_by_default(mock_provider, scorer):
    tool = TechnicalAnalysisTool(provider=mock_provider, scorer=scorer)

    await tool.execute("AAPL")

    mock_provider.get_price_history.assert_awaited_once_with("AAPL", "3y")


@pytest.mark.asyncio
async def test_technical_tool_has_indicators(mock_provider, scorer):
    tool = TechnicalAnalysisTool(provider=mock_provider, scorer=scorer)
    result = await tool.execute("AAPL")

    # Support both old (indicators) and new (snapshot) fields
    snapshot = result.data.indicators or result.data.snapshot
    assert snapshot.price > 0
    assert snapshot.sma_20 is not None


@pytest.mark.asyncio
async def test_valid_last_bar_emits_no_stale_warning(mock_provider, scorer):
    """정상 경로: 마지막 봉이 유효하면 경고 없이 동작 불변."""
    tool = TechnicalAnalysisTool(provider=mock_provider, scorer=scorer)
    result = await tool.execute("AAPL")

    assert result.success is True
    assert not result.data.warnings
    mock_provider.get_quote.assert_not_awaited()


TRAILING_NAN_DATES = pd.date_range("2024-01-01", periods=130, freq="D")
DROPPED_BAR_DATE = str(TRAILING_NAN_DATES[-1].date())
LAST_VALID_DATE = str(TRAILING_NAN_DATES[-2].date())


def _provider_with_trailing_nan_close(live_price: float | None) -> AsyncMock:
    provider = AsyncMock()
    close = (100 + np.arange(130) * 0.5).astype(float)
    close[-1] = np.nan  # 최신 봉 종가 결측 (yfinance 미마감 봉)
    df = pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": [1_000_000] * 130,
        },
        index=TRAILING_NAN_DATES,
    )
    provider.get_price_history.return_value = df
    if live_price is None:
        provider.get_quote.side_effect = RuntimeError("quote unavailable")
    else:
        provider.get_quote.return_value = {"price": live_price, "previous_close": None}
    return provider


@pytest.mark.asyncio
async def test_trailing_nan_close_surfaces_stale_warning(scorer, caplog):
    provider = _provider_with_trailing_nan_close(live_price=108.80)
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)

    with caplog.at_level(logging.WARNING, logger="src.tools.technical.tool"):
        result = await tool.execute("INTC")

    assert result.success is True
    snapshot = result.data.snapshot
    # 마지막 유효 봉 종가(스테일)로 계산 — 0.0/NaN 붕괴 없음
    expected_valid_close = 100 + 128 * 0.5  # 2024-01-01 + 128 steps (index -2)
    assert snapshot.price == pytest.approx(expected_valid_close)
    assert snapshot.price > 0

    # 조용히 내보내지 않는다: 경고 부착 + 실시간가 병기
    assert result.data.warnings
    warning_text = " ".join(result.data.warnings)
    assert "108.8" in warning_text
    assert DROPPED_BAR_DATE in warning_text
    assert LAST_VALID_DATE in warning_text

    # 런타임 표면화: logger.warning
    assert any(r.levelno == logging.WARNING for r in caplog.records)


@pytest.mark.asyncio
async def test_trailing_nan_close_warns_even_when_quote_unavailable(scorer):
    provider = _provider_with_trailing_nan_close(live_price=None)
    tool = TechnicalAnalysisTool(provider=provider, scorer=scorer)

    result = await tool.execute("INTC")

    assert result.success is True
    assert result.data.warnings  # get_quote 실패해도 경고는 남는다
    assert result.data.snapshot.price > 0

"""골든 테스트: yfinance가 최신 봉을 Close=NaN으로 반환한 실제 raw 응답을 고정한다.

INTC/BE_2y.csv는 2026-09-18 실측 raw 응답으로, 마지막 봉(2026-09-17)의 OHLC가 전부 NaN이다.
이 fixture가 (a) 스테일 종가가 조용히 나가지 않고 (b) 경고로 표면화되는지, 그리고
(c) market context가 close=0.0으로 붕괴하지 않는지를 raw→최종 결과 전 구간으로 고정한다.
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from src.tools.technical.context import build_market_context
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.staleness import drop_trailing_nan_close
from src.tools.technical.tool import TechnicalAnalysisTool


FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "technical" / "stale_close"

# 실측(2026-09-18) 정답값: 마지막 유효 봉(2026-09-16) 종가 vs 실시간 get_quote
GOLDEN = {
    "INTC": {"valid_close": 101.05, "live_price": 108.80},
    "BE": {"valid_close": 270.02, "live_price": 280.76},
}
DROPPED_BAR_DATE = "2026-09-17"
LAST_VALID_DATE = "2026-09-16"


def _load_raw(ticker: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURE_DIR / f"{ticker}_2y.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


@pytest.mark.parametrize("ticker", ["INTC", "BE"])
def test_fixture_last_bar_close_is_nan(ticker):
    """계약: fixture의 마지막 봉 종가는 실제로 결측이다(가정이 깨지면 setup에서 실패)."""
    df = _load_raw(ticker)
    assert bool(df["Close"].isna().iloc[-1]) is True
    assert str(df.index[-1].date()) == DROPPED_BAR_DATE
    assert float(df["Close"].dropna().iloc[-1]) == pytest.approx(
        GOLDEN[ticker]["valid_close"], abs=0.01
    )


@pytest.mark.parametrize("ticker", ["INTC", "BE"])
def test_context_close_not_corrupted_after_guard(ticker):
    """raw→context: 정제 없이는 close=0.0으로 붕괴, 정제 후에는 마지막 유효 종가."""
    calc = IndicatorCalculator()
    raw = _load_raw(ticker)

    corrupted = build_market_context(calc.calculate(raw))
    assert corrupted.close == 0.0  # 가드가 없으면 스코어링이 오염된다(회귀 방지 문서화)

    cleaned, _ = drop_trailing_nan_close(raw)
    guarded = build_market_context(calc.calculate(cleaned))
    assert guarded.close == pytest.approx(GOLDEN[ticker]["valid_close"], abs=0.01)


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["INTC", "BE"])
async def test_stale_close_not_emitted_silently(ticker):
    expected = GOLDEN[ticker]
    provider = AsyncMock()
    provider.get_price_history.return_value = _load_raw(ticker)
    provider.get_quote.return_value = {"price": expected["live_price"], "previous_close": None}

    tool = TechnicalAnalysisTool(provider=provider, scorer=TechnicalScorer())
    result = await tool.execute(ticker)

    assert result.success is True
    # 지표 무결성: 마지막 유효 봉 종가로 계산(0.0/NaN 붕괴 없음)
    assert result.data.snapshot.price == pytest.approx(expected["valid_close"], abs=0.01)

    # 조용히 나가지 않는다: 경고 + 실시간가 병기
    assert result.data.warnings
    text = " ".join(result.data.warnings)
    assert DROPPED_BAR_DATE in text
    assert LAST_VALID_DATE in text
    assert f"{expected['live_price']:.2f}" in text

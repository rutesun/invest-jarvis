import pandas as pd

from src.tools.technical.context import build_market_context


def _context_df(close_values: list[float]) -> pd.DataFrame:
    rows = []
    for idx, close in enumerate(close_values):
        rows.append(
            {
                "Open": close - 0.5,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000 if idx < len(close_values) - 1 else 1_800_000,
                "SMA_20": close - 2.0,
                "SMA_50": close - 5.0,
                "SMA_150": close - 10.0,
                "SMA_200": close - 12.0,
                "Vol_SMA_20": 1_000_000,
                "RSI": 62.0,
                "ATR": 2.0,
                "SuperTrend_Dir": 1,
            }
        )
    return pd.DataFrame(rows)


def test_build_market_context_uptrend_state():
    df = _context_df([100 + i for i in range(30)])

    context = build_market_context(df)

    assert context.close == 129.0
    assert context.close_above_sma20 is True
    assert context.close_above_sma50 is True
    assert context.sma20_above_sma50 is True
    assert context.is_uptrend is True
    assert context.is_downtrend is False
    assert context.volume_ratio_20d == 1.8


def test_build_market_context_overextension_state():
    df = _context_df([100 + i for i in range(29)] + [150])
    df.loc[df.index[-1], "RSI"] = 78.0

    context = build_market_context(df)

    assert context.ret_1d is not None
    assert context.ret_1d >= 8.0
    assert context.is_overextended is True


def test_build_market_context_breakdown_state():
    df = _context_df([120 - i for i in range(30)])
    last = df.index[-1]
    prev = df.index[-2]
    df.loc[last, "Close"] = 80.0
    df.loc[last, "Low"] = 79.0
    df.loc[last, "SMA_20"] = 95.0
    df.loc[last, "SMA_50"] = 100.0
    df.loc[last, "SuperTrend_Dir"] = -1
    df.loc[prev, "SuperTrend_Dir"] = 1
    df.loc[last, "Volume"] = 2_000_000

    context = build_market_context(df)

    assert context.is_breakdown is True
    assert context.is_downtrend is True
    assert context.supertrend_sell_transition is True

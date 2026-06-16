import pandas as pd


def test_momentum_events_model_defaults():
    from src.tools.technical.events_models import MomentumEvents

    ev = MomentumEvents()
    assert ev.macd_cross is None
    assert ev.rsi_divergence is None
    assert ev.ud_volume_ratio is None
    assert ev.volume_trend is None
    assert ev.price_events == []
    assert ev.rs_event is None


def _df(closes, volumes):
    return pd.DataFrame(
        {"Close": closes, "Volume": volumes},
        index=pd.date_range("2026-01-01", periods=len(closes), freq="D"),
    )


def test_ud_volume_ratio_buy_pressure():
    from src.tools.technical.events import compute_ud_volume_ratio

    # closes 10,11,10,11,10,11 → 상승일 3개(vol 200×3=600), 하락일 2개(vol 100×2=200) → 3.0
    closes = [10, 11, 10, 11, 10, 11]
    volumes = [100, 200, 100, 200, 100, 200]
    assert compute_ud_volume_ratio(_df(closes, volumes), window=10) == 3.0


def test_ud_volume_ratio_no_down_days_returns_none():
    from src.tools.technical.events import compute_ud_volume_ratio

    assert compute_ud_volume_ratio(_df([10, 11, 12, 13], [100, 100, 100, 100]), window=10) is None


def test_volume_trend_rising():
    from src.tools.technical.events import compute_volume_trend

    assert compute_volume_trend(vol_sma_20=1_800_000, vol_sma_50=1_500_000) == "증가"
    assert compute_volume_trend(vol_sma_20=1_400_000, vol_sma_50=1_500_000) == "감소"
    assert compute_volume_trend(vol_sma_20=None, vol_sma_50=1_500_000) is None


def test_macd_golden_cross_with_date():
    from src.tools.technical.events import detect_macd_cross

    df = pd.DataFrame(
        {"MACD": [-1.0, -0.5, -0.2, 0.3, 0.5], "MACD_Signal": [0.0] * 5},
        index=pd.date_range("2026-06-01", periods=5, freq="D"),
    )
    cross = detect_macd_cross(df, lookback=10)
    assert cross is not None
    assert cross.cross_type == "golden"
    assert cross.date == "2026-06-04"
    assert cross.days_ago == 1


def test_macd_no_cross_returns_none():
    from src.tools.technical.events import detect_macd_cross

    df = pd.DataFrame(
        {"MACD": [1.0, 1.1, 1.2], "MACD_Signal": [0.0] * 3},
        index=pd.date_range("2026-06-01", periods=3, freq="D"),
    )
    assert detect_macd_cross(df, lookback=10) is None


def test_price_events_new_high_breakout():
    from src.tools.technical.events import detect_price_events

    n = 60
    closes = [100.0] * (n - 1) + [115.0]
    df = pd.DataFrame(
        {
            "Close": closes,
            "High": [c + 1 for c in closes],
            "High_52w": [110.0] * n,
            "Swing_Low": [float("nan")] * (n - 1) + [90.0],
        },
        index=pd.date_range("2026-04-01", periods=n, freq="D"),
    )
    events = detect_price_events(df)
    breakout = next(e for e in events if e.code == "NEW_HIGH_BREAKOUT")
    assert breakout.side == "bull"


def test_price_events_swing_low_break():
    from src.tools.technical.events import detect_price_events

    n = 60
    closes = [100.0] * (n - 1) + [85.0]
    df = pd.DataFrame(
        {
            "Close": closes,
            "High": [c + 1 for c in closes],
            "High_52w": [130.0] * n,
            "Swing_Low": [float("nan")] * (n - 2) + [90.0, float("nan")],
        },
        index=pd.date_range("2026-04-01", periods=n, freq="D"),
    )
    events = detect_price_events(df)
    brk = next(e for e in events if e.code == "SWING_LOW_BREAK")
    assert brk.side == "bear"


def test_rsi_bearish_divergence_with_date():
    from src.tools.technical.events import detect_rsi_divergence

    close = [100, 105, 101, 108, 102] + [101] * 15
    rsi = [60, 72, 64, 68, 62] + [60] * 15
    df = pd.DataFrame(
        {"Close": close, "RSI": rsi},
        index=pd.date_range("2026-05-01", periods=len(close), freq="D"),
    )
    div = detect_rsi_divergence(df)
    assert div is not None
    assert div.divergence_type == "bearish"


def test_rsi_no_divergence_returns_none():
    from src.tools.technical.events import detect_rsi_divergence

    df = pd.DataFrame(
        {"Close": list(range(100, 130)), "RSI": list(range(40, 70))},
        index=pd.date_range("2026-05-01", periods=30, freq="D"),
    )
    assert detect_rsi_divergence(df) is None


def test_build_momentum_events_assembles():
    from src.tools.technical.events import build_momentum_events
    from src.tools.technical.events_models import MomentumEvents

    n = 60
    # 상승/하락이 교대해야 ud_volume_ratio 계산 가능 (하락일 없으면 None)
    closes = [100.0 + (1 if i % 2 == 0 else -0.5) for i in range(n)]
    df = pd.DataFrame(
        {
            "Close": closes,
            "High": [c + 1 for c in closes],
            "Volume": [100 + (i % 2) * 100 for i in range(n)],
            "MACD": [0.1] * n,
            "MACD_Signal": [0.0] * n,
            "RSI": [55.0] * n,
            "High_52w": [120.0] * n,
            "Swing_Low": [float("nan")] * (n - 1) + [95.0],
        },
        index=pd.date_range("2026-04-01", periods=n, freq="D"),
    )
    ev = build_momentum_events(df, vol_sma_20=1800.0, vol_sma_50=1500.0)
    assert isinstance(ev, MomentumEvents)
    assert ev.ud_volume_ratio is not None
    assert ev.volume_trend == "증가"
    assert ev.rs_event is None  # RS 전환은 deep_dive 가 주입


def test_price_events_use_last_valid_close_when_trailing_nan():
    """당일 미완성 봉(마지막 행 Close=NaN)이 섞여도 pct가 NaN이면 안 된다."""
    from src.tools.technical.events import detect_price_events

    n = 30
    closes = [100.0 + i for i in range(n - 1)] + [float("nan")]  # 마지막 봉 미완성
    swing_low = [float("nan")] * n
    swing_low[20] = 90.0  # 스윙로우 90 → 마지막 유효 종가 128 대비 +42.2%
    df = pd.DataFrame(
        {"Close": closes, "Swing_Low": swing_low},
        index=pd.date_range("2026-04-01", periods=n, freq="D"),
    )
    events = detect_price_events(df)
    held = [e for e in events if e.code == "SWING_LOW_HELD"]
    assert held, "스윙로우 유지 이벤트가 있어야 함"
    assert "nan" not in held[0].detail.lower()
    assert "+42" in held[0].detail  # 마지막 유효 종가(128) 기준 pct

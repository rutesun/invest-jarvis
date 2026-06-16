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

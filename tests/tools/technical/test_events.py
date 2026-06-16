def test_momentum_events_model_defaults():
    from src.tools.technical.events_models import MomentumEvents

    ev = MomentumEvents()
    assert ev.macd_cross is None
    assert ev.rsi_divergence is None
    assert ev.ud_volume_ratio is None
    assert ev.volume_trend is None
    assert ev.price_events == []
    assert ev.rs_event is None

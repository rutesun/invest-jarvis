from src.tools.technical.aggregator import ScoreAggregator
from src.tools.technical.models import ComponentSignal, MarketContext


def _component(score: int, metadata: list[ComponentSignal]) -> dict:
    return {"score": score, "signals": [], "evidence": [], "metrics": {}, "signal_metadata": metadata}


def test_downtrend_reversal_is_capped_to_watch():
    components = {
        "divergence": _component(
            45,
            [
                ComponentSignal(
                    signal_type="reversal",
                    bias="bullish",
                    intent="watch",
                    severity="medium",
                    entry_eligible=False,
                    source="divergence",
                    reason="bullish divergence",
                )
            ],
        )
    }
    context = MarketContext(close=100, is_downtrend=True, rsi=35)

    result = ScoreAggregator().aggregate(components, context)

    assert result.adjusted_score <= 35
    assert result.technical_verdict.action == "watch"
    assert result.technical_verdict.new_entry_allowed is False
    assert result.technical_verdict.reasons[0] == "하락 추세의 반전 신호라 확인 필요"
    assert any(trace.rule == "downtrend_reversal_cap" for trace in result.aggregation_trace)


def test_overextended_strong_trend_becomes_hold_not_buy():
    components = {
        "minervini": _component(
            40,
            [
                ComponentSignal(
                    signal_type="trend",
                    bias="bullish",
                    intent="hold",
                    severity="medium",
                    entry_eligible=True,
                    source="minervini",
                    reason="Stage 2",
                )
            ],
        ),
        "volume": _component(
            25,
            [
                ComponentSignal(
                    signal_type="breakout",
                    bias="bullish",
                    intent="entry",
                    severity="high",
                    entry_eligible=True,
                    source="volume",
                    reason="Power Gap Up",
                )
            ],
        ),
    }
    context = MarketContext(close=100, is_uptrend=True, is_overextended=True, rsi=78, ret_5d=18)

    result = ScoreAggregator().aggregate(components, context)

    assert result.technical_verdict.action == "hold"
    assert result.technical_verdict.new_entry_allowed is False
    assert result.technical_verdict.cautions


def test_volume_breakdown_overrides_positive_score():
    components = {
        "minervini": _component(40, []),
        "risk": _component(
            -10,
            [
                ComponentSignal(
                    signal_type="breakdown",
                    bias="bearish",
                    intent="risk",
                    severity="high",
                    entry_eligible=False,
                    source="risk",
                    reason="SMA50 break",
                )
            ],
        ),
    }
    context = MarketContext(close=100, is_breakdown=True, volume_ratio_20d=1.8, is_downtrend=True)

    result = ScoreAggregator().aggregate(components, context)

    assert result.technical_verdict.action in {"reduce", "avoid"}
    assert result.technical_verdict.new_entry_allowed is False
    assert result.adjusted_score < 40


def test_aggregator_does_not_parse_signal_strings():
    components = {
        "fake": {
            "score": 90,
            "signals": ["Supertrend 매도 전환", "SMA50 이탈"],
            "evidence": [],
            "metrics": {},
            "signal_metadata": [],
        }
    }
    context = MarketContext(close=100, is_uptrend=True)

    result = ScoreAggregator().aggregate(components, context)

    assert result.adjusted_score == 90
    assert result.technical_verdict.action in {"buy", "add", "hold"}


def test_contextual_pullback_add_without_string_parsing():
    components = {
        "velocity": _component(20, []),
        "patterns": _component(
            10,
            [
                ComponentSignal(
                    signal_type="reversal",
                    bias="bullish",
                    intent="watch",
                    severity="medium",
                    entry_eligible=False,
                    source="patterns",
                    reason="Hammer",
                )
            ],
        ),
        "supertrend": _component(
            25,
            [
                ComponentSignal(
                    signal_type="trend",
                    bias="bullish",
                    intent="hold",
                    severity="medium",
                    entry_eligible=False,
                    source="supertrend",
                    reason="Supertrend 상승",
                )
            ],
        ),
    }
    context = MarketContext(
        close=100,
        is_uptrend=True,
        close_above_sma20=True,
        distance_from_20d_high_pct=-3.5,
        ret_1d=-1.2,
        ret_10d=7.4,
        supertrend_direction=1,
        is_overextended=False,
        is_breakdown=False,
    )

    result = ScoreAggregator().aggregate(components, context)

    assert result.adjusted_score == 55
    assert result.technical_verdict.action == "add"
    assert result.technical_verdict.entry_mode == "pullback_add"
    assert result.technical_verdict.confidence == "high"
    assert result.technical_verdict.new_entry_allowed is True


def test_contextual_pullback_add_blocks_downtrend():
    components = {
        "velocity": _component(30, []),
        "supertrend": _component(
            25,
            [
                ComponentSignal(
                    signal_type="trend",
                    bias="bullish",
                    intent="hold",
                    severity="medium",
                    entry_eligible=False,
                    source="supertrend",
                    reason="Supertrend 상승",
                )
            ],
        ),
    }
    context = MarketContext(
        close=100,
        is_uptrend=False,
        is_downtrend=True,
        close_above_sma20=True,
        distance_from_20d_high_pct=-3.5,
        ret_1d=-1.2,
        ret_10d=7.4,
        supertrend_direction=1,
        is_overextended=False,
        is_breakdown=False,
    )

    result = ScoreAggregator().aggregate(components, context)

    assert result.adjusted_score == 55
    assert result.technical_verdict.action == "watch"
    assert result.technical_verdict.entry_mode == "confirmation_needed"
    assert result.technical_verdict.new_entry_allowed is False

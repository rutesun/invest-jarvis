from src.tools.technical.aggregator import (
    ACCUMULATE_FLOOR,
    BOTTOMING_CEILING,
    ScoreAggregator,
)
from src.tools.technical.bottoming import BottomingStructure
from src.tools.technical.models import ComponentSignal, MarketContext


def _component(score: int, metadata: list[ComponentSignal]) -> dict:
    return {
        "score": score,
        "signals": [],
        "evidence": [],
        "metrics": {},
        "signal_metadata": metadata,
    }


def _qualifying_bottoming() -> BottomingStructure:
    return BottomingStructure(
        higher_low=True,
        bullish_divergence=True,
        volume_dry=True,
        momentum_improving=True,
    )


def test_bottoming_bonus_lifts_avoid_into_accumulate_band():
    # 깊은 마이너스 raw + 바닥 구조 충족 + 추세 확인선(SMA50) 아래 → accumulate로 완만화.
    components = {"risk": _component(-65, [])}
    context = MarketContext(close=100, is_downtrend=True, close_above_sma50=False)

    result = ScoreAggregator().aggregate(components, context, bottoming=_qualifying_bottoming())

    assert result.adjusted_score == -25  # -65 + 40(bonus), 상한(-15) 아래
    assert ACCUMULATE_FLOOR <= result.adjusted_score <= BOTTOMING_CEILING
    assert result.technical_verdict.action == "accumulate"
    assert result.technical_verdict.new_entry_allowed is False
    assert any(t.rule == "bottoming_gradient_bonus" for t in result.aggregation_trace)


def test_bottoming_bonus_never_exceeds_ceiling():
    components = {"risk": _component(-30, [])}
    context = MarketContext(close=100, is_downtrend=True, close_above_sma50=False)

    result = ScoreAggregator().aggregate(components, context, bottoming=_qualifying_bottoming())

    # -30 + 40 = 10 이지만 상한 -15로 클램프.
    assert result.adjusted_score == BOTTOMING_CEILING
    assert result.technical_verdict.action == "accumulate"


def test_deep_negative_stays_avoid_when_bonus_insufficient():
    # 적격(3신호, bonus 30)이라도 raw가 너무 깊으면 -80 + 30 = -50 < accumulate floor(-40)
    # → avoid 유지. 상한이 있어 바닥 신호만으로 avoid를 뒤집지 않는다.
    components = {"risk": _component(-80, [])}
    context = MarketContext(close=100, is_downtrend=True, close_above_sma50=False)
    bottoming = BottomingStructure(higher_low=True, volume_dry=True, bullish_divergence=True)

    result = ScoreAggregator().aggregate(components, context, bottoming=bottoming)

    assert result.adjusted_score == -50
    assert result.technical_verdict.action == "avoid"


def test_bottoming_bonus_skipped_above_sma50():
    # 이평 위(추세 확인) 종목은 바닥 가점 대상 아님 → 점수 불변.
    components = {"risk": _component(-65, [])}
    context = MarketContext(close=100, close_above_sma50=True, is_uptrend=True)

    result = ScoreAggregator().aggregate(components, context, bottoming=_qualifying_bottoming())

    assert result.adjusted_score == -65
    assert not any(t.rule == "bottoming_gradient_bonus" for t in result.aggregation_trace)


def test_bottoming_bonus_skipped_on_volume_backed_breakdown():
    # 신선한 거래량 동반 이탈(forced avoid) 앞에서는 가점 생략 — 가짜 바닥 차단.
    components = {
        "risk": _component(
            -65,
            [
                ComponentSignal(
                    signal_type="breakdown",
                    bias="bearish",
                    intent="risk",
                    severity="high",
                    source="risk",
                    reason="SMA50 break",
                )
            ],
        )
    }
    context = MarketContext(close=100, is_breakdown=True, volume_ratio_20d=1.8, is_downtrend=True)

    result = ScoreAggregator().aggregate(components, context, bottoming=_qualifying_bottoming())

    assert result.technical_verdict.action == "avoid"
    assert not any(t.rule == "bottoming_gradient_bonus" for t in result.aggregation_trace)


def test_aggregate_without_bottoming_is_unchanged():
    # 기존 호출부 하위호환: bottoming 미전달 → 종전 동작.
    components = {"risk": _component(-65, [])}
    context = MarketContext(close=100, is_downtrend=True, close_above_sma50=False)

    result = ScoreAggregator().aggregate(components, context)

    assert result.adjusted_score == -65
    assert result.technical_verdict.action == "avoid"


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


def test_negative_adjusted_avoid_reason_prioritizes_risk_over_bullish_support():
    components = {
        "patterns": _component(
            10,
            [
                ComponentSignal(
                    signal_type="support",
                    bias="bullish",
                    intent="watch",
                    severity="medium",
                    entry_eligible=False,
                    source="patterns",
                    reason="지지 confluence",
                )
            ],
        ),
        "risk": _component(-45, []),
    }
    context = MarketContext(close=100)

    result = ScoreAggregator().aggregate(components, context)

    assert result.technical_verdict.action == "avoid"
    assert result.technical_verdict.reasons[0] == "조정 점수가 -25점 미만으로 리스크 우위"
    assert "지지 confluence" in result.technical_verdict.reasons


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

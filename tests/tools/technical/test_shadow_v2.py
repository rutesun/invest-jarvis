"""A′ shadow 레이어 테스트 — 점수 vs 게이트 분리(합의안) 검증.

setup_score(움직임 품질) × regime gate(minervini 스테이지) × supertrend 방향/flip →
action_v2. 기존 action/score는 건드리지 않는 shadow 산출.
"""

from __future__ import annotations

from src.tools.technical.shadow_v2 import decide_action_v2


def _decide(**kwargs):
    base = {
        "regime": "weak",
        "st_up": False,
        "fresh_buy_flip": False,
        "setup_score": 0,
        "bottoming_watch": False,
        "overextended": False,
        "volume_breakdown": False,
        "fresh_sell_flip": False,
        "sma20_break_2d": False,
    }
    base.update(kwargs)
    return decide_action_v2(**base)


def test_weak_regime_strong_setup_with_bottoming_is_accumulate():
    action, entry = _decide(regime="weak", setup_score=45, bottoming_watch=True)
    assert action == "accumulate"
    assert entry is False


def test_weak_regime_strong_setup_without_bottoming_is_watch():
    action, entry = _decide(regime="weak", setup_score=45, bottoming_watch=False)
    assert action == "watch"
    assert entry is False


def test_stage2_up_negative_setup_holds_not_reduce():
    # 확인된 상승(Stage2+ST up)은 하루 노이즈로 음수여도 hold 유지(floor=hold). NVDA 오강등 방지.
    action, entry = _decide(regime="trend", st_up=True, setup_score=-10)
    assert action == "hold"
    assert entry is False


def test_stage2_up_severe_setup_still_holds():
    action, _ = _decide(regime="trend", st_up=True, setup_score=-35)
    assert action == "hold"


def test_stage2_up_deterioration_demotes_to_watch():
    # 음수 setup + 종가<SMA20 2거래일 지속 → 조기 경고로 watch(가격 확인형 악화).
    action, _ = _decide(
        regime="trend", st_up=True, setup_score=-10, sma20_break_2d=True
    )
    assert action == "watch"


def test_above50_negative_setup_is_reduce():
    action, _ = _decide(regime="above50", st_up=True, setup_score=-10)
    assert action == "reduce"


def test_weak_negative_setup_is_reduce():
    action, _ = _decide(regime="weak", setup_score=-10)
    assert action == "reduce"


def test_weak_severe_setup_is_avoid():
    action, _ = _decide(regime="weak", setup_score=-40, bottoming_watch=True)
    assert action == "avoid"


def test_above50_up_strong_setup_capped_to_watch():
    # SMA50은 넘었으나 Stage2 미만 → 아무리 강해도 watch 상한.
    action, entry = _decide(regime="above50", st_up=True, setup_score=50)
    assert action == "watch"
    assert entry is False


def test_stage2_up_strong_no_flip_is_hold():
    action, entry = _decide(regime="trend", st_up=True, setup_score=50)
    assert action == "hold"
    assert entry is False


def test_fresh_flip_alone_does_not_buy():
    # flip 단독 buy 제거(Round 7): 종가 돌파 없이 flip만으로는 buy 아님(hold).
    action, entry = _decide(
        regime="trend", st_up=True, fresh_buy_flip=True, setup_score=50
    )
    assert action == "hold"
    assert entry is False


def test_stage2_up_mid_setup_is_hold():
    action, _ = _decide(regime="trend", st_up=True, setup_score=25)
    assert action == "hold"


def test_stage2_up_weak_band_is_hold():
    # Stage2/up floor=hold — 약 밴드(0~19)도 hold(승자 보유). demotion 조건 없을 때.
    action, _ = _decide(regime="trend", st_up=True, setup_score=10)
    assert action == "hold"


def test_stage2_down_strong_is_watch():
    action, _ = _decide(regime="trend", st_up=False, setup_score=50)
    assert action == "watch"


def test_volume_breakdown_override_forces_avoid():
    action, entry = _decide(
        regime="trend", st_up=True, fresh_buy_flip=True, setup_score=50, volume_breakdown=True
    )
    assert action == "avoid"
    assert entry is False


def test_fresh_sell_flip_override_forces_reduce():
    action, entry = _decide(regime="trend", st_up=True, setup_score=50, fresh_sell_flip=True)
    assert action == "reduce"
    assert entry is False


def test_overextended_downgrades_buy_to_hold_no_entry():
    action, entry = _decide(
        regime="trend", st_up=True, fresh_buy_flip=True, setup_score=50, overextended=True
    )
    assert action == "hold"
    assert entry is False


def _raw_row(setup_score, regime="weak", bottoming_watch=True, st_up=False,
             volume_breakdown=False, fresh_sell_flip=False):
    """apply_hysteresis 입력용 raw ShadowScoreV2 (action_v2는 재계산되므로 placeholder)."""
    from src.tools.technical.shadow_v2 import ShadowScoreV2, _setup_band
    return ShadowScoreV2(
        setup_score=setup_score, setup_band=_setup_band(setup_score), regime=regime,
        st_up=st_up, buy_flip_age=None, fresh_buy_flip=False, bottoming_watch=bottoming_watch,
        action_v2="", new_entry_allowed_v2=False, volume_breakdown=volume_breakdown,
        fresh_sell_flip=fresh_sell_flip, overextended=False, sma20_break_2d=False,
    )


def test_hysteresis_delays_downgrade_two_days():
    from src.tools.technical.shadow_v2 import apply_hysteresis
    # weak+bottoming: 중(25)→음(-10)→음(-10)→중(25). 하향은 2일째에만 강등, 상승은 즉시.
    rows = [_raw_row(25), _raw_row(-10), _raw_row(-10), _raw_row(25)]
    out = [r.action_v2 for r in apply_hysteresis(rows)]
    assert out == ["accumulate", "accumulate", "reduce", "accumulate"]


def test_hysteresis_hard_override_immediate():
    from src.tools.technical.shadow_v2 import apply_hysteresis
    # 거래량 breakdown은 2일 확인 없이 즉시 avoid.
    rows = [_raw_row(25), _raw_row(25, volume_breakdown=True)]
    out = [r.action_v2 for r in apply_hysteresis(rows)]
    assert out == ["accumulate", "avoid"]


def test_established_weakness_true_for_sustained_below_sma50():
    import pandas as pd

    from src.tools.technical.shadow_v2 import _established_weakness
    df = pd.DataFrame({"Close": [90.0] * 10, "SMA_50": [100.0] * 10})
    assert _established_weakness(df) is True


def test_established_weakness_false_for_fresh_drop():
    import pandas as pd

    from src.tools.technical.shadow_v2 import _established_weakness
    # 최근 10일 중 8일은 위, 2일만 아래 = 갓 떨어진 상태 → 확립 아님.
    df = pd.DataFrame({"Close": [110.0] * 8 + [90.0] * 2, "SMA_50": [100.0] * 10})
    assert _established_weakness(df) is False


def test_breakout_near52_triggers_buy_even_with_low_setup():
    # 신선한 종가 신고가 돌파 + 52주고점 근처면 setup가 낮아(과매수) 도 buy (PANW형 초기돌파).
    action, entry = _decide(
        regime="trend", st_up=True, setup_score=0, fresh_breakout=True, near52=True
    )
    assert action == "buy"
    assert entry is True


def test_breakout_without_near52_does_not_buy():
    # 52주고점서 먼 돌파(하락중 20일신고가 반등)는 buy 아님.
    action, _ = _decide(
        regime="trend", st_up=True, setup_score=0, fresh_breakout=True, near52=False
    )
    assert action == "hold"


def test_breakout_buy_blocked_when_overextended():
    action, _ = _decide(
        regime="trend", st_up=True, setup_score=0, fresh_breakout=True, near52=True,
        overextended=True,
    )
    assert action == "hold"

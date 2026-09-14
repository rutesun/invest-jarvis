"""A′ shadow 레이어 테스트 — 점수 vs 게이트 분리(합의안) 검증.

setup_score(움직임 품질) × regime gate(minervini 스테이지) × supertrend 방향/flip →
action_v2. 기존 action/score는 건드리지 않는 shadow 산출.
"""

from __future__ import annotations

from src.tools.technical.shadow_v2 import decide_action_v2


def _decide(**kwargs):
    base = dict(
        regime="weak",
        st_up=False,
        fresh_buy_flip=False,
        setup_score=0,
        bottoming_watch=False,
        overextended=False,
        volume_breakdown=False,
        fresh_sell_flip=False,
    )
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


def test_negative_setup_is_reduce_regardless_of_regime():
    action, entry = _decide(regime="Stage2", st_up=True, setup_score=-10)
    assert action == "reduce"
    assert entry is False


def test_severe_negative_setup_is_avoid():
    action, _ = _decide(regime="weak", setup_score=-40, bottoming_watch=True)
    assert action == "avoid"


def test_above50_up_strong_setup_capped_to_watch():
    # SMA50은 넘었으나 Stage2 미만 → 아무리 강해도 watch 상한.
    action, entry = _decide(regime="above50", st_up=True, setup_score=50)
    assert action == "watch"
    assert entry is False


def test_stage2_up_strong_no_flip_is_hold():
    action, entry = _decide(regime="Stage2", st_up=True, setup_score=50)
    assert action == "hold"
    assert entry is False


def test_stage2_up_strong_with_fresh_flip_is_buy():
    action, entry = _decide(
        regime="Stage2", st_up=True, fresh_buy_flip=True, setup_score=50
    )
    assert action == "buy"
    assert entry is True


def test_stage2_up_mid_setup_is_hold():
    action, _ = _decide(regime="Stage2", st_up=True, setup_score=25)
    assert action == "hold"


def test_stage2_up_weak_band_is_watch():
    action, _ = _decide(regime="Stage2", st_up=True, setup_score=10)
    assert action == "watch"


def test_stage2_down_strong_is_watch():
    action, _ = _decide(regime="Stage2", st_up=False, setup_score=50)
    assert action == "watch"


def test_volume_breakdown_override_forces_avoid():
    action, entry = _decide(
        regime="Stage2", st_up=True, fresh_buy_flip=True, setup_score=50, volume_breakdown=True
    )
    assert action == "avoid"
    assert entry is False


def test_fresh_sell_flip_override_forces_reduce():
    action, entry = _decide(regime="Stage2", st_up=True, setup_score=50, fresh_sell_flip=True)
    assert action == "reduce"
    assert entry is False


def test_overextended_downgrades_buy_to_hold_no_entry():
    action, entry = _decide(
        regime="Stage2", st_up=True, fresh_buy_flip=True, setup_score=50, overextended=True
    )
    assert action == "hold"
    assert entry is False

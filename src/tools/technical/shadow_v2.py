"""A′ shadow 레이어 — 점수 vs 게이트 분리(Claude↔codex 합의안).

설계: docs/worklog/score-vs-gate-consensus.md

- setup_score = 움직임/거래량/모멘텀 컴포넌트(velocity+crsi+volume+patterns+divergence+risk)만 합산.
  추세 레짐(minervini)·방향(supertrend)은 점수에서 제외.
- regime gate = minervini 스테이지(weak/above50/Stage2). action 상한을 결정(점수 가산 X).
- supertrend = 방향(up/down)은 게이트, 매수전환은 3거래일 TTL 트리거.
- bottoming_watch = weak + 저점 높이기 + 거래량 마름 + 종가 SMA200 위(상태, 점수 가산 X).

기존 adjusted_score/action은 건드리지 않는 병행(shadow) 산출이다. 밴드는 잠정값 —
holdout 재보정 전 "점수를 눈으로 보기" 위한 것.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.tools.technical.bottoming import _detect_higher_low, _detect_volume_dry


# setup_score 밴드 (잠정 — minervini/supertrend 제외 분포 기준, holdout 재보정 대상)
SETUP_STRONG = 40
SETUP_MID = 20
SETUP_WEAK = 0
SETUP_NEGATIVE = -25  # 이 미만은 '심각'

FRESH_FLIP_MAX_AGE = 3  # supertrend 매수전환 유효 거래일

_MOVEMENT_COMPONENTS = ("velocity", "crsi", "volume", "patterns", "divergence", "risk")


@dataclass
class ShadowScoreV2:
    setup_score: int
    setup_band: str
    regime: str  # weak | above50 | Stage2
    st_up: bool
    buy_flip_age: int | None
    fresh_buy_flip: bool
    bottoming_watch: bool
    action_v2: str
    new_entry_allowed_v2: bool


def _setup_band(score: int) -> str:
    if score >= SETUP_STRONG:
        return "강"
    if score >= SETUP_MID:
        return "중"
    if score >= SETUP_WEAK:
        return "약"
    if score >= SETUP_NEGATIVE:
        return "음"
    return "심각"


def decide_action_v2(
    *,
    regime: str,
    st_up: bool,
    fresh_buy_flip: bool,
    setup_score: int,
    bottoming_watch: bool,
    overextended: bool,
    volume_breakdown: bool,
    fresh_sell_flip: bool,
) -> tuple[str, bool]:
    """regime × st × setup_band → (action, new_entry_allowed). 게이트는 상한만 적용."""
    # 선행 override (매트릭스보다 우선)
    if volume_breakdown:
        return "avoid", False
    if fresh_sell_flip:
        return "reduce", False

    band = _setup_band(setup_score)

    # 음수 밴드는 레짐 무관하게 리스크 우선
    if band == "심각":
        return "avoid", False
    if band == "음":
        return "reduce", False

    # 비음수: 레짐 게이트가 상한
    if regime == "weak":
        return ("accumulate" if bottoming_watch else "watch"), False
    if regime == "above50":
        return "watch", False

    # Stage2
    if not st_up:
        return "watch", False
    if band == "약":
        return "watch", False
    # Stage2 + up + (중|강)
    if band == "강" and fresh_buy_flip and not overextended:
        return "buy", True  # buy/add 분기는 상위(Playbook)에서 position으로 결정
    return "hold", False


def _regime(components: dict[str, dict], context) -> str:
    minervini = components.get("minervini") or {}
    metrics = minervini.get("metrics") or {}
    if metrics.get("is_stage2") == 1.0:
        return "Stage2"
    if getattr(context, "close_above_sma50", False):
        return "above50"
    return "weak"


def _buy_flip_age(df: pd.DataFrame) -> tuple[bool, int | None]:
    """(현재 up인가, 매수전환 후 경과 거래일). 전환이 관측 안 되면 age=None."""
    if "SuperTrend_Dir" not in df.columns:
        return False, None
    direction = df["SuperTrend_Dir"].to_numpy(dtype=float)
    n = len(direction)
    if n == 0 or direction[-1] != 1:
        return False, None
    count = 0
    i = n - 1
    while i >= 0 and direction[i] == 1:
        count += 1
        i -= 1
    if i < 0:
        # 관측 구간 내내 up — 신선한 전환으로 보지 않음
        return True, None
    return True, count - 1


def _bottoming_watch(regime: str, df: pd.DataFrame, context, fresh_sell_flip: bool) -> bool:
    if regime != "weak":
        return False
    if not getattr(context, "close_above_sma200", False):
        return False
    if getattr(context, "is_breakdown", False) or fresh_sell_flip:
        return False
    return _detect_higher_low(df) and _detect_volume_dry(df)


def compute_shadow_v2(df: pd.DataFrame, components: dict[str, dict], context) -> ShadowScoreV2:
    setup_score = int(
        sum(
            int((components.get(name) or {}).get("score", 0) or 0)
            for name in _MOVEMENT_COMPONENTS
        )
    )
    regime = _regime(components, context)
    st_up, buy_flip_age = _buy_flip_age(df)
    fresh_buy_flip = st_up and buy_flip_age is not None and buy_flip_age <= FRESH_FLIP_MAX_AGE
    fresh_sell_flip = bool(getattr(context, "supertrend_sell_transition", False))
    bottoming_watch = _bottoming_watch(regime, df, context, fresh_sell_flip)

    volume_breakdown = bool(
        getattr(context, "is_breakdown", False)
        and (context.volume_ratio_20d is not None and context.volume_ratio_20d >= 1.3)
    )
    overextended = bool(getattr(context, "is_overextended", False))

    action_v2, entry_v2 = decide_action_v2(
        regime=regime,
        st_up=st_up,
        fresh_buy_flip=fresh_buy_flip,
        setup_score=setup_score,
        bottoming_watch=bottoming_watch,
        overextended=overextended,
        volume_breakdown=volume_breakdown,
        fresh_sell_flip=fresh_sell_flip,
    )

    return ShadowScoreV2(
        setup_score=setup_score,
        setup_band=_setup_band(setup_score),
        regime=regime,
        st_up=st_up,
        buy_flip_age=buy_flip_age,
        fresh_buy_flip=fresh_buy_flip,
        bottoming_watch=bottoming_watch,
        action_v2=action_v2,
        new_entry_allowed_v2=entry_v2,
    )

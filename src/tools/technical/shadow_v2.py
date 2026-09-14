"""A′ shadow 레이어 — 점수 vs 게이트 분리(Claude↔codex 합의안).

설계: docs/worklog/score-vs-gate-consensus.md (Round 1~4)

- setup_score = **상태(state)만** 합산: velocity 기울기 방향, cRSI 밴드위치/squeeze, patterns VCP,
  risk 지지/저항 confluence. 일회성 **이벤트**(velocity 가속·전환점, cRSI Hook, 거래량 surge,
  breakout·candlestick, divergence)는 점수에서 제외해 trigger로만 본다(변동성 완화).
- regime gate = minervini 스테이지(weak/above50/Stage2) + supertrend 방향. action에 [floor,ceiling]
  밴드만 적용(점수 가산 X). supertrend 매수전환은 3거래일 TTL 트리거.
- bottoming_watch = weak + 저점 높이기 + 거래량 마름 + 종가 SMA200 위(상태). hard 위험에만 무효화.
- 비대칭 히스테리시스: score에 의한 하향 강등만 2거래일 확인, 회복·regime/ST 변경·hard override는 즉시.

기존 adjusted_score/action은 건드리지 않는 병행(shadow) 산출. 밴드는 잠정값(holdout 재보정 대상).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from src.tools.technical.bottoming import _detect_higher_low, _detect_volume_dry
from src.tools.technical.components.patterns import _detect_vcp
from src.tools.technical.components.velocity import SLOPE_THRESHOLD


# setup_score 밴드 (잠정 — 상태만 합산한 분포 기준, holdout 재보정 대상)
SETUP_STRONG = 40
SETUP_MID = 20
SETUP_WEAK = 0
SETUP_NEGATIVE = -25  # 이 미만은 '심각'

FRESH_FLIP_MAX_AGE = 3  # supertrend 매수전환 유효 거래일
_BAND_ORDER = {"심각": 0, "음": 1, "약": 2, "중": 3, "강": 4}


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
    # 매트릭스 입력(히스테리시스 재계산·진단용)
    volume_breakdown: bool = False
    fresh_sell_flip: bool = False
    overextended: bool = False
    sma20_break_2d: bool = False


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
    sma20_break_2d: bool = False,
) -> tuple[str, bool]:
    """regime × st × setup_band → (action, new_entry_allowed).

    게이트는 [floor, ceiling] 밴드를 정하고 setup은 그 안 위치만 결정한다. risk override만
    floor를 뚫는다(설계: score-vs-gate-consensus.md Round 3).
    """
    # 선행 override (밴드보다 우선, floor 관통)
    if volume_breakdown:
        return "avoid", False
    if fresh_sell_flip:
        return "reduce", False

    band = _setup_band(setup_score)

    if regime == "weak":
        # [avoid ... accumulate/watch]
        if band == "심각":
            return "avoid", False
        if band == "음":
            return "reduce", False
        return ("accumulate" if bottoming_watch else "watch"), False

    if regime == "above50" or (regime == "Stage2" and not st_up):
        # [reduce ... watch]
        return ("reduce" if band in ("음", "심각") else "watch"), False

    # Stage2 + ST up: floor = hold (확인된 상승은 노이즈 음수여도 보유)
    # 가격 확인형 악화: 음수 setup + 종가<SMA20 2거래일 지속 → 조기 경고 watch
    if setup_score < 0 and sma20_break_2d:
        return "watch", False
    if band == "강" and fresh_buy_flip and not overextended:
        return "buy", True  # buy/add 분기는 상위(Playbook)에서 position으로 결정
    return "hold", False


def _velocity_state(df: pd.DataFrame) -> int:
    """velocity 상태(SMA20 기울기 방향 ±10). 가속·전환점 이벤트는 제외.

    종가가 이미 SMA20 위면 하락 기울기는 지연 신호로 보고 벌점 보류(velocity.py와 동일 규율)."""
    if "SMA_20" not in df.columns:
        return 0
    ser = df["SMA_20"].dropna()
    if len(ser) < 15:
        return 0
    recent = ser.iloc[-15:].to_numpy(dtype=float)
    slope = float(np.polyfit(np.arange(5), recent[-5:], 1)[0])
    latest = recent[-1]
    if latest == 0:
        return 0
    norm_slope = (slope / latest) * 100
    if norm_slope > SLOPE_THRESHOLD:
        return 10
    if norm_slope < -SLOPE_THRESHOLD:
        price_above = "Close" in df.columns and float(df["Close"].iloc[-1]) > latest
        return 0 if price_above else -10
    return 0


def _crsi_state(df: pd.DataFrame) -> int:
    """cRSI 상태(과매도 +10 / 과매수 -10 / squeeze +5). Hook 이벤트는 제외."""
    for col in ("cRSI", "cRSI_HighBand", "cRSI_LowBand"):
        if col not in df.columns:
            return 0
    latest = df.iloc[-1]
    crsi, high, low = latest.get("cRSI"), latest.get("cRSI_HighBand"), latest.get("cRSI_LowBand")
    if pd.isna(crsi) or pd.isna(high) or pd.isna(low):
        return 0
    crsi, high, low = float(crsi), float(high), float(low)
    score = 0
    if (high - low) < 10:
        score += 5
    if crsi < low:
        score += 10
    elif crsi > high:
        score -= 10
    return score


def setup_state_score(df: pd.DataFrame, components: dict[str, dict]) -> int:
    """상태(state)만 합산한 setup 점수. 일회성 이벤트는 제외해 변동성을 낮춘다.

    - velocity: 기울기 방향 ±10
    - cRSI: 밴드 위치 ±10, squeeze +5
    - patterns: VCP +10/+20 (돌파·캔들 제외)
    - risk: 지지/저항 confluence(추세 벌점은 이미 제거됨 → risk.score = confluence)
    - volume·divergence: 상태 기여 없음(전부 이벤트)
    """
    vcp = int(_detect_vcp(df).get("score", 0) or 0)
    risk_confluence = int((components.get("risk") or {}).get("score", 0) or 0)
    return _velocity_state(df) + _crsi_state(df) + vcp + risk_confluence


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


def _close_below_sma20_streak(df: pd.DataFrame, days: int) -> bool:
    if "Close" not in df.columns or "SMA_20" not in df.columns or len(df) < days:
        return False
    close = df["Close"].to_numpy(dtype=float)[-days:]
    sma20 = df["SMA_20"].to_numpy(dtype=float)[-days:]
    return bool((close < sma20).all())


def _volume_breakdown(context) -> bool:
    return bool(
        getattr(context, "is_breakdown", False)
        and (context.volume_ratio_20d is not None and context.volume_ratio_20d >= 1.3)
    )


def _established_weakness(df: pd.DataFrame, need: int = 8, lookback: int = 10) -> bool:
    """최근 lookback 거래일 중 need일 이상 종가가 SMA50 아래 = 확립된 약세.

    고점에서 막 무너진 첫 다리(ARM류)는 아직 SMA50 아래 일수가 적어 제외되고, 수주간 다진
    진짜 바닥(BE류)만 통과한다 — dead-cat 가짜 바닥 방지."""
    if "Close" not in df.columns or "SMA_50" not in df.columns or len(df) < lookback:
        return False
    close = df["Close"].to_numpy(dtype=float)[-lookback:]
    sma50 = df["SMA_50"].to_numpy(dtype=float)[-lookback:]
    return bool(np.count_nonzero(close < sma50) >= need)


def _bottoming_watch(regime: str, df: pd.DataFrame, context, fresh_sell_flip: bool) -> bool:
    """weak + 확립된 약세 + 저점높이기 + 거래량마름 + SMA200 위. hard 위험에만 무효화.

    느슨한 is_breakdown(SMA20 아래+10일수익률 음수)까지 끄면 진짜 바닥이 깜빡이므로 제외하되,
    '확립된 약세'로 갓 무너진 종목의 가짜 바닥은 배제한다."""
    if regime != "weak":
        return False
    if not getattr(context, "close_above_sma200", False):
        return False
    if _volume_breakdown(context) or fresh_sell_flip:
        return False
    if not _established_weakness(df):
        return False
    return _detect_higher_low(df) and _detect_volume_dry(df)


def compute_shadow_v2(df: pd.DataFrame, components: dict[str, dict], context) -> ShadowScoreV2:
    """단일 바 shadow 산출(히스테리시스 미적용, as-of 결정적)."""
    setup = setup_state_score(df, components)
    regime = _regime(components, context)
    st_up, buy_flip_age = _buy_flip_age(df)
    fresh_buy_flip = st_up and buy_flip_age is not None and buy_flip_age <= FRESH_FLIP_MAX_AGE
    fresh_sell_flip = bool(getattr(context, "supertrend_sell_transition", False))
    bottoming_watch = _bottoming_watch(regime, df, context, fresh_sell_flip)
    volume_breakdown = _volume_breakdown(context)
    overextended = bool(getattr(context, "is_overextended", False))
    sma20_break_2d = _close_below_sma20_streak(df, 2)

    action_v2, entry_v2 = decide_action_v2(
        regime=regime,
        st_up=st_up,
        fresh_buy_flip=fresh_buy_flip,
        setup_score=setup,
        bottoming_watch=bottoming_watch,
        overextended=overextended,
        volume_breakdown=volume_breakdown,
        fresh_sell_flip=fresh_sell_flip,
        sma20_break_2d=sma20_break_2d,
    )

    return ShadowScoreV2(
        setup_score=setup,
        setup_band=_setup_band(setup),
        regime=regime,
        st_up=st_up,
        buy_flip_age=buy_flip_age,
        fresh_buy_flip=fresh_buy_flip,
        bottoming_watch=bottoming_watch,
        action_v2=action_v2,
        new_entry_allowed_v2=entry_v2,
        volume_breakdown=volume_breakdown,
        fresh_sell_flip=fresh_sell_flip,
        overextended=overextended,
        sma20_break_2d=sma20_break_2d,
    )


def apply_hysteresis(rows: list[ShadowScoreV2]) -> list[ShadowScoreV2]:
    """비대칭 2거래일 히스테리시스. score에 의한 하향 강등만 2일 확인하고, 상승 복귀·regime/ST
    변경·hard override(거래량 breakdown·매도전환)는 즉시 반영. 단일 바 raw 시퀀스를 받아 재산출."""
    out: list[ShadowScoreV2] = []
    prev_eff: int | None = None
    prev_regime: str | None = None
    prev_st: bool | None = None
    pending_down = 0

    for r in rows:
        hard = r.volume_breakdown or r.fresh_sell_flip
        regime_or_st_changed = prev_regime is not None and (
            r.regime != prev_regime or r.st_up != prev_st
        )
        if prev_eff is None or hard or regime_or_st_changed:
            eff = r.setup_score
            pending_down = 0
        elif _BAND_ORDER[_setup_band(r.setup_score)] >= _BAND_ORDER[_setup_band(prev_eff)]:
            eff = r.setup_score  # 상승·동일 밴드는 즉시
            pending_down = 0
        else:
            pending_down += 1  # 하향 강등은 2일 확인
            if pending_down >= 2:
                eff = r.setup_score
                pending_down = 0
            else:
                eff = prev_eff

        action, entry = decide_action_v2(
            regime=r.regime,
            st_up=r.st_up,
            fresh_buy_flip=r.fresh_buy_flip,
            setup_score=eff,
            bottoming_watch=r.bottoming_watch,
            overextended=r.overextended,
            volume_breakdown=r.volume_breakdown,
            fresh_sell_flip=r.fresh_sell_flip,
            sma20_break_2d=r.sma20_break_2d,
        )
        out.append(
            replace(
                r,
                setup_score=eff,
                setup_band=_setup_band(eff),
                action_v2=action,
                new_entry_allowed_v2=entry,
            )
        )
        prev_eff = eff
        prev_regime = r.regime
        prev_st = r.st_up

    return out

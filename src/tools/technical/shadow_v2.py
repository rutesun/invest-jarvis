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

import pandas as pd

from src.tools.technical.bottoming import (
    _detect_higher_low,
    _detect_volume_dry,
    bottoming_measurements,
)
from src.tools.technical.chart_analysis.models import FactRef, FactSelection
from src.tools.technical.components.patterns import _detect_vcp
from src.tools.technical.components.velocity import SLOPE_THRESHOLD
from src.tools.technical.context import (
    common_evidence,
    compatibility_rule_request,
    matches_common_request,
)


# setup_score 밴드. 39종목×2.5년(US+KR) 재보정:
# 상태만 합산한 setup 분포는 95%가 ≤20, buy 후보(Stage2+up+fresh flip, n=272)도 중앙값 0·최대 30이라
# 기존 STRONG=40은 buy가 절대 안 나오는 dead branch였다. buy 후보 20일 forward return이 setup≥10(중)
# 구간에서 우위(+7.3%, 중앙값 +1.7%)이고 음수 구간은 -2.3%라, STRONG=10을 buy 임계로 채택.
# 음/심각 경계(-25)는 forward상 변별이 약해 유지(리스크 규율용).
SETUP_STRONG = 10  # 강: buy 임계 (Stage2+up+fresh flip 시)
SETUP_MID = 5
SETUP_WEAK = 0
SETUP_NEGATIVE = -25  # 이 미만은 '심각'

FRESH_FLIP_MAX_AGE = 3  # supertrend 매수전환 유효 거래일
_BAND_ORDER = {"심각": 0, "음": 1, "약": 2, "중": 3, "강": 4}


@dataclass
class ShadowScoreV2:
    setup_score: int
    setup_band: str
    regime: str  # weak | above50 | trend  (trend = is_uptrend OR Stage2)
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
    fresh_breakout: bool = False
    near52: bool = False
    stage2: bool = False


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
    fresh_breakout: bool = False,
    near52: bool = False,
) -> tuple[str, bool]:
    """regime × st × setup_band → (action, new_entry_allowed).

    게이트는 [floor, ceiling] 밴드를 정하고 setup은 그 안 위치만 결정한다. risk override만
    floor를 뚫는다(설계: score-vs-gate-consensus.md Round 3·6).
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

    if regime == "above50" or (regime == "trend" and not st_up):
        # [reduce ... watch]
        return ("reduce" if band in ("음", "심각") else "watch"), False

    # trend(is_uptrend|Stage2) + ST up: floor = hold (확인된 상승은 노이즈 음수여도 보유)
    # 가격 확인형 악화: 음수 setup + 종가<SMA20 2거래일 지속 → 조기 경고 watch
    if setup_score < 0 and sma20_break_2d:
        return "watch", False
    # buy 트리거: 신선한 종가 신고가 돌파 + 52주고점 근처(진짜 돌파) + 음수 아님.
    # 돌파일은 과매수로 setup이 낮아 setup>=0만 요구(추세·ST·near52·종가돌파가 품질 담당).
    # supertrend 매수전환(fresh_flip)은 단독 buy로 쓰지 않는다 — flip-only buy는 파라볼릭 고점
    # flip 같은 꼬리 손실이 크고(ARM −29%) 성과가 약함(+0.7%). flip은 timing metadata로만 유지
    # (설계: score-vs-gate-consensus.md Round 7).
    buy_ok = not overextended and fresh_breakout and near52 and setup_score >= 0
    if buy_ok:
        return "buy", True  # buy/add 분기는 상위(Playbook)에서 position으로 결정
    return "hold", False


def _velocity_state(df: pd.DataFrame) -> int:
    """velocity 상태(SMA20 기울기 방향 ±10). 가속·전환점 이벤트는 제외.

    종가가 이미 SMA20 위면 하락 기울기는 지연 신호로 보고 벌점 보류(velocity.py와 동일 규율).
    """
    from src.tools.technical.chart_analysis._legacy_components import (
        raw_latest_close,
        velocity_slope_values,
    )

    values = velocity_slope_values(df)
    norm = values.get("norm_slope", 0)
    if norm > SLOPE_THRESHOLD:
        return 10
    if norm < -SLOPE_THRESHOLD:
        close = raw_latest_close(df)
        return 0 if close is not None and close > values["last_valid_sma20"] else -10
    return 0


def _crsi_state(df: pd.DataFrame) -> int:
    """cRSI 상태(과매도 +10 / 과매수 -10 / squeeze +5). Hook 이벤트는 제외."""
    from src.tools.technical.chart_analysis._legacy_structure import latest_values

    values = latest_values(df, ("cRSI", "cRSI_HighBand", "cRSI_LowBand"))
    value, high, low = (values.get(key) for key in ("cRSI", "cRSI_HighBand", "cRSI_LowBand"))
    return (
        0
        if None in (value, high, low)
        else (5 if high - low < 10 else 0) + (10 if value < low else -10 if value > high else 0)
    )


def setup_state_score(
    df: pd.DataFrame, components: dict[str, dict], *, common_analysis=None
) -> int:
    """상태(state)만 합산한 setup 점수. 일회성 이벤트는 제외해 변동성을 낮춘다.

    - velocity: 기울기 방향 ±10
    - cRSI: 밴드 위치 ±10, squeeze +5
    - patterns: VCP +10/+20 (돌파·캔들 제외)
    - risk: 지지/저항 confluence(추세 벌점은 이미 제거됨 → risk.score = confluence)
    - volume·divergence: 상태 기여 없음(전부 이벤트)
    """
    if common_analysis is None:
        velocity, crsi = _velocity_state(df), _crsi_state(df)
        vcp = int(_detect_vcp(df).get("score", 0) or 0)
    else:
        slope = common_evidence(df, common_analysis, "chart.velocity.legacy")
        latest = common_evidence(df, common_analysis, "chart.legacy.state_windows")["latest"]
        norm = slope.get("norm_slope", 0)
        # A-prime uses the last Close, while the Legacy component drops NaN Close.
        above = (
            slope.get("last_close") is not None
            and slope.get("last_valid_sma20") is not None
            and slope["last_close"] > slope["last_valid_sma20"]
        )
        velocity = (
            10 if norm > SLOPE_THRESHOLD else -10 if norm < -SLOPE_THRESHOLD and not above else 0
        )
        value, high, low = (latest.get(key) for key in ("cRSI", "cRSI_HighBand", "cRSI_LowBand"))
        crsi = (
            0
            if None in (value, high, low)
            else (5 if high - low < 10 else 0) + (10 if value < low else -10 if value > high else 0)
        )
        pattern = common_evidence(df, common_analysis, "chart.vcp.legacy")
        vcp = 20 if pattern.get("strong") else 10 if pattern.get("in_vcp") else 0
    risk_confluence = int((components.get("risk") or {}).get("score", 0) or 0)
    return velocity + crsi + vcp + risk_confluence


def _regime(components: dict[str, dict], context) -> str:
    """weak / above50 / trend. trend = is_uptrend(종가>SMA50 & SMA20>SMA50 & ST!=down) OR Stage2.

    Stage2 강제는 SMA150/200 지연 동안 초기 recovery 돌파를 놓친다(PANW). is_uptrend로 완화해
    확립된 상승추세면 hold/buy를 허용하되, 단순 SMA50 재탈환(미확인)은 above50에 둔다."""
    stage2 = (components.get("minervini") or {}).get("metrics", {}).get("is_stage2") == 1.0
    if stage2 or getattr(context, "is_uptrend", False):
        return "trend"
    if getattr(context, "close_above_sma50", False):
        return "above50"
    return "weak"


def _near_52w_high(components: dict[str, dict]) -> bool:
    """종가가 52주 고점 -25% 이내(진짜 돌파와 하락중 20일신고가 반등 구분)."""
    return (components.get("minervini") or {}).get("metrics", {}).get(
        "cond_within_52w_high_25pct"
    ) == 1.0


def _fresh_close_breakout(df: pd.DataFrame, lookback: int = 20) -> bool:
    """종가가 직전 lookback일 고점을 처음 상향 돌파(장중 wick 제외, 당일이 첫 돌파일)."""
    from src.tools.technical.chart_analysis._legacy_structure import nanmax_close_breakout_values

    return nanmax_close_breakout_values(df, lookback=lookback)["fresh"]


def _buy_flip_age(df: pd.DataFrame) -> tuple[bool, int | None]:
    """(현재 up인가, 매수전환 후 경과 거래일). 전환이 관측 안 되면 age=None."""
    from src.tools.technical.chart_analysis._legacy_structure import supertrend_age_values

    values = supertrend_age_values(df)
    return values["st_up"], values["buy_flip_age"]


def _close_below_sma20_streak(df: pd.DataFrame, days: int) -> bool:
    from src.tools.technical.chart_analysis._legacy_structure import below_streak_value

    return below_streak_value(df, "SMA_20", days)


def _volume_breakdown(context) -> bool:
    return bool(
        getattr(context, "is_breakdown", False)
        and (context.volume_ratio_20d is not None and context.volume_ratio_20d >= 1.3)
    )


def _established_weakness(df: pd.DataFrame, need: int = 8, lookback: int = 10) -> bool:
    """최근 lookback 거래일 중 need일 이상 종가가 SMA50 아래 = 확립된 약세.

    고점에서 막 무너진 첫 다리(ARM류)는 아직 SMA50 아래 일수가 적어 제외되고, 수주간 다진
    진짜 바닥(BE류)만 통과한다 — dead-cat 가짜 바닥 방지.
    """
    from src.tools.technical.chart_analysis._legacy_structure import below_count_value

    if not {"Close", "SMA_50"} <= set(df) or len(df) < lookback:
        return False
    return below_count_value(df, "SMA_50", lookback) >= need


def _bottoming_watch(
    regime: str, df: pd.DataFrame, context, fresh_sell_flip: bool, *, common_analysis=None
) -> bool:
    """weak + 확립된 약세 + 저점높이기 + 거래량마름 + SMA200 위. hard 위험에만 무효화.

    느슨한 is_breakdown(SMA20 아래+10일수익률 음수)까지 끄면 진짜 바닥이 깜빡이므로 제외하되,
    '확립된 약세'로 갓 무너진 종목의 가짜 바닥은 배제한다."""
    if regime != "weak":
        return False
    if not getattr(context, "close_above_sma200", False):
        return False
    if _volume_breakdown(context) or fresh_sell_flip:
        return False
    if common_analysis is not None:
        values = common_evidence(df, common_analysis, "chart.legacy.state_windows")
        if values["below_sma50_count"] < 8:
            return False
        higher_low, volume_dry = bottoming_measurements(values)
        return higher_low and volume_dry
    if not _established_weakness(df):
        return False
    return _detect_higher_low(df) and _detect_volume_dry(df)


def compute_shadow_v2(
    df: pd.DataFrame, components: dict[str, dict], context, *, common_analysis=None
) -> ShadowScoreV2:
    """단일 바 shadow 산출(히스테리시스 미적용, as-of 결정적)."""
    setup = setup_state_score(df, components, common_analysis=common_analysis)
    regime = _regime(components, context)
    stage2 = (components.get("minervini") or {}).get("metrics", {}).get("is_stage2") == 1.0
    windows = (
        common_evidence(df, common_analysis, "chart.legacy.state_windows")
        if common_analysis is not None
        else None
    )
    st_up, buy_flip_age = (
        _buy_flip_age(df) if windows is None else (windows["st_up"], windows["buy_flip_age"])
    )
    fresh_buy_flip = st_up and buy_flip_age is not None and buy_flip_age <= FRESH_FLIP_MAX_AGE
    fresh_sell_flip = bool(getattr(context, "supertrend_sell_transition", False))
    bottoming_watch = _bottoming_watch(
        regime, df, context, fresh_sell_flip, common_analysis=common_analysis
    )
    volume_breakdown = _volume_breakdown(context)
    overextended = bool(getattr(context, "is_overextended", False))
    sma20_break_2d = (
        _close_below_sma20_streak(df, 2) if windows is None else windows["below_sma20_streak"]
    )
    fresh_breakout = (
        _fresh_close_breakout(df)
        if windows is None
        else common_evidence(df, common_analysis, "chart.close_breakout.nanmax")["fresh"]
    )
    near52 = _near_52w_high(components)

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
        fresh_breakout=fresh_breakout,
        near52=near52,
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
        fresh_breakout=fresh_breakout,
        near52=near52,
        stage2=stage2,
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
            fresh_breakout=r.fresh_breakout,
            near52=r.near52,
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


# Raw setup measurements plus the existing component/context values actually read above.
APRIME_RULE_IDS = (
    "chart.velocity.legacy",
    "chart.vcp.legacy",
    "chart.legacy.state_windows",
    "chart.context.breakdown",
    "chart.close_breakout.nanmax",
    "chart.stage2.minervini",
    "legacy.confluence",
)
_APRIME_UNUSED_FAMILIES = {
    "chart.crsi.legacy": "APRIME_CURRENT_CRSI_FROM_STATE_WINDOWS",
    "chart.supertrend.legacy": "APRIME_SUPERTREND_FROM_STATE_WINDOWS",
    "chart.legacy.patterns_extra": "APRIME_PATTERN_EVENTS_NOT_USED",
    "chart.legacy.volume_extra": "APRIME_VOLUME_COMPONENT_NOT_USED",
    "chart.pocket_pivot.down_candle": "APRIME_VOLUME_COMPONENT_NOT_USED",
    "chart.power_gap": "APRIME_VOLUME_COMPONENT_NOT_USED",
    "legacy.divergence": "APRIME_DIVERGENCE_NOT_USED",
}


def shadow_fact_selections(analysis, components):
    """Audit A-prime's actual dependency map independently of whether a condition is true."""
    selections = []
    for item in analysis.items:
        if item.rule_id not in APRIME_RULE_IDS and item.rule_id not in _APRIME_UNUSED_FAMILIES:
            continue
        if not matches_common_request(item, compatibility_rule_request(item.rule_id)):
            selected, reason = False, "APRIME_FACT_VARIANT_NOT_SELECTED"
        elif item.rule_id in _APRIME_UNUSED_FAMILIES:
            selected, reason = False, _APRIME_UNUSED_FAMILIES[item.rule_id]
        elif item.state == "UNAVAILABLE":
            selected = False
            reason = "APRIME_FACT_" + next(iter(item.evidence.get("reasons", ())), "UNAVAILABLE")
        elif item.rule_id == "chart.stage2.minervini" and not (
            components.get("minervini") or {}
        ).get("metrics"):
            selected, reason = False, "APRIME_MINERVINI_COMPONENT_UNAVAILABLE"
        elif item.rule_id == "legacy.confluence" and not (components.get("risk") or {}).get(
            "metrics"
        ):
            selected, reason = False, "APRIME_RISK_COMPONENT_UNAVAILABLE"
        else:
            selected, reason = True, "APRIME_CONSUMED"
        selections.append(FactSelection(FactRef(analysis.analysis_id, item.id), selected, reason))
    return tuple(selections)

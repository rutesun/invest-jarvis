"""바닥 다지기(bottoming) 구조 탐지.

추세 확인형 adjusted score는 종가가 SMA50 아래면 저점을 계단식으로 높여도 −50~−90에
고정된다. 이 모듈은 "매수 신호"가 아니라 **건설적 바닥 구조**(저점 높이기·강세
다이버전스·거래량 마름·모멘텀 개선)를 as-of 안전하게 계량해, aggregator가 avoid를
accumulate 밴드까지만 완만히 끌어올릴 수 있게 한다.

가중치·상한은 `BottomingThresholds` 상수로 노출한다(튜닝 대상). 점수→액션 밴드 정책
(ceiling·accumulate floor)은 aggregator가 소유한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.tools.technical.models import ComponentSignal


class BottomingThresholds:
    """바닥 구조 탐지·가점 임계값 (평가세트로 튜닝)."""

    # 저점 높이기 룩백. 짧은 5/10 창은 하락 추세의 dead-cat 반등에도 True가 돼
    # 가짜 바닥을 만든다(LULU 하락 구간 오검출). 최근 10일 저점이 직전 30일 저점보다
    # 높은가로 늘려, 지속적으로 신저점을 깨는 하락주를 배제한다(평가세트로 튜닝).
    HIGHER_LOW_RECENT = 10
    HIGHER_LOW_PRIOR = 30

    # 거래량 마름: 최근 평균 거래량이 직전 구간 평균 대비 이 비율 미만이면 "마름"
    VOLUME_DRY_RECENT = 5
    VOLUME_DRY_PRIOR = 20
    VOLUME_DRY_RATIO = 0.85

    # 모멘텀 개선: velocity SMA20 기울기 변화율(slope_change)이 이 값 초과면 개선
    MOMENTUM_MIN_SLOPE_CHANGE = 0.0

    # 후보 자격 최소 신호 수. 2는 하락 추세 반등에 과검출 → 3으로 "동시 충족"을 요구
    # (평가세트: LULU 하락 구간 가짜 accumulate 8일→0일, BE 바닥 그라데이션은 유지).
    MIN_SIGNALS = 3

    # 가점 가중치 (신호별). 결과 상한은 aggregator BOTTOMING_CEILING이 별도로 통제.
    W_HIGHER_LOW = 12
    W_BULLISH_DIV = 10
    W_VOLUME_DRY = 8
    W_MOMENTUM = 10
    BONUS_MAX = 40


@dataclass
class BottomingStructure:
    """한 시점의 바닥 구조 상태. 예측이 아니라 완만화·조기 관찰 보조용."""

    higher_low: bool = False
    bullish_divergence: bool = False
    volume_dry: bool = False
    momentum_improving: bool = False

    @property
    def signal_count(self) -> int:
        return sum(
            [
                self.higher_low,
                self.bullish_divergence,
                self.volume_dry,
                self.momentum_improving,
            ]
        )

    @property
    def qualifies(self) -> bool:
        return self.signal_count >= BottomingThresholds.MIN_SIGNALS

    @property
    def bonus(self) -> int:
        """상한 있는 바닥 가점. 후보 자격 미달이면 0(단발 신호 누수 방지)."""
        if not self.qualifies:
            return 0
        raw = (
            self.higher_low * BottomingThresholds.W_HIGHER_LOW
            + self.bullish_divergence * BottomingThresholds.W_BULLISH_DIV
            + self.volume_dry * BottomingThresholds.W_VOLUME_DRY
            + self.momentum_improving * BottomingThresholds.W_MOMENTUM
        )
        return int(min(raw, BottomingThresholds.BONUS_MAX))


def _detect_higher_low(df: pd.DataFrame) -> bool:
    recent = BottomingThresholds.HIGHER_LOW_RECENT
    prior = BottomingThresholds.HIGHER_LOW_PRIOR
    n = len(df)
    if n < recent + prior or "Low" not in df.columns:
        return False
    low = df["Low"].to_numpy(dtype=float)
    recent_low = np.nanmin(low[n - recent : n])
    prior_low = np.nanmin(low[n - recent - prior : n - recent])
    return bool(np.isfinite(recent_low) and np.isfinite(prior_low) and recent_low > prior_low)


def _detect_volume_dry(df: pd.DataFrame) -> bool:
    recent = BottomingThresholds.VOLUME_DRY_RECENT
    prior = BottomingThresholds.VOLUME_DRY_PRIOR
    n = len(df)
    if n < recent + prior or "Volume" not in df.columns:
        return False
    volume = df["Volume"].to_numpy(dtype=float)
    recent_avg = np.nanmean(volume[n - recent : n])
    prior_avg = np.nanmean(volume[n - recent - prior : n - recent])
    if not np.isfinite(recent_avg) or not np.isfinite(prior_avg) or prior_avg <= 0:
        return False
    return bool(recent_avg < BottomingThresholds.VOLUME_DRY_RATIO * prior_avg)


def _detect_bullish_divergence(components: dict[str, dict]) -> bool:
    divergence = components.get("divergence") or {}
    for item in divergence.get("signal_metadata", []):
        bias = item.bias if isinstance(item, ComponentSignal) else item.get("bias")
        signal_type = (
            item.signal_type if isinstance(item, ComponentSignal) else item.get("signal_type")
        )
        if bias == "bullish" and signal_type == "reversal":
            return True
    return False


def _detect_momentum_improving(components: dict[str, dict]) -> bool:
    velocity = components.get("velocity") or {}
    metrics = velocity.get("metrics") or {}
    slope_change = metrics.get("slope_change")
    if slope_change is None:
        return False
    return float(slope_change) > BottomingThresholds.MOMENTUM_MIN_SLOPE_CHANGE


def detect_bottoming_structure(
    df: pd.DataFrame | None,
    components: dict[str, dict],
    context=None,
) -> BottomingStructure:
    """계산 완료된 지표 DataFrame + 컴포넌트 결과에서 바닥 구조를 산출."""
    if df is None or df.empty:
        return BottomingStructure()

    return BottomingStructure(
        higher_low=_detect_higher_low(df),
        volume_dry=_detect_volume_dry(df),
        bullish_divergence=_detect_bullish_divergence(components),
        momentum_improving=_detect_momentum_improving(components),
    )

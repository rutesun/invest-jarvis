"""턴어라운드 신호 스코어러.

하락에서 반등이 시작된 종목을 표면화하는 도구. **예측 알파가 아니다** —
백테스트상 이 신호 자체는 나이브 기준선("3개월 저점 대비 +10% 반등")을
이기지 못한다. 목적은 후보를 기계적으로 발굴해 사용자가 기사·시장 상황
같은 판단을 얹을 수 있게 하는 것이다. 그래서 마커 내역·check 확인 상태·
손절선을 함께 제공한다.

4개 마커(모두 as-of 안전, lookahead 없음)를 점수화(AND 아님):
- oversold_rebound: 급락(60일 고점 대비 -15%) 중 cRSI 과매도 훅업
- ma_reclaim: 종가가 20/50일선을 상향 돌파
- volume_surge: 거래량 20일평균 1.5배 동반 양봉
- higher_low: 최근 저점 > 이전 저점

관련 설계/검증: docs/superpowers/specs/2026-08-24-bottom-watch-design.md,
docs/worklog/bottom-watch-signal.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# 튜닝 파라미터 (검증 결과 상수로 분리)
TURNAROUND_WINDOW = 7  # 마커 발화 룩백(거래일)
OVERSOLD_CRSI = 35.0
DECLINE_RATIO = 0.85  # 60일 고점 대비 -15%
DECLINE_LOOKBACK = 60
VOLUME_MULT = 1.5
WEAK_LOOKBACK = 20  # 약세 맥락(50일선 아래) 확인 룩백
HIGHER_LOW_RECENT = 5
HIGHER_LOW_PRIOR = 10
DEFAULT_THRESHOLD = 2  # 후보로 볼 최소 마커 수

MARKER_LABELS: dict[str, str] = {
    "oversold_rebound": "급락 후 과매도 반등",
    "ma_reclaim": "20/50일선 재탈환",
    "volume_surge": "거래량 수반 양봉",
    "higher_low": "저점 높이기",
}

_REQUIRED_COLUMNS = (
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "SMA_20",
    "SMA_50",
    "Vol_SMA_20",
    "cRSI",
    "cRSI_LowBand",
    "SuperTrend_Dir",
)


@dataclass
class TurnaroundSignal:
    """한 시점의 턴어라운드 상태. 예측이 아니라 발굴·해석·실행 보조용."""

    score: int = 0
    markers: list[str] = field(default_factory=list)
    is_candidate: bool = False
    confirmed: bool = False  # check(supertrend)가 이미 추세 on인가
    stop_level: float | None = None  # 최근 스윙 저점(직전 저점)
    stop_pct: float | None = None  # 현재가 대비 손절까지 하락률(%)
    close: float | None = None

    @property
    def marker_labels(self) -> list[str]:
        return [MARKER_LABELS.get(name, name) for name in self.markers]

    def summary_line(self) -> str:
        """CLI/리포트 한 줄 표현."""
        if self.score == 0:
            return "턴어라운드: 없음"
        labels = " · ".join(self.marker_labels)
        status = "check 확인됨(추세 on)" if self.confirmed else "check 미확인(소량 테스트)"
        parts = [f"턴어라운드 {self.score}/4", f"[{labels}]", status]
        if self.stop_level is not None and self.stop_pct is not None:
            parts.append(f"손절 {self.stop_level:,.0f}({self.stop_pct:+.1f}%)")
        parts.append("★후보" if self.is_candidate else "관찰")
        return " · ".join(parts)


def score_turnaround(
    df: pd.DataFrame | None,
    threshold: int = DEFAULT_THRESHOLD,
) -> TurnaroundSignal:
    """계산 완료된 지표 DataFrame에서 최신 바 기준 턴어라운드 신호를 산출.

    df는 IndicatorCalculator.calculate() 결과(또는 TechnicalResult.raw_dataframe)여야
    하며 _REQUIRED_COLUMNS를 포함해야 한다. 부족하면 빈 신호를 반환한다(조용한
    오작동 방지).
    """
    if df is None or df.empty:
        return TurnaroundSignal()
    if any(col not in df.columns for col in _REQUIRED_COLUMNS):
        return TurnaroundSignal()

    n = len(df)
    if n < 2:
        return TurnaroundSignal()

    close = df["Close"].to_numpy(dtype=float)
    open_ = df["Open"].to_numpy(dtype=float)
    high = df["High"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    volume = df["Volume"].to_numpy(dtype=float)
    sma20 = df["SMA_20"].to_numpy(dtype=float)
    sma50 = df["SMA_50"].to_numpy(dtype=float)
    vol_sma = df["Vol_SMA_20"].to_numpy(dtype=float)
    crsi = df["cRSI"].to_numpy(dtype=float)
    low_band = df["cRSI_LowBand"].to_numpy(dtype=float)
    st_dir = df["SuperTrend_Dir"].to_numpy(dtype=float)

    window = min(TURNAROUND_WINDOW, n - 1)
    window_start = n - window
    markers: list[str] = []

    # M1 급락 후 과매도 반등: 훅업(cRSI 하단밴드 상향) + 과매도 + 급락 상태
    for j in range(max(1, window_start), n):
        hook_up = crsi[j - 1] < low_band[j] and crsi[j] > low_band[j]
        if not hook_up or not (crsi[j] < OVERSOLD_CRSI):
            continue
        peak = np.nanmax(high[max(0, j - DECLINE_LOOKBACK) : j + 1])
        if np.isfinite(peak) and close[j] <= DECLINE_RATIO * peak:
            markers.append("oversold_rebound")
            break

    # M2 20/50일선 재탈환: 상향 돌파(전일 아래 → 당일 위)
    for j in range(max(1, window_start), n):
        reclaim_20 = close[j] > sma20[j] and close[j - 1] <= sma20[j - 1]
        reclaim_50 = close[j] > sma50[j] and close[j - 1] <= sma50[j - 1]
        if reclaim_20 or reclaim_50:
            markers.append("ma_reclaim")
            break

    # M3 거래량 수반 양봉
    for j in range(window_start, n):
        if close[j] > open_[j] and vol_sma[j] > 0 and volume[j] > VOLUME_MULT * vol_sma[j]:
            markers.append("volume_surge")
            break

    # M4 저점 높이기(as-of 안전): 최근 저점 > 이전 저점
    if n >= HIGHER_LOW_RECENT + HIGHER_LOW_PRIOR:
        recent_low = np.nanmin(low[n - HIGHER_LOW_RECENT : n])
        prior_low = np.nanmin(low[n - HIGHER_LOW_RECENT - HIGHER_LOW_PRIOR : n - HIGHER_LOW_RECENT])
        if np.isfinite(recent_low) and np.isfinite(prior_low) and recent_low > prior_low:
            markers.append("higher_low")

    score = len(markers)

    # 약세 맥락: 최근 WEAK_LOOKBACK 거래일 중 50일선 아래였던 적이 있어야
    # (상승추세 중 눌림이 아니라 하락에서의 반등만 후보로)
    weak_slice = slice(max(0, n - WEAK_LOOKBACK), n)
    weak_context = bool(np.any(close[weak_slice] < sma50[weak_slice]))

    confirmed = bool(st_dir[n - 1] == 1)

    recent_low = float(np.nanmin(low[window_start:n]))
    last_close = float(close[n - 1])
    stop_level = recent_low if np.isfinite(recent_low) else None
    stop_pct = (
        round((stop_level / last_close - 1) * 100, 1)
        if stop_level is not None and last_close
        else None
    )

    return TurnaroundSignal(
        score=score,
        markers=markers,
        is_candidate=score >= threshold and weak_context,
        confirmed=confirmed,
        stop_level=stop_level,
        stop_pct=stop_pct,
        close=last_close,
    )

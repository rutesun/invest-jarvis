from __future__ import annotations

import pandas as pd

from src.tools.technical.events_models import (
    MacdCross,
    MomentumEvents,
    PriceEvent,
    RsiDivergence,
)


def compute_ud_volume_ratio(df: pd.DataFrame, window: int = 50) -> float | None:
    """최근 window일 상승일 거래량 합 ÷ 하락일 거래량 합. 하락일 없으면 None."""
    if "Close" not in df.columns or "Volume" not in df.columns or len(df) < 2:
        return None
    recent = df.tail(window)
    prev_close = recent["Close"].shift(1)
    up_vol = float(recent.loc[recent["Close"] > prev_close, "Volume"].sum())
    down_vol = float(recent.loc[recent["Close"] < prev_close, "Volume"].sum())
    if down_vol == 0:
        return None
    return round(up_vol / down_vol, 2)


def compute_volume_trend(vol_sma_20: float | None, vol_sma_50: float | None) -> str | None:
    """거래량 추세: 20일 평균 vs 50일 평균. ±2% 이내는 횡보."""
    if vol_sma_20 is None or vol_sma_50 is None or vol_sma_50 == 0:
        return None
    ratio = vol_sma_20 / vol_sma_50
    if ratio > 1.02:
        return "증가"
    if ratio < 0.98:
        return "감소"
    return "횡보"


def detect_macd_cross(df: pd.DataFrame, lookback: int = 60) -> MacdCross | None:
    """최근 lookback일 내 가장 최근 MACD-시그널 교차. 없으면 None."""
    if "MACD" not in df.columns or "MACD_Signal" not in df.columns:
        return None
    recent = df.tail(lookback).dropna(subset=["MACD", "MACD_Signal"])
    if len(recent) < 2:
        return None
    diff = recent["MACD"] - recent["MACD_Signal"]
    sign = diff.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    for i in range(len(sign) - 1, 0, -1):
        cur, prev = sign.iloc[i], sign.iloc[i - 1]
        if cur != 0 and prev != 0 and cur != prev:
            cross_date = recent.index[i]
            days_ago = len(df) - 1 - df.index.get_loc(cross_date)
            return MacdCross(
                cross_type="golden" if cur > 0 else "dead",
                date=cross_date.strftime("%Y-%m-%d"),
                days_ago=int(days_ago),
                macd=round(float(recent["MACD"].iloc[i]), 4),
                signal=round(float(recent["MACD_Signal"].iloc[i]), 4),
            )
    return None


def detect_price_events(df: pd.DataFrame) -> list[PriceEvent]:
    """신고가 돌파/실패 + 스윙로우 이탈/유지 사건. raw_dataframe 컬럼 사용."""
    events: list[PriceEvent] = []
    if "Close" not in df.columns:
        return events

    # 당일 미완성 봉(마지막 행 Close=NaN)이 섞일 수 있어 마지막 유효 봉 기준으로 본다.
    df = df[df["Close"].notna()]
    if len(df) < 2:
        return events

    last_close = float(df["Close"].iloc[-1])
    last_date = df.index[-1].strftime("%Y-%m-%d")

    if "High_52w" in df.columns and not pd.isna(df["High_52w"].iloc[-2]):
        prev_high_52w = float(df["High_52w"].iloc[-2])
        if last_close > prev_high_52w:
            events.append(
                PriceEvent(
                    code="NEW_HIGH_BREAKOUT",
                    side="bull",
                    headline="52주 신고가 돌파",
                    detail=f"종가 {last_close:.2f} > 직전 52주 고가 {prev_high_52w:.2f}",
                    date=last_date,
                    days_ago=0,
                )
            )
        elif "High" in df.columns:
            last_high = float(df["High"].iloc[-1])
            if last_high > prev_high_52w >= last_close:
                events.append(
                    PriceEvent(
                        code="NEW_HIGH_FAIL",
                        side="bear",
                        headline="신고가 돌파 실패",
                        detail=f"장중 {last_high:.2f} 신고가 터치 후 종가 {last_close:.2f} 마감",
                        date=last_date,
                        days_ago=0,
                    )
                )

    if "Swing_Low" in df.columns:
        swing_lows = df["Swing_Low"].dropna()
        if not swing_lows.empty:
            recent_swing_low = float(swing_lows.iloc[-1])
            if last_close < recent_swing_low:
                events.append(
                    PriceEvent(
                        code="SWING_LOW_BREAK",
                        side="bear",
                        headline="스윙로우 이탈",
                        detail=f"종가 {last_close:.2f} < 스윙로우 {recent_swing_low:.2f}",
                        date=last_date,
                        days_ago=0,
                    )
                )
            else:
                pct = (last_close - recent_swing_low) / recent_swing_low * 100
                events.append(
                    PriceEvent(
                        code="SWING_LOW_HELD",
                        side="neutral",
                        headline="스윙로우 유지",
                        detail=f"스윙로우 {recent_swing_low:.2f} 대비 {pct:+.1f}% (이탈 없음)",
                        date=swing_lows.index[-1].strftime("%Y-%m-%d"),
                    )
                )

    return events


def _find_peaks(values: list[float]) -> list[int]:
    """local maxima 인덱스. plateau 대응: 왼쪽은 >, 오른쪽은 >= 로 평탄한 고점도 포착."""
    peaks = []
    for i in range(1, len(values) - 1):
        if values[i] > values[i - 1] and values[i] >= values[i + 1]:
            peaks.append(i)
    return peaks


def _find_troughs(values: list[float]) -> list[int]:
    """local minima 인덱스. plateau 대응: 왼쪽은 <, 오른쪽은 <= 로 평탄한 저점도 포착."""
    troughs = []
    for i in range(1, len(values) - 1):
        if values[i] < values[i - 1] and values[i] <= values[i + 1]:
            troughs.append(i)
    return troughs


def detect_rsi_divergence(df: pd.DataFrame, window: int = 20) -> RsiDivergence | None:
    """최근 window일 가격-RSI 다이버전스. bearish는 고점끼리, bullish는 저점끼리 비교."""
    if "RSI" not in df.columns or "Close" not in df.columns or len(df) < window:
        return None
    # 당일 미완성 봉(trailing NaN)이 peak/trough 비교를 무력화하지 않도록 제거
    recent = df.tail(window).dropna(subset=["Close", "RSI"]).reset_index()
    if len(recent) < 2:
        return None
    date_col = recent.columns[0]
    closes = recent["Close"].tolist()
    rsis = recent["RSI"].tolist()

    # Bearish: 가격 고점 상승 + RSI 고점 하락 (고점끼리 비교)
    price_peaks, rsi_peaks = _find_peaks(closes), _find_peaks(rsis)
    if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
        pl, pp = price_peaks[-1], price_peaks[-2]
        rl, rp = rsi_peaks[-1], rsi_peaks[-2]
        if closes[pl] > closes[pp] and rsis[rl] < rsis[rp]:
            return RsiDivergence(
                divergence_type="bearish",
                date=recent[date_col].iloc[pl].strftime("%Y-%m-%d"),
                days_ago=int(len(recent) - 1 - pl),
                detail=f"가격 고점 상승, RSI 고점 하락 ({rsis[rp]:.0f}→{rsis[rl]:.0f})",
            )

    # Bullish: 가격 저점 하락 + RSI 저점 상승 (저점끼리 비교)
    price_troughs, rsi_troughs = _find_troughs(closes), _find_troughs(rsis)
    if len(price_troughs) >= 2 and len(rsi_troughs) >= 2:
        pl, pp = price_troughs[-1], price_troughs[-2]
        rl, rp = rsi_troughs[-1], rsi_troughs[-2]
        if closes[pl] < closes[pp] and rsis[rl] > rsis[rp]:
            return RsiDivergence(
                divergence_type="bullish",
                date=recent[date_col].iloc[pl].strftime("%Y-%m-%d"),
                days_ago=int(len(recent) - 1 - pl),
                detail=f"가격 저점 하락, RSI 저점 상승 ({rsis[rp]:.0f}→{rsis[rl]:.0f})",
            )
    return None


_SR_PROXIMITY_PCT = 1.0  # within 1% triggers "테스트 중" event


def detect_sr_proximity_events(
    snapshot_dict: dict, *, threshold_pct: float = _SR_PROXIMITY_PCT
) -> list[PriceEvent]:
    """피봇/지지/저항 근접 이벤트. 현재가가 threshold_pct% 이내면 '테스트 중' 사건 생성."""
    events: list[PriceEvent] = []
    price = snapshot_dict.get("price")
    if price is None or price <= 0:
        return events

    levels = [
        ("피봇", snapshot_dict.get("pivot")),
        ("지지 S1", snapshot_dict.get("support_s1")),
        ("저항 R1", snapshot_dict.get("resistance_r1")),
    ]
    for label, level in levels:
        if level is None or level <= 0:
            continue
        dist_pct = abs(price - level) / level * 100
        if dist_pct <= threshold_pct:
            side = "bull" if price >= level else "bear"
            above_below = "위" if price >= level else "아래"
            events.append(
                PriceEvent(
                    code="SR_TEST",
                    side=side,
                    headline=f"{label} 테스트 중",
                    detail=f"현재가 {price:.2f}, {label} {level:.2f} ({above_below}, 거리 {dist_pct:.1f}%)",
                )
            )
    return events


def build_momentum_events(
    df: pd.DataFrame,
    *,
    vol_sma_20: float | None,
    vol_sma_50: float | None,
    snapshot_dict: dict | None = None,
) -> MomentumEvents:
    """raw_dataframe + 거래량 SMA로 신규 사건 일괄 감지. RS 전환은 deep_dive 가 주입."""
    sr_events = detect_sr_proximity_events(snapshot_dict) if snapshot_dict else []
    return MomentumEvents(
        macd_cross=detect_macd_cross(df),
        rsi_divergence=detect_rsi_divergence(df),
        ud_volume_ratio=compute_ud_volume_ratio(df),
        volume_trend=compute_volume_trend(vol_sma_20, vol_sma_50),
        price_events=detect_price_events(df) + sr_events,
        rs_event=None,
    )

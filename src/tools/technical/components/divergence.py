import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from src.tools.technical.models import ComponentResult


def analyze_divergence(df: pd.DataFrame) -> ComponentResult:
    """Analyze price/indicator divergence patterns."""
    if df.empty or len(df) < 50:
        return ComponentResult(
            signals=[], evidence=["데이터 부족 (50일 이상 필요)"], metrics={}, score=0,
        )

    # Check required columns
    if "Close" not in df.columns or "RSI" not in df.columns:
        return ComponentResult(
            signals=[], evidence=["필수 지표 없음"], metrics={}, score=0,
        )

    signals = []
    evidence = []
    metrics = {}
    score = 0

    # Detect price peaks (swing highs/lows)
    price_values = df["Close"].values
    price_highs_idx = argrelextrema(price_values, np.greater, order=5)[0]
    price_lows_idx = argrelextrema(price_values, np.less, order=5)[0]

    # Detect RSI peaks
    rsi_values = df["RSI"].fillna(50).values
    rsi_highs_idx = argrelextrema(rsi_values, np.greater, order=5)[0]
    rsi_lows_idx = argrelextrema(rsi_values, np.less, order=5)[0]

    metrics["price_highs_count"] = len(price_highs_idx)
    metrics["price_lows_count"] = len(price_lows_idx)
    metrics["rsi_highs_count"] = len(rsi_highs_idx)
    metrics["rsi_lows_count"] = len(rsi_lows_idx)

    # Bearish divergence (가격 고점↑, RSI 고점↓)
    bearish_div = _detect_bearish_divergence(
        df, price_highs_idx, rsi_highs_idx, price_values, rsi_values
    )
    if bearish_div:
        signals.append(bearish_div["signal"])
        evidence.append(bearish_div["evidence"])
        score += bearish_div["score"]

    # Bullish divergence (가격 저점↓, RSI 저점↑)
    bullish_div = _detect_bullish_divergence(
        df, price_lows_idx, rsi_lows_idx, price_values, rsi_values
    )
    if bullish_div:
        signals.append(bullish_div["signal"])
        evidence.append(bullish_div["evidence"])
        score += bullish_div["score"]

    # MACD divergence (if available)
    if "MACD_12_26_9" in df.columns:
        macd_div = _detect_macd_divergence(df, price_highs_idx, price_lows_idx, price_values)
        if macd_div:
            signals.append(macd_div["signal"])
            evidence.append(macd_div["evidence"])
            score += macd_div["score"]

    # cRSI divergence (if available)
    if "cRSI" in df.columns:
        crsi_div = _detect_crsi_divergence(df, price_highs_idx, price_lows_idx, price_values)
        if crsi_div:
            signals.append(crsi_div["signal"])
            evidence.append(crsi_div["evidence"])
            score += crsi_div["score"]
            # Stronger signal if both RSI and cRSI agree
            if (bearish_div and "bearish" in crsi_div["signal"].lower()) or \
               (bullish_div and "bullish" in crsi_div["signal"].lower()):
                signals.append("RSI + cRSI 다이버전스 일치 (강력)")
                score = int(score * 1.5)

    return ComponentResult(
        signals=signals, evidence=evidence, metrics=metrics, score=score,
    )


def _detect_bearish_divergence(df, price_highs_idx, rsi_highs_idx, price_values, rsi_values):
    """Detect bearish divergence: price making higher highs, RSI making lower highs."""
    if len(price_highs_idx) < 2 or len(rsi_highs_idx) < 2:
        return None

    # Get last 2 price peaks
    recent_price_peaks = price_highs_idx[-2:]
    if recent_price_peaks[-1] < len(price_values) - 10:
        return None  # Too old

    # Find corresponding RSI peaks (within 5 bars)
    rsi_peaks = []
    for price_peak in recent_price_peaks:
        nearby_rsi = [idx for idx in rsi_highs_idx if abs(idx - price_peak) <= 5]
        if nearby_rsi:
            rsi_peaks.append(nearby_rsi[0])

    if len(rsi_peaks) < 2:
        return None

    # Check divergence
    price1, price2 = price_values[recent_price_peaks[0]], price_values[recent_price_peaks[1]]
    rsi1, rsi2 = rsi_values[rsi_peaks[0]], rsi_values[rsi_peaks[1]]

    if price2 > price1 and rsi2 < rsi1:
        strength = ((price2 - price1) / price1) * 100
        rsi_diff = rsi1 - rsi2
        return {
            "signal": "약세 다이버전스 (Bearish Divergence)",
            "evidence": f"가격 고점 상승 ({price1:.2f}→{price2:.2f}, +{strength:.1f}%), RSI 고점 하락 ({rsi1:.1f}→{rsi2:.1f}, -{rsi_diff:.1f})",
            "score": -15,
        }

    return None


def _detect_bullish_divergence(df, price_lows_idx, rsi_lows_idx, price_values, rsi_values):
    """Detect bullish divergence: price making lower lows, RSI making higher lows."""
    if len(price_lows_idx) < 2 or len(rsi_lows_idx) < 2:
        return None

    # Get last 2 price troughs
    recent_price_lows = price_lows_idx[-2:]
    if recent_price_lows[-1] < len(price_values) - 10:
        return None  # Too old

    # Find corresponding RSI troughs
    rsi_lows = []
    for price_low in recent_price_lows:
        nearby_rsi = [idx for idx in rsi_lows_idx if abs(idx - price_low) <= 5]
        if nearby_rsi:
            rsi_lows.append(nearby_rsi[0])

    if len(rsi_lows) < 2:
        return None

    # Check divergence
    price1, price2 = price_values[recent_price_lows[0]], price_values[recent_price_lows[1]]
    rsi1, rsi2 = rsi_values[rsi_lows[0]], rsi_values[rsi_lows[1]]

    if price2 < price1 and rsi2 > rsi1:
        strength = ((price1 - price2) / price1) * 100
        rsi_diff = rsi2 - rsi1
        return {
            "signal": "강세 다이버전스 (Bullish Divergence)",
            "evidence": f"가격 저점 하락 ({price1:.2f}→{price2:.2f}, -{strength:.1f}%), RSI 저점 상승 ({rsi1:.1f}→{rsi2:.1f}, +{rsi_diff:.1f})",
            "score": 15,
        }

    return None


def _detect_macd_divergence(df, price_highs_idx, price_lows_idx, price_values):
    """Detect MACD divergence."""
    if "MACD_12_26_9" not in df.columns:
        return None

    macd_values = df["MACD_12_26_9"].fillna(0).values
    macd_highs_idx = argrelextrema(macd_values, np.greater, order=5)[0]
    macd_lows_idx = argrelextrema(macd_values, np.less, order=5)[0]

    # Bearish MACD divergence
    if len(price_highs_idx) >= 2 and len(macd_highs_idx) >= 2:
        recent_price_peaks = price_highs_idx[-2:]
        if recent_price_peaks[-1] >= len(price_values) - 10:
            macd_peaks = []
            for price_peak in recent_price_peaks:
                nearby_macd = [idx for idx in macd_highs_idx if abs(idx - price_peak) <= 5]
                if nearby_macd:
                    macd_peaks.append(nearby_macd[0])

            if len(macd_peaks) >= 2:
                price1, price2 = price_values[recent_price_peaks[0]], price_values[recent_price_peaks[1]]
                macd1, macd2 = macd_values[macd_peaks[0]], macd_values[macd_peaks[1]]

                if price2 > price1 and macd2 < macd1:
                    return {
                        "signal": "MACD 약세 다이버전스",
                        "evidence": f"가격↑, MACD↓ ({macd1:.2f}→{macd2:.2f})",
                        "score": -10,
                    }

    # Bullish MACD divergence
    if len(price_lows_idx) >= 2 and len(macd_lows_idx) >= 2:
        recent_price_lows = price_lows_idx[-2:]
        if recent_price_lows[-1] >= len(price_values) - 10:
            macd_lows = []
            for price_low in recent_price_lows:
                nearby_macd = [idx for idx in macd_lows_idx if abs(idx - price_low) <= 5]
                if nearby_macd:
                    macd_lows.append(nearby_macd[0])

            if len(macd_lows) >= 2:
                price1, price2 = price_values[recent_price_lows[0]], price_values[recent_price_lows[1]]
                macd1, macd2 = macd_values[macd_lows[0]], macd_values[macd_lows[1]]

                if price2 < price1 and macd2 > macd1:
                    return {
                        "signal": "MACD 강세 다이버전스",
                        "evidence": f"가격↓, MACD↑ ({macd1:.2f}→{macd2:.2f})",
                        "score": 10,
                    }

    return None


def _detect_crsi_divergence(df, price_highs_idx, price_lows_idx, price_values):
    """Detect cRSI divergence."""
    if "cRSI" not in df.columns:
        return None

    crsi_values = df["cRSI"].fillna(50).values
    crsi_highs_idx = argrelextrema(crsi_values, np.greater, order=5)[0]
    crsi_lows_idx = argrelextrema(crsi_values, np.less, order=5)[0]

    # Bearish cRSI divergence
    if len(price_highs_idx) >= 2 and len(crsi_highs_idx) >= 2:
        recent_price_peaks = price_highs_idx[-2:]
        if recent_price_peaks[-1] >= len(price_values) - 10:
            crsi_peaks = []
            for price_peak in recent_price_peaks:
                nearby_crsi = [idx for idx in crsi_highs_idx if abs(idx - price_peak) <= 5]
                if nearby_crsi:
                    crsi_peaks.append(nearby_crsi[0])

            if len(crsi_peaks) >= 2:
                price1, price2 = price_values[recent_price_peaks[0]], price_values[recent_price_peaks[1]]
                crsi1, crsi2 = crsi_values[crsi_peaks[0]], crsi_values[crsi_peaks[1]]

                if price2 > price1 and crsi2 < crsi1:
                    return {
                        "signal": "cRSI 약세 다이버전스",
                        "evidence": f"가격↑, cRSI↓ ({crsi1:.1f}→{crsi2:.1f})",
                        "score": -10,
                    }

    # Bullish cRSI divergence
    if len(price_lows_idx) >= 2 and len(crsi_lows_idx) >= 2:
        recent_price_lows = price_lows_idx[-2:]
        if recent_price_lows[-1] >= len(price_values) - 10:
            crsi_lows = []
            for price_low in recent_price_lows:
                nearby_crsi = [idx for idx in crsi_lows_idx if abs(idx - price_low) <= 5]
                if nearby_crsi:
                    crsi_lows.append(nearby_crsi[0])

            if len(crsi_lows) >= 2:
                price1, price2 = price_values[recent_price_lows[0]], price_values[recent_price_lows[1]]
                crsi1, crsi2 = crsi_values[crsi_lows[0]], crsi_values[crsi_lows[1]]

                if price2 < price1 and crsi2 > crsi1:
                    return {
                        "signal": "cRSI 강세 다이버전스",
                        "evidence": f"가격↓, cRSI↑ ({crsi1:.1f}→{crsi2:.1f})",
                        "score": 10,
                    }

    return None

"""Prefix-local confluence/extrema facts; no historical slicing of centered extrema."""

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema


def confluence_values(frame):
    result = {"available": False, "metrics": {}}
    if len(frame) < 20:
        return result
    row = frame.iloc[-1]
    close = float(row.get("Close", 0))
    if close == 0:
        return result
    support, resistance = [], []
    for column in ("SMA_20", "SMA_50", "SMA_150", "SMA_200", "Pivot"):
        if column in frame and pd.notna(row.get(column)):
            value = float(row[column])
            (support if value < close else resistance).append({"level": value, "type": column})
    # Original order is MAs, swing levels, then Pivot/S1/R1, then gap levels.
    pivot_support = [item for item in support if item["type"] == "Pivot"]
    pivot_resistance = [item for item in resistance if item["type"] == "Pivot"]
    support = [item for item in support if item["type"] != "Pivot"]
    resistance = [item for item in resistance if item["type"] != "Pivot"]
    for column, kind, target, predicate in (
        ("Swing_High", "Swing High", resistance, lambda value: value > close),
        ("Swing_Low", "Swing Low", support, lambda value: value < close),
    ):
        if column in frame:
            target.extend(
                {"level": float(value), "type": kind}
                for value in frame[column].dropna().tail(5)
                if predicate(float(value))
            )
    support.extend(pivot_support)
    resistance.extend(pivot_resistance)
    for column, target, predicate in (
        ("S1", support, lambda value: value < close),
        ("R1", resistance, lambda value: value > close),
    ):
        if column in frame and pd.notna(row.get(column)) and predicate(float(row[column])):
            target.append({"level": float(row[column]), "type": column})
    for flag, level, kind, target, predicate in (
        ("Is_Gap_Up", "Gap_Up_Lower", "Gap Up (unfilled)", support, lambda value: value < close),
        (
            "Is_Gap_Down",
            "Gap_Down_Upper",
            "Gap Down (unfilled)",
            resistance,
            lambda value: value > close,
        ),
    ):
        if flag in frame and level in frame:
            for _, gap in frame[frame[flag]].tail(3).iterrows():
                if pd.notna(gap.get(level)) and predicate(float(gap[level])):
                    target.append({"level": float(gap[level]), "type": kind})
    nearby_support = [item for item in support if abs(item["level"] - close) <= close * 0.02]
    nearby_resistance = [item for item in resistance if abs(item["level"] - close) <= close * 0.02]
    metrics = {
        "close": close,
        "support_levels_count": len(support),
        "resistance_levels_count": len(resistance),
        "support_confluence": len(nearby_support),
        "resistance_confluence": len(nearby_resistance),
    }
    result.update(
        available=True,
        close=close,
        support_levels=support,
        resistance_levels=resistance,
        support_confluence=nearby_support,
        resistance_confluence=nearby_resistance,
    )
    for name, levels, chooser, sign in (
        ("support", support, max, -1),
        ("resistance", resistance, min, 1),
    ):
        if levels:
            nearest = chooser(levels, key=lambda item: item["level"])
            distance = sign * (nearest["level"] - close) / close * 100
            result[f"nearest_{name}"] = nearest
            result[f"{name}_distance_pct"] = distance
            metrics[f"nearest_{name}"] = round(nearest["level"], 2)
            metrics[f"{name}_distance_pct"] = round(distance, 2)
    result["below_sma50"] = (
        "SMA_50" in frame and pd.notna(row.get("SMA_50")) and close < float(row["SMA_50"])
    )
    result["supertrend_down"] = (
        "SuperTrend_Dir" in frame
        and pd.notna(row.get("SuperTrend_Dir"))
        and int(row["SuperTrend_Dir"]) == -1
    )
    if "ATR" in frame and pd.notna(row.get("ATR")):
        stop = close - 2 * float(row["ATR"])
        result.update(stop_loss=stop, stop_loss_distance_pct=(close - stop) / close * 100)
        metrics.update(
            stop_loss=round(stop, 2), stop_loss_distance_pct=round((close - stop) / close * 100, 2)
        )
    result["metrics"] = metrics
    return result


def _matching_divergence(price, price_indices, indicator, indicator_indices, *, bearish):
    if len(price_indices) < 2 or len(indicator_indices) < 2:
        return None
    peaks = price_indices[-2:]
    if peaks[-1] < len(price) - 10:
        return None
    matches = []
    for peak in peaks:
        nearby = [idx for idx in indicator_indices if abs(idx - peak) <= 5]
        if nearby:
            matches.append(nearby[0])
    if len(matches) < 2:
        return None
    p1, p2 = price[peaks[0]], price[peaks[1]]
    i1, i2 = indicator[matches[0]], indicator[matches[1]]
    if not ((p2 > p1 and i2 < i1) if bearish else (p2 < p1 and i2 > i1)):
        return None
    return {
        "bias": "bearish" if bearish else "bullish",
        "price_indices": tuple(int(i) for i in peaks),
        "indicator_indices": tuple(int(i) for i in matches),
        "price1": p1,
        "price2": p2,
        "indicator1": i1,
        "indicator2": i2,
        "price_change_pct": ((p2 - p1) if bearish else (p1 - p2)) / p1 * 100,
        "indicator_difference": (i1 - i2) if bearish else (i2 - i1),
    }


def divergence_values(frame):
    """Raw occurrences and descriptive bias agreement, never a score bonus.

    ``rsi_crsi_bias_agreement`` must not replace the legacy consumer's separate
    string predicate: it searches English bearish/bullish inside the Korean
    cRSI signal. That existing predicate remains consumer-owned and false for
    its current cRSI strings, even when the numerical biases agree.
    """
    result = {
        "available": False,
        "metrics": {},
        "rsi_bearish": None,
        "rsi_bullish": None,
        "macd": None,
        "crsi": None,
    }
    if len(frame) < 50 or not {"Close", "RSI"} <= set(frame):
        return result
    price = frame["Close"].values
    highs = argrelextrema(price, np.greater, order=5)[0]
    lows = argrelextrema(price, np.less, order=5)[0]
    result.update(
        available=True,
        price_highs=tuple(int(i) for i in highs),
        price_lows=tuple(int(i) for i in lows),
    )
    for column, fallback, name in (("RSI", 50, "rsi"), ("MACD", 0, "macd"), ("cRSI", 50, "crsi")):
        if column not in frame:
            continue
        matches = indicator_divergences(frame, price, highs, lows, column=column, fallback=fallback)
        ihigh, ilow, bearish, bullish = (
            matches[key] for key in ("highs", "lows", "bearish", "bullish")
        )
        result[f"{name}_highs"] = ihigh
        result[f"{name}_lows"] = ilow
        if name == "rsi":
            result.update(rsi_bearish=bearish, rsi_bullish=bullish)
            result["metrics"] = {
                "price_highs_count": len(highs),
                "price_lows_count": len(lows),
                "rsi_highs_count": len(ihigh),
                "rsi_lows_count": len(ilow),
            }
        else:
            # These old helpers return the bearish occurrence first when both exist.
            result[name] = bearish or bullish
    result["rsi_crsi_bias_agreement"] = bool(
        result["crsi"] and result["rsi_" + result["crsi"]["bias"]]
    )
    return result


def indicator_divergences(frame, price, highs, lows, *, column, fallback):
    if column not in frame:
        return {"highs": (), "lows": (), "bearish": None, "bullish": None}
    values = frame[column].fillna(fallback).values
    ihigh = argrelextrema(values, np.greater, order=5)[0]
    ilow = argrelextrema(values, np.less, order=5)[0]
    return {
        "highs": tuple(int(i) for i in ihigh),
        "lows": tuple(int(i) for i in ilow),
        "bearish": _matching_divergence(price, highs, values, ihigh, bearish=True),
        "bullish": _matching_divergence(price, lows, values, ilow, bearish=False),
    }

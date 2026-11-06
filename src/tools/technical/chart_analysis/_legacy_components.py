"""ASOF legacy numerical conditions. Scores, wording and actions stay in consumers."""

import numpy as np
import pandas as pd

from src.tools.technical.chart_analysis.pattern_parameters import validated_thresholds


def number(value):
    return None if value is None or pd.isna(value) else float(value)


def valid(frame, length, columns):
    return len(frame) >= length and set(columns) <= set(frame.columns)


def vcp_values(frame, *, thresholds=None):
    thresholds = validated_thresholds("chart.vcp.legacy", thresholds)
    result = {"in_vcp": False, "strong": False, "metrics": {}}
    if not valid(frame, 20, ("High", "Low", "ATR")):
        return result
    atr = frame["ATR"].dropna()
    if len(atr) < 8:
        return result
    recent = atr.iloc[-8:].values
    first, last = recent[:4].mean(), recent[-4:].mean()
    if first == 0:
        return result
    ratio = (first - last) / first
    result.update(
        atr_contraction_ratio=ratio, atr_current=recent[-1], first_4_avg=first, last_4_avg=last
    )
    result["metrics"] = {
        "atr_contraction_ratio": round(ratio, 3),
        "atr_current": round(recent[-1], 2),
    }
    if ratio <= thresholds["VCP_ATR_CONTRACTION"]:
        return result
    recent20 = frame.iloc[-20:]
    tight = (
        recent20["High"] - recent20["Low"]
        < recent20["ATR"] * thresholds["VCP_TIGHTNESS_MULTIPLIER"]
    )
    count, recent3 = (
        int(tight.sum()),
        bool(tight.iloc[-thresholds["VCP_RECENT_TIGHT_WINDOW"] :].all()),
    )
    result.update(
        in_vcp=True,
        strong=bool(count >= thresholds["VCP_MIN_TIGHT_DAYS"] and recent3),
        tight_days_count=count,
        recent_3_tight=recent3,
    )
    result["metrics"].update(tight_days_count=count, recent_3_tight=recent3)
    return result


def pocket_pivot_values(frame, *, latest=None, thresholds=None):
    thresholds = validated_thresholds("chart.pocket_pivot.down_candle", thresholds)
    lookback = thresholds["PP_LOOKBACK_DAYS"]
    result = {"detected": False, "metrics": {}}
    if not valid(frame, lookback + 1, ("Open", "Close", "Volume", "SMA_50")):
        return result
    row = frame.iloc[-1] if latest is None else latest
    close, opening, volume, sma50 = (
        number(row.get(k)) for k in ("Close", "Open", "Volume", "SMA_50")
    )
    if None in (close, opening, volume, sma50) or sma50 == 0:
        return result
    distance = abs(close - sma50) / sma50
    prior = frame.iloc[-(lookback + 1) : -1]
    down = prior[prior["Close"] < prior["Open"]]
    result.update(
        close=close,
        open=opening,
        volume=volume,
        sma_50=sma50,
        distance_pct=distance,
        down_days_count=len(down),
    )
    if close >= opening or distance > thresholds["PP_SMA_DISTANCE_PCT"] or len(down) < 3:
        return result
    maximum = float(down["Volume"].max())
    result["max_down_volume_10d"] = maximum
    result["detected"] = bool(volume > maximum)
    if result["detected"]:
        result["metrics"] = {"pocket_pivot_volume": volume, "max_down_volume_10d": maximum}
    return result


def power_gap_values(frame, *, thresholds=None):
    thresholds = validated_thresholds("chart.power_gap", thresholds)
    result = {"detected": False, "metrics": {}}
    if not valid(frame, 2, ("Open", "High", "Volume", "Vol_SMA_20")):
        return result
    opening, volume, average = (
        number(frame.iloc[-1].get(k)) for k in ("Open", "Volume", "Vol_SMA_20")
    )
    high = number(frame.iloc[-2].get("High"))
    if None in (opening, high, volume, average) or high == 0 or average == 0:
        return result
    gap, ratio = (opening - high) / high, volume / average
    result.update(
        gap_size_pct=gap,
        gap_vol_ratio=ratio,
        previous_high=high,
        open=opening,
        volume=volume,
        vol_sma_20=average,
    )
    result["detected"] = bool(
        gap >= thresholds["GAP_SIZE_MIN_PCT"] and ratio >= thresholds["GAP_VOLUME_MULTIPLIER"]
    )
    if result["detected"]:
        result["metrics"] = {"gap_size_pct": round(gap, 3), "gap_vol_ratio": round(ratio, 2)}
    return result


def breakout_values(frame):
    result = {
        "high_breakout": False,
        "swing_high_breakout": False,
        "metrics": {},
    }
    if valid(frame, 21, ("Close",)):
        close, high = (number(frame.iloc[-1].get(k)) for k in ("Close", "High"))
        if close is not None and high is not None:
            prior = frame["High"].iloc[-21:-1].max()
            result.update(high_20=prior, high=high, close=close, high_breakout=bool(high > prior))
            if result["high_breakout"]:
                result["metrics"]["high_20"] = round(prior, 2)
            if "Swing_High" in frame:
                peaks = frame["Swing_High"].dropna()
                if not peaks.empty:
                    peak = peaks.iloc[-1]
                    result.update(last_swing_high=peak, swing_high_breakout=bool(close > peak))
                    if result["swing_high_breakout"]:
                        result["metrics"]["last_swing_high"] = round(peak, 2)
    return result


def candlestick_values(frame):
    result = {"hammer": False, "bullish_engulfing": False, "metrics": {}}
    if not valid(frame, 2, ("Open", "High", "Low", "Close")):
        return result
    opening, high, low, close = (
        number(frame.iloc[-1].get(k)) for k in ("Open", "High", "Low", "Close")
    )
    prev_o, prev_c = (number(frame.iloc[-2].get(k)) for k in ("Open", "Close"))
    if None in (opening, high, low, close, prev_o, prev_c):
        return result
    body, upper, lower = abs(close - opening), high - max(opening, close), min(opening, close) - low
    prev_body = abs(prev_c - prev_o)
    hammer = high - low > 0 and body > 0 and lower > 2 * body and upper < body * 0.5
    engulfing = (
        prev_c < prev_o
        and close > opening
        and close > prev_o
        and opening < prev_c
        and body > prev_body
    )
    result.update(
        body=body,
        upper_shadow=upper,
        lower_shadow=lower,
        total_range=high - low,
        previous_body=prev_body,
        hammer=hammer,
        bullish_engulfing=engulfing,
    )
    if hammer:
        result["metrics"]["hammer_ratio"] = round(lower / body, 2)
    if engulfing:
        result["metrics"]["engulfing_body"] = round(body, 2)
    return result


def patterns_extra_values(frame):
    breakout, candles = breakout_values(frame), candlestick_values(frame)
    return {**breakout, **candles, "metrics": {**breakout["metrics"], **candles["metrics"]}}


def volume_extra_values(frame, *, thresholds=None):
    thresholds = validated_thresholds("chart.legacy.volume_extra", thresholds)
    result = {"available": False, "metrics": {}}
    if not valid(frame, 2, ("Vol_SMA_20",)):
        return result
    row, prev = frame.iloc[-1], frame.iloc[-2]
    volume, average = number(row.get("Volume")), number(row.get("Vol_SMA_20"))
    if volume is None or average in (None, 0):
        return result
    close, prev_c, opening = (
        number(x) for x in (row.get("Close"), prev.get("Close"), row.get("Open"))
    )
    ratio = volume / average
    up = close is not None and prev_c is not None and close > prev_c
    down = close is not None and prev_c is not None and close < prev_c
    down_candle = close is not None and opening is not None and close < opening
    result.update(
        available=True,
        vol_ratio=ratio,
        volume=volume,
        vol_sma_20=average,
        price_up=up,
        price_down=down,
        down_candle=down_candle,
        surge=ratio > thresholds["VOLUME_SURGE_MULTIPLIER"],
        increase=1.5 < ratio <= thresholds["VOLUME_SURGE_MULTIPLIER"],
        moderate=thresholds["VOLUME_MODERATE_MULTIPLIER"] < ratio <= 1.5,
        reduced=ratio < 0.5,
        tennis_ball=False,
        egg=False,
    )
    result["metrics"] = {"vol_ratio": round(ratio, 2), "volume": volume, "vol_sma_20": average}
    for values in (
        pocket_pivot_values(
            frame, thresholds={k: v for k, v in thresholds.items() if k.startswith("PP_")}
        ),
        power_gap_values(
            frame, thresholds={k: v for k, v in thresholds.items() if k.startswith("GAP_")}
        ),
    ):
        result["metrics"].update(values["metrics"])
    tennis = tennis_ball_values(frame, thresholds=thresholds)
    result.update({key: value for key, value in tennis.items() if key != "metrics"})
    result["metrics"].update(tennis["metrics"])
    return result


def stage2_values(frame):
    result = {"available": False, "conditions": {}, "metrics": {}}
    if len(frame) < 200:
        return result
    row = frame.iloc[-1]
    close, sma50, sma150, sma200, high, low = (
        number(row.get(k)) or 0.0
        for k in ("Close", "SMA_50", "SMA_150", "SMA_200", "High_52w", "Low_52w")
    )
    if not all((close, sma50, sma150, sma200)):
        return result
    prev150 = number(frame.iloc[-22].get("SMA_150")) or 0.0
    prev200 = number(frame.iloc[-22].get("SMA_200")) or 0.0
    conditions = {
        "ma_stack": close > sma150 > sma200,
        "ma_50_stack": sma50 > sma150 > sma200,
        "sma_150_rising": bool(prev150 and sma150 > prev150),
        "sma_200_rising": bool(prev200 and sma200 > prev200),
        "above_50": close > sma50,
        "above_52w_low_30pct": bool(low and close >= low * 1.30),
        "within_52w_high_25pct": bool(high and close >= high * 0.75),
    }
    count = sum(conditions.values())
    result.update(
        available=True,
        conditions=conditions,
        conditions_met=count,
        is_stage2=count == 7,
        close=close,
        sma_50=sma50,
        sma_150=sma150,
        sma_200=sma200,
        sma_150_previous=prev150,
        sma_200_previous=prev200,
        high_52w=high,
        low_52w=low,
    )
    result["metrics"] = dict(
        conditions_met=float(count),
        is_stage2=float(count == 7),
        close=close,
        sma_50=sma50,
        sma_150=sma150,
        sma_200=sma200,
        **{f"cond_{key}": float(value) for key, value in conditions.items()},
    )
    return result


def linear_slope(values):
    if len(values) < 2:
        return 0.0
    return np.polyfit(np.arange(len(values)), values, 1)[0]


def velocity_slope_values(frame):
    result = {"available": False, "metrics": {}}
    if not valid(frame, 15, ("SMA_20",)):
        return result
    sma = frame["SMA_20"].dropna()
    if len(sma) < 15 or sma.iloc[-1] == 0:
        return result
    recent = sma.iloc[-15:].values
    current, previous = (linear_slope(window) for window in (recent[-5:], recent[-10:-5]))
    norm, prior_norm = current / recent[-1] * 100, previous / recent[-1] * 100
    change = norm - prior_norm
    result.update(
        available=True,
        current_slope=current,
        previous_slope=previous,
        norm_slope=norm,
        norm_previous_slope=prior_norm,
        slope_change=change,
        last_valid_sma20=recent[-1],
    )
    result["metrics"] = {"norm_slope": round(norm, 4), "slope_change": round(change, 4)}
    return result


def raw_latest_close(frame):
    """A-prime reads the original last row, including its NaN/exception semantics."""
    return float(frame["Close"].iloc[-1]) if "Close" in frame else None


def velocity_values(frame):
    result = velocity_slope_values(frame)
    if not result["available"]:
        return result
    current, previous, norm, change = (
        result[key] for key in ("current_slope", "previous_slope", "norm_slope", "slope_change")
    )
    closes = frame["Close"].dropna() if "Close" in frame else pd.Series(dtype=float)
    above = bool(not closes.empty and float(closes.iloc[-1]) > result["last_valid_sma20"])
    last_close = (
        raw_latest_close(frame)
        if "Close" in frame and not pd.isna(frame["Close"].iloc[-1])
        else None
    )
    result.update(
        last_close=last_close,
        price_above_sma20=above,
        upward=bool(norm > 0.05),
        downward=bool(norm < -0.05 and not above),
        negative_suppressed=bool(norm < -0.05 and above),
        up_acceleration=bool(norm > 0.05 and change > 0.02),
        up_fatigue=bool(norm > 0.05 and change < -0.04),
        up_deceleration=bool(norm > 0.05 and -0.04 <= change < -0.02),
        down_acceleration=bool(norm < -0.05 and not above and change < -0.02),
        down_deceleration=bool(norm < -0.05 and not above and change > 0.02),
        turn_down=bool(previous > 0 and current < 0 and not above),
        turn_up=bool(previous < 0 and current > 0),
    )
    return result


def crsi_values(frame):
    result = {"available": False, "metrics": {}}
    if not valid(frame, 2, ("cRSI",)):
        return result
    crsi, high, low = (
        number(frame.iloc[-1].get(k)) for k in ("cRSI", "cRSI_HighBand", "cRSI_LowBand")
    )
    previous = number(frame.iloc[-2].get("cRSI"))
    if None in (crsi, high, low, previous):
        return result
    result.update(
        available=True,
        crsi=crsi,
        crsi_high_band=high,
        crsi_low_band=low,
        previous_crsi=previous,
        band_width=high - low,
        hook_down=previous > high and crsi < high,
        hook_up=previous < low and crsi > low,
        squeeze=high - low < 10,
        above_band=crsi > high,
        below_band=crsi < low,
    )
    result["metrics"] = {
        "crsi": round(crsi, 2),
        "crsi_high_band": round(high, 2),
        "crsi_low_band": round(low, 2),
    }
    return result


def supertrend_values(frame):
    result = {"available": False, "metrics": {}}
    if not valid(frame, 2, ("SuperTrend_Dir",)):
        return result
    row = frame.iloc[-1]
    direction = number(row.get("SuperTrend_Dir"))
    if direction is None:
        return result
    direction = int(direction)
    previous = number(frame.iloc[-2].get("SuperTrend_Dir"))
    previous = direction if previous is None else int(previous)
    line = number(row.get("SuperTrend_Up" if direction == 1 else "SuperTrend_Dn"))
    close = number(row.get("Close"))
    result.update(
        available=True,
        supertrend_direction=direction,
        previous_direction=previous,
        supertrend_value=line,
        close=close,
        changed=previous != direction,
        turn_up=previous != direction and direction == 1,
        turn_down=previous != direction and direction != 1,
    )
    result["metrics"] = {"supertrend_direction": direction}
    if line is not None:
        result["metrics"]["supertrend_value"] = round(line, 2)
    if close is not None:
        result["metrics"]["close"] = round(close, 2)
    if close is not None and line is not None and direction in (1, -1):
        distance = ((close - line) if direction == 1 else (line - close)) / line * 100
        result.update(distance_pct=distance, far_from_line=distance > 5, near_line=distance < 2)
    return result


def tennis_ball_values(frame, *, latest=None, is_down_day=None, thresholds=None):
    """Independent direct-helper boundary; no Vol_SMA_20 dependency."""
    thresholds = validated_thresholds("chart.legacy.volume_extra", thresholds)
    lookback = thresholds["MEAN_REVERSION_LOOKBACK"]
    result = {"tennis_ball": False, "egg": False, "metrics": {}}
    if not valid(frame, lookback + 1, ("Close", "Open", "Volume")):
        return result
    row = frame.iloc[-1] if latest is None else latest
    if is_down_day is None:
        close, opening = number(row.get("Close")), number(row.get("Open"))
        is_down_day = close is not None and opening is not None and close < opening
    if not is_down_day:
        return result
    volume = number(row.get("Volume"))
    if volume is None:
        return result
    prior = frame.iloc[-(lookback + 1) : -1]
    prior = prior[prior["Close"] < prior["Open"]]
    if len(prior) < 2:
        return result
    average = float(prior["Volume"].mean())
    if average != 0:
        ratio = volume / average
        result.update(
            volume=volume,
            avg_down_volume_5d=average,
            down_volume_ratio=ratio,
            tennis_ball=ratio < thresholds["TENNIS_BALL_THRESHOLD"],
            egg=ratio > thresholds["EGG_THRESHOLD"],
        )
        if result["tennis_ball"] or result["egg"]:
            result["metrics"]["down_volume_ratio"] = round(ratio, 2)
    return result

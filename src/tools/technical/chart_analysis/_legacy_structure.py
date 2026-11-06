"""Causal windows, strict/nanmax breakouts and Swing/observation primitives."""

import numpy as np
import pandas as pd


def calculate_legacy_windows(
    frame, *, direction_lookback=21, trend_breakout_lookback=50, deep_recovery_lookback=20
):
    """Owned copy, adding absent windows only; supplied compatibility columns win.

    This is separate from the exact IndicatorCalculator shadow columns contract.
    It never calculates centered extrema or infers pivots from historical slices.
    """
    frame = frame.copy(deep=True)
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)

    def numeric(key):
        return pd.to_numeric(frame[key], errors="coerce")

    def put(key, value):
        if key not in frame:
            frame[key] = value

    for period in (50, 150, 200):
        column = f"SMA_{period}"
        if column in frame:
            put(
                f"{column}_Slope_{direction_lookback}",
                frame[column] - frame[column].shift(direction_lookback),
            )
    if "SMA_20" in frame:
        put("SMA_20_Slope_5", frame["SMA_20"] - frame["SMA_20"].shift(5))
    for key, series in (
        ("High_20_Prev", frame["High"].rolling(20).max().shift(1)),
        ("High_50_Prev", frame["High"].rolling(50).max().shift(1)),
        ("Low_20", frame["Low"].rolling(20).min()),
        ("Low_20_Prev", frame["Low"].rolling(20).min().shift(1)),
        ("Vol_SMA_20", frame["Volume"].rolling(20).mean()),
        ("Vol_SMA_20_Prev", frame["Volume"].rolling(20).mean().shift(1)),
        ("Vol_SMA_5", frame["Volume"].rolling(5).mean()),
        ("Vol_SMA_20_Shift5", frame["Volume"].rolling(20).mean().shift(5)),
        ("High_52w", frame["High"].rolling(252, min_periods=50).max()),
        ("Low_52w", frame["Low"].rolling(252, min_periods=50).min()),
        ("Trend_Breakout_High_Prev", frame["High"].rolling(trend_breakout_lookback).max().shift(1)),
        ("Deep_Recovery_High_Prev", frame["High"].rolling(deep_recovery_lookback).max().shift(1)),
    ):
        put(key, series)
    put("History_Bars", range(1, len(frame) + 1))
    put("Previous_Close", frame["Close"].shift(1))
    # Recompute these definitions from raw rolling windows, as the old observation
    # boundary did. Vol_SMA compatibility columns may have different supplied values.
    put(
        "Volume_Ratio_Prev20",
        frame["Volume"] / frame["Volume"].rolling(20).mean().shift(1).replace(0, float("nan")),
    )
    put(
        "Volume_Contraction_Ratio",
        frame["Volume"].rolling(5).mean()
        / frame["Volume"].rolling(20).mean().shift(5).replace(0, float("nan")),
    )
    if {"SMA_150", "SMA_150_Slope_21"} <= set(frame):
        trend = (frame["Close"] > numeric("SMA_150")) & (numeric("SMA_150_Slope_21") >= 0)
        put(
            "Contraction_Context",
            trend & (frame["Close"] <= frame["High"].rolling(20).max().shift(1)),
        )
        put("Prior_Trend_Context", trend.shift(1).rolling(20).max().fillna(0).astype(bool))
    if "SMA_20" in frame:
        put(
            "Prior_Below_SMA20",
            (frame["Close"] < numeric("SMA_20")).shift(1).rolling(10).max().fillna(0).astype(bool),
        )
    if "SMA_20_Slope_5" in frame:
        put("Previous_SMA20_Slope", frame["SMA_20_Slope_5"].shift(1))
    put("Return_5", frame["Close"] / frame["Close"].shift(5) - 1)
    put("High_Break_5", frame["Close"] > frame["High"].rolling(5).max().shift(1))
    high50 = frame["High"].rolling(50).max().shift(1)
    put(
        "Price_Breakout_Event",
        (frame["Close"] > high50) & (frame["Close"].shift(1) <= high50.shift(1)),
    )
    return frame


def observation_feature_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Causal Observation inputs; all reference windows exclude overlapping bars."""
    frame = frame.copy()
    frame["History_Bars"] = range(1, len(frame) + 1)
    frame["Previous_Close"] = frame["Close"].shift(1)
    frame["Volume_Ratio_Prev20"] = frame["Volume"] / frame["Volume"].rolling(20).mean().shift(
        1
    ).replace(0, float("nan"))
    frame["Volume_Contraction_Ratio"] = frame["Volume"].rolling(5).mean() / frame["Volume"].rolling(
        20
    ).mean().shift(5).replace(0, float("nan"))
    prior_high = frame["High"].rolling(20).max().shift(1)
    trend = (frame["Close"] > frame["SMA_150"]) & (frame["SMA_150_Slope_21"] >= 0)
    frame["Contraction_Context"] = trend & (frame["Close"] <= prior_high)
    frame["Prior_Trend_Context"] = trend.shift(1).rolling(20).max().fillna(0).astype(bool)
    frame["Prior_Below_SMA20"] = (
        (frame["Close"] < frame["SMA_20"]).shift(1).rolling(10).max().fillna(0).astype(bool)
    )
    frame["Previous_SMA20_Slope"] = frame["SMA_20_Slope_5"].shift(1)
    frame["Return_5"] = frame["Close"] / frame["Close"].shift(5) - 1
    frame["High_Break_5"] = frame["Close"] > frame["High"].rolling(5).max().shift(1)
    breakout = frame["High"].rolling(50).max().shift(1)
    frame["Price_Breakout_Event"] = (frame["Close"] > breakout) & (
        frame["Close"].shift(1) <= breakout.shift(1)
    )
    return frame


def swing_feature_frame(
    raw, *, direction_lookback=21, trend_breakout_lookback=50, deep_recovery_lookback=20
):
    """Exact original SWING input material; caller windows are explicit."""
    from src.tools.technical.chart_analysis.legacy_features import calculate_legacy_features
    from src.tools.technical.chart_analysis.pivots import confirmed_pivots

    frame = calculate_legacy_features(raw)
    for period in (50, 150, 200):
        column = f"SMA_{period}"
        frame[f"{column}_Slope_{direction_lookback}"] = frame[column] - frame[column].shift(
            direction_lookback
        )
    frame["Trend_Breakout_High_Prev"] = (
        frame["High"].rolling(trend_breakout_lookback).max().shift(1)
    )
    frame["Deep_Recovery_High_Prev"] = frame["High"].rolling(deep_recovery_lookback).max().shift(1)
    frame["Higher_Low"], frame["Lower_Low_Lower_High"] = confirmed_pivots(
        frame["High"].to_numpy(float), frame["Low"].to_numpy(float)
    )
    return observation_feature_columns(frame)


def _prev(values):
    return np.r_[np.nan, values[:-1]]


def close_breakout_values(frame, *, lookback=20):
    """Strict rolling baseline, with known previous baseline and Close required."""
    close = frame["Close"].to_numpy(float)
    reference = frame["High"].rolling(lookback).max().shift(1).to_numpy(float)
    previous_close, previous_reference = _prev(close), _prev(reference)
    known = (
        ~np.isnan(close)
        & ~np.isnan(reference)
        & ~np.isnan(previous_close)
        & ~np.isnan(previous_reference)
    )
    above = close > reference
    return {
        "reference": reference,
        "above": above,
        "fresh": known & above & (previous_close <= previous_reference),
        "known": known,
    }


def nanmax_close_breakout_values(frame, *, lookback=20):
    result = {"fresh": False, "current_above": False, "previous_above": False}
    if not {"Close", "High"} <= set(frame) or len(frame) < lookback + 2:
        return result
    close, high = frame["Close"].to_numpy(float), frame["High"].to_numpy(float)
    for label, index in (("current", len(frame) - 1), ("previous", len(frame) - 2)):
        prior = high[index - lookback : index]
        reference = np.nanmax(prior)
        result[f"{label}_reference"] = reference
        result[f"{label}_above"] = bool(
            len(prior) > 0 and np.isfinite(reference) and close[index] > reference
        )
    result["fresh"] = result["current_above"] and not result["previous_above"]
    return result


def close_location_values(high, low, close):
    """Supplied arrays retain NumPy broadcasting and degenerate-range semantics."""
    rng = high - low
    return np.where(rng > 0, (close - low) / np.where(rng > 0, rng, 1), 0.5)


def swing_s01_array_values(
    close,
    reference,
    sma,
    slope,
    volume,
    average,
    *,
    volume_multiple=1.4,
    comparison_profile="V1_REPLAY",
):
    previous_close, previous_reference = _prev(close), _prev(reference)
    known = (
        ~np.isnan(sma)
        & ~np.isnan(slope)
        & ~np.isnan(average)
        & ~np.isnan(reference)
        & ~np.isnan(previous_reference)
    )
    if comparison_profile == "V2_SIGNAL":
        known &= ~np.isnan(close) & ~np.isnan(previous_close) & ~np.isnan(volume)
        fresh = (close > reference) & (previous_close <= previous_reference)
    else:
        fresh = (close > reference) & ~(previous_close > previous_reference)
    return {
        "trigger": known
        & (close > sma)
        & (slope > 0)
        & fresh
        & (volume > volume_multiple * average),
        "fresh": fresh,
        "known": known,
        "reference": reference,
    }


def swing_s01_values(
    frame,
    *,
    reference_column="High_50_Prev",
    direction_lookback=21,
    volume_multiple=1.4,
    comparison_profile="V1_REPLAY",
):
    values = (
        frame[column].to_numpy(float)
        for column in (
            "Close",
            reference_column,
            "SMA_150",
            f"SMA_150_Slope_{direction_lookback}",
            "Volume",
            "Vol_SMA_20",
        )
    )
    return swing_s01_array_values(
        *values, volume_multiple=volume_multiple, comparison_profile=comparison_profile
    )


def swing_structure_values(frame, st, lhll, *, volume_multiple=1.5, weak_close_location=0.25):
    """Selective frame inputs in legacy evaluation order, without shape coercion."""
    close, high, low, volume = (
        frame[key].values.astype(float) for key in ("Close", "High", "Low", "Volume")
    )
    sma50, sma200 = frame["SMA_50"].values, frame["SMA_200"].values
    vr20 = volume / frame["Vol_SMA_20_Prev"].values
    location = close_location_values(high, low, close)
    low_break = (close < frame["Low_20_Prev"].values) & (vr20 >= volume_multiple)
    ma_break = (
        (close < sma50) & (location <= weak_close_location) & (vr20 >= volume_multiple) & (st == -1)
    )
    down_structure = (close < sma200) & (close < sma50) & (st == -1) & lhll
    return {
        "close_location": location,
        "volume_ratio_prev20": vr20,
        "low_break_volume": low_break,
        "weak_close_ma_break": ma_break,
        "down_structure": down_structure,
        "structure_breakdown": low_break | ma_break | down_structure,
    }


def swing_deep_recovery_values(frame, st, breakdown, higher_low):
    """Read each required column only when the original expression reaches it."""
    close = frame["Close"].values.astype(float)
    return (
        ~breakdown
        & (close < frame["SMA_200"].values)
        & (close > frame["SMA_20"].values)
        & (close > frame["SMA_50"].values)
        & (frame["SMA_20_Slope_5"].values > 0)
        & higher_low
        & (st == 1)
    )


def swing_d_trigger_array_values(close, high20, sma50, deep):
    """Replay's negated previous comparison deliberately accepts previous NaN."""
    fresh20 = (close > high20) & ~(_prev(close) > _prev(high20))
    reclaim50 = (_prev(close) <= _prev(sma50)) & (close > sma50)
    return {
        "fresh20_replay": fresh20,
        "reclaim50": reclaim50,
        "d_trigger": deep & (fresh20 | reclaim50),
    }


def swing_numerical_values(
    frame,
    *,
    st,
    higher_low,
    lower_low_lower_high,
    volume_multiple=1.5,
    weak_close_location=0.25,
    trend_volume_multiple=1.4,
    direction_lookback=21,
):
    """Arrays only. Caller explicitly supplies its pivot/finality/ST fallback profile.

    replay uses NaN ST→1; V2 preserves its own inputs. Missing pivot arrays are never
    silently reconstructed. No warmup, emission priority or position state here.
    """
    close, _high, _low, _volume = (
        frame[key].to_numpy(float) for key in ("Close", "High", "Low", "Volume")
    )
    st, higher_low, lhll = np.asarray(st), np.asarray(higher_low), np.asarray(lower_low_lower_high)
    if any(len(values) != len(frame) for values in (st, higher_low, lhll)):
        raise ValueError("Swing primitive arrays must match frame length")
    # The facade has always converted its numerical inputs to float. Direct
    # compatibility helpers retain supplied dtypes and read only their own columns.
    numeric = frame.astype(
        dict.fromkeys(
            ("SMA_20", "SMA_50", "SMA_200", "Vol_SMA_20_Prev", "Low_20_Prev", "SMA_20_Slope_5"),
            float,
        )
    )
    structure = swing_structure_values(
        numeric,
        st,
        lhll,
        volume_multiple=volume_multiple,
        weak_close_location=weak_close_location,
    )
    deep = swing_deep_recovery_values(
        numeric,
        st,
        structure["structure_breakdown"],
        higher_low,
    )
    s01 = swing_s01_values(
        frame, volume_multiple=trend_volume_multiple, direction_lookback=direction_lookback
    )
    return {
        **structure,
        "deep_recovery": deep,
        "fresh50_replay": s01["fresh"],
        "s_trigger": s01["trigger"],
        **swing_d_trigger_array_values(
            close, frame["High_20_Prev"].to_numpy(float), numeric["SMA_50"].to_numpy(float), deep
        ),
    }


def swing_signal_values(frame, *, direction_lookback=21, trend_volume_multiple=1.4):
    """V2's explicit previous<=reference comparisons, distinct from replay NaNs.

    deep_recovery_trigger is the price/MA branch only: consumer combines the
    supplied deep condition, warmup, finality, emission priority and state.
    """
    close = frame["Close"]
    prior_close = close.shift(1)
    sma20, sma50, sma200, slope20 = (
        frame[key] for key in ("SMA_20", "SMA_50", "SMA_200", "SMA_20_Slope_5")
    )
    high20, prior20, prior50 = (
        frame["Deep_Recovery_High_Prev"],
        frame["Deep_Recovery_High_Prev"].shift(1),
        sma50.shift(1),
    )
    known_deep = (
        pd.concat(
            (close, sma20, sma50, sma200, high20, prior20, prior_close, prior50, slope20), axis=1
        )
        .notna()
        .all(axis=1)
    )
    fresh20 = (close > high20) & (prior_close <= prior20)
    reclaim = (prior_close <= prior50) & (close > sma50)
    trigger = (
        known_deep
        & (close < sma200)
        & (close > sma20)
        & (close > sma50)
        & (slope20 > 0)
        & (fresh20 | reclaim)
    )
    return {
        "trend_breakout": swing_s01_values(
            frame,
            reference_column="Trend_Breakout_High_Prev",
            direction_lookback=direction_lookback,
            volume_multiple=trend_volume_multiple,
            comparison_profile="V2_SIGNAL",
        )["trigger"],
        "deep_recovery_trigger": trigger.to_numpy(bool),
        "fresh20_v2": fresh20.to_numpy(bool),
        "reclaim50_v2": reclaim.to_numpy(bool),
    }


def swing_frame_values(frame):
    """Prepared pivot profile required; this function does not invent pivot state."""
    if not {"Higher_Low", "Lower_Low_Lower_High"} <= set(frame):
        raise ValueError("Swing family requires explicitly prepared pivot columns")
    return swing_numerical_values(
        frame,
        st=np.nan_to_num(frame["SuperTrend_Dir"].to_numpy(float), nan=1.0),
        higher_low=frame["Higher_Low"].to_numpy(bool),
        lower_low_lower_high=frame["Lower_Low_Lower_High"].to_numpy(bool),
    )


def observation_numerical_values(frame, *, kind="all", prepared=False):
    """Raw per-row predicates; default all preserves the family facade contract.

    Selected volume/contraction/deceleration paths read only their prerequisites.
    Thresholds, finality and episode state stay external.
    """
    frame = frame if prepared else calculate_legacy_windows(frame)
    result = frame.loc[
        :,
        [
            key
            for key in (
                "Previous_Close",
                "Volume_Ratio_Prev20",
                "Volume_Contraction_Ratio",
                "Contraction_Context",
                "Prior_Trend_Context",
                "Prior_Below_SMA20",
                "Previous_SMA20_Slope",
                "Return_5",
                "High_Break_5",
                "Price_Breakout_Event",
            )
            if key in frame
        ],
    ].copy()
    if kind == "contraction":
        return result
    close = frame["Close"]
    if "Previous_Close" in frame:
        result["Up_Day"] = close > frame["Previous_Close"]
        result["Down_Day"] = close < frame["Previous_Close"]
    if kind == "volume":
        return result
    sma20, slope, prior = (
        frame[key] for key in ("SMA_20", "SMA_20_Slope_5", "Previous_SMA20_Slope")
    )
    trend = frame["Prior_Trend_Context"].fillna(False).astype(bool)
    result["Momentum_Weak"] = (
        close.notna() & sma20.notna() & slope.notna() & trend & (close < sma20) & (slope <= 0)
    )
    result["Momentum_Weak_Start"] = (
        result["Momentum_Weak"] & (slope < 0) & prior.notna() & (prior >= 0)
    )
    if kind == "deceleration":
        return result
    result["Reacceleration_Turn"] = (
        close.notna()
        & sma20.notna()
        & slope.notna()
        & trend
        & frame["Prior_Below_SMA20"].fillna(False).astype(bool)
        & (close > sma20)
        & (slope > 0)
        & prior.notna()
        & (prior <= 0)
    )
    result["Reacceleration_Positive_Return"] = result["Reacceleration_Turn"] & (
        frame.get("Return_5", pd.Series(0, index=frame.index)).fillna(0) > 0
    )
    result["Reacceleration_High_Break"] = result["Reacceleration_Turn"] & frame.get(
        "High_Break_5", pd.Series(False, index=frame.index)
    ).fillna(False).astype(bool)
    return result


def fixed_anchor_close_values(
    close,
    *,
    breakout_level=None,
    origin_support=None,
    pullback_low=None,
    signal_close=None,
    signal_atr=None,
):
    """Explicit fixed prices only; None preserves unavailable comparisons."""
    close, breakout_level, origin_support, pullback_low, signal_close, signal_atr = (
        None if value is None or pd.isna(value) else value
        for value in (close, breakout_level, origin_support, pullback_low, signal_close, signal_atr)
    )
    result = {"close": close}
    for label, level in (
        ("breakout", breakout_level),
        ("origin", origin_support),
        ("pullback", pullback_low),
    ):
        result[f"{label}_level"] = level
        result[f"below_{label}"] = None if close is None or level is None else close < level
        result[f"at_or_above_{label}"] = None if close is None or level is None else close >= level
    combined = (
        max(origin_support, pullback_low)
        if origin_support is not None and pullback_low is not None
        else None
    )
    threshold = (
        signal_close - 3 * signal_atr
        if signal_close is not None and signal_atr is not None
        else None
    )
    result.update(
        max_origin_pullback=combined,
        below_max_origin_pullback=None if combined is None or close is None else close < combined,
        signal_minus_3atr=threshold,
        at_or_below_signal_minus_3atr=None
        if threshold is None or close is None
        else close <= threshold,
    )
    return result


STATE_WINDOW_PARAMETERS = {
    "directional_windows": {
        **{f"SMA_{n}": {"bars": 21, "percent": True} for n in (20, 50, 100, 150, 200)},
        **{
            key: {"bars": 5, "percent": False}
            for key in ("cRSI", "MACD", "MACD_Signal", "MACD_Hist")
        },
        **{key: {"bars": 5, "percent": True} for key in ("Volume", "Vol_SMA_20", "Vol_SMA_50")},
    },
    "streak_bars": 2,
    "weakness_lookback": 10,
    "low_recent": 10,
    "low_prior": 30,
    "volume_recent": 5,
    "volume_prior": 20,
}


def numeric_value(frame, column, offset=0):
    if column not in frame or len(frame) <= offset:
        return None
    value = frame.iloc[-1 - offset][column]
    if value is None or isinstance(value, (bool, np.bool_)) or pd.isna(value):
        return None
    return float(value)


def latest_values(frame, columns):
    return {column: numeric_value(frame, column) for column in columns}


def directional_window_values(frame, column, bars, *, percent=False):
    value, previous, past, preceding = (
        numeric_value(frame, column, offset) for offset in (0, 1, bars, bars + 1)
    )

    def slope(current, prior):
        if current is None or prior is None or (percent and prior == 0):
            return None
        return (current - prior) / prior * 100 if percent else current - prior

    return {
        "value": value,
        "delta": value - previous if value is not None and previous is not None else None,
        "slope": slope(value, past),
        "prior_slope": slope(previous, preceding),
    }


def supertrend_age_values(frame):
    direction = (
        frame["SuperTrend_Dir"].to_numpy(float) if "SuperTrend_Dir" in frame else np.array([])
    )
    up = bool(len(direction) and direction[-1] == 1)
    age = None
    if up:
        i = len(direction) - 1
        while i >= 0 and direction[i] == 1:
            i -= 1
        if i >= 0:
            age = len(direction) - i - 2
    return {"st_up": up, "buy_flip_age": age}


def below_window_values(frame, column, length):
    if not {"Close", column} <= set(frame) or len(frame) < length:
        return np.array([], dtype=bool)
    return frame["Close"].to_numpy(float)[-length:] < frame[column].to_numpy(float)[-length:]


def below_streak_value(frame, column, length):
    return bool(
        {"Close", column} <= set(frame)
        and len(frame) >= length
        and below_window_values(frame, column, length).all()
    )


def below_count_value(frame, column, length):
    return int(np.count_nonzero(below_window_values(frame, column, length)))


def _window_pair_values(frame, column, recent, prior, reducer):
    if column not in frame or len(frame) < recent + prior:
        return None, None
    values = frame[column].to_numpy(float)
    a, b = reducer(values[-recent:]), reducer(values[-recent - prior : -recent])
    return (float(a) if np.isfinite(a) else None, float(b) if np.isfinite(b) else None)


def low_window_values(frame, *, recent=10, prior=30):
    return _window_pair_values(frame, "Low", recent, prior, np.nanmin)


def volume_window_values(frame, *, recent=5, prior=20):
    return _window_pair_values(frame, "Volume", recent, prior, np.nanmean)


def state_window_values(frame, **parameters):
    """Full fact facade; each direct compatibility helper uses only its primitive."""
    settings = {**STATE_WINDOW_PARAMETERS, **parameters}
    directional = {
        column: directional_window_values(frame, column, spec["bars"], percent=spec["percent"])
        for column, spec in settings["directional_windows"].items()
    }
    supertrend = supertrend_age_values(frame)
    streak = below_streak_value(frame, "SMA_20", settings["streak_bars"])
    count = below_count_value(frame, "SMA_50", settings["weakness_lookback"])
    recent_low, prior_low = low_window_values(
        frame, recent=settings["low_recent"], prior=settings["low_prior"]
    )
    recent_volume, prior_volume = volume_window_values(
        frame, recent=settings["volume_recent"], prior=settings["volume_prior"]
    )
    return {
        "directional": directional,
        "latest": latest_values(
            frame, ("Close", "SMA_20", "SMA_50", "cRSI", "cRSI_HighBand", "cRSI_LowBand")
        ),
        **supertrend,
        "below_sma20_streak": streak,
        "below_sma50_count": count,
        "recent_low": recent_low,
        "prior_low": prior_low,
        "recent_volume_mean": recent_volume,
        "prior_volume_mean": prior_volume,
    }

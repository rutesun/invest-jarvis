"""Playbook numerical facts without gate, severity, sizing or trading policy."""

import pandas as pd

from src.tools.technical.chart_analysis._legacy_components import vcp_values


def playbook_vcp_values(frame, *, thresholds=None):
    vcp = vcp_values(frame, thresholds=thresholds)
    result = {"in_vcp": vcp["in_vcp"], "pivot": None, "breakout": False, "vcp": vcp}
    if not result["in_vcp"] or len(frame) < 21:
        return result
    pivot = float(frame.iloc[-21:]["High"].iloc[:-1].max())
    row = frame.iloc[-1]
    close = float(row["Close"])
    average = None
    if (
        "Vol_SMA_50" in frame
        and row.get("Vol_SMA_50") is not None
        and pd.notna(row.get("Vol_SMA_50"))
    ):
        average = float(row["Vol_SMA_50"])
    vol_ok = average is not None and float(row["Volume"]) >= average * 1.5
    result.update(
        pivot_raw=pivot,
        pivot=round(pivot, 2),
        close=close,
        vol_sma_50=average,
        vol_ok=vol_ok,
        breakout=bool(close > pivot and vol_ok),
    )
    return result


def accumulation_values(frame, *, window=25):
    result = {
        "accumulation_days": 0,
        "distribution_days": 0,
        "accumulation_ratio": 0.0,
        "window": window,
        "accumulation_ratio_raw": 0.0,
        "occurrences": [],
    }
    if (
        frame is None
        or frame.empty
        or not {"Open", "High", "Low", "Close", "Volume"} <= set(frame)
        or len(frame) < 2
    ):
        return result
    recent = frame.tail(window + 1)
    for pos in range(1, len(recent)):
        previous, row = recent.iloc[pos - 1], recent.iloc[pos]
        prev_close, prev_volume = float(previous["Close"]), float(previous["Volume"])
        close, high, low, volume = (float(row[key]) for key in ("Close", "High", "Low", "Volume"))
        if not volume > prev_volume:
            continue
        if close < prev_close * (1 - 0.002):
            kind = "distribution"
        elif close > prev_close:
            location = (close - low) / (high - low) if high - low > 0 else 1.0
            if location < 0.5 or pd.isna(location):
                continue
            kind = "accumulation"
        else:
            continue
        result[f"{kind}_days"] += 1
        result["occurrences"].append({"index": recent.index[pos], "kind": kind})
    total = result["accumulation_days"] + result["distribution_days"]
    ratio = result["accumulation_days"] / total if total > 0 else 0.0
    result.update(accumulation_ratio_raw=ratio, accumulation_ratio=round(ratio, 4))
    return result


def market_regime_values(frame):
    close = frame["Close"].dropna()
    if len(close) < 200:
        return {"available": False, "regime": "unknown", "above": False, "rising": False}
    sma50, sma200 = close.rolling(50).mean(), close.rolling(200).mean()
    last, s50, s200 = float(close.iloc[-1]), float(sma50.iloc[-1]), float(sma200.iloc[-1])
    # Original >=200 guard and actual 20-session endpoint gap are both preserved.
    prior = float(sma200.iloc[-21])
    above, rising = last > s50 and last > s200, s200 > prior
    regime = "상승" if above and rising else "조정" if last > s200 else "하락"
    return {
        "available": True,
        "close": last,
        "sma_50": s50,
        "sma_200": s200,
        "sma_200_lag20": prior,
        "above": above,
        "rising": rising,
        "regime": regime,
    }


def relative_strength_values(stock_frame, index_frame):
    """Exact dropna/intersection/short-window/round behavior of legacy RS."""
    stock, index = stock_frame["Close"].dropna(), index_frame["Close"].dropna()
    common = stock.index.intersection(index.index)
    rp = (stock.loc[common] / index.loc[common]).dropna()
    if len(rp) < 2:
        return {
            "mansfield_rs": 0.0,
            "outperform_6m": 0.0,
            "rp_slope_4w": 0.0,
            "strong": False,
            "rp_count": len(rp),
            "common_sessions": tuple(common),
        }
    window = min(252, len(rp))
    # pandas raises if window<20, as the old public numerical path does.
    average = rp.rolling(window=window, min_periods=max(20, window // 4)).mean()
    last_rp, last_sma = float(rp.iloc[-1]), float(average.iloc[-1])
    mansfield = ((last_rp / last_sma) - 1) * 100 if last_sma else 0.0
    slope_n = min(20, len(rp) - 1)
    slope = float(rp.iloc[-1] - rp.iloc[-1 - slope_n])

    def performance(series):
        n = min(126, len(series) - 1)
        past = float(series.iloc[-1 - n])
        return ((float(series.iloc[-1]) - past) / past) * 100 if past else 0.0

    outperform = performance(stock.loc[common]) - performance(index.loc[common])
    rounded_rs, rounded_slope = round(mansfield, 2), round(slope, 6)
    return {
        "mansfield_rs": rounded_rs,
        "outperform_6m": round(outperform, 2),
        "rp_slope_4w": rounded_slope,
        "mansfield_rs_raw": mansfield,
        "outperform_6m_raw": outperform,
        "rp_slope_4w_raw": slope,
        "strong": rounded_rs > 0 and rounded_slope >= 0,
        "rp_count": len(rp),
        "common_sessions": tuple(common),
        "sma_window": window,
        "last_rp": last_rp,
        "last_rp_sma": last_sma,
    }

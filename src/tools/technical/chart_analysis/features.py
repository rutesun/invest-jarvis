"""CHART_FEATURE_V1: causal float64 materials, with no score/publication policy.

Every row describes its own fixed-origin prefix. PROVISIONAL values are preview
only; a later row cannot consume that preview as FINAL history. Recursive state
starts at the supplied origin and never restarts after missing dependencies.
"""

from datetime import date
from importlib.metadata import version
from importlib.util import find_spec

import numpy as np
import pandas as pd

from src.providers.price_history_range import normalize_history
from src.tools.technical.chart_analysis.models import CalculationScope, FeatureValue, SeriesInput


STRICT_VERSION = "CHART_FEATURE_V1"
LEGACY_VERSION = "LEGACY_FEATURE_AD880AF"
SUPPLIED_VERSION = "SUPPLIED_LEGACY_FEATURE_AD880AF"
SMA_PERIODS = (10, 20, 50, 100, 120, 150, 200)


def feature_provider_identity(feature_version: str) -> dict:
    """Describe the actual provider; 4C binds this payload into calculation keys."""
    if feature_version == SUPPLIED_VERSION:
        return {"feature_version": feature_version, "backend": "supplied-columns"}
    if feature_version not in (STRICT_VERSION, LEGACY_VERSION):
        raise ValueError(f"Unknown feature provider: {feature_version}")
    packages = {name: version(name) for name in ("numpy", "pandas")}
    result = {
        "feature_version": feature_version,
        "backend": "ordered-float64",
        "packages": packages,
    }
    if feature_version == LEGACY_VERSION:
        packages.update({name: version(name) for name in ("pandas-ta", "scipy")})
        talib = find_spec("talib") is not None
        result.update(
            backend="pandas-ta/talib" if talib else "pandas-ta/native", talib_installed=talib
        )
        if talib:
            packages["TA-Lib"] = version("TA-Lib")
    return result


def _sum(values: np.ndarray) -> np.float64:
    total = np.float64(0)
    for value in values:
        total = np.float64(total + value)
    return total


def _mean(values: np.ndarray) -> float:
    return float(_sum(values) / np.float64(len(values)))


def _value(value: float | None, reason: str = "INPUT_MISSING") -> FeatureValue:
    if value is None or not np.isfinite(value):
        return FeatureValue(None, "UNAVAILABLE", (reason,))
    return FeatureValue(float(value), "READY")


def _window(values: np.ndarray, end: int, size: int, operation, *, lag: int = 0) -> FeatureValue:
    stop = end + 1 - lag
    start = stop - size
    if start < 0:
        return _value(None, "HISTORY_SHORT")
    window = values[start:stop]
    return _value(float(operation(window))) if np.isfinite(window).all() else _value(None)


def _recursive(tr: np.ndarray, close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    atr, rsi = np.full(len(close), np.nan), np.full(len(close), np.nan)
    gain, loss = np.float64(0), np.float64(0)
    atr_valid = rsi_valid = True
    for i in range(len(close)):
        atr_valid = atr_valid and bool(np.isfinite(tr[i]))
        if atr_valid and i == 13:
            atr[i] = _mean(tr[:14])
        elif atr_valid and i > 13:
            atr[i] = (np.float64(13) * atr[i - 1] + tr[i]) / np.float64(14)
        rsi_valid = rsi_valid and bool(np.isfinite(close[i]))
        if not rsi_valid or i == 0:
            continue
        delta = np.float64(close[i] - close[i - 1])
        up, down = max(delta, np.float64(0)), max(-delta, np.float64(0))
        if i <= 14:
            gain, loss = np.float64(gain + up), np.float64(loss + down)
            if i < 14:
                continue
            gain, loss = gain / np.float64(14), loss / np.float64(14)
        else:
            gain = (np.float64(13) * gain + up) / np.float64(14)
            loss = (np.float64(13) * loss + down) / np.float64(14)
        rsi[i] = (
            50
            if gain == loss == 0
            else 100
            if loss == 0
            else 0
            if gain == 0
            else 100 - 100 / (1 + gain / loss)
        )
    return atr, rsi


def _volume_features(close: np.ndarray, volume: np.ndarray, i: int) -> dict[str, FeatureValue]:
    keys = (
        "Up_Volume_20",
        "Down_Volume_20",
        "Flat_Volume_20",
        "Up_Days_20",
        "Down_Days_20",
        "Flat_Days_20",
        "Directional_Sample_20",
        "Max_Directional_Volume_20",
        "Max_Directional_Share_20",
    )
    if i < 20:
        return {key: _value(None, "HISTORY_SHORT") for key in keys}
    prices, volumes = close[i - 20 : i + 1], volume[i - 19 : i + 1]
    if not np.isfinite(prices).all() or not np.isfinite(volumes).all():
        return {key: _value(None) for key in keys}
    changes = prices[1:] - prices[:-1]
    up, down, flat = changes > 0, changes < 0, changes == 0
    directional = (up | down) & (volumes > 0)
    up_volume, down_volume, flat_volume = (_sum(volumes[mask]) for mask in (up, down, flat))
    maximum = float(volumes[directional].max()) if directional.any() else 0.0
    denominator = np.float64(up_volume + down_volume)
    values = (
        up_volume,
        down_volume,
        flat_volume,
        int(up.sum()),
        int(down.sum()),
        int(flat.sum()),
        int(directional.sum()),
        maximum,
    )
    result = {key: _value(value) for key, value in zip(keys[:-1], values, strict=True)}
    result[keys[-1]] = (
        _value(maximum / denominator)
        if denominator > 0
        else _value(None, "ZERO_DIRECTIONAL_VOLUME")
    )
    return result


def _session_finality(series: SeriesInput, day: date) -> str:
    finality = series.manifest.finality
    return str(finality if isinstance(finality, str) else finality.get(day, "UNKNOWN"))


def _input_frame(series: SeriesInput) -> pd.DataFrame:
    raw = series.raw
    coverage = series.manifest.coverage
    expected = coverage.get("expected_sessions", ()) if hasattr(coverage, "get") else ()
    index = pd.DatetimeIndex(
        [day for day in expected if pd.Timestamp(day).date() <= series.manifest.as_of]
    )
    if len(index) and (not index.is_monotonic_increasing or not index.is_unique):
        raise ValueError("expected sessions must be ascending and unique")
    if not len(raw) and not len(index):
        return raw
    start = index[0].date() if len(index) else raw.index[0].date()
    if len(index) and not raw.index.isin(index).all():
        raise ValueError("raw contains dates outside expected sessions")
    frame = normalize_history(raw, start=start, end=series.manifest.as_of)
    return frame.reindex(index) if len(index) else frame


def calculate_features(scope: CalculationScope) -> dict[date, dict[str, FeatureValue]]:
    """Calculate strict instrument-only materials; related readiness is irrelevant.

    ``History_Status`` describes complete valid FINAL history from origin, while
    ``Valid_Final_Streak`` counts the current contiguous valid FINAL run. Neither
    enforces Quality's 220 calculation / 252 publication policy.
    """
    series = scope.primary
    if series.manifest.feature_version != STRICT_VERSION:
        raise ValueError("calculate_features requires CHART_FEATURE_V1")
    frame = _input_frame(series)
    if frame.empty:
        return {}
    close, high, low, volume = (
        frame[key].to_numpy(dtype=np.float64) for key in ("Close", "High", "Low", "Volume")
    )
    tr = np.full(len(frame), np.nan)
    for i in range(len(frame)):
        if not np.isfinite(high[i]) or not np.isfinite(low[i]):
            continue
        if i == 0:
            tr[i] = high[i] - low[i]
        elif np.isfinite(close[i - 1]):
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr, rsi = _recursive(tr, close)
    results: dict[date, dict[str, FeatureValue]] = {}
    incomplete_finality = False
    incomplete_history = False
    streak = 0
    # An unproven origin affects this prefix; later whole-range coverage does not.
    coverage = series.manifest.coverage
    origin_missing = hasattr(coverage, "get") and coverage.get("reached_start") is False
    for i, stamp in enumerate(frame.index):
        day = stamp.date()
        finality = _session_finality(series, day)
        valid = bool(np.isfinite(frame.iloc[i].to_numpy(dtype=np.float64)).all())
        streak = streak + 1 if valid and finality == "FINAL" else 0
        incomplete_history = (
            incomplete_history or not valid or finality != "FINAL" or origin_missing
        )
        row = {
            key: _value(frame[key].iloc[i]) for key in ("Open", "High", "Low", "Close", "Volume")
        }
        row["TR"] = _value(tr[i])
        row["ATR"] = _value(
            atr[i],
            "HISTORY_SHORT" if i < 13 and np.isfinite(tr[: i + 1]).all() else "INPUT_MISSING",
        )
        row["RSI"] = _value(
            rsi[i],
            "HISTORY_SHORT" if i < 14 and np.isfinite(close[: i + 1]).all() else "INPUT_MISSING",
        )
        for period in SMA_PERIODS:
            row[f"SMA_{period}"] = _window(close, i, period, _mean)
        row["SMA_200_Lag20"] = _window(close, i, 200, _mean, lag=20)
        for field, values, operation in (("High", high, np.max), ("Low", low, np.min)):
            row[f"{field}_20_New"] = _window(values, i, 20, operation)
            row[f"{field}_20_Prior"] = _window(values, i, 20, operation, lag=20)
        for lag in (5, 20, 60):
            # Entire return path is required even though the consumer uses endpoints.
            history = close[max(0, i - lag) : i + 1]
            row[f"Close_Lag{lag}"] = (
                _value(None, "HISTORY_SHORT")
                if i < lag
                else _value(close[i - lag])
                if np.isfinite(history).all()
                else _value(None)
            )
        row.update(_volume_features(close, volume, i))
        row["History_Bars"] = _value(i + 1)
        row["Valid_Final_Streak"] = _value(streak)
        row["History_Status"] = (
            FeatureValue(1.0, "READY")
            if not incomplete_history
            else FeatureValue(None, "UNAVAILABLE", ("INCOMPLETE_PREFIX",))
        )
        if origin_missing:
            for key in ("ATR", "RSI"):
                row[key] = FeatureValue(
                    None,
                    "UNAVAILABLE",
                    tuple(dict.fromkeys((*row[key].reasons, "INCOMPLETE_PREFIX"))),
                )
        if incomplete_finality or finality not in ("FINAL", "PROVISIONAL"):
            row = {
                key: FeatureValue(
                    None, "UNAVAILABLE", tuple(dict.fromkeys((*value.reasons, "INCOMPLETE_PREFIX")))
                )
                for key, value in row.items()
            }
        elif finality == "PROVISIONAL":
            row = {
                key: FeatureValue(
                    value.value, "PROVISIONAL", (*value.reasons, "PROVISIONAL_PREVIEW")
                )
                for key, value in row.items()
            }
        results[day] = row
        incomplete_finality = incomplete_finality or finality != "FINAL"
    return results

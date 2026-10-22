"""Shadow scorecard built from existing persistent technical state rules."""

from datetime import date

import pandas as pd

from src.tools.technical.components.patterns import PatternThresholds
from src.tools.technical.components.velocity import ACCEL_THRESHOLD, SLOPE_THRESHOLD
from src.tools.technical.models import TechnicalResult
from src.tools.technical.scorecard_models import (
    Acceleration,
    DataStatus,
    Direction,
    DirectionalMetric,
    Evidence,
    Importance,
    Observation,
    ScoreContribution,
    ScoreDimension,
    TechnicalScorecard,
)
from src.tools.technical.triggers import detect_analysis_triggers


_VERSION = "TECHNICAL_SCORECARD_V1"
_DIRECTION_VERSION = "DIRECTION_V1"


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool) or pd.isna(value):
        return None
    return float(value)


def _latest(df: pd.DataFrame, column: str, offset: int = 0) -> float | None:
    if column not in df or len(df) <= offset:
        return None
    return _number(df.iloc[-1 - offset][column])


def _metric(
    df: pd.DataFrame, column: str, code: str, bars: int, *, percent: bool = False
) -> DirectionalMetric:
    value = _latest(df, column)
    previous = _latest(df, column, 1)
    past = _latest(df, column, bars)
    preceding = _latest(df, column, bars + 1)
    delta = value - previous if value is not None and previous is not None else None
    slope = None
    prior_slope = None
    if value is not None and past is not None and (not percent or past != 0):
        slope = (value - past) / past * 100 if percent else value - past
    if previous is not None and preceding is not None and (not percent or preceding != 0):
        prior_slope = (previous - preceding) / preceding * 100 if percent else previous - preceding
    # DIRECTION_V1: exact zero is flat; a direction transition has unknown acceleration.
    direction = (
        Direction.UNKNOWN
        if slope is None
        else Direction.RISING
        if slope > 0
        else Direction.FALLING
        if slope < 0
        else Direction.FLAT
    )
    if (
        slope is None
        or prior_slope is None
        or (slope > 0) != (prior_slope > 0)
        or (slope < 0) != (prior_slope < 0)
    ):
        acceleration = Acceleration.UNKNOWN
    elif abs(slope) > abs(prior_slope):
        acceleration = Acceleration.ACCELERATING
    elif abs(slope) < abs(prior_slope):
        acceleration = Acceleration.DECELERATING
    else:
        acceleration = Acceleration.STABLE
    return DirectionalMetric(
        code=code,
        value=value,
        unit="percent" if percent else None,
        direction=direction,
        delta_1d=delta,
        slope=slope,
        slope_unit="percent" if percent else "value",
        slope_lookback_bars=bars,
        acceleration=acceleration,
        calculation_version=_DIRECTION_VERSION,
        data_status=DataStatus.COMPLETE
        if slope is not None and prior_slope is not None
        else DataStatus.INSUFFICIENT_DATA,
        missing_reason=None
        if slope is not None and prior_slope is not None
        else f"{column}: {bars + 2} valid bars required",
    )


def _observation(
    code: str,
    message: str,
    source: str,
    metrics: list[str],
    *,
    observed: float | None = None,
    reference: float | None = None,
    direction: Direction | None = None,
) -> Observation:
    return Observation(
        code=code,
        message=message,
        direction=direction,
        importance=Importance.MEDIUM,
        source_metrics=metrics,
        evidence=[
            Evidence(
                code=code,
                message=message,
                observed_value=observed,
                reference_value=reference,
                importance=Importance.MEDIUM,
                source=source,
            )
        ],
    )


def _contribution(
    code: str, points: int, raw_state: str, required: list[str], missing: list[str], source: str
) -> ScoreContribution:
    message = (
        f"{code}: {raw_state} ({points:+d})"
        if not missing
        else f"{code}: missing {', '.join(missing)}"
    )
    return ScoreContribution(
        rule_code=code,
        raw_state=raw_state,
        points=points,
        required_inputs=required,
        missing_inputs=missing,
        calculation_version=_VERSION,
        evidence=[
            Evidence(
                code=code,
                message=message,
                observed_value=None,
                reference_value=None,
                importance=Importance.MEDIUM,
                source=source,
            )
        ],
    )


def _dimension(
    code: str,
    bounds: tuple[int, int],
    contributions: list[ScoreContribution],
    metrics: dict,
    observations: list[Observation],
) -> ScoreDimension:
    complete = bool(contributions) and all(not part.missing_inputs for part in contributions)
    minimum, maximum = bounds
    raw = sum(part.points for part in contributions) if complete else None
    score = (
        max(0, min(100, round(100 * (raw - minimum) / (maximum - minimum))))
        if raw is not None and maximum > minimum
        else None
    )
    optional = [metric for metric in metrics.values() if isinstance(metric, DirectionalMetric)]
    optional_complete = sum(metric.data_status is DataStatus.COMPLETE for metric in optional)
    status = (
        DataStatus.INSUFFICIENT_DATA
        if score is None
        else DataStatus.PARTIAL
        if optional_complete < len(optional)
        else DataStatus.COMPLETE
    )
    covered = sum(not part.missing_inputs for part in contributions) + optional_complete
    coverage = 100.0 * covered / (len(contributions) + len(optional)) if contributions else 0.0
    return ScoreDimension(
        code=code,
        score=score,
        raw_state_points=raw,
        minimum_points=minimum,
        maximum_points=maximum,
        calculation_version=_VERSION,
        data_status=status,
        coverage_pct=coverage,
        metrics=metrics,
        observations=observations,
        score_contributions=contributions,
    )


def _missing(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if _latest(df, column) is None]


def _trend(df: pd.DataFrame, legacy: TechnicalResult) -> ScoreDimension:
    metrics: dict = {
        f"sma{length}": _metric(df, f"SMA_{length}", f"sma{length}", 21, percent=True)
        for length in (20, 50, 100, 150, 200)
    }
    metrics["supertrend_direction"] = _latest(df, "SuperTrend_Dir")
    observations = []
    close = _latest(df, "Close")
    for length in (20, 50, 150, 200):
        sma = _latest(df, f"SMA_{length}")
        if close is not None and sma is not None:
            observations.append(
                _observation(
                    f"close_vs_sma{length}",
                    f"종가 {'ABOVE' if close > sma else 'BELOW'} SMA{length}",
                    "trend",
                    ["close", f"sma{length}"],
                    observed=close,
                    reference=sma,
                )
            )

    minervini = legacy.components.get("minervini", {})
    min_metrics = minervini.get("metrics") or {}
    min_required = ["Close", "SMA_50", "SMA_150", "SMA_200", "High_52w", "Low_52w"]
    min_missing = _missing(df, min_required)
    if len(df) < 200 or not min_metrics:
        min_missing.append("minervini:200_bars")
    min_points = int(minervini.get("score", 0)) if not min_missing else 0
    min_state = (
        "stage2" if min_points == 40 else "above_sma50" if min_points == 25 else "below_sma50"
    )
    contributions = [
        _contribution(
            "minervini.state",
            min_points,
            min_state,
            min_required + ["200_bars"],
            min_missing,
            "minervini",
        )
    ]

    direction = _latest(df, "SuperTrend_Dir")
    super_value = _latest(df, "SuperTrend_Up" if direction == 1 else "SuperTrend_Dn")
    super_missing = _missing(df, ["SuperTrend_Dir"])
    if len(df) < 2:
        super_missing.append("supertrend:2_bars")
    # The line distance is a persistent state; ±15 transition bonuses are omitted.
    super_points = 20 if direction == 1 else -20 if direction == -1 else 0
    if direction in (1, -1) and close is not None and super_value not in (None, 0):
        distance = (close - super_value) / super_value * 100
        if direction == 1 and distance > 5:
            super_points += 5
        elif direction == -1 and -distance > 5:
            super_points -= 5
    contributions.append(
        _contribution(
            "supertrend.state",
            super_points if not super_missing else 0,
            str(direction),
            ["SuperTrend_Dir", "2_bars"],
            super_missing,
            "supertrend",
        )
    )
    return _dimension("trend", (-45, 65), contributions, metrics, observations)


def _structure(df: pd.DataFrame, legacy: TechnicalResult) -> ScoreDimension:
    pattern = legacy.components.get("patterns", {})
    values = pattern.get("metrics") or {}
    contraction = _number(values.get("atr_contraction_ratio"))
    missing = _missing(df, ["High", "Low", "ATR"])
    if (
        len(df) < 20
        or df.get("ATR", pd.Series(dtype=float)).dropna().size < 8
        or contraction is None
    ):
        missing.append("vcp:20_bars_and_8_atr")
    points = 0
    if contraction is not None and contraction > PatternThresholds.VCP_ATR_CONTRACTION:
        points = (
            20
            if values.get("recent_3_tight")
            and values.get("tight_days_count", 0) >= PatternThresholds.VCP_MIN_TIGHT_DAYS
            else 10
        )
    contribution = _contribution(
        "patterns.vcp_state",
        points if not missing else 0,
        "strong" if points == 20 else "contracting" if points == 10 else "none",
        ["High", "Low", "ATR", "20_bars", "8_atr"],
        missing,
        "patterns",
    )
    metrics = {
        "atr_contraction_ratio": contraction,
        "tight_days_count": values.get("tight_days_count"),
        "recent_3_tight": values.get("recent_3_tight"),
    }
    return _dimension("structure", (0, 20), [contribution], metrics, [])


def _momentum(df: pd.DataFrame, legacy: TechnicalResult) -> ScoreDimension:
    metrics: dict = {"crsi": _metric(df, "cRSI", "crsi", 5)}
    for column, code in (
        ("MACD", "macd"),
        ("MACD_Signal", "macd_signal"),
        ("MACD_Hist", "macd_histogram"),
    ):
        metrics[code] = _metric(df, column, code, 5)
    metrics["rsi"] = _latest(df, "RSI")
    observations = []
    macd = _latest(df, "MACD")
    signal = _latest(df, "MACD_Signal")
    if macd is not None and signal is not None:
        observations.append(
            _observation(
                "macd_vs_signal",
                f"MACD {'ABOVE' if macd > signal else 'BELOW'} signal",
                "momentum",
                ["macd", "macd_signal"],
                observed=macd,
                reference=signal,
            )
        )
    crsi = _latest(df, "cRSI")
    upper = _latest(df, "cRSI_HighBand")
    lower = _latest(df, "cRSI_LowBand")
    if crsi is not None and upper is not None and lower is not None:
        position = "ABOVE" if crsi > upper else "BELOW" if crsi < lower else "INSIDE"
        observations.append(
            _observation(
                "crsi_band_position",
                f"cRSI {position} bands",
                "momentum",
                ["crsi", "crsi_high_band", "crsi_low_band"],
                observed=crsi,
                reference=upper if position == "ABOVE" else lower,
            )
        )
    metrics["crsi_high_band"] = upper
    metrics["crsi_low_band"] = lower
    divergence = legacy.components.get("divergence", {})
    for name, value in (divergence.get("metrics") or {}).items():
        metrics[f"divergence_{name}"] = value
    for signal_text in divergence.get("signals") or []:
        observations.append(_observation("divergence_state", signal_text, "divergence", []))

    velocity = legacy.components.get("velocity", {})
    velocity_metrics = velocity.get("metrics") or {}
    slope = _number(velocity_metrics.get("norm_slope"))
    change = _number(velocity_metrics.get("slope_change"))
    velocity_missing = _missing(df, ["SMA_20"])
    if slope is None or change is None:
        velocity_missing.append("velocity:15_sma20_bars")
    close = _latest(df, "Close")
    sma20 = _latest(df, "SMA_20")
    velocity_points = 0
    if slope is not None and change is not None:
        if slope > SLOPE_THRESHOLD:
            velocity_points = 10 + (
                10 if change > ACCEL_THRESHOLD else -5 if change < -ACCEL_THRESHOLD * 2 else 0
            )
        elif slope < -SLOPE_THRESHOLD and not (
            close is not None and sma20 is not None and close > sma20
        ):
            velocity_points = -10 + (
                -10 if change < -ACCEL_THRESHOLD else 5 if change > ACCEL_THRESHOLD else 0
            )
    crsi_missing = _missing(df, ["cRSI", "cRSI_HighBand", "cRSI_LowBand"])
    crsi_points = 0
    if crsi is not None and upper is not None and lower is not None:
        crsi_points = (5 if upper - lower < 10 else 0) + (
            -10 if crsi > upper else 10 if crsi < lower else 0
        )
    contributions = [
        _contribution(
            "velocity.state",
            velocity_points if not velocity_missing else 0,
            "slope_and_acceleration",
            ["SMA_20", "15_sma20_bars"],
            velocity_missing,
            "velocity",
        ),
        _contribution(
            "crsi.state",
            crsi_points if not crsi_missing else 0,
            "band_width_and_position",
            ["cRSI", "cRSI_HighBand", "cRSI_LowBand"],
            crsi_missing,
            "crsi",
        ),
    ]
    return _dimension("momentum", (-30, 35), contributions, metrics, observations)


def _demand(df: pd.DataFrame) -> ScoreDimension:
    metrics: dict = {
        "volume": _metric(df, "Volume", "volume", 5, percent=True),
        "vol_sma20": _metric(df, "Vol_SMA_20", "vol_sma20", 5, percent=True),
        "vol_sma50": _metric(df, "Vol_SMA_50", "vol_sma50", 5, percent=True),
    }
    volume = _latest(df, "Volume")
    average = _latest(df, "Vol_SMA_20")
    metrics["vol_ratio"] = (
        volume / average if volume is not None and average not in (None, 0) else None
    )
    missing = _missing(df, ["Volume", "Vol_SMA_20"])
    message = (
        f"수급 입력 결측: {', '.join(missing)}"
        if missing
        else "TECHNICAL_SCORECARD_V1에 승인된 지속 수급 점수 규칙 없음"
    )
    return _dimension(
        "demand",
        (0, 0),
        [],
        metrics,
        [
            _observation(
                "demand_unscored" if not missing else "demand_missing_input",
                message,
                "volume",
                ["volume", "vol_sma20", "vol_ratio"],
                observed=metrics["vol_ratio"],
            )
        ],
    )


def _safety(df: pd.DataFrame, legacy: TechnicalResult) -> ScoreDimension:
    risk = legacy.components.get("risk", {})
    values = risk.get("metrics") or {}
    missing = _missing(df, ["Close"])
    if len(df) < 20 or "support_confluence" not in values or "resistance_confluence" not in values:
        missing.append("risk:20_bars_and_confluence")
    contribution = _contribution(
        "risk.confluence_state",
        int(risk.get("score", 0)) if not missing else 0,
        "support_resistance_confluence",
        ["Close", "20_bars", "confluence"],
        missing,
        "risk",
    )
    metrics = {
        "atr": _latest(df, "ATR"),
        "support_distance_pct": values.get("support_distance_pct"),
        "resistance_distance_pct": values.get("resistance_distance_pct"),
        "support_confluence": values.get("support_confluence"),
        "resistance_confluence": values.get("resistance_confluence"),
    }
    return _dimension("safety", (-15, 15), [contribution], metrics, [])


def build_scorecard(
    df: pd.DataFrame, legacy: TechnicalResult, *, ticker: str, as_of: date, version: str = _VERSION
) -> TechnicalScorecard:
    """Build parallel five-axis state scores; legacy totals and verdict stay authoritative."""
    if version != _VERSION:
        raise ValueError(f"Unsupported scorecard version: {version}")
    return TechnicalScorecard(
        version=version,
        ticker=ticker,
        as_of=as_of,
        trend=_trend(df, legacy),
        structure=_structure(df, legacy),
        momentum=_momentum(df, legacy),
        demand=_demand(df),
        safety=_safety(df, legacy),
        triggers=detect_analysis_triggers(df, as_of=as_of),
        legacy_raw_total=legacy.component_raw_total,
        legacy_adjusted_score=legacy.adjusted_score,
    )

from dataclasses import asdict
from datetime import UTC, datetime

import pandas as pd

from src.tools.technical.aggregator import ScoreAggregator
from src.tools.technical.bottoming import detect_bottoming_structure
from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.models import FactRef, FactSelection
from src.tools.technical.components.crsi import analyze_crsi
from src.tools.technical.components.divergence import analyze_divergence
from src.tools.technical.components.minervini import analyze_minervini
from src.tools.technical.components.patterns import analyze_patterns
from src.tools.technical.components.risk import analyze_risk
from src.tools.technical.components.supertrend import analyze_supertrend
from src.tools.technical.components.velocity import analyze_velocity
from src.tools.technical.components.volume import analyze_volume
from src.tools.technical.context import (
    build_market_context,
    common_analysis_for_frame,
    matches_common_request,
    validate_common_requests,
    validate_common_scope,
)
from src.tools.technical.context import compatibility_rule_request as rule_request
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.models import ScoreHistoryPoint, TechnicalResult
from src.tools.technical.scorecard import build_scorecard
from src.tools.technical.shadow_v2 import APRIME_RULE_IDS, compute_shadow_v2, shadow_fact_selections
from src.tools.technical.trigger_registry import TRIGGER_RULES


LEGACY_RULE_IDS = (
    "chart.stage2.minervini",
    "chart.velocity.legacy",
    "chart.crsi.legacy",
    "chart.supertrend.legacy",
    "chart.vcp.legacy",
    "chart.legacy.patterns_extra",
    "chart.legacy.volume_extra",
    "chart.pocket_pivot.down_candle",
    "chart.power_gap",
    "legacy.confluence",
    "legacy.divergence",
    "chart.context.breakdown",
    "chart.legacy.state_windows",
)


def technical_rule_requests():
    """Exact supplied-frame compatibility facts required by enabled consumers."""
    return tuple(
        rule_request(rule) for rule in dict.fromkeys((*LEGACY_RULE_IDS, *APRIME_RULE_IDS))
    ) + tuple(rule_request(rule.code, {"frame_policy": "SUPPLIED_AS_IS"}) for rule in TRIGGER_RULES)


_OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class TechnicalScorer:
    """Unified scoring system for technical analysis."""

    def __init__(self):
        self.calculator = IndicatorCalculator()
        self.aggregator = ScoreAggregator()

    def score(
        self,
        df: pd.DataFrame,
        ticker: str | None = None,
        include_history: bool = True,
        history_days: int = 5,
        *,
        common_analysis=None,
        request_context=None,
    ) -> TechnicalResult:
        """Calculate technical score from OHLCV data."""
        if common_analysis is not None:
            validate_common_scope(df, common_analysis, ticker=ticker)
            validate_common_requests(common_analysis, technical_rule_requests())
        context = request_context or AnalysisRequestContext()
        if common_analysis is None:
            common_analysis = common_analysis_for_frame(
                df,
                ticker=ticker,
                context=context,
                rules=technical_rule_requests(),
            )
        result = self._score_current(df, ticker=ticker, common_analysis=common_analysis)
        if include_history and history_days > 0:
            history, warning = self._build_score_history(
                df,
                ticker=ticker,
                history_days=history_days,
                request_context=context if common_analysis is not None else None,
            )
            result.score_history = history
            result.score_history_warning = warning
            if result.technical_verdict is not None:
                result.technical_verdict.score_trend_summary = _summarize_score_history(history)
        return result

    def _score_current(
        self, df: pd.DataFrame, ticker: str | None = None, *, common_analysis=None
    ) -> TechnicalResult:
        """Calculate the current score without building score history."""
        # Analyze with each component
        minervini_result = analyze_minervini(df, common_analysis=common_analysis)
        velocity_result = analyze_velocity(df, common_analysis=common_analysis)
        crsi_result = analyze_crsi(df, common_analysis=common_analysis)
        volume_result = analyze_volume(df, common_analysis=common_analysis)
        patterns_result = analyze_patterns(df, common_analysis=common_analysis)
        supertrend_result = analyze_supertrend(df, common_analysis=common_analysis)
        divergence_result = analyze_divergence(df, common_analysis=common_analysis)
        risk_result = analyze_risk(df, common_analysis=common_analysis)

        # Aggregate component results
        components = {
            "minervini": {
                "score": minervini_result.score,
                "signals": minervini_result.signals,
                "evidence": minervini_result.evidence,
                "metrics": minervini_result.metrics,
                "signal_metadata": minervini_result.signal_metadata,
            },
            "velocity": {
                "score": velocity_result.score,
                "signals": velocity_result.signals,
                "evidence": velocity_result.evidence,
                "metrics": velocity_result.metrics,
                "signal_metadata": velocity_result.signal_metadata,
            },
            "crsi": {
                "score": crsi_result.score,
                "signals": crsi_result.signals,
                "evidence": crsi_result.evidence,
                "metrics": crsi_result.metrics,
                "signal_metadata": crsi_result.signal_metadata,
            },
            "volume": {
                "score": volume_result.score,
                "signals": volume_result.signals,
                "evidence": volume_result.evidence,
                "metrics": volume_result.metrics,
                "signal_metadata": volume_result.signal_metadata,
            },
            "patterns": {
                "score": patterns_result.score,
                "signals": patterns_result.signals,
                "evidence": patterns_result.evidence,
                "metrics": patterns_result.metrics,
                "signal_metadata": patterns_result.signal_metadata,
            },
            "supertrend": {
                "score": supertrend_result.score,
                "signals": supertrend_result.signals,
                "evidence": supertrend_result.evidence,
                "metrics": supertrend_result.metrics,
                "signal_metadata": supertrend_result.signal_metadata,
            },
            "divergence": {
                "score": divergence_result.score,
                "signals": divergence_result.signals,
                "evidence": divergence_result.evidence,
                "metrics": divergence_result.metrics,
                "signal_metadata": divergence_result.signal_metadata,
            },
            "risk": {
                "score": risk_result.score,
                "signals": risk_result.signals,
                "evidence": risk_result.evidence,
                "metrics": risk_result.metrics,
                "signal_metadata": risk_result.signal_metadata,
            },
        }

        component_raw_total = sum(comp["score"] for comp in components.values())
        snapshot = self.calculator.create_snapshot(df)
        context = build_market_context(df, common_analysis=common_analysis)
        bottoming = detect_bottoming_structure(
            df, components, context, common_analysis=common_analysis
        )
        aggregation = self.aggregator.aggregate(components, context, bottoming=bottoming)
        shadow = compute_shadow_v2(df, components, context, common_analysis=common_analysis)

        result = TechnicalResult.from_analysis(
            df,
            ticker=ticker,
            timestamp=datetime.now(UTC),
            snapshot=snapshot,
            components=components,
            total_score=component_raw_total,
            component_raw_total=aggregation.component_raw_total,
            adjusted_score=aggregation.adjusted_score,
            technical_verdict=aggregation.technical_verdict,
            aggregation_trace=aggregation.aggregation_trace,
            shadow_v2=asdict(shadow),
        )
        as_of = df.index[-1].date() if hasattr(df.index[-1], "date") else datetime.now(UTC).date()
        result.scorecard = build_scorecard(
            df, result, ticker=ticker or "", as_of=as_of, common_analysis=common_analysis
        )
        if common_analysis is not None:
            result.chart_analysis_id = common_analysis.analysis_id
            result.common_analyses = (common_analysis,)
            result.fact_selections = (
                tuple(
                    _legacy_fact_selection(common_analysis, item, df, components)
                    for item in common_analysis.items
                    if item.rule_id in LEGACY_RULE_IDS
                )
                + shadow_fact_selections(common_analysis, components)
                + (result.scorecard.fact_selections or ())
            )
        return result

    def _build_score_history(
        self,
        df: pd.DataFrame,
        ticker: str | None,
        history_days: int,
        request_context=None,
    ) -> tuple[list[ScoreHistoryPoint], str | None]:
        raw_ohlcv = df.loc[:, _OHLCV_COLUMNS].copy()
        valid_df = raw_ohlcv.dropna(subset=["Close"])
        recent_dates = list(valid_df.index[-history_days:])
        history: list[ScoreHistoryPoint] = []
        failures: list[str] = []
        previous_components: dict[str, dict] | None = None

        for date in recent_dates:
            try:
                raw_slice = raw_ohlcv.loc[:date].copy()
                frame = self.calculator.calculate(raw_slice)
                analysis = (
                    common_analysis_for_frame(
                        frame,
                        ticker=ticker,
                        context=request_context,
                        rules=technical_rule_requests(),
                    )
                    if request_context is not None
                    else None
                )
                daily = self._score_current(frame, ticker=ticker, common_analysis=analysis)
                first_reason = (
                    daily.technical_verdict.reasons[0]
                    if daily.technical_verdict and daily.technical_verdict.reasons
                    else "핵심 reason 없음"
                )
                history.append(
                    ScoreHistoryPoint(
                        date=str(date.date()) if hasattr(date, "date") else str(date),
                        close=float(raw_slice.dropna(subset=["Close"]).iloc[-1]["Close"]),
                        component_raw_total=daily.component_raw_total,
                        adjusted_score=daily.adjusted_score,
                        verdict_action=daily.technical_verdict.action,
                        one_line_reason=first_reason,
                        new_entry_allowed=daily.technical_verdict.new_entry_allowed,
                        driver_components=_top_component_drivers(daily.components),
                        change_drivers=_top_component_changes(
                            previous_components, daily.components
                        ),
                        events=_daily_events(previous_components, daily.components),
                        cautions=daily.technical_verdict.cautions[:2],
                    )
                )
                previous_components = daily.components
            except Exception as exc:
                failures.append(f"{date}: {exc}")

        warning = "; ".join(failures) if failures else None
        return history, warning


def _summarize_score_history(history: list[ScoreHistoryPoint]) -> str | None:
    if len(history) < 2:
        return None
    first = history[0].adjusted_score
    last = history[-1].adjusted_score
    direction = "개선" if last > first else "악화" if last < first else "정체"
    return f"최근 {len(history)}거래일 adjusted score는 {first}에서 {last}로 {direction}"


def _top_component_drivers(components: dict[str, dict], limit: int = 2) -> list[str]:
    scored = [(name, score) for name, score in _component_scores(components).items() if score != 0]
    scored.sort(key=lambda item: abs(item[1]), reverse=True)
    return [f"{name} {score:+d}" for name, score in scored[:limit]]


def _daily_events(
    previous_components: dict[str, dict] | None,
    current_components: dict[str, dict],
) -> list[str]:
    """Signals that newly turned on today (onset vs. the prior day)."""
    if previous_components is None:
        return []
    events: list[str] = []
    for name, component in current_components.items():
        previous = previous_components.get(name, {})
        previous_signals = set(previous.get("signals") or [])
        for signal in component.get("signals") or []:
            if signal not in previous_signals:
                events.append(signal)
    return events


# Components whose score is driven by a continuous indicator value.
# Narrate the actual indicator move instead of the score delta so that
# one-time event bonuses (e.g. cRSI Hook) don't create phantom "악화/개선".
_CONTINUOUS_COMPONENTS: dict[str, dict] = {
    "crsi": {
        "metric": "crsi",
        "label": "cRSI",
        "threshold": 3.0,
        "decimals": 1,
        "signed": False,
        "suffix": "",
    },
    "velocity": {
        "metric": "norm_slope",
        "label": "SMA20 기울기",
        "threshold": 0.02,
        "decimals": 2,
        "signed": True,
        "suffix": "%",
    },
}


def _continuous_value(name: str, component: dict) -> float | None:
    spec = _CONTINUOUS_COMPONENTS.get(name)
    if spec is None:
        return None
    metrics = component.get("metrics") or {}
    value = metrics.get(spec["metric"])
    return float(value) if value is not None else None


def _format_continuous(name: str, prev_val: float, cur_val: float) -> str | None:
    spec = _CONTINUOUS_COMPONENTS[name]
    delta = cur_val - prev_val
    sign_flip = (prev_val < 0 < cur_val) or (prev_val > 0 > cur_val)
    if abs(delta) < spec["threshold"] and not sign_flip:
        return None
    if sign_flip:
        direction = "상승전환" if cur_val > prev_val else "하락전환"
    else:
        direction = "상승" if delta > 0 else "하락"
    decimals = spec["decimals"]
    fmt = f"{{:+.{decimals}f}}" if spec["signed"] else f"{{:.{decimals}f}}"
    suffix = spec["suffix"]
    prev_text = fmt.format(prev_val) + suffix
    cur_text = fmt.format(cur_val) + suffix
    return f"{spec['label']} {prev_text}→{cur_text} {direction}"


def _is_pure_rolloff(previous: dict, current: dict) -> bool:
    previous_signals = set(previous.get("signals") or [])
    current_signals = set(current.get("signals") or [])
    disappeared = previous_signals - current_signals
    appeared = current_signals - previous_signals
    return bool(disappeared) and not appeared


def _top_component_changes(
    previous_components: dict[str, dict] | None,
    current_components: dict[str, dict],
    limit: int = 2,
) -> list[str]:
    if previous_components is None:
        return []
    previous_scores = _component_scores(previous_components)
    current_scores = _component_scores(current_components)
    component_names = set(previous_scores) | set(current_scores)

    continuous: list[str] = []
    discrete_changes: list[tuple[str, int]] = []

    for name in component_names:
        previous = previous_components.get(name, {})
        current = current_components.get(name, {})

        if name in _CONTINUOUS_COMPONENTS:
            prev_val = _continuous_value(name, previous)
            cur_val = _continuous_value(name, current)
            if prev_val is not None and cur_val is not None:
                driver = _format_continuous(name, prev_val, cur_val)
                if driver is not None:
                    continuous.append(driver)
                continue  # metrics present → continuous track owns this component

        delta = current_scores.get(name, 0) - previous_scores.get(name, 0)
        if delta == 0:
            continue
        if _is_pure_rolloff(previous, current):
            continue
        discrete_changes.append((name, delta))

    discrete_changes.sort(key=lambda item: (-abs(item[1]), item[0]))
    selected = discrete_changes[:limit]
    remaining_delta = sum(delta for _, delta in discrete_changes[limit:])
    formatted = [f"{name} {delta:+d} {_change_label(delta)}" for name, delta in selected]
    if remaining_delta:
        formatted.append(f"기타 {remaining_delta:+d} {_change_label(remaining_delta)}")
    formatted.extend(continuous)
    return formatted


def _component_scores(components: dict[str, dict]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for name, component in components.items():
        score = component.get("score", 0)
        scores[name] = int(score) if score is not None else 0
    return scores


def _change_label(delta: int) -> str:
    return "개선" if delta > 0 else "악화"


_LEGACY_RULE_COMPONENT = {
    "chart.stage2.minervini": "minervini",
    "chart.velocity.legacy": "velocity",
    "chart.crsi.legacy": "crsi",
    "chart.supertrend.legacy": "supertrend",
    "chart.vcp.legacy": "patterns",
    "chart.legacy.patterns_extra": "patterns",
    "chart.legacy.volume_extra": "volume",
    "chart.pocket_pivot.down_candle": "volume",
    "chart.power_gap": "volume",
    "legacy.confluence": "risk",
    "legacy.divergence": "divergence",
}
_COMPONENT_MINIMUM_BARS = {
    "minervini": 200,
    "velocity": 15,
    "crsi": 2,
    "supertrend": 2,
    "patterns": 3,
    "volume": 2,
    "risk": 20,
    "divergence": 50,
}


def _component_skip_reason(frame, name, component):
    """Use the existing component's return/guard, never infer consumption from availability."""
    if name == "volume" and "Vol_SMA_20" not in frame:
        return "LEGACY_VOLUME_MISSING_VOL_SMA_20"
    if len(frame) < _COMPONENT_MINIMUM_BARS[name]:
        return f"LEGACY_{name.upper()}_HISTORY_SHORT"
    # A valid pattern evaluation can have no metrics and no detected events.
    if name == "patterns" or component.get("metrics"):
        return None
    if name == "volume":
        return "LEGACY_VOLUME_VALUES_UNAVAILABLE"
    return f"LEGACY_{name.upper()}_INPUT_UNAVAILABLE"


def _legacy_fact_selection(analysis, item, frame, components):
    component = _LEGACY_RULE_COMPONENT.get(item.rule_id)
    skipped = _component_skip_reason(frame, component, components[component]) if component else None
    if not matches_common_request(item, rule_request(item.rule_id)):
        selected, reason = False, "LEGACY_FACT_VARIANT_NOT_SELECTED"
    elif skipped:
        selected, reason = False, skipped
    elif item.state == "UNAVAILABLE":
        selected = False
        reason = "LEGACY_FACT_" + next(iter(item.evidence.get("reasons", ())), "UNAVAILABLE")
    else:
        selected, reason = True, "LEGACY_CONSUMED"
    return FactSelection(FactRef(analysis.analysis_id, item.id), selected, reason)

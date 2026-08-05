from datetime import UTC, datetime

import pandas as pd

from src.tools.technical.aggregator import ScoreAggregator
from src.tools.technical.components.crsi import analyze_crsi
from src.tools.technical.components.divergence import analyze_divergence
from src.tools.technical.components.minervini import analyze_minervini
from src.tools.technical.components.patterns import analyze_patterns
from src.tools.technical.components.risk import analyze_risk
from src.tools.technical.components.supertrend import analyze_supertrend
from src.tools.technical.components.velocity import analyze_velocity
from src.tools.technical.components.volume import analyze_volume
from src.tools.technical.context import build_market_context
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.models import ScoreHistoryPoint, TechnicalResult


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
    ) -> TechnicalResult:
        """Calculate technical score from OHLCV data."""
        result = self._score_current(df, ticker=ticker)
        if include_history and history_days > 0:
            history, warning = self._build_score_history(
                df, ticker=ticker, history_days=history_days
            )
            result.score_history = history
            result.score_history_warning = warning
            if result.technical_verdict is not None:
                result.technical_verdict.score_trend_summary = _summarize_score_history(history)
        return result

    def _score_current(self, df: pd.DataFrame, ticker: str | None = None) -> TechnicalResult:
        """Calculate the current score without building score history."""
        # Analyze with each component
        minervini_result = analyze_minervini(df)
        velocity_result = analyze_velocity(df)
        crsi_result = analyze_crsi(df)
        volume_result = analyze_volume(df)
        patterns_result = analyze_patterns(df)
        supertrend_result = analyze_supertrend(df)
        divergence_result = analyze_divergence(df)
        risk_result = analyze_risk(df)

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
        context = build_market_context(df)
        aggregation = self.aggregator.aggregate(components, context)

        return TechnicalResult.from_analysis(
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
        )

    def _build_score_history(
        self,
        df: pd.DataFrame,
        ticker: str | None,
        history_days: int,
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
                daily = self._score_current(self.calculator.calculate(raw_slice), ticker=ticker)
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
    changes = [
        (name, current_scores.get(name, 0) - previous_scores.get(name, 0))
        for name in component_names
    ]
    changes = [(name, delta) for name, delta in changes if delta != 0]
    changes.sort(key=lambda item: (-abs(item[1]), item[0]))

    selected = changes[:limit]
    remaining_delta = sum(delta for _, delta in changes[limit:])
    formatted = [f"{name} {delta:+d} {_change_label(delta)}" for name, delta in selected]
    if remaining_delta:
        formatted.append(f"기타 {remaining_delta:+d} {_change_label(remaining_delta)}")
    return formatted


def _component_scores(components: dict[str, dict]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for name, component in components.items():
        score = component.get("score", 0)
        scores[name] = int(score) if score is not None else 0
    return scores


def _change_label(delta: int) -> str:
    return "개선" if delta > 0 else "악화"

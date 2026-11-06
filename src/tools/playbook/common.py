"""Playbook's explicit instrument/benchmark scope and fact transport adapters."""

import pandas as pd

from src.storage.canonical import canonical_hash
from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.features import SUPPLIED_VERSION
from src.tools.technical.chart_analysis.models import (
    CalculationScope,
    InputManifest,
    SeriesInput,
    content_hash,
)
from src.tools.technical.context import compatibility_rule_request as rule_request
from src.tools.technical.context import matches_common_request, validate_common_requests
from src.tools.technical.indicators import IndicatorCalculator


def chart_frame(series):
    return pd.DataFrame(
        {
            name: [float(getattr(bar, name.lower())) for bar in series.bars]
            for name in ("Open", "High", "Low", "Close", "Volume")
        },
        index=pd.DatetimeIndex([bar.session_date for bar in series.bars]),
    )


def stock_is_ready(bundle):
    series = bundle.instrument
    return (
        series.coverage.complete
        and series.coverage.truncation_reason is None
        and len(series.bars) >= 221
    )


def playbook_rule_requests(bundle):
    if not stock_is_ready(bundle):
        return ()
    rules = ["chart.accumulation.days", "chart.stage2.minervini", "chart.vcp.playbook"]
    if bundle.market is not None:
        rules.extend(("chart.market.regime", "chart.rs"))
    return tuple(rule_request(rule) for rule in rules)


def playbook_scope(bundle, stock):
    calendar = canonical_hash("jarvis:playbook-calendar:v1", bundle.exchange_sessions)

    def series_input(series, frame, ticker):
        return SeriesInput(
            InputManifest(
                ticker=ticker,
                exchange="UNSPECIFIED",
                as_of=bundle.as_of,
                origin=str(frame.index[0].date())
                if len(frame)
                else str(series.coverage.actual_start),
                input_profile=bundle.profile_version,
                feature_version=SUPPLIED_VERSION,
                input_hash="",
                adjustment_policy="AS_SUPPLIED",
                calendar_version=calendar,
                finality={bar.session_date: bar.finality.value.upper() for bar in series.bars},
                coverage=series.coverage.model_dump(mode="python"),
            ),
            frame,
        )

    related = {}
    if bundle.market is not None:
        related["market"] = series_input(
            bundle.market, chart_frame(bundle.market), bundle.market_ticker
        )
    return CalculationScope(series_input(bundle.instrument, stock, bundle.ticker), related)


def common_analysis_for_bundle(bundle, *, stock_frame=None, context=None):
    """Snapshot the exact legacy stock frame and raw market with real bundle metadata."""
    if stock_frame is None:
        stock_frame = chart_frame(bundle.instrument)
        if stock_is_ready(bundle):
            stock_frame = IndicatorCalculator().calculate(stock_frame)
    return (context or AnalysisRequestContext()).get(
        playbook_scope(bundle, stock_frame), playbook_rule_requests(bundle)
    )


def validate_playbook_scope(bundle, stock, analysis):
    scope = playbook_scope(bundle, stock)
    dependencies = {role: value.manifest for role, value in scope.related.items()}
    if analysis.manifest != scope.primary.manifest or analysis.dependencies != dependencies:
        raise ValueError("common_analysis does not match Playbook evaluation scope")
    validate_common_requests(analysis, playbook_rule_requests(bundle))


def playbook_evidence(
    frame, analysis, rule_id, *, role="instrument", market=None, index_symbol=None
):
    """Read a scalar fact; public adapters validate the exact frames they consume."""
    manifest = analysis.manifest if role == "instrument" else analysis.dependencies.get(role)
    if (
        manifest is None
        or manifest.feature_version != SUPPLIED_VERSION
        or manifest.input_hash != content_hash(frame)
        or (role == "instrument" and frame.empty and rule_id != "chart.rs")
        or (role == "instrument" and not frame.empty and manifest.as_of != frame.index[-1].date())
        or (role == "market" and index_symbol is not None and manifest.ticker != index_symbol)
    ):
        raise ValueError("common_analysis does not match Playbook frame scope")
    if market is not None:
        dependency = analysis.dependencies.get("market")
        if (
            dependency is None
            or dependency.feature_version != SUPPLIED_VERSION
            or dependency.input_hash != content_hash(market)
            or (index_symbol is not None and dependency.ticker != index_symbol)
        ):
            raise ValueError("common_analysis does not match Playbook market scope")
    expected = rule_request(rule_id)
    validate_common_requests(analysis, (expected,))
    items = [item for item in analysis.items if matches_common_request(item, expected)]
    if (
        len(items) != 1
        or items[0].rule_version != expected.rule_version
        or items[0].parameter_id != expected.parameter_id
        or items[0].status_as_of != analysis.manifest.as_of
    ):
        raise ValueError(f"common_analysis {rule_id} fact contract mismatch")
    return items[0].evidence

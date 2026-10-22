from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from src.strategies.models import (
    BarFinality,
    ChartBar,
    ChartBundle,
    ChartSeries,
    CoverageManifest,
    ObservationCode,
    ObservationStatus,
    SignalFinality,
    StrategySignal,
)
from src.strategies.observations import make_observation
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.swing_w150.features import SwingFeatureFrame
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.tools.technical.scorecard_models import DataStatus, Direction, Evidence, Importance


def _evidence(code, value):
    return Evidence(
        code=code,
        message=code,
        observed_value=110,
        reference_value=value,
        importance=Importance.MEDIUM,
        source="SWING_W150_V2",
    )


def _inputs(code="PULLBACK_REVERSAL_ENTRY", finality=SignalFinality.FINAL):
    days = tuple(date(2026, 9, 1) + timedelta(days=i) for i in range(5))
    bars = tuple(
        ChartBar(
            session_date=day,
            open=Decimal("100"),
            high=Decimal("115"),
            low=Decimal(str(low)),
            close=Decimal("110"),
            volume=Decimal("1000"),
        )
        for day, low in zip(days, (95, 98, 97, 99, 50), strict=True)
    )
    bundle = ChartBundle(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=days[-1],
        instrument=ChartSeries(
            bars=bars,
            coverage=CoverageManifest(
                requested_start=days[0],
                actual_start=days[0],
                actual_end=days[-1],
                expected_sessions=days,
                complete=True,
            ),
        ),
        exchange_sessions=days,
    )
    params = SwingW150Parameters()
    source = StrategySignal(
        signal_id="frozen-source",
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version=params.parameter_set_version,
        parameter_fingerprint=params.parameter_fingerprint,
        code=code,
        occurred_on=days[3],
        finality=finality,
        direction=Direction.RISING,
        signal_price=Decimal("110"),
        evidence=[_evidence(code, 106), _evidence("SMA_50", 106)],
        data_status=DataStatus.COMPLETE,
    )
    features = SwingFeatureFrame(
        frame=pd.DataFrame(
            {
                "ATR": [1, 2, 3, 4, 40],
                "SMA_50": [99, 100, 103, 106, 200],
                "SuperTrend_Up": [98, 99, 101, 105, 190],
                "Trend_Breakout_High_Prev": [100, 101, 102, 104, 300],
                "Deep_Recovery_High_Prev": [90, 91, 92, 94, 200],
            },
            index=pd.DatetimeIndex(days),
        ),
        data_status=DataStatus.COMPLETE,
        finalities=(BarFinality.FINAL,) * 5,
    )
    episode = make_observation(
        ticker="AAPL",
        code=ObservationCode.PULLBACK_WATCH,
        origin=days[1],
        params=ObservationParameters(),
        status_as_of=days[3],
        ended_on=days[3],
        status=ObservationStatus.RESOLVED_TO_SIGNAL,
        evidence=[_evidence("SMA_50", 103), _evidence("SuperTrend_Up", 101)],
    )
    return source, bundle, features, episode


def _build(*args):
    from src.strategies.entry_anchors import build_entry_source_anchors

    return build_entry_source_anchors(*args)


def test_pullback_anchors_use_matched_episode_initial_support_and_source_bounded_low():
    source, bundle, features, episode = _inputs()
    unrelated = episode.model_copy(
        update={"started_on": bundle.exchange_sessions[0], "ended_on": bundle.as_of}
    )
    anchors = _build(source, bundle, features, [episode, unrelated])
    assert anchors.source_id == "frozen-source"
    assert anchors.source_date == date(2026, 9, 4)
    assert anchors.source_type == "PULLBACK_REVERSAL_ENTRY"
    assert anchors.signal_price == Decimal("110")
    assert anchors.atr_at_signal == Decimal("4")
    assert anchors.origin_support == Decimal("100")
    assert anchors.pullback_low == Decimal("97")
    assert anchors.breakout_level is None
    assert anchors.anchor_finality is SignalFinality.FINAL


def test_pullback_support_uses_observation_evidence_order():
    source, bundle, features, episode = _inputs()
    episode = episode.model_copy(update={"evidence": list(reversed(episode.evidence))})
    anchors = _build(source, bundle, features, [episode])
    assert anchors.origin_support == Decimal("99")


def test_future_chart_features_and_observations_cannot_change_anchors():
    source, bundle, features, episode = _inputs()
    before = source.model_dump(mode="json")
    full = _build(source, bundle, features, [episode])
    prefix = bundle.prefix(source.occurred_on)
    prefix_features = SwingFeatureFrame(
        frame=features.frame.iloc[:4],
        data_status=features.data_status,
        finalities=features.finalities[:4],
    )
    bounded = _build(source, prefix, prefix_features, [episode])
    assert full.model_dump(mode="json") == bounded.model_dump(mode="json")
    assert source.model_dump(mode="json") == before


@pytest.mark.parametrize(
    ("code", "expected"),
    [("TREND_BREAKOUT_ENTRY", "104"), ("DEEP_RECOVERY_ENTRY", "94")],
)
def test_breakout_anchor_is_source_feature_value(code, expected):
    source, bundle, features, _ = _inputs(code)
    anchors = _build(source, bundle, features, [])
    assert anchors.breakout_level == Decimal(expected)
    assert anchors.origin_support is None
    assert anchors.pullback_low is None


def test_missing_episode_and_nan_features_stay_explicitly_missing():
    source, bundle, features, _ = _inputs(finality=SignalFinality.PROVISIONAL)
    features.frame.loc[pd.Timestamp(source.occurred_on), "ATR"] = float("nan")
    anchors = _build(source, bundle, features, [])
    assert anchors.origin_support is None
    assert anchors.pullback_low is None
    assert anchors.atr_at_signal is None
    assert anchors.anchor_finality is SignalFinality.PROVISIONAL


def test_missing_initial_support_is_not_replaced_with_moving_reversal_support():
    source, bundle, features, episode = _inputs()
    features.frame.loc[pd.Timestamp(episode.started_on), "SMA_50"] = float("nan")
    anchors = _build(source, bundle, features, [episode])
    assert anchors.origin_support is None
    assert anchors.pullback_low == Decimal("97")


def test_nonresolved_episode_cannot_supply_pullback_anchors():
    source, bundle, features, episode = _inputs()
    episode = episode.model_copy(update={"status": ObservationStatus.EXPIRED})
    anchors = _build(source, bundle, features, [episode])
    assert anchors.origin_support is None
    assert anchors.pullback_low is None


@pytest.mark.parametrize(
    "kind,price", [("SMA50", "102"), ("PRIOR_BREAKOUT_LEVEL", "101"), ("SMA150", "99")]
)
def test_reversal_uses_matching_watch_anchor_origin(kind, price):
    source, bundle, features, episode = _inputs()
    episode = episode.model_copy(
        update={
            "anchor_id": f"cycle:{kind}",
            "anchor_type": kind,
            "anchor_origin_on": bundle.exchange_sessions[0],
            "anchor_origin_price": Decimal(price),
        }
    )
    earlier = episode.model_copy(
        update={
            "started_on": bundle.exchange_sessions[0],
            "ended_on": bundle.exchange_sessions[2],
            "status": ObservationStatus.INVALIDATED,
            "anchor_origin_price": Decimal("500"),
        }
    )
    anchors = _build(source, bundle, features, [earlier, episode])
    assert anchors.origin_support == Decimal(price)
    assert anchors.pullback_low == Decimal("97")

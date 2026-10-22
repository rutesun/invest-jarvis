from datetime import date

import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorecard import _metric, build_scorecard
from src.tools.technical.scorecard_models import Acceleration, DataStatus, Direction
from src.tools.technical.scorer import TechnicalScorer


@pytest.fixture
def calculated_df() -> pd.DataFrame:
    index = pd.bdate_range("2025-01-01", periods=260)
    close = [100 + i * 0.2 for i in range(260)]
    raw = pd.DataFrame(
        {
            "Open": [value - 0.5 for value in close],
            "High": [value + 1 for value in close],
            "Low": [value - 1 for value in close],
            "Close": close,
            "Volume": [1_000_000 + i * 100 for i in range(260)],
        },
        index=index,
    )
    return IndicatorCalculator().calculate(raw)


def test_scorecard_owns_each_persistent_rule_once_and_preserves_legacy(calculated_df):
    legacy = TechnicalScorer().score(calculated_df, ticker="AAPL", include_history=False)
    scorecard = build_scorecard(calculated_df, legacy, ticker="AAPL", as_of=date(2025, 12, 30))

    owners = [
        (dimension.code, contribution.rule_code)
        for dimension in scorecard.dimensions()
        for contribution in dimension.score_contributions
    ]
    assert len(owners) == len({rule for _, rule in owners})
    assert {dimension for dimension, _ in owners} == {"trend", "structure", "momentum", "safety"}
    assert scorecard.legacy_raw_total == legacy.component_raw_total
    assert scorecard.legacy_adjusted_score == legacy.adjusted_score
    assert all(trigger.occurred_on <= scorecard.as_of for trigger in scorecard.triggers)


def test_demand_exposes_unscored_volume_without_event_points(calculated_df):
    legacy = TechnicalScorer().score(calculated_df, ticker="AAPL", include_history=False)
    result = build_scorecard(calculated_df, legacy, ticker="AAPL", as_of=date(2025, 12, 30))

    assert result.demand.score is None
    assert result.demand.raw_state_points is None
    assert result.demand.data_status is DataStatus.INSUFFICIENT_DATA
    assert result.demand.minimum_points == result.demand.maximum_points == 0
    assert result.demand.coverage_pct == 0.0
    assert result.demand.score_contributions == []
    assert "volume" in result.demand.metrics
    assert any(
        "승인된 지속 수급 점수 규칙 없음" in item.message for item in result.demand.observations
    )


def test_missing_volume_reports_missing_input_without_reweighting(calculated_df):
    legacy = TechnicalScorer().score(calculated_df, ticker="AAPL", include_history=False)
    without_volume = calculated_df.drop(columns=["Volume", "Vol_SMA_20"])
    result = build_scorecard(without_volume, legacy, ticker="AAPL", as_of=date(2025, 12, 30))

    assert result.demand.score is None
    assert result.demand.data_status is DataStatus.INSUFFICIENT_DATA
    assert any("Volume" in item.message for item in result.demand.observations)


def test_directional_metric_preserves_value_slope_and_acceleration(calculated_df):
    legacy = TechnicalScorer().score(calculated_df, ticker="AAPL", include_history=False)
    result = build_scorecard(calculated_df, legacy, ticker="AAPL", as_of=date(2025, 12, 30))

    metric = result.trend.metrics["sma150"]
    assert metric.value == pytest.approx(calculated_df.iloc[-1]["SMA_150"])
    assert metric.slope_lookback_bars == 21
    assert metric.direction is Direction.RISING
    assert metric.acceleration in Acceleration
    assert metric.calculation_version == "DIRECTION_V1"


@pytest.mark.parametrize(
    ("values", "direction", "acceleration"),
    [
        ([10.0, 9.0, 7.0], Direction.FALLING, Acceleration.ACCELERATING),
        ([10.0, 8.0, 7.0], Direction.FALLING, Acceleration.DECELERATING),
        ([10.0, 9.0, 11.0], Direction.RISING, Acceleration.UNKNOWN),
        ([10.0, 10.0, 10.0], Direction.FLAT, Acceleration.STABLE),
    ],
)
def test_direction_v1_acceleration_uses_magnitude_and_sign_transition_policy(
    values, direction, acceleration
):
    metric = _metric(pd.DataFrame({"indicator": values}), "indicator", "indicator", 1)

    assert metric.calculation_version == "DIRECTION_V1"
    assert metric.direction is direction
    assert metric.acceleration is acceleration


def test_scorecard_version_matches_every_scored_rule_and_rejects_other_versions(calculated_df):
    legacy = TechnicalScorer().score(calculated_df, ticker="AAPL", include_history=False)
    result = build_scorecard(calculated_df, legacy, ticker="AAPL", as_of=date(2025, 12, 30))

    assert result.version == "TECHNICAL_SCORECARD_V1"
    assert all(dimension.calculation_version == result.version for dimension in result.dimensions())
    assert all(
        contribution.calculation_version == result.version
        for dimension in result.dimensions()
        for contribution in dimension.score_contributions
    )
    with pytest.raises(ValueError, match="Unsupported scorecard version"):
        build_scorecard(
            calculated_df,
            legacy,
            ticker="AAPL",
            as_of=date(2025, 12, 30),
            version="TECHNICAL_SCORECARD_V2",
        )


def test_optional_direction_input_reduces_coverage_without_reweighting(calculated_df):
    legacy = TechnicalScorer().score(calculated_df, ticker="AAPL", include_history=False)
    complete = build_scorecard(calculated_df, legacy, ticker="AAPL", as_of=date(2025, 12, 30))
    without_macd = calculated_df.drop(columns=["MACD_Hist"])
    partial = build_scorecard(without_macd, legacy, ticker="AAPL", as_of=date(2025, 12, 30))

    assert partial.momentum.score == complete.momentum.score
    assert partial.momentum.data_status is DataStatus.PARTIAL
    assert partial.momentum.coverage_pct < complete.momentum.coverage_pct
    assert partial.momentum.metrics["macd_histogram"].direction is Direction.UNKNOWN


def test_crsi_current_state_scores_without_previous_bar_or_hook(calculated_df):
    current_state = calculated_df.copy()
    current_state.loc[current_state.index[-2], "cRSI"] = float("nan")
    current_state.loc[current_state.index[-1], ["cRSI", "cRSI_HighBand", "cRSI_LowBand"]] = [
        10.0,
        100.0,
        20.0,
    ]
    legacy = TechnicalScorer().score(current_state, ticker="AAPL", include_history=False)
    result = build_scorecard(current_state, legacy, ticker="AAPL", as_of=date(2025, 12, 30))
    crsi_state = next(
        contribution
        for contribution in result.momentum.score_contributions
        if contribution.rule_code == "crsi.state"
    )

    assert legacy.components["crsi"]["score"] == 0
    assert crsi_state.points == 10
    assert crsi_state.missing_inputs == []
    assert result.momentum.score is not None


def test_hook_and_supertrend_transition_do_not_enter_state_points(calculated_df):
    event_day = calculated_df.copy()
    event_day.loc[event_day.index[-2], "cRSI"] = 120.0
    event_day.loc[event_day.index[-1], ["cRSI", "cRSI_HighBand", "cRSI_LowBand"]] = [
        80.0,
        100.0,
        20.0,
    ]
    event_day.loc[event_day.index[-2], "SuperTrend_Dir"] = -1
    event_day.loc[event_day.index[-1], "SuperTrend_Dir"] = 1
    legacy = TechnicalScorer().score(event_day, ticker="AAPL", include_history=False)
    result = build_scorecard(event_day, legacy, ticker="AAPL", as_of=date(2025, 12, 30))
    rules = {
        contribution.rule_code: contribution.points
        for dimension in result.dimensions()
        for contribution in dimension.score_contributions
    }

    assert legacy.components["crsi"]["score"] == -20
    assert rules["crsi.state"] == 0
    assert legacy.components["supertrend"]["score"] > rules["supertrend.state"]
    assert rules["supertrend.state"] in (20, 25)


def test_scorer_attaches_shadow_scorecard_without_changing_legacy(calculated_df):
    scorer = TechnicalScorer()
    result = scorer.score(calculated_df, ticker="AAPL", include_history=False)

    assert result.scorecard is not None
    assert result.scorecard.ticker == "AAPL"
    assert result.scorecard.legacy_raw_total == result.total_score
    assert result.scorecard.legacy_adjusted_score == result.adjusted_score
    assert result.technical_verdict is not None

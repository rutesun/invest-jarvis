import pandas as pd
import pytest

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer


@pytest.fixture
def sample_df():
    """Create sample OHLCV data for testing."""
    data = []
    for i in range(250):
        data.append(
            {
                "Open": 100 + i * 0.1,
                "High": 101 + i * 0.1,
                "Low": 99 + i * 0.1,
                "Close": 100.5 + i * 0.1,
                "Volume": 1000000 + i * 1000,
            }
        )
    df = pd.DataFrame(data)

    calculator = IndicatorCalculator()
    return calculator.calculate(df)


def test_technical_scorer_basic(sample_df):
    """Test TechnicalScorer returns TechnicalResult."""
    scorer = TechnicalScorer()
    result = scorer.score(sample_df)

    assert result.ticker is None  # No ticker passed
    assert isinstance(result.total_score, int)
    assert isinstance(result.components, dict)
    assert len(result.components) > 0


def test_technical_scorer_with_ticker(sample_df):
    """Test TechnicalScorer with ticker symbol."""
    scorer = TechnicalScorer()
    result = scorer.score(sample_df, ticker="AAPL")

    assert result.ticker == "AAPL"
    assert result.total_score is not None


def test_technical_scorer_components_structure(sample_df):
    """Test that all expected components are present."""
    scorer = TechnicalScorer()
    result = scorer.score(sample_df)

    expected_components = ["minervini", "velocity", "crsi", "volume", "patterns"]
    for component in expected_components:
        assert component in result.components
        assert "score" in result.components[component]
        assert "signals" in result.components[component]
        assert "evidence" in result.components[component]


def test_technical_scorer_total_score_calculation(sample_df):
    """Test total score is sum of component scores."""
    scorer = TechnicalScorer()
    result = scorer.score(sample_df)

    component_scores = [comp["score"] for comp in result.components.values()]
    expected_total = sum(component_scores)

    assert result.total_score == expected_total


def test_technical_scorer_preserves_total_score_as_component_sum(sample_df):
    scorer = TechnicalScorer()
    result = scorer.score(sample_df, include_history=False)

    expected_total = sum(comp["score"] for comp in result.components.values())

    assert result.total_score == expected_total
    assert result.component_raw_total == expected_total
    assert isinstance(result.adjusted_score, int)
    assert result.technical_verdict is not None


def test_technical_scorer_score_history_uses_recent_trading_days(sample_df):
    scorer = TechnicalScorer()
    result = scorer.score(sample_df, ticker="AAPL", history_days=5)

    assert len(result.score_history) == 5
    assert all(point.verdict_action for point in result.score_history)
    assert result.technical_verdict.score_trend_summary is not None


def test_score_history_does_not_use_future_rows(sample_df):
    scorer = TechnicalScorer()
    baseline = scorer.score(sample_df, ticker="AAPL", history_days=5)

    changed = sample_df.copy()
    changed.loc[changed.index[-1], "Close"] = changed.loc[changed.index[-1], "Close"] * 1.5
    changed.loc[changed.index[-1], "Volume"] = changed.loc[changed.index[-1], "Volume"] * 4
    mutated = scorer.score(changed, ticker="AAPL", history_days=5)

    assert baseline.score_history[-2] == mutated.score_history[-2]


def test_technical_scorer_insufficient_data():
    """Test with insufficient data."""
    df = pd.DataFrame(
        {
            "Open": [100],
            "High": [101],
            "Low": [99],
            "Close": [100],
            "Volume": [1000000],
        }
    )

    calculator = IndicatorCalculator()
    df = calculator.calculate(df)

    scorer = TechnicalScorer()
    result = scorer.score(df)

    # Should still return result, but with low/zero scores
    assert isinstance(result.total_score, int)
    assert result.total_score <= 0


def test_technical_scorer_snapshot_included(sample_df):
    """Test that snapshot is included in result."""
    scorer = TechnicalScorer()
    result = scorer.score(sample_df)

    assert result.snapshot is not None
    assert result.snapshot.price > 0
    assert result.snapshot.change_pct is not None

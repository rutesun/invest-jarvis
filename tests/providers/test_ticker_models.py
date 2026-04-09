import pytest
from src.providers.ticker_models import CandidateTicker


def test_candidate_ticker_creation():
    """Test CandidateTicker model creation"""
    candidate = CandidateTicker(
        symbol="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        score=35427.0,
        quote_type="EQUITY"
    )

    assert candidate.symbol == "AAPL"
    assert candidate.name == "Apple Inc."
    assert candidate.exchange == "NASDAQ"
    assert candidate.score == 35427.0
    assert candidate.quote_type == "EQUITY"


def test_candidate_ticker_validation():
    """Test CandidateTicker field validation"""
    with pytest.raises(ValueError):
        CandidateTicker(
            symbol="",  # Empty symbol should fail
            name="Apple",
            exchange="NASDAQ",
            score=100.0,
            quote_type="EQUITY"
        )

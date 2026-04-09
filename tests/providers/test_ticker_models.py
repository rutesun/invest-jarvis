from datetime import datetime

import pytest
from src.providers.ticker_models import CachedMapping, CandidateTicker, TickerResolution


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


def test_ticker_resolution_single_result():
    """Test TickerResolution with single result"""
    resolution = TickerResolution(
        original_query="AAPL",
        resolved_ticker="AAPL",
        display_name="Apple Inc.",
        confidence="high",
        candidates=[],
        resolution_method="direct_ticker",
        source="user_input"
    )

    assert resolution.original_query == "AAPL"
    assert resolution.resolved_ticker == "AAPL"
    assert resolution.confidence == "high"
    assert resolution.resolution_method == "direct_ticker"
    assert len(resolution.candidates) == 0


def test_ticker_resolution_with_candidates():
    """Test TickerResolution with multiple candidates"""
    candidates = [
        CandidateTicker(
            symbol="005930.KS",
            name="SamsungElec",
            exchange="KSC",
            score=23044.0,
            quote_type="EQUITY"
        ),
        CandidateTicker(
            symbol="207940.KS",
            name="SAMSUNG BIOLOGICS",
            exchange="KSC",
            score=20002.0,
            quote_type="EQUITY"
        )
    ]

    resolution = TickerResolution(
        original_query="Samsung",
        resolved_ticker="005930.KS",
        display_name="SamsungElec",
        confidence="low",
        candidates=candidates,
        resolution_method="yfinance_search_multiple",
        source="yfinance_api"
    )

    assert len(resolution.candidates) == 2
    assert resolution.confidence == "low"


def test_cached_mapping_creation():
    """Test CachedMapping model creation"""
    now = datetime.now()
    mapping = CachedMapping(
        ticker="AAPL",
        display_name="Apple Inc.",
        created_at=now,
        last_used=now,
        use_count=1
    )

    assert mapping.ticker == "AAPL"
    assert mapping.display_name == "Apple Inc."
    assert mapping.use_count == 1

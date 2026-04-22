from datetime import datetime

import pytest
from pydantic import ValidationError

from src.providers.ticker_models import CachedMapping, TickerResolution


def test_ticker_resolution_creation():
    resolution = TickerResolution(
        original_query="삼성전자",
        resolved_ticker="005930.KS",
        display_name="Samsung Electronics Co., Ltd.",
        source="llm_agent",
    )
    assert resolution.original_query == "삼성전자"
    assert resolution.resolved_ticker == "005930.KS"
    assert resolution.display_name == "Samsung Electronics Co., Ltd."
    assert resolution.source == "llm_agent"


def test_ticker_resolution_requires_fields():
    with pytest.raises(ValidationError):
        TickerResolution(original_query="test")


def test_cached_mapping_creation():
    now = datetime.now()
    mapping = CachedMapping(
        ticker="AAPL", display_name="Apple Inc.", created_at=now, last_used=now, use_count=1
    )
    assert mapping.ticker == "AAPL"
    assert mapping.use_count == 1


def test_cached_mapping_rejects_zero_use_count():
    now = datetime.now()
    with pytest.raises(ValueError):
        CachedMapping(
            ticker="AAPL", display_name="Apple Inc.", created_at=now, last_used=now, use_count=0
        )

"""Tests for FmpProvider (Plan 5 — TDD)."""

import pytest

from src.providers.fmp_provider import FmpProvider


# ---------------------------------------------------------------------------
# Task 2: FmpProvider mock tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_industry_snapshot_averages_by_exchange(monkeypatch):
    """industry_snapshot이 같은 industry의 exchange 값을 평균낸다."""
    sample = [
        {
            "date": "2026-06-10",
            "industry": "Semiconductors",
            "exchange": "NASDAQ",
            "averageChange": 2.1,
        },
        {
            "date": "2026-06-10",
            "industry": "Semiconductors",
            "exchange": "NYSE",
            "averageChange": 1.5,
        },
        {"date": "2026-06-10", "industry": "Airlines", "exchange": "NASDAQ", "averageChange": -0.8},
    ]

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return sample

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr("src.providers.fmp_provider.httpx.AsyncClient", FakeClient)
    fmp = FmpProvider("KEY")
    snap = await fmp.industry_snapshot("2026-06-10")

    assert snap["Semiconductors"] == pytest.approx((2.1 + 1.5) / 2)
    assert "Airlines" in snap
    assert snap["Airlines"] == pytest.approx(-0.8)


@pytest.mark.asyncio
async def test_industry_snapshot_skips_none_values(monkeypatch):
    """industry나 averageChange가 None이면 해당 행을 건너뛴다."""
    sample = [
        {"date": "2026-06-10", "industry": None, "exchange": "NASDAQ", "averageChange": 1.0},
        {"date": "2026-06-10", "industry": "Tech", "exchange": "NYSE", "averageChange": None},
        {"date": "2026-06-10", "industry": "Tech", "exchange": "NASDAQ", "averageChange": 2.0},
    ]

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return sample

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr("src.providers.fmp_provider.httpx.AsyncClient", FakeClient)
    fmp = FmpProvider("KEY")
    snap = await fmp.industry_snapshot("2026-06-10")

    assert None not in snap
    assert "Tech" in snap
    assert snap["Tech"] == pytest.approx(2.0)  # None 행 제외 후 2.0만


@pytest.mark.asyncio
async def test_historical_industry_returns_list(monkeypatch):
    """historical_industry가 리스트를 반환한다."""
    sample = [
        {
            "date": "2026-06-10",
            "industry": "Semiconductors",
            "exchange": "NASDAQ",
            "averageChange": 2.1,
        },
        {
            "date": "2026-06-09",
            "industry": "Semiconductors",
            "exchange": "NASDAQ",
            "averageChange": -0.5,
        },
    ]

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return sample

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr("src.providers.fmp_provider.httpx.AsyncClient", FakeClient)
    fmp = FmpProvider("KEY")
    hist = await fmp.historical_industry("Semiconductors")

    assert isinstance(hist, list)
    assert len(hist) == 2
    assert hist[0]["averageChange"] == pytest.approx(2.1)

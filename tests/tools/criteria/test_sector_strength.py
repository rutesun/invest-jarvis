"""Tests for sector strength model and providers (Plan 5 — TDD)."""

import pandas as pd
import pytest

from src.tools.criteria.models import SectorStrengthResult


# ---------------------------------------------------------------------------
# Task 1: SectorStrengthResult model
# ---------------------------------------------------------------------------


def test_sector_strength_result_basic():
    r = SectorStrengthResult(
        industry="Semiconductors",
        rank_pct=0.12,
        trend="up",
        is_strong=True,
        source="FMP",
    )
    assert r.is_strong is True
    assert r.source == "FMP"


def test_sector_strength_none_when_unmapped():
    r = SectorStrengthResult(
        industry=None,
        rank_pct=None,
        trend="unknown",
        is_strong=None,
        source="none",
    )
    assert r.is_strong is None


def test_sector_strength_detail_defaults_empty():
    r = SectorStrengthResult(
        industry="Airlines",
        rank_pct=0.8,
        trend="down",
        is_strong=False,
        source="FMP",
    )
    assert r.detail == ""


# ---------------------------------------------------------------------------
# Task 4: Pure logic helpers (_rank_pct, _trend_from_hist)
# ---------------------------------------------------------------------------


def test_rank_pct_top_industry():
    """가장 높은 등락의 업종은 rank_pct=0."""
    from src.tools.criteria.sector_strength import _rank_pct

    snap = {"A": 5.0, "B": 3.0, "C": 1.0}
    assert _rank_pct(snap, "A") == pytest.approx(0.0)


def test_rank_pct_bottom_industry():
    """가장 낮은 등락의 업종은 rank_pct=1."""
    from src.tools.criteria.sector_strength import _rank_pct

    snap = {"A": 5.0, "B": 3.0, "C": 1.0}
    assert _rank_pct(snap, "C") == pytest.approx(1.0)


def test_rank_pct_missing_industry():
    """스냅샷에 없는 업종은 None 반환."""
    from src.tools.criteria.sector_strength import _rank_pct

    snap = {"A": 5.0}
    assert _rank_pct(snap, "Z") is None


def test_trend_from_hist_up():
    """히스토리 합산이 양수면 up."""
    from src.tools.criteria.sector_strength import _trend_from_hist

    hist = [{"averageChange": 1.0}, {"averageChange": 2.0}]
    assert _trend_from_hist(hist) == "up"


def test_trend_from_hist_down():
    """히스토리 합산이 음수면 down."""
    from src.tools.criteria.sector_strength import _trend_from_hist

    hist = [{"averageChange": -1.0}, {"averageChange": -2.0}]
    assert _trend_from_hist(hist) == "down"


def test_trend_from_hist_empty():
    """데이터 없으면 unknown."""
    from src.tools.criteria.sector_strength import _trend_from_hist

    assert _trend_from_hist([]) == "unknown"


# ---------------------------------------------------------------------------
# Task 4: FmpSectorStrength.evaluate — pure judgment (no API)
# ---------------------------------------------------------------------------


def test_fmp_evaluate_strong():
    """rank_pct 낮고 trend=up → is_strong=True."""
    from src.tools.criteria.sector_strength import FmpSectorStrength

    snapshot = {"Semiconductors": 3.0, "Airlines": 0.5, "Banks": -1.0}
    hist = [{"averageChange": 2.0}, {"averageChange": 1.0}]

    provider = FmpSectorStrength(
        snapshot=snapshot,
        historical={"Semiconductors": hist},
        normalize_map={},
    )
    result = provider.evaluate_industry("Semiconductors")

    assert result.is_strong is True
    assert result.source == "FMP"
    assert result.trend == "up"
    assert result.rank_pct == pytest.approx(0.0)


def test_fmp_evaluate_weak():
    """rank_pct 높고 trend=down → is_strong=False."""
    from src.tools.criteria.sector_strength import FmpSectorStrength

    snapshot = {"Semiconductors": 3.0, "Airlines": 0.5, "Banks": -1.0}
    hist = [{"averageChange": -2.0}, {"averageChange": -1.0}]

    provider = FmpSectorStrength(
        snapshot=snapshot,
        historical={"Banks": hist},
        normalize_map={},
    )
    result = provider.evaluate_industry("Banks")

    assert result.is_strong is False
    assert result.trend == "down"


def test_fmp_evaluate_unmapped():
    """yfinance industry → FMP에 없으면 is_strong=None, source=none."""
    from src.tools.criteria.sector_strength import FmpSectorStrength

    snapshot = {"Semiconductors": 3.0}
    provider = FmpSectorStrength(
        snapshot=snapshot,
        historical={},
        normalize_map={},
    )
    result = provider.evaluate_industry("Unknown Industry XYZ")

    assert result.is_strong is None
    assert result.source == "none"


def test_fmp_evaluate_uses_normalize_map():
    """normalize_map을 통해 yfinance industry → FMP industry 변환."""
    from src.tools.criteria.sector_strength import FmpSectorStrength

    snapshot = {"Auto - Manufacturers": 2.5, "Banks": -0.5}
    hist = [{"averageChange": 1.0}, {"averageChange": 0.5}]

    provider = FmpSectorStrength(
        snapshot=snapshot,
        historical={"Auto - Manufacturers": hist},
        normalize_map={"Auto Manufacturers": "Auto - Manufacturers"},
    )
    result = provider.evaluate_industry("Auto Manufacturers")

    assert result.industry == "Auto - Manufacturers"
    assert result.is_strong is True


# ---------------------------------------------------------------------------
# Task 4: KisSectorStrength.evaluate_sector_code — pure judgment (no API)
# ---------------------------------------------------------------------------


def _make_df(closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="B", tz="Asia/Seoul")
    return pd.DataFrame(
        {
            "Close": closes,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Volume": [1000] * len(closes),
        },
        index=dates,
    )


def test_kis_evaluate_strong():
    """업종지수가 코스피 대비 우상향 → is_strong=True."""
    from src.tools.criteria.sector_strength import KisSectorStrength

    # 업종: +20% 상승 / 코스피: +5% 상승 → 업종이 더 강함
    sector_df = _make_df([100, 110, 120])
    kospi_df = _make_df([100, 102, 105])

    provider = KisSectorStrength()
    result = provider.evaluate_sector_df(sector_code="0013", sector_df=sector_df, kospi_df=kospi_df)

    assert result.is_strong is True
    assert result.source == "KIS"
    assert result.rank_pct is None  # KIS는 rank_pct 없음


def test_kis_evaluate_weak():
    """업종지수가 코스피 대비 하락 → is_strong=False."""
    from src.tools.criteria.sector_strength import KisSectorStrength

    # 업종: -10% 하락 / 코스피: +5% 상승
    sector_df = _make_df([100, 95, 90])
    kospi_df = _make_df([100, 102, 105])

    provider = KisSectorStrength()
    result = provider.evaluate_sector_df(sector_code="0013", sector_df=sector_df, kospi_df=kospi_df)

    assert result.is_strong is False


def test_kis_evaluate_empty_data():
    """데이터 없으면 is_strong=None."""
    from src.tools.criteria.sector_strength import KisSectorStrength

    provider = KisSectorStrength()
    result = provider.evaluate_sector_df(
        sector_code="0013",
        sector_df=pd.DataFrame(),
        kospi_df=pd.DataFrame(),
    )

    assert result.is_strong is None
    assert result.source == "none"

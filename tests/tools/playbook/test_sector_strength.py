"""Tests for sector strength model and providers (Plan 5 — TDD)."""

from src.tools.playbook.models import SectorStrengthResult


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

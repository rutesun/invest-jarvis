"""Tests for EPS extension of fundamental.py (Plan 2)."""

import pandas as pd
import pytest

from src.llm.models import FundamentalSummaryInput
from src.tools.fundamental import AnnualData, FundamentalSnapshot, FundamentalTool, QuarterlyData


# ---------------------------------------------------------------------------
# Task 2: model extension
# ---------------------------------------------------------------------------


def test_quarterly_data_has_eps_fields():
    q = QuarterlyData(period="2025-Q2", eps=1920.0, eps_yoy=0.62)
    assert q.eps == 1920.0
    assert q.eps_yoy == 0.62


def test_annual_data_model():
    a = AnnualData(year="2025", eps=6564.0, revenue=3.0e14, earnings=3.0e13)
    assert a.year == "2025" and a.eps == 6564.0


def test_snapshot_holds_annual_data():
    snap = FundamentalSnapshot(annual_data=[AnnualData(year="2025", eps=6564.0)])
    assert snap.annual_data[0].eps == 6564.0


# ---------------------------------------------------------------------------
# Task 3: Korean financial-ratio EPS parsing
# ---------------------------------------------------------------------------


def test_kis_quarterly_eps_yoy_matches_same_month():
    # financial-ratio div=1 분기 행 (최신순). eps 문자열은 KIS 응답 형식.
    rows = [
        {"stac_yymm": "202506", "eps": "1920.00"},
        {"stac_yymm": "202503", "eps": "1186.00"},
        {"stac_yymm": "202412", "eps": "4950.00"},
        {"stac_yymm": "202409", "eps": "3701.00"},
        {"stac_yymm": "202406", "eps": "1186.00"},  # 전년 동기(6월)
    ]
    q = FundamentalTool._build_quarterly_eps(rows)
    # 202506 EPS YoY = (1920 - 1186)/1186
    latest = q[0]
    assert latest.period.endswith("06")
    assert latest.eps == 1920.0
    assert abs(latest.eps_yoy - (1920.0 - 1186.0) / 1186.0) < 1e-6


def test_kis_quarterly_eps_yoy_none_when_no_prior_year():
    """전년 동기 행이 없으면 eps_yoy=None."""
    rows = [
        {"stac_yymm": "202506", "eps": "1920.00"},
        {"stac_yymm": "202503", "eps": "1186.00"},
        {"stac_yymm": "202412", "eps": "4950.00"},
        {"stac_yymm": "202409", "eps": "3701.00"},
        # 202406 없음
    ]
    q = FundamentalTool._build_quarterly_eps(rows)
    latest = q[0]
    assert latest.eps == 1920.0
    assert latest.eps_yoy is None


def test_kis_quarterly_eps_returns_at_most_4():
    rows = [{"stac_yymm": f"20250{i}", "eps": f"{i * 100}.0"} for i in range(1, 9)]
    q = FundamentalTool._build_quarterly_eps(rows)
    assert len(q) <= 4


# ---------------------------------------------------------------------------
# Task 4: US yfinance EPS parsing
# ---------------------------------------------------------------------------


def _make_qis_df(periods, eps_values):
    """Helper: build a quarterly_income_stmt-shaped DataFrame.

    yfinance quarterly_income_stmt shape: index=metric_name, columns=Timestamps (newest first).
    """
    cols = [pd.Timestamp(p) for p in periods]
    # Build {col: {metric: val}} then transpose to get index=metric, columns=dates
    data = {col: {"Diluted EPS": val} for col, val in zip(cols, eps_values, strict=True)}
    return pd.DataFrame(data)  # index=metric, columns=dates


def test_yf_quarterly_eps_yoy():
    """quarterly_income_stmt Diluted EPS → 4 quarters + yoy vs 4 periods ago."""
    periods = [
        "2026-03-31",
        "2025-12-31",
        "2025-09-30",
        "2025-06-30",
        "2025-03-31",  # 4 periods ago = yoy for 2026-03
    ]
    eps_values = [2.01, 2.84, 1.85, 1.57, 1.65]
    qis = _make_qis_df(periods, eps_values)

    result = FundamentalTool._build_yf_quarterly_eps(qis)

    assert len(result) == 4
    latest = result[0]
    assert latest.eps == pytest.approx(2.01)
    expected_yoy = (2.01 - 1.65) / 1.65
    assert latest.eps_yoy == pytest.approx(expected_yoy, rel=1e-5)


def test_yf_quarterly_eps_yoy_none_when_insufficient():
    """5개 미만이면 yoy=None."""
    periods = [
        "2026-03-31",
        "2025-12-31",
        "2025-09-30",
        "2025-06-30",
    ]
    eps_values = [2.01, 2.84, 1.85, 1.57]
    qis = _make_qis_df(periods, eps_values)

    result = FundamentalTool._build_yf_quarterly_eps(qis)

    assert len(result) == 4
    assert result[0].eps_yoy is None


def test_yf_quarterly_eps_nan_skipped():
    """NaN EPS 행은 None으로 처리."""

    periods = ["2026-03-31", "2025-12-31"]
    eps_values = [float("nan"), 2.84]
    qis = _make_qis_df(periods, eps_values)

    result = FundamentalTool._build_yf_quarterly_eps(qis)

    assert result[0].eps is None


# ---------------------------------------------------------------------------
# Task 5: FundamentalSummaryInput EPS fields
# ---------------------------------------------------------------------------


def test_fundamental_summary_input_has_eps_growth_fields():
    """FundamentalSummaryInput에 eps_growth_quarterly와 eps_cagr_annual 필드가 있어야 한다."""
    inp = FundamentalSummaryInput(
        ticker="AAPL",
        eps_growth_quarterly=0.2182,
        eps_cagr_annual=0.07,
    )
    assert inp.eps_growth_quarterly == pytest.approx(0.2182)
    assert inp.eps_cagr_annual == pytest.approx(0.07)


def test_fundamental_summary_input_eps_fields_default_none():
    """기존 필드와 호환: 새 필드는 optional."""
    inp = FundamentalSummaryInput(ticker="AAPL")
    assert inp.eps_growth_quarterly is None
    assert inp.eps_cagr_annual is None

"""Tests for CAN SLIM aggregation (Plan 7)."""

from src.tools.playbook.models import CanslimResult, ElementVerdict


def _ev(met) -> ElementVerdict:
    return ElementVerdict(met=met, detail="")


# ---------------------------------------------------------------------------
# Task 1: ElementVerdict + CanslimResult model
# ---------------------------------------------------------------------------


def test_canslim_score_counts_met():
    e = _ev
    r = CanslimResult(
        c=e(True),
        a=e(True),
        n=e(False),
        s=e(None),
        l=e(True),
        i=e(True),
        m=e(True),
    )
    assert r.score == 5  # met True 개수 (None 제외)
    assert "C✅" in r.summary
    assert "S—" in r.summary


def test_canslim_score_all_none():
    e = _ev
    r = CanslimResult(
        c=e(None),
        a=e(None),
        n=e(None),
        s=e(None),
        l=e(None),
        i=e(None),
        m=e(None),
    )
    assert r.score == 0
    assert "0/0" in r.summary


def test_canslim_score_all_false():
    e = _ev
    r = CanslimResult(
        c=e(False),
        a=e(False),
        n=e(False),
        s=e(False),
        l=e(False),
        i=e(False),
        m=e(False),
    )
    assert r.score == 0
    assert "0/7" in r.summary


def test_canslim_summary_shows_all_symbols():
    e = _ev
    r = CanslimResult(
        c=e(True),
        a=e(False),
        n=e(None),
        s=e(True),
        l=e(False),
        i=e(None),
        m=e(True),
    )
    summary = r.summary
    assert "C✅" in summary
    assert "A❌" in summary
    assert "N—" in summary
    assert "S✅" in summary
    assert "L❌" in summary
    assert "I—" in summary
    assert "M✅" in summary


def test_element_verdict_detail_optional():
    v = ElementVerdict(met=True)
    assert v.met is True
    assert v.detail == ""


# ---------------------------------------------------------------------------
# Task 3: compute_canslim pure function
# ---------------------------------------------------------------------------


def test_compute_canslim_strong_stock_high_score():
    """부품 결과 주입 → 강한 종목은 높은 score."""
    from src.tools.fundamental import AnnualData, FundamentalSnapshot, QuarterlyData
    from src.tools.playbook.canslim import compute_canslim
    from src.tools.playbook.models import (
        AccumulationResult,
        MarketRegimeResult,
        RelativeStrengthResult,
        SectorStrengthResult,
    )

    # C/A: 강한 EPS 성장
    fundamental = FundamentalSnapshot(
        roe=0.25,
        quarterly_data=[
            QuarterlyData(period="2025-Q2", eps=2.0, eps_yoy=0.35),  # +35% YoY
            QuarterlyData(period="2025-Q1", eps=1.5, eps_yoy=0.20),  # 전분기 낮은 성장 → 가속
        ],
        annual_data=[
            AnnualData(year="2025", eps=8.0),
            AnnualData(year="2024", eps=5.0),  # 연간 60% 성장
        ],
    )

    # N: 52주 신고가 근처
    class Snapshot:
        price = 180.0
        high_52w = 185.0  # 신고가 -3% 이내

    # S: volume score > 0
    components = {"volume": {"score": 2, "signals": ["Pocket Pivot on 2025-06-01"]}}

    # I: 매집 우세
    accumulation = AccumulationResult(
        accumulation_days=8, distribution_days=3, accumulation_ratio=0.73, window=25
    )

    # L: 업종 강세 + RS 강세
    sector = SectorStrengthResult(
        industry="Semiconductors", rank_pct=0.05, trend="up", is_strong=True, source="FMP"
    )
    rs = RelativeStrengthResult(
        mansfield_rs=5.0, outperform_6m=12.0, rp_slope_4w=0.8, index_symbol="SPY"
    )

    # M: 상승장
    regime = MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="SPY")

    result = compute_canslim(
        snapshot=Snapshot(),
        components=components,
        fundamental=fundamental,
        accumulation=accumulation,
        sector_strength=sector,
        relative_strength=rs,
        market_regime=regime,
    )

    assert result.c.met is True, f"C should be met: {result.c.detail}"
    assert result.a.met is True, f"A should be met: {result.a.detail}"
    assert result.n.met is True, f"N should be met: {result.n.detail}"
    assert result.s.met is True, f"S should be met: {result.s.detail}"
    assert result.l.met is True, f"L should be met: {result.l.detail}"
    assert result.i.met is True, f"I should be met: {result.i.detail}"
    assert result.m.met is True, f"M should be met: {result.m.detail}"
    assert result.score == 7


def test_compute_canslim_no_data_returns_none():
    """데이터 없으면 met=None."""
    from src.tools.playbook.canslim import compute_canslim

    result = compute_canslim(
        snapshot=None,
        components=None,
        fundamental=None,
        accumulation=None,
        sector_strength=None,
        relative_strength=None,
        market_regime=None,
    )

    assert result.c.met is None
    assert result.a.met is None
    assert result.n.met is None
    assert result.l.met is None
    assert result.m.met is None


def test_compute_canslim_weak_eps_c_not_met():
    """분기 EPS YoY < 25% → C = False."""
    from src.tools.fundamental import FundamentalSnapshot, QuarterlyData
    from src.tools.playbook.canslim import compute_canslim

    fundamental = FundamentalSnapshot(
        roe=0.10,
        quarterly_data=[
            QuarterlyData(period="2025-Q2", eps=1.0, eps_yoy=0.10),  # 10% < 25%
        ],
        annual_data=None,
    )

    result = compute_canslim(
        snapshot=None,
        components=None,
        fundamental=fundamental,
        accumulation=None,
        sector_strength=None,
        relative_strength=None,
        market_regime=None,
    )

    assert result.c.met is False


def test_compute_canslim_l_detail_shows_sector_and_rs_status():
    """L detail에 업종강세·RS강세 상태가 각각 드러난다 (met=False 근거 명확화)."""
    from src.tools.playbook.canslim import compute_canslim
    from src.tools.playbook.models import RelativeStrengthResult, SectorStrengthResult

    sector_strong = SectorStrengthResult(
        industry="Semiconductors", rank_pct=0.05, trend="up", is_strong=True, source="FMP"
    )
    rs_weak = RelativeStrengthResult(
        mansfield_rs=-5.0, outperform_6m=-10.0, rp_slope_4w=-0.5, index_symbol="SPY"
    )

    result = compute_canslim(
        snapshot=None,
        components=None,
        fundamental=None,
        accumulation=None,
        sector_strength=sector_strong,
        relative_strength=rs_weak,
        market_regime=None,
    )

    assert result.l.met is False
    assert "업종강세=True" in result.l.detail
    assert "RS강세=False" in result.l.detail
    assert "Semiconductors" in result.l.detail  # 업종명
    assert "Mansfield" in result.l.detail  # 종목 RS 수치
    assert "기울기" in result.l.detail  # 4주 RP 기울기 (RS강세 판정의 결정 요인)


def test_compute_canslim_s_detail_shows_volume_ratio():
    """S detail에 거래량 비율(vol_ratio, 20일평균 대비)이 드러난다."""
    from src.tools.playbook.canslim import compute_canslim

    components = {"volume": {"score": 0, "signals": [], "metrics": {"vol_ratio": 0.86}}}

    result = compute_canslim(
        snapshot=None,
        components=components,
        fundamental=None,
        accumulation=None,
        sector_strength=None,
        relative_strength=None,
        market_regime=None,
    )

    assert result.s.met is False
    assert "0.86" in result.s.detail


def test_compute_canslim_m_detail_shows_regime_and_basis():
    """M detail에 시장 국면 + 근거(지수/판정 근거)가 드러난다."""
    from src.tools.playbook.canslim import compute_canslim
    from src.tools.playbook.models import MarketRegimeResult

    regime = MarketRegimeResult(
        regime="상승", allow_new_buy=True, index_symbol="^GSPC", detail="close>SMA200"
    )

    result = compute_canslim(
        snapshot=None,
        components=None,
        fundamental=None,
        accumulation=None,
        sector_strength=None,
        relative_strength=None,
        market_regime=regime,
    )

    assert result.m.met is True
    assert "상승" in result.m.detail
    assert "close>SMA200" in result.m.detail or "^GSPC" in result.m.detail

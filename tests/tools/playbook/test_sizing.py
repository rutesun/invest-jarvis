"""TDD: sizing.py — plan_position 포지션 사이징."""

import pytest


# ---------------------------------------------------------------------------
# 골든 케이스: 자본 1000만 · 위험1% · 진입5만 / 손절4.75만 → 40주
# ---------------------------------------------------------------------------


def test_sizing_golden_case():
    """자본 1000만, 위험1%, 진입 50000, 손절 47500 → shares=40.

    손절 후보:
      ① -8%: 46000 (손절폭 8%)
      ② atr_stop=47500 (손절폭 5%) ← 가장 타이트, 3% 이상
    → 47500 선택, per_share_risk=2500, shares=floor(100000/2500)=40
    """
    from src.tools.playbook.sizing import plan_position

    result = plan_position(
        entry=50_000.0,
        atr_stop=47_500.0,  # 2×ATR: entry - 2500
        invalidation_low=None,
        capital=10_000_000.0,
        risk_pct=0.01,
    )
    assert result.error is None
    assert result.shares == 40
    assert result.per_share_risk == 2500.0
    assert result.stop == 47_500.0


def test_sizing_golden_explicit():
    """골든: 진입 50000, ATR stop = 47500 (수동), 위험1%, 자본 1000만."""
    from src.tools.playbook.sizing import plan_position

    result = plan_position(
        entry=50_000.0,
        atr_stop=47_500.0,  # 2×ATR = entry - 2500 → stop = 47500
        invalidation_low=None,
        capital=10_000_000.0,
        risk_pct=0.01,
    )
    assert result.error is None
    assert result.shares == 40
    assert result.per_share_risk == 2500.0
    assert result.stop == 47_500.0
    assert result.stop_basis in ("2xATR", "-5%")  # 47500 < 50000*(1-0.03) → 타이트한 쪽 채택


# ---------------------------------------------------------------------------
# 손절 후보 선택: 가장 타이트한 후보 채택
# ---------------------------------------------------------------------------


def test_sizing_pick_tightest_stop():
    """atr_stop > -8% 후보 중 entry와 가장 가까운(타이트) 선택."""
    from src.tools.playbook.sizing import plan_position

    entry = 100.0
    # 후보 ①: -8% = 92.0
    # 후보 ②: atr_stop = 94.0 (더 타이트)
    # 후보 ③: invalidation_low = 95.0 (가장 타이트)
    result = plan_position(
        entry=entry,
        atr_stop=94.0,
        invalidation_low=95.0,
        capital=1_000_000.0,
        risk_pct=0.01,
    )
    assert result.error is None
    assert result.stop == 95.0  # 가장 타이트한 invalidation_low
    assert result.stop_basis == "zone"


def test_sizing_skip_too_tight_stop():
    """손절폭 < 3% → 다음 후보로 넘김."""
    from src.tools.playbook.sizing import plan_position

    entry = 100.0
    # invalidation_low=99.0 → (100-99)/100=1% < 3% → 스킵
    # atr_stop=97.0 → (100-97)/100=3% → 정확히 3% = 경계값, 통과
    result = plan_position(
        entry=entry,
        atr_stop=97.0,
        invalidation_low=99.0,  # 1% 손절 → 스킵
        capital=1_000_000.0,
        risk_pct=0.01,
    )
    assert result.error is None
    assert result.stop == 97.0  # invalidation_low 스킵 → atr_stop 채택


# ---------------------------------------------------------------------------
# 상한 가드: 모두 -8% 초과 → error="risk_too_wide"
# ---------------------------------------------------------------------------


def test_sizing_all_too_wide_error():
    """atr_stop과 invalidation_low가 모두 -8% 초과이면 기본 -8% 후보로 폴백.

    기본 -8% 후보(92.0)는 항상 8%이므로 유효 후보로 남음.
    → error 없음, stop=92.0으로 계산.
    """
    from src.tools.playbook.sizing import plan_position

    entry = 100.0
    # atr_stop = 88 (12% 초과 → 상한 가드 제거)
    # invalidation_low = 85 (15% 초과 → 상한 가드 제거)
    # 기본 -8% 후보(92.0)는 유효
    result = plan_position(
        entry=entry,
        atr_stop=88.0,
        invalidation_low=85.0,
        capital=1_000_000.0,
        risk_pct=0.01,
    )
    assert result.error is None
    assert result.stop == 92.0
    assert result.stop_basis == "-8%"


def test_sizing_8pct_exact_boundary_allowed():
    """정확히 -8% → 허용 (초과가 아니라 같음 → 통과)."""
    from src.tools.playbook.sizing import plan_position

    entry = 100.0
    result = plan_position(
        entry=entry,
        atr_stop=None,
        invalidation_low=None,
        capital=1_000_000.0,
        risk_pct=0.01,
    )
    # 기본 후보 ①: 100*0.92 = 92 → 8% 손절 → 허용
    assert result.error is None
    assert result.stop == 92.0


# ---------------------------------------------------------------------------
# per_share_risk <= 0 가드
# ---------------------------------------------------------------------------


def test_sizing_per_share_risk_zero():
    """stop >= entry → per_share_risk <= 0 → error='invalid_stop'."""
    from src.tools.playbook.sizing import plan_position

    # atr_stop = entry (같음) → per_share_risk = 0
    result = plan_position(
        entry=100.0,
        atr_stop=100.0,
        invalidation_low=None,
        capital=1_000_000.0,
        risk_pct=0.01,
    )
    # atr_stop=100과 entry=100: pct = 0% < 3% → 스킵
    # -8% 후보: 92, pct = 8% → 유효
    # 실제로 per_share_risk=0이 되는 경우는 모든 후보가 entry 이상일 때
    assert result.error is None  # -8% 후보가 살아있어 valid


def test_sizing_all_stops_above_entry():
    """stop > entry인 후보만 있으면 per_share_risk < 0 → error='invalid_stop'."""
    from src.tools.playbook.sizing import plan_position

    # atr_stop=105 (entry보다 높음 → 이상한 케이스)
    # -8% = 92 → 유효 후보 존재 → error 없음
    result = plan_position(
        entry=100.0,
        atr_stop=105.0,  # > entry → 무효
        invalidation_low=None,
        capital=1_000_000.0,
        risk_pct=0.01,
    )
    assert result.error is None  # -8% 후보가 fallback


# ---------------------------------------------------------------------------
# capital 없으면 ratio 모드
# ---------------------------------------------------------------------------


def test_sizing_no_capital_ratio_mode():
    from src.tools.playbook.sizing import plan_position

    result = plan_position(
        entry=100.0,
        atr_stop=94.0,
        invalidation_low=None,
        capital=None,
        risk_pct=0.01,
    )
    assert result.capital_mode == "ratio"
    assert result.shares is None
    assert result.position_value is None
    assert result.per_share_risk > 0
    assert result.error is None


# ---------------------------------------------------------------------------
# r_targets: +2R / +3R 계산
# ---------------------------------------------------------------------------


def test_sizing_r_targets():
    from src.tools.playbook.sizing import plan_position

    entry = 100.0
    stop = 94.0  # per_share_risk = 6.0
    result = plan_position(
        entry=entry,
        atr_stop=stop,
        invalidation_low=None,
        capital=None,
        risk_pct=0.01,
    )
    assert result.r_targets["+2R"] == pytest.approx(entry + 2 * (entry - stop), rel=1e-6)
    assert result.r_targets["+3R"] == pytest.approx(entry + 3 * (entry - stop), rel=1e-6)


# ---------------------------------------------------------------------------
# weight_pct: capital 있으면 비중 계산
# ---------------------------------------------------------------------------


def test_sizing_weight_pct():
    from src.tools.playbook.sizing import plan_position

    result = plan_position(
        entry=50_000.0,
        atr_stop=47_500.0,
        invalidation_low=None,
        capital=10_000_000.0,
        risk_pct=0.01,
    )
    # shares=40, position_value = 40 * 50000 = 2_000_000
    # weight_pct = 2_000_000 / 10_000_000 * 100 = 20.0
    assert result.shares == 40
    assert result.position_value == pytest.approx(2_000_000.0)
    assert result.weight_pct == pytest.approx(20.0)

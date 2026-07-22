"""Plan 8 모델 TDD — GateCheck/GateResult/PositionPlan/ExitSignal/ExitVerdict/PlaybookVerdict."""

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# GateCheck / GateResult
# ---------------------------------------------------------------------------


def test_gate_check_required_met():
    from src.tools.playbook.models import GateCheck

    g = GateCheck(name="A", required=True, met=True, reason="시장 상승")
    assert g.name == "A"
    assert g.required is True
    assert g.met is True
    assert g.reason == "시장 상승"


def test_gate_check_met_none():
    from src.tools.playbook.models import GateCheck

    g = GateCheck(name="C", required=True, met=None, reason="데이터 없음")
    assert g.met is None


def test_gate_result_passed():
    from src.tools.playbook.models import GateCheck, GateResult

    checklist = [
        GateCheck(name="A", required=True, met=True, reason=""),
        GateCheck(name="B", required=True, met=True, reason=""),
    ]
    r = GateResult(passed=True, checklist=checklist, quality_grade="A", veto_reason=None)
    assert r.passed is True
    assert r.quality_grade == "A"
    assert r.veto_reason is None
    assert len(r.checklist) == 2


def test_gate_result_vetoed():
    from src.tools.playbook.models import GateCheck, GateResult

    checklist = [
        GateCheck(name="A", required=True, met=False, reason="시장 하락"),
    ]
    r = GateResult(passed=False, checklist=checklist, quality_grade=None, veto_reason="시장 하락")
    assert r.passed is False
    assert r.veto_reason == "시장 하락"
    assert r.quality_grade is None


# ---------------------------------------------------------------------------
# PositionPlan
# ---------------------------------------------------------------------------


def test_position_plan_full():
    from src.tools.playbook.models import PositionPlan

    p = PositionPlan(
        entry=50000.0,
        stop=47500.0,
        stop_basis="-5%",
        per_share_risk=2500.0,
        shares=40,
        position_value=2_000_000.0,
        weight_pct=20.0,
        r_targets={"+2R": 55000.0, "+3R": 57500.0},
        capital_mode="absolute",
        error=None,
    )
    assert p.shares == 40
    assert p.per_share_risk == 2500.0
    assert p.error is None


def test_position_plan_error_state():
    from src.tools.playbook.models import PositionPlan

    p = PositionPlan(
        entry=50000.0,
        stop=50000.0,
        stop_basis="-8%",
        per_share_risk=0.0,
        shares=None,
        position_value=None,
        weight_pct=None,
        r_targets={},
        capital_mode="ratio",
        error="invalid_stop",
    )
    assert p.shares is None
    assert p.error == "invalid_stop"


def test_position_plan_ratio_mode():
    from src.tools.playbook.models import PositionPlan

    p = PositionPlan(
        entry=200.0,
        stop=184.0,
        stop_basis="-8%",
        per_share_risk=16.0,
        shares=None,
        position_value=None,
        weight_pct=None,
        r_targets={"+2R": 232.0, "+3R": 248.0},
        capital_mode="ratio",
        error=None,
    )
    assert p.capital_mode == "ratio"
    assert p.shares is None
    assert p.position_value is None


# ---------------------------------------------------------------------------
# ExitSignal / ExitVerdict
# ---------------------------------------------------------------------------


def test_exit_signal_structure():
    from src.tools.playbook.models import ExitSignal

    s = ExitSignal(code="CHARACTER_CHANGE", severity="strong", detail="신고가 실패")
    assert s.code == "CHARACTER_CHANGE"
    assert s.severity == "strong"


def test_exit_verdict_liquidate():
    from src.tools.playbook.models import ExitSignal, ExitVerdict

    signals = [ExitSignal(code="SMA_SHORT", severity="medium", detail="종가<SMA20")]
    v = ExitVerdict(
        action="liquidate",
        signals=signals,
        current_r=2.5,
        trailing_stop=180.0,
        detail="강한 매도 신호",
    )
    assert v.action == "liquidate"
    assert v.current_r == 2.5
    assert len(v.signals) == 1


def test_exit_verdict_hold():
    from src.tools.playbook.models import ExitVerdict

    v = ExitVerdict(
        action="hold",
        signals=[],
        current_r=None,
        trailing_stop=None,
        detail="보유 유지",
    )
    assert v.action == "hold"
    assert v.current_r is None


@pytest.mark.parametrize("action", ["청산", "비중축소", "sell"])
def test_exit_verdict_rejects_non_domain_action(action):
    from src.tools.playbook.models import ExitVerdict

    with pytest.raises(ValidationError):
        ExitVerdict(
            action=action,
            signals=[],
            current_r=None,
            trailing_stop=None,
            detail="invalid",
        )


# ---------------------------------------------------------------------------
# PlaybookVerdict
# ---------------------------------------------------------------------------


def test_playbook_verdict_not_holding():
    from src.tools.playbook.models import (
        GateCheck,
        GateResult,
        MarketRegimeResult,
        PlaybookVerdict,
        PositionPlan,
        RelativeStrengthResult,
    )

    regime = MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC")
    rs = RelativeStrengthResult(
        mansfield_rs=5.0, outperform_6m=10.0, rp_slope_4w=0.5, index_symbol="^GSPC"
    )
    gate = GateResult(
        passed=True,
        checklist=[GateCheck(name="A", required=True, met=True, reason="")],
        quality_grade="A",
        veto_reason=None,
    )
    plan = PositionPlan(
        entry=200.0,
        stop=184.0,
        stop_basis="-8%",
        per_share_risk=16.0,
        shares=62,
        position_value=12_400.0,
        weight_pct=12.4,
        r_targets={"+2R": 232.0, "+3R": 248.0},
        capital_mode="absolute",
        error=None,
    )
    v = PlaybookVerdict(
        ticker="AAPL",
        holding=False,
        market_regime=regime,
        relative_strength=rs,
        sector_strength=None,
        canslim=None,
        gate=gate,
        position_plan=plan,
        exit_verdict=None,
        headline="매수 적격: 게이트 통과",
    )
    assert v.ticker == "AAPL"
    assert v.holding is False
    assert v.gate.passed is True
    assert v.exit_verdict is None
    assert v.headline == "매수 적격: 게이트 통과"


def test_playbook_verdict_holding_with_exit():
    from src.tools.playbook.models import (
        ExitSignal,
        ExitVerdict,
        MarketRegimeResult,
        PlaybookVerdict,
        RelativeStrengthResult,
    )

    regime = MarketRegimeResult(regime="조정", allow_new_buy=False, index_symbol="^GSPC")
    rs = RelativeStrengthResult(
        mansfield_rs=-1.0, outperform_6m=-3.0, rp_slope_4w=-0.1, index_symbol="^GSPC"
    )
    signals = [ExitSignal(code="RS_WEAKENING", severity="weak", detail="RS 음전환")]
    ev = ExitVerdict(
        action="hold",
        signals=signals,
        current_r=1.5,
        trailing_stop=175.0,
        detail="경고: RS 약화",
    )
    v = PlaybookVerdict(
        ticker="005930.KS",
        holding=True,
        market_regime=regime,
        relative_strength=rs,
        sector_strength=None,
        canslim=None,
        gate=None,
        position_plan=None,
        exit_verdict=ev,
        headline="보유 경고: RS 음전환",
    )
    assert v.holding is True
    assert v.gate is None
    assert v.exit_verdict.action == "hold"
    assert v.exit_verdict.current_r == 1.5

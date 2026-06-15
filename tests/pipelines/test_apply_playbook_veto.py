"""TDD: apply_criteria_veto — decision_summary 후처리 순수 함수 (Plan 9 Task 3)."""

from src.pipelines.analyze_decision import (
    AnalyzeDecisionSummary,
    apply_criteria_veto,
)
from src.tools.criteria.models import (
    CanslimResult,
    CriteriaCheck,
    CriteriaVerdict,
    ElementVerdict,
    ExitVerdict,
    MarketRegimeResult,
    RelativeStrengthResult,
)


def _make_summary(action: str = "매수") -> AnalyzeDecisionSummary:
    return AnalyzeDecisionSummary(
        leader="technical",
        core_variables=["가격 모멘텀"],
        action=action,
        timing="조정_대기",
        action_sentence="눌림 후 접근",
    )


def _make_verdict_gate_fail() -> CriteriaVerdict:
    """미보유 + 게이트 FAIL verdict."""
    return CriteriaVerdict(
        ticker="AAPL",
        holding=False,
        market_regime=MarketRegimeResult(regime="하락", allow_new_buy=False, index_symbol="SPY"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=-3.0,
            outperform_6m=-5.0,
            rp_slope_4w=-0.2,
            index_symbol="SPY",
        ),
        sector_strength=None,
        canslim=None,
        checks=[CriteriaCheck(name="A", required=True, met=False, reason="하락 국면")],
        quality_grade=None,
        veto_reason="시장 환경 불량: 하락 국면",
        position_plan=None,
        exit_verdict=None,
        headline="AAPL: 매수 거부 — 시장 환경 불량: 하락 국면",
    )


def _make_verdict_gate_pass() -> CriteriaVerdict:
    """미보유 + 게이트 PASS verdict."""
    return CriteriaVerdict(
        ticker="AAPL",
        holding=False,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="SPY"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=5.0,
            outperform_6m=10.0,
            rp_slope_4w=0.5,
            index_symbol="SPY",
        ),
        sector_strength=None,
        canslim=CanslimResult(
            c=ElementVerdict(met=True),
            a=ElementVerdict(met=True),
            n=ElementVerdict(met=None),
            s=ElementVerdict(met=True),
            l=ElementVerdict(met=True),
            i=ElementVerdict(met=None),
            m=ElementVerdict(met=True),
        ),
        checks=[CriteriaCheck(name="A", required=True, met=True, reason="상승 국면")],
        quality_grade="B",
        veto_reason=None,
        position_plan=None,
        exit_verdict=None,
        headline="AAPL: 매수 적격 (grade=B) — 비율 모드",
    )


def _make_verdict_holding_liquidate() -> CriteriaVerdict:
    """보유 + 청산 exit_verdict."""
    return CriteriaVerdict(
        ticker="AAPL",
        holding=True,
        market_regime=MarketRegimeResult(regime="하락", allow_new_buy=False, index_symbol="SPY"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=-2.0,
            outperform_6m=-8.0,
            rp_slope_4w=-0.5,
            index_symbol="SPY",
        ),
        sector_strength=None,
        canslim=None,
        position_plan=None,
        exit_verdict=ExitVerdict(
            action="청산",
            signals=[],
            current_r=-1.5,
            trailing_stop=None,
            detail="추세 이탈로 청산",
        ),
        headline="AAPL: 청산(-1.50R) — 추세 이탈로 청산",
    )


def _make_verdict_holding_reduce() -> CriteriaVerdict:
    """보유 + 비중축소 exit_verdict."""
    return CriteriaVerdict(
        ticker="AAPL",
        holding=True,
        market_regime=MarketRegimeResult(regime="조정", allow_new_buy=False, index_symbol="SPY"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=1.0,
            outperform_6m=2.0,
            rp_slope_4w=-0.1,
            index_symbol="SPY",
        ),
        sector_strength=None,
        canslim=None,
        position_plan=None,
        exit_verdict=ExitVerdict(
            action="비중축소",
            signals=[],
            current_r=1.2,
            trailing_stop=170.0,
            detail="RS 약화로 비중 조정",
        ),
        headline="AAPL: 비중축소(1.20R) — RS 약화로 비중 조정",
    )


def _make_verdict_holding_hold() -> CriteriaVerdict:
    """보유 + 보유유지 exit_verdict."""
    return CriteriaVerdict(
        ticker="AAPL",
        holding=True,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="SPY"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=5.0,
            outperform_6m=10.0,
            rp_slope_4w=0.3,
            index_symbol="SPY",
        ),
        sector_strength=None,
        canslim=None,
        position_plan=None,
        exit_verdict=ExitVerdict(
            action="hold",
            signals=[],
            current_r=2.5,
            trailing_stop=165.0,
            detail="추세 유지 중",
        ),
        headline="AAPL: 보유유지(2.50R) — 추세 유지 중",
    )


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


def test_apply_criteria_veto_none_verdict_returns_original():
    """verdict=None이면 summary를 그대로 반환해야 한다."""
    summary = _make_summary("매수")
    result = apply_criteria_veto(summary, None)
    assert result is summary  # 동일 객체


def test_apply_criteria_veto_not_holding_gate_fail_overrides_action():
    """미보유 + gate FAIL → action='관망', veto_applied=True, action_original 보존."""
    summary = _make_summary("매수")
    verdict = _make_verdict_gate_fail()

    result = apply_criteria_veto(summary, verdict)

    assert result.action == "관망"
    assert result.veto_applied is True
    assert result.action_original == "매수"
    assert "시장 환경 불량" in result.action_sentence


def test_apply_criteria_veto_not_holding_gate_pass_no_change():
    """미보유 + gate PASS → veto 없음, 원래 action 유지."""
    summary = _make_summary("매수")
    verdict = _make_verdict_gate_pass()

    result = apply_criteria_veto(summary, verdict)

    assert result.action == "매수"
    assert result.veto_applied is False
    assert result.action_original is None


def test_apply_criteria_veto_holding_liquidate_adds_sentence():
    """보유 + 청산 → veto_applied=True, action_original 보존, action_sentence에 청산 포함."""
    summary = _make_summary("관망")
    verdict = _make_verdict_holding_liquidate()

    result = apply_criteria_veto(summary, verdict)

    assert result.veto_applied is True
    assert result.action_original == "관망"
    assert "청산" in result.action_sentence


def test_apply_criteria_veto_holding_reduce_adds_sentence():
    """보유 + 비중축소 → veto_applied=True."""
    summary = _make_summary("관망")
    verdict = _make_verdict_holding_reduce()

    result = apply_criteria_veto(summary, verdict)

    assert result.veto_applied is True
    assert "비중축소" in result.action_sentence


def test_apply_criteria_veto_holding_hold_no_change():
    """보유 + hold → veto 없음."""
    summary = _make_summary("매수")
    verdict = _make_verdict_holding_hold()

    result = apply_criteria_veto(summary, verdict)

    assert result.veto_applied is False
    assert result.action_original is None
    assert result.action == "매수"


def test_apply_criteria_veto_preserves_immutability():
    """apply_criteria_veto는 원본 summary를 변경하지 않는다."""
    summary = _make_summary("매수")
    verdict = _make_verdict_gate_fail()

    result = apply_criteria_veto(summary, verdict)

    # 원본 변경 없음
    assert summary.action == "매수"
    assert summary.veto_applied is False
    # 반환된 객체는 다른 객체
    assert result is not summary

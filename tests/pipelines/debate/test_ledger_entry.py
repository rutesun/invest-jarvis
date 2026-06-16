from src.pipelines.analyze_decision import FactorAssessment
from src.tools.criteria.models import (
    CanslimResult,
    CriteriaCheck,
    CriteriaVerdict,
    ElementVerdict,
    MarketRegimeResult,
    RelativeStrengthResult,
)


def _verdict(mansfield=2.1):
    canslim = CanslimResult(
        c=ElementVerdict(met=True, detail="EPS +42%"),
        a=ElementVerdict(met=True, detail="CAGR +28%"),
        n=ElementVerdict(met=False, detail="촉매 없음"),
        s=ElementVerdict(met=True, detail="거래량"),
        l=ElementVerdict(met=True, detail="RS 강세"),
        i=ElementVerdict(met=False, detail="분산 우세"),
        m=ElementVerdict(met=True, detail="상승장"),
    )
    return CriteriaVerdict(
        ticker="TEST",
        holding=False,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=mansfield, outperform_6m=10.0, rp_slope_4w=0.5, index_symbol="^GSPC"
        ),
        sector_strength=None,
        canslim=canslim,
        checks=[
            CriteriaCheck(name="A", required=True, met=True, reason="시장환경=상승"),
            CriteriaCheck(name="B", required=True, met=True, reason="is_stage2=1.0"),
            CriteriaCheck(name="C", required=True, met=True, reason="RS=True, 업종강세=True"),
            CriteriaCheck(name="E", required=True, met=False, reason="breakout=False"),
        ],
        quality_grade="B",
        veto_reason=None,
        position_plan=None,
        exit_verdict=None,
        headline="t",
    )


def test_entry_ledger_routing_and_exclusions():
    from src.pipelines.debate.ledger import build_evidence_ledger

    factors = [
        FactorAssessment(
            factor_type="flow",
            role="참고",
            freshness_score=2,
            magnitude_score=2,
            actionability_score=2,
            total_score=6,
            summary="s",
            role_reason="r",
            evidence=[],
            bias="bullish",
        ),
        FactorAssessment(
            factor_type="technical",
            role="주도",
            freshness_score=4,
            magnitude_score=4,
            actionability_score=4,
            total_score=12,
            summary="s",
            role_reason="r",
            evidence=[],
            bias="bullish",
        ),
    ]
    ledger = build_evidence_ledger(
        criteria_verdict=_verdict(),
        factor_assessments=factors,
        snapshot=None,
        flow=None,
        mode="entry",
    )
    keys = {e.key for e in ledger.bull + ledger.bear + ledger.neutral}
    assert "market_regime" in keys and "vcp_trigger" in keys
    assert "canslim_L" not in keys  # rs_leadership 중복
    assert "canslim_M" not in keys  # market_regime 중복 (entry)
    assert "factor_flow" not in keys  # flow 행 중복
    assert "factor_technical" in keys
    assert "rs_magnitude" in {e.key for e in ledger.bull}
    assert ledger.bull_weight > ledger.bear_weight

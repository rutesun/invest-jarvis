from src.tools.criteria.models import (
    CanslimResult,
    CriteriaVerdict,
    ElementVerdict,
    ExitSignal,
    ExitVerdict,
    MarketRegimeResult,
    RelativeStrengthResult,
)


def _holding(signals, action="hold", current_r=None):
    cs = CanslimResult(
        c=ElementVerdict(met=True),
        a=ElementVerdict(met=True),
        n=ElementVerdict(met=True),
        s=ElementVerdict(met=True),
        l=ElementVerdict(met=True),
        i=ElementVerdict(met=True),
        m=ElementVerdict(met=True),
    )
    return CriteriaVerdict(
        ticker="T",
        holding=True,
        market_regime=MarketRegimeResult(regime="상승", allow_new_buy=True, index_symbol="^GSPC"),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=1.0, outperform_6m=5.0, rp_slope_4w=0.1, index_symbol="^GSPC"
        ),
        sector_strength=None,
        canslim=cs,
        checks=[],
        position_plan=None,
        exit_verdict=ExitVerdict(
            action=action, signals=signals, current_r=current_r, trailing_stop=None, detail="d"
        ),
        headline="t",
    )


def test_holding_routes_exit_and_keeps_canslim_m():
    from src.pipelines.debate.ledger import build_evidence_ledger

    signals = [ExitSignal(code="SMA_LONG", severity="strong", detail="종가<SMA200")]
    ledger = build_evidence_ledger(
        criteria_verdict=_holding(signals, action="liquidate"),
        factor_assessments=[],
        snapshot=None,
        flow=None,
        mode="holding",
    )
    keys = {e.key for e in ledger.bull + ledger.bear}
    assert "exit_SMA_LONG" in keys
    assert "canslim_M" in keys  # holding은 게이트 없으니 M 유지
    assert "canslim_L" not in keys  # L은 항상 제외
    assert not any(k.startswith("gate_") for k in keys)
    assert next(e for e in ledger.bear if e.key == "exit_SMA_LONG").weight == 5.0

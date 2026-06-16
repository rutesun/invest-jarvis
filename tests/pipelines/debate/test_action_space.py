from src.pipelines.debate.ledger import compute_action_space
from src.tools.criteria.models import (
    CriteriaVerdict,
    ExitSignal,
    ExitVerdict,
    MarketRegimeResult,
    RelativeStrengthResult,
)


def _v(regime_allow=True, exit_signals=None, exit_action="hold", holding=False):
    return CriteriaVerdict(
        ticker="T",
        holding=holding,
        market_regime=MarketRegimeResult(
            regime="상승" if regime_allow else "하락",
            allow_new_buy=regime_allow,
            index_symbol="^GSPC",
        ),
        relative_strength=RelativeStrengthResult(
            mansfield_rs=1.0, outperform_6m=5.0, rp_slope_4w=0.1, index_symbol="^GSPC"
        ),
        sector_strength=None,
        canslim=None,
        checks=[],
        position_plan=None,
        exit_verdict=(
            ExitVerdict(
                action=exit_action,
                signals=exit_signals or [],
                current_r=None,
                trailing_stop=None,
                detail="d",
            )
            if holding
            else None
        ),
        headline="t",
    )


def test_bear_market_entry_only_watch():
    assert compute_action_space(_v(regime_allow=False), "entry") == ["관망"]


def test_bull_market_entry_allows_buy():
    assert compute_action_space(_v(regime_allow=True), "entry") == ["매수", "관망"]


def test_medium_signal_allows_reduce_or_hold():
    one = [ExitSignal(code="SMA_SHORT", severity="medium", detail="d")]
    assert compute_action_space(
        _v(exit_signals=one, exit_action="reduce", holding=True), "holding"
    ) == [
        "비중축소",
        "보유",
    ]


def test_two_medium_same_bucket_as_one():
    """medium >= 1 이므로 2개도 1개와 같은 버킷 — 역전 방지 확인."""
    two = [
        ExitSignal(code="SMA_SHORT", severity="medium", detail="d"),
        ExitSignal(code="DISTRIBUTION", severity="medium", detail="d"),
    ]
    assert compute_action_space(
        _v(exit_signals=two, exit_action="reduce", holding=True), "holding"
    ) == [
        "비중축소",
        "보유",
    ]


def test_strong_exit_no_add():
    s = [ExitSignal(code="SMA_LONG", severity="strong", detail="d")]
    assert compute_action_space(
        _v(exit_signals=s, exit_action="liquidate", holding=True), "holding"
    ) == [
        "청산",
        "비중축소",
    ]


def test_none_verdict_graceful():
    assert compute_action_space(None, "entry") == ["매수", "관망"]

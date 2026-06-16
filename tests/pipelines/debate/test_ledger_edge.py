"""Edge-case tests for build_evidence_ledger and compute_action_space."""

from __future__ import annotations

import pytest

from src.pipelines.debate.ledger import build_evidence_ledger, compute_action_space


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------


class _FakeSnapshot:
    def __init__(self, rsi=None):
        self.rsi = rsi


class _FakeFlow:
    def __init__(self, foreign="N/A", inst="N/A"):
        self.foreign_direction_5d = foreign
        self.institution_direction_5d = inst


class _FakeRegime:
    def __init__(self, allow_new_buy=True):
        self.allow_new_buy = allow_new_buy


class _FakeFA:
    def __init__(self, factor_type, bias, total_score=6, headline="h", summary="s"):
        self.factor_type = factor_type
        self.bias = bias
        self.total_score = total_score
        self.headline = headline
        self.summary = summary


class _FakeRS:
    def __init__(self, mansfield_rs=0.0):
        self.mansfield_rs = mansfield_rs


class _FakeVerdict:
    def __init__(
        self,
        *,
        market_regime=None,
        checks=None,
        canslim=None,
        relative_strength=None,
        exit_verdict=None,
        holding=False,
    ):
        self.market_regime = market_regime
        self.checks = checks or []
        self.canslim = canslim
        self.relative_strength = relative_strength
        self.exit_verdict = exit_verdict
        self.holding = holding
        self.gate_passed = True


# ---------------------------------------------------------------------------
# 1. criteria_verdict=None → 빈 장부, 기본 action_space
# ---------------------------------------------------------------------------


def test_build_ledger_all_none_returns_empty():
    ledger = build_evidence_ledger(
        criteria_verdict=None,
        factor_assessments=[],
        snapshot=None,
        flow=None,
        mode="entry",
    )
    assert ledger.bull == []
    assert ledger.bear == []
    assert ledger.neutral == []
    assert ledger.bull_weight == 0.0
    assert ledger.bear_weight == 0.0
    assert ledger.action_space == ["매수", "관망"]


def test_build_ledger_all_none_holding_mode():
    ledger = build_evidence_ledger(
        criteria_verdict=None,
        factor_assessments=[],
        snapshot=None,
        flow=None,
        mode="holding",
    )
    assert ledger.action_space == ["보유", "비중축소", "청산"]


# ---------------------------------------------------------------------------
# 2. check.met=None → side="bear" (False 취급)
# ---------------------------------------------------------------------------


def test_check_met_none_goes_to_bear():
    from src.tools.criteria.models import CriteriaCheck

    verdict = _FakeVerdict(
        checks=[CriteriaCheck(name="E", required=False, met=None, reason="미확인")]
    )
    ledger = build_evidence_ledger(
        criteria_verdict=verdict,
        factor_assessments=[],
        snapshot=None,
        flow=None,
        mode="entry",
    )
    keys = [e.key for e in ledger.bear]
    assert "vcp_trigger" in keys


# ---------------------------------------------------------------------------
# 3. rs_magnitude=0 → 증거 없음 (중립 신호 추가 안 함)
# ---------------------------------------------------------------------------


def test_rs_magnitude_zero_not_added():
    verdict = _FakeVerdict(relative_strength=_FakeRS(mansfield_rs=0.0))
    ledger = build_evidence_ledger(
        criteria_verdict=verdict,
        factor_assessments=[],
        snapshot=None,
        flow=None,
        mode="entry",
    )
    all_keys = [e.key for e in ledger.bull + ledger.bear + ledger.neutral]
    assert "rs_magnitude" not in all_keys


# ---------------------------------------------------------------------------
# 4. flow 양방향 — 외인만 매수 → bull, 기관만 매수 → bull, 둘 다 매도 → 없음
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "foreign,inst,expect_flow_bull",
    [
        ("매수", "매도", True),
        ("매도", "매수", True),
        ("매도", "매도", False),
        ("N/A", "N/A", False),
    ],
)
def test_flow_routing(foreign, inst, expect_flow_bull):
    ledger = build_evidence_ledger(
        criteria_verdict=None,
        factor_assessments=[],
        snapshot=None,
        flow=_FakeFlow(foreign=foreign, inst=inst),
        mode="entry",
    )
    has_flow = any(e.key == "flow" for e in ledger.bull)
    assert has_flow is expect_flow_bull


# ---------------------------------------------------------------------------
# 5. RSI 경계값 — 79 → 없음, 80 → bear 추가
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rsi,expect_bear", [(79.9, False), (80.0, True), (90.0, True)])
def test_rsi_overbought_boundary(rsi, expect_bear):
    ledger = build_evidence_ledger(
        criteria_verdict=None,
        factor_assessments=[],
        snapshot=_FakeSnapshot(rsi=rsi),
        flow=None,
        mode="entry",
    )
    has_rsi_bear = any(e.key == "rsi_overbought" for e in ledger.bear)
    assert has_rsi_bear is expect_bear


# ---------------------------------------------------------------------------
# 6. factor_type="flow" → 제외
# ---------------------------------------------------------------------------


def test_factor_flow_excluded():
    fa_flow = _FakeFA(factor_type="flow", bias="bullish")
    fa_tech = _FakeFA(factor_type="technical", bias="bullish")
    ledger = build_evidence_ledger(
        criteria_verdict=None,
        factor_assessments=[fa_flow, fa_tech],
        snapshot=None,
        flow=None,
        mode="entry",
    )
    keys = [e.key for e in ledger.bull]
    assert "factor_flow" not in keys
    assert "factor_technical" in keys


# ---------------------------------------------------------------------------
# 7. factor weight capped at 5.0 (total_score 초과 시)
# ---------------------------------------------------------------------------


def test_factor_weight_cap():
    fa = _FakeFA(factor_type="technical", bias="bullish", total_score=30)  # 30/3=10 → cap 5
    ledger = build_evidence_ledger(
        criteria_verdict=None,
        factor_assessments=[fa],
        snapshot=None,
        flow=None,
        mode="entry",
    )
    assert ledger.bull[0].weight == 5.0


# ---------------------------------------------------------------------------
# 8. rs_magnitude weight capped at 3.0 (|rs|>30)
# ---------------------------------------------------------------------------


def test_rs_magnitude_weight_cap():
    verdict = _FakeVerdict(relative_strength=_FakeRS(mansfield_rs=50.0))
    ledger = build_evidence_ledger(
        criteria_verdict=verdict,
        factor_assessments=[],
        snapshot=None,
        flow=None,
        mode="entry",
    )
    rs_ev = next(e for e in ledger.bull if e.key == "rs_magnitude")
    assert rs_ev.weight == 3.0


# ---------------------------------------------------------------------------
# 9. compute_action_space: allow_new_buy=False → ["관망"] 강제
# ---------------------------------------------------------------------------


def test_action_space_block_entry_when_regime_off():
    verdict = _FakeVerdict(market_regime=_FakeRegime(allow_new_buy=False))
    space = compute_action_space(verdict, "entry")
    assert space == ["관망"]


# ---------------------------------------------------------------------------
# 10. bull_weight / bear_weight 정확성 — 복수 증거 합산
# ---------------------------------------------------------------------------


def test_weight_aggregation():
    fa1 = _FakeFA(factor_type="technical", bias="bullish", total_score=9)  # weight=3.0
    fa2 = _FakeFA(factor_type="valuation", bias="bearish", total_score=6)  # weight=2.0
    ledger = build_evidence_ledger(
        criteria_verdict=None,
        factor_assessments=[fa1, fa2],
        snapshot=None,
        flow=None,
        mode="entry",
    )
    assert ledger.bull_weight == pytest.approx(3.0)
    assert ledger.bear_weight == pytest.approx(2.0)

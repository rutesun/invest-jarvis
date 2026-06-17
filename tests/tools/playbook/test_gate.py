"""TDD: gate.py — evaluate_gate 매수 게이트."""


def _regime(allow: bool):
    from src.tools.playbook.models import MarketRegimeResult

    return MarketRegimeResult(
        regime="상승" if allow else "하락",
        allow_new_buy=allow,
        index_symbol="^GSPC",
    )


def _rs(strong: bool):
    from src.tools.playbook.models import RelativeStrengthResult

    return RelativeStrengthResult(
        mansfield_rs=5.0 if strong else -5.0,
        outperform_6m=10.0 if strong else -10.0,
        rp_slope_4w=0.5 if strong else -0.5,
        index_symbol="^GSPC",
    )


def _sector(strong: bool | None):
    from src.tools.playbook.models import SectorStrengthResult

    if strong is None:
        return None
    return SectorStrengthResult(
        industry="Technology",
        rank_pct=0.1 if strong else 0.9,
        trend="up" if strong else "down",
        is_strong=strong,
        source="FMP",
    )


def _vcp(breakout: bool):
    from src.tools.playbook.models import VcpResult

    return VcpResult(in_vcp=True, pivot=100.0, breakout=breakout)


def _canslim(score: int):
    from src.tools.playbook.models import CanslimResult, ElementVerdict

    bools = [True] * score + [False] * (7 - score)
    e = [ElementVerdict(met=b) for b in bools]
    return CanslimResult(c=e[0], a=e[1], n=e[2], s=e[3], l=e[4], i=e[5], m=e[6])


# ---------------------------------------------------------------------------
# 적격 케이스: 모든 필수 게이트 통과
# ---------------------------------------------------------------------------


def test_gate_passed_all_required():
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is True
    assert result.veto_reason is None
    assert result.quality_grade is not None


# ---------------------------------------------------------------------------
# ★ 탈락 케이스: A — 시장 환경 거부
# ---------------------------------------------------------------------------


def test_gate_fail_market_regime():
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(False),
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is False
    assert result.veto_reason is not None
    assert "A" in result.veto_reason or "시장" in result.veto_reason


# ---------------------------------------------------------------------------
# ★ 탈락 케이스: B — Stage 2 미충족
# ---------------------------------------------------------------------------


def test_gate_fail_stage2():
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=0.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is False
    assert result.veto_reason is not None
    assert (
        "B" in result.veto_reason or "Stage" in result.veto_reason or "2단계" in result.veto_reason
    )


# ---------------------------------------------------------------------------
# ★ 탈락 케이스: C — RS 약세
# ---------------------------------------------------------------------------


def test_gate_fail_rs_weak():
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(False),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is False
    assert result.veto_reason is not None


# ---------------------------------------------------------------------------
# ★ sector_strength=None graceful: 종목 RS만으로 C 통과
# ---------------------------------------------------------------------------


def test_gate_sector_none_graceful_rs_strong():
    """sector_strength=None이어도 종목 RS 강세면 C 통과."""
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=None,  # 섹터 데이터 없음
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is True, f"sector=None + RS강세면 통과해야 함: {result.veto_reason}"


def test_gate_sector_none_rs_weak_fails():
    """sector_strength=None + RS 약세 → C 탈락."""
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(False),
        sector_strength=None,
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is False


# ---------------------------------------------------------------------------
# ★ 탈락 케이스: E — VCP 돌파 없음
# ---------------------------------------------------------------------------


def test_gate_fail_no_breakout():
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(False),
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is False
    assert result.veto_reason is not None


# ---------------------------------------------------------------------------
# ★ 입력 None → 보수적 FAIL
# ---------------------------------------------------------------------------


def test_gate_fail_regime_none():
    """market_regime=None → 보수적 FAIL."""
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=None,
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is False
    assert "데이터" in result.veto_reason or "A" in result.veto_reason


def test_gate_fail_rs_none():
    """relative_strength=None → 보수적 FAIL (C 항목)."""
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=None,
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is False


def test_gate_fail_vcp_none():
    """vcp=None → 보수적 FAIL (E 항목)."""
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=None,
        canslim=_canslim(5),
        flow=None,
    )
    assert result.passed is False


# ---------------------------------------------------------------------------
# quality_grade: 통과 시 가점 비율
# ---------------------------------------------------------------------------


def test_gate_quality_grade_a_high_score():
    """canslim 높은 점수 → grade A."""
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(7),
        flow=None,
    )
    assert result.passed is True
    assert result.quality_grade == "A"


def test_gate_quality_grade_c_low_score():
    """canslim 낮은 점수 → grade C."""
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(1),
        flow=None,
    )
    assert result.passed is True
    assert result.quality_grade == "C"


# ---------------------------------------------------------------------------
# checklist: 모든 항목 포함 확인
# ---------------------------------------------------------------------------


def test_gate_checklist_has_all_required_items():
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    names = {c.name for c in result.checklist}
    # A, B, C, E 필수 항목 포함
    for required in ("A", "B", "C", "E"):
        assert required in names, f"{required} not in checklist names: {names}"


# ---------------------------------------------------------------------------
# flow 수급 가점 (한국): 외인/기관 매수 → 가점
# ---------------------------------------------------------------------------


def test_gate_flow_bonus_does_not_fail_gate():
    """flow가 None이어도 가점 0으로 처리, 통과에 영향 없음."""
    from src.tools.playbook.gate import evaluate_gate

    result_no_flow = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=1.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(4),
        flow=None,
    )
    assert result_no_flow.passed is True


# ---------------------------------------------------------------------------
# B 근접도 노출: Stage2 미충족 시 충족 개수 + 미충족 조건 라벨
# ---------------------------------------------------------------------------


def test_gate_b_reason_shows_stage2_proximity():
    """B 미충족 시 reason에 충족 개수(6/7)와 미충족 조건 라벨이 노출된다."""
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=0.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
        stage2_met_count=6.0,
        stage2_failed_labels=["종가>50일선"],
    )
    b_check = next(c for c in result.checklist if c.name == "B")
    assert "6/7" in b_check.reason
    assert "종가>50일선" in b_check.reason
    assert result.veto_reason is not None and "6/7" in result.veto_reason


def test_gate_b_reason_omits_proximity_when_no_detail():
    """met_count 미제공 시 기존 동작 유지 — 하위호환(개수 정보 없음)."""
    from src.tools.playbook.gate import evaluate_gate

    result = evaluate_gate(
        market_regime=_regime(True),
        is_stage2=0.0,
        relative_strength=_rs(True),
        sector_strength=_sector(True),
        vcp=_vcp(True),
        canslim=_canslim(5),
        flow=None,
    )
    b_check = next(c for c in result.checklist if c.name == "B")
    assert "/7" not in b_check.reason

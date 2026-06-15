"""매수 게이트 평가 (Plan 8).

A = market_regime.allow_new_buy
B = is_stage2 == 1.0
C = relative_strength.is_strong AND (sector_strength.is_strong in {True, None})
    sector_strength=None → 종목 RS만으로 graceful 통과 (§6.3)
E = vcp.breakout

하나라도 False/None → passed=False, veto_reason = 가장 결정적 항목.
입력 None → 보수적 FAIL ("데이터 제한: {항목}").

가점: D(canslim.score) · I(canslim.i.met) · 수급(flow).
quality_grade: 통과 시 가점 충족 비율 → A/B/C.
"""

from __future__ import annotations

from src.tools.playbook.models import GateCheck, GateResult


def evaluate_gate(
    *,
    market_regime,
    is_stage2: float,
    relative_strength,
    sector_strength,
    vcp,
    canslim,
    flow,
    stage2_met_count: float | None = None,
    stage2_failed_labels: list[str] | None = None,
) -> GateResult:
    """매수 게이트 평가. 순수 함수 — I/O 없음."""
    checklist: list[GateCheck] = []

    # ── A: 시장 환경 ──────────────────────────────────────────────────────────
    if market_regime is None:
        a_met: bool | None = None
        a_reason = "데이터 제한: 시장환경"
    else:
        a_met = bool(market_regime.allow_new_buy)
        a_reason = f"시장환경={market_regime.regime}"
    checklist.append(GateCheck(name="A", required=True, met=a_met, reason=a_reason))

    # ── B: Stage 2 (미충족 시 충족 개수 + 미충족 조건 노출) ───────────────────
    b_met: bool | None = bool(is_stage2 == 1.0) if is_stage2 is not None else None
    b_reason = f"is_stage2={is_stage2}"
    if stage2_met_count is not None:
        detail = f"{int(stage2_met_count)}/7"
        if not b_met and stage2_failed_labels:
            detail += f", 미충족: {', '.join(stage2_failed_labels)}"
        b_reason += f" ({detail})"
    checklist.append(GateCheck(name="B", required=True, met=b_met, reason=b_reason))

    # ── C: RS 강세 AND 업종 강세 (sector None → RS만) ────────────────────────
    if relative_strength is None:
        c_met: bool | None = None
        c_reason = "데이터 제한: RS"
    else:
        rs_ok = bool(relative_strength.is_strong)
        if sector_strength is None:
            # graceful: 종목 RS만으로 판정
            c_met = rs_ok
            c_reason = f"RS={rs_ok} (업종 데이터 없음 — 종목 RS만 적용)"
        else:
            # sector.is_strong=None → 업종 무시, RS만 체크 (graceful)
            sec_ok = sector_strength.is_strong
            if sec_ok is None:
                c_met = rs_ok
                c_reason = f"RS={rs_ok} (업종 판정 불가 — graceful)"
            else:
                c_met = rs_ok and bool(sec_ok)
                c_reason = f"RS={rs_ok}, 업종강세={sec_ok}"
    checklist.append(GateCheck(name="C", required=True, met=c_met, reason=c_reason))

    # ── E: VCP 돌파 ───────────────────────────────────────────────────────────
    if vcp is None:
        e_met: bool | None = None
        e_reason = "데이터 제한: VCP"
    else:
        e_met = bool(vcp.breakout)
        e_reason = f"breakout={vcp.breakout}"
        if vcp.pivot is not None:
            e_reason += f", pivot={vcp.pivot:.2f}"
    checklist.append(GateCheck(name="E", required=True, met=e_met, reason=e_reason))

    # ── 가점: D(canslim.score) · I(canslim.i.met) · 수급(flow) ──────────────
    bonus_checks: list[GateCheck] = []

    if canslim is not None:
        # D: canslim score >= 4 (7점 중 4점 이상 → 가점)
        d_score = canslim.score
        d_met = d_score >= 4
        bonus_checks.append(
            GateCheck(name="D", required=False, met=d_met, reason=f"canslim.score={d_score}")
        )
        # I: 매집 우세
        i_verdict = canslim.i
        i_met = i_verdict.met
        bonus_checks.append(
            GateCheck(
                name="I",
                required=False,
                met=bool(i_met) if i_met is not None else None,
                reason=i_verdict.detail or "매집",
            )
        )
    else:
        bonus_checks.append(GateCheck(name="D", required=False, met=None, reason="canslim 없음"))
        bonus_checks.append(GateCheck(name="I", required=False, met=None, reason="canslim 없음"))

    # 수급(Flow): 한국 외인/기관 매수 여부
    if flow is not None:
        flow_ok = (
            getattr(flow, "foreign_direction_5d", "N/A") == "매수"
            or getattr(flow, "institution_direction_5d", "N/A") == "매수"
        )
        bonus_checks.append(
            GateCheck(name="수급", required=False, met=flow_ok, reason="외인/기관 5일 방향")
        )
    else:
        bonus_checks.append(
            GateCheck(name="수급", required=False, met=None, reason="수급 데이터 없음")
        )

    checklist.extend(bonus_checks)

    # ── veto 판정 ─────────────────────────────────────────────────────────────
    required_checks = [c for c in checklist if c.required]
    veto_reason: str | None = None

    # 우선순위: A → B → C → E 순서로 가장 먼저 걸린 항목
    for check in required_checks:
        if check.met is False or check.met is None:
            veto_reason = f"{check.name}: {check.reason}"
            break

    passed = veto_reason is None

    # ── quality_grade ─────────────────────────────────────────────────────────
    quality_grade: str | None = None
    if passed:
        bonus_met = sum(1 for c in bonus_checks if c.met is True)
        bonus_total = len(bonus_checks)
        ratio = bonus_met / bonus_total if bonus_total > 0 else 0.0

        if ratio >= 2 / 3:
            quality_grade = "A"
        elif ratio >= 1 / 3:
            quality_grade = "B"
        else:
            quality_grade = "C"

    return GateResult(
        passed=passed,
        checklist=checklist,
        quality_grade=quality_grade,
        veto_reason=veto_reason,
    )

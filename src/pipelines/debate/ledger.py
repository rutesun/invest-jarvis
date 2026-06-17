from __future__ import annotations

from src.pipelines.debate.models import BullBearLedger, Evidence


# check.name → (signal code, weight)
_CHECK_SIGNAL: dict[str, tuple[str, float]] = {
    "A": ("market_regime", 4.0),
    "B": ("stage2", 4.0),
    "C": ("rs_leadership", 4.0),
    "E": ("vcp_trigger", 3.0),
}

# CAN SLIM attrs → label (L and M excluded per dedup rules)
_CANSLIM_ENTRY: dict[str, str] = {
    "c": "분기 EPS",
    "a": "연간 CAGR",
    "n": "신요소",
    "s": "수급",
    "i": "기관매집",
}
# holding adds M (no gate duplication), L always excluded
_CANSLIM_HOLDING: dict[str, str] = {**_CANSLIM_ENTRY, "m": "시장"}

# factor_type → label (flow excluded)
_FACTOR_LABELS: dict[str, str] = {
    "technical": "기술",
    "valuation": "밸류",
    "event": "이벤트",
}


def _add(buckets: dict, ev: Evidence) -> None:
    buckets[ev.side].append(ev)


def build_evidence_ledger(
    *,
    criteria_verdict,
    factor_assessments,
    snapshot,
    flow,
    mode: str,
) -> BullBearLedger:
    """기존 판정 결과를 bull/bear/neutral 로 분류·채점.
    순수 함수, 새 데이터 안 만듦.
    momentum_events 는 증거가 아님(Event 섹션 표시용).
    """
    buckets: dict[str, list[Evidence]] = {"bull": [], "bear": [], "neutral": []}

    # A·B·C·E checks → 신호 (entry/holding 모두 — spec §7.1/7.2)
    if criteria_verdict is not None and criteria_verdict.checks:
        for check in criteria_verdict.checks:
            if check.name not in _CHECK_SIGNAL:
                continue
            code, weight = _CHECK_SIGNAL[check.name]
            side = "bull" if check.met is True else "bear"
            _add(
                buckets,
                Evidence(
                    side=side,
                    key=code,
                    weight=weight,
                    headline=f"신호 {check.name} ({code})",
                    detail=check.reason,
                    source="playbook",
                    kind="signal",
                ),
            )

    # CAN SLIM (mode별 라벨셋 — L 항상 제외, M은 holding만)
    if criteria_verdict is not None and criteria_verdict.canslim is not None:
        labels = _CANSLIM_ENTRY if mode == "entry" else _CANSLIM_HOLDING
        cs = criteria_verdict.canslim
        for attr, label in labels.items():
            v = getattr(cs, attr)
            if v.met is True:
                side = "bull"
            elif v.met is False:
                side = "bear"
            else:
                side = "neutral"
            _add(
                buckets,
                Evidence(
                    side=side,
                    key=f"canslim_{attr.upper()}",
                    weight=1.0,
                    headline=f"CAN SLIM {attr.upper()} {label}",
                    detail=v.detail or "—",
                    source="playbook",
                    kind="signal",
                ),
            )

    # rs_magnitude (연속값 — L 제거 대신 크기 반영)
    if criteria_verdict is not None and criteria_verdict.relative_strength is not None:
        rs = criteria_verdict.relative_strength.mansfield_rs
        if rs != 0:
            side = "bull" if rs > 0 else "bear"
            _add(
                buckets,
                Evidence(
                    side=side,
                    key="rs_magnitude",
                    weight=min(abs(rs) / 10.0, 3.0),
                    headline="상대강도 크기",
                    detail=f"Mansfield RS={rs:+.2f}",
                    source="playbook",
                    kind="signal",
                ),
            )

    # flow 행 (factor_flow 제외, 이 행만): 매수 우세 → bull, 동시 매도 → bear(분산)
    if flow is not None:
        foreign = getattr(flow, "foreign_direction_5d", "N/A")
        inst = getattr(flow, "institution_direction_5d", "N/A")
        flow_side = None
        if foreign == "매수" or inst == "매수":
            flow_side = "bull"
        elif foreign == "매도" and inst == "매도":
            flow_side = "bear"
        if flow_side is not None:
            _add(
                buckets,
                Evidence(
                    side=flow_side,
                    key="flow",
                    weight=2.0,
                    headline="수급",
                    detail=f"외인 5일 {foreign} / 기관 5일 {inst}",
                    source="flow",
                    kind="signal",
                ),
            )

    # factor_assessments (flow 제외)
    for fa in factor_assessments or []:
        if fa.factor_type not in _FACTOR_LABELS:
            continue
        if fa.bias == "bullish":
            side = "bull"
        elif fa.bias == "bearish":
            side = "bear"
        else:
            side = "neutral"
        _add(
            buckets,
            Evidence(
                side=side,
                key=f"factor_{fa.factor_type}",
                weight=min(fa.total_score / 3.0, 5.0),
                headline=fa.headline or f"{_FACTOR_LABELS[fa.factor_type]} 팩터",
                detail=fa.summary,
                source="factor",
                kind="signal",
            ),
        )

    # rsi_overbought (단방향 하드 신호)
    if snapshot is not None:
        rsi = getattr(snapshot, "rsi", None)
        if rsi is not None and rsi >= 80:
            _add(
                buckets,
                Evidence(
                    side="bear",
                    key="rsi_overbought",
                    weight=2.0,
                    headline="RSI 과매수",
                    detail=f"RSI={rsi:.1f} ≥ 80",
                    source="technical",
                    kind="signal",
                ),
            )

    # holding: exit signals + r_cushion
    if mode == "holding" and criteria_verdict is not None:
        ev = getattr(criteria_verdict, "exit_verdict", None)
        if ev is not None:
            sw = {"strong": 5.0, "medium": 3.0, "weak": 1.0}
            for sig in ev.signals:
                _add(
                    buckets,
                    Evidence(
                        side="bear",
                        key=f"exit_{sig.code}",
                        weight=sw.get(sig.severity, 1.0),
                        headline=f"매도신호 {sig.code}",
                        detail=sig.detail,
                        source="playbook",
                        kind="signal",
                    ),
                )
            if ev.current_r is not None and ev.current_r != 0:
                side = "bull" if ev.current_r > 0 else "bear"
                _add(
                    buckets,
                    Evidence(
                        side=side,
                        key="r_cushion",
                        weight=min(abs(ev.current_r), 3.0),
                        headline="R 쿠션",
                        detail=f"current_r={ev.current_r:.2f}",
                        source="playbook",
                        kind="signal",
                    ),
                )

    return BullBearLedger(
        mode=mode,
        bull=buckets["bull"],
        bear=buckets["bear"],
        neutral=buckets["neutral"],
        bull_weight=round(sum(e.weight for e in buckets["bull"]), 2),
        bear_weight=round(sum(e.weight for e in buckets["bear"]), 2),
        action_space=compute_action_space(criteria_verdict, mode),
    )


def compute_action_space(criteria_verdict, mode: str) -> list[str]:
    """하드 리스크 가드레일 — 판사의 허용 액션 제한."""
    if criteria_verdict is None:
        return ["매수", "관망"] if mode == "entry" else ["보유", "비중축소", "청산"]
    if mode == "entry":
        regime = getattr(criteria_verdict, "market_regime", None)
        if regime is not None and regime.allow_new_buy is False:
            return ["관망"]
        return ["매수", "관망"]
    ev = getattr(criteria_verdict, "exit_verdict", None)
    if ev is not None:
        if any(s.severity == "strong" for s in ev.signals) or ev.action == "liquidate":
            return ["청산", "비중축소"]
        if sum(1 for s in ev.signals if s.severity == "medium") >= 1:
            return ["비중축소", "보유"]
    return ["보유", "비중축소"]

"""One ordered markdown view of scorecard and strategy opinions."""

from __future__ import annotations

from src.pipelines.strategy_analysis import AnalysisStrategyResult
from src.strategies.models import (
    EntryOpportunityStatus,
    ObservationDirection,
    ObservationKind,
    ObservationStatus,
    ObservationTemporalType,
    SignalFinality,
)
from src.strategies.observations.registry import OBSERVATION_REGISTRY
from src.strategies.signal_performance import ENTRY_SIGNAL_CODES, SignalPerformance
from src.tools.technical.scorecard_models import Importance, TechnicalScorecard


def render_strategy_sections(
    scorecard: TechnicalScorecard | None,
    analysis: AnalysisStrategyResult | None,
    *,
    warning: str | None = None,
    detail: bool = False,
) -> str:
    if scorecard is None:
        return f"### Strategy\n- {warning or 'Scorecard unavailable'}"
    warning = warning or getattr(analysis, "warning", None)

    dimensions = scorecard.dimensions()
    labels = ("추세", "구조", "모멘텀", "수급", "안전도")
    lines = [
        "### Technical Scorecard",
        " | ".join(
            f"{label} {dimension.score if dimension.score is not None else 'N/A'}"
            for label, dimension in zip(labels, dimensions, strict=True)
        ),
    ]

    if analysis is not None:
        lines.extend(["", "### 최근 5거래일 Technical Score"])
        lines.extend(_score_history_lines(analysis))

    lines.extend(["", "### 중요 상태 / Evidence"])
    if scorecard.trend.metrics.get("supertrend_direction") == -1:
        lines.append("- Technical Evidence 경고: Supertrend DOWN — 현재 하락 방향")
    for dimension in dimensions:
        for observation in dimension.observations:
            if detail or observation.importance == Importance.HIGH:
                direction = (
                    f" ({observation.direction.value})"
                    if detail and observation.direction is not None
                    else ""
                )
                lines.append(f"- {observation.message}{direction}")
            for evidence in observation.evidence:
                if detail or evidence.importance == Importance.HIGH:
                    lines.append(f"  - {evidence.message}")
        for contribution in dimension.score_contributions:
            for evidence in contribution.evidence:
                if detail or evidence.importance == Importance.HIGH:
                    lines.append(f"- {evidence.message}")
        if detail:
            for code, metric in dimension.metrics.items():
                value = metric.model_dump(mode="json") if hasattr(metric, "model_dump") else metric
                lines.append(f"- {dimension.code}.{code}: {value}")

    lines.extend(["", "### 최근 Analysis Trigger — 20거래일"])
    for trigger in sorted(
        scorecard.triggers, key=lambda item: (item.occurred_on, item.code), reverse=True
    ):
        if trigger.bars_ago <= 20:
            lines.append(
                f"- {trigger.occurred_on} {trigger.code} — {trigger.status.value}"
                f" ({trigger.status_reason})"
            )
            if detail:
                lines.extend(f"  - {evidence.message}" for evidence in trigger.evidence)

    bundles = getattr(analysis.strategy_run, "signal_bundles", []) if analysis else []
    recent = set(analysis.exchange_sessions[-20:]) if analysis else set()
    lines.extend(["", "### cycle / support"])
    for bundle in bundles:
        lines.extend(_cycle_support_lines(bundle, detail))
    if not bundles:
        lines.append("- 미평가 — Strategy bundle 없음")

    lines.extend(["", "### 현재 Observation"])
    current = [
        (bundle, episode)
        for bundle in bundles
        for episode in bundle.observation_history
        if episode.status is ObservationStatus.ACTIVE
        and episode.temporal_type is ObservationTemporalType.EPISODE
    ]
    for label, selected in (
        (
            "SETUP",
            [(bundle, item) for bundle, item in current if item.kind is ObservationKind.SETUP],
        ),
        (
            "Positive Observations",
            [
                (bundle, item)
                for bundle, item in current
                if item.direction is ObservationDirection.POSITIVE
            ],
        ),
        (
            "Risk Observations",
            [
                (bundle, item)
                for bundle, item in current
                if item.direction is ObservationDirection.RISK
            ],
        ),
    ):
        lines.append(f"#### {label} — ACTIVE EPISODE")
        for bundle, episode in selected:
            lines.extend(_observation_lines(bundle.strategy_id, episode, detail))
        if not selected:
            lines.append("- 해당 ACTIVE EPISODE 기록 없음 — 평가 상태는 아래 참조")
    lines.append("#### 당일 EVENT")
    today_events = [
        (bundle, item)
        for bundle in bundles
        for item in bundle.observation_history
        if item.temporal_type is ObservationTemporalType.EVENT
        and (item.confirmed_on or item.started_on) == bundle.as_of
    ]
    for bundle, event in today_events:
        lines.extend(_observation_lines(bundle.strategy_id, event, detail))
    if not today_events:
        lines.append("- 당일 EVENT 기록 없음 — 평가 상태는 아래 참조")
    lines.append("#### 평가 상태")
    for bundle in bundles:
        lines.extend(_observation_evaluation_lines(bundle, detail))
    if not bundles:
        lines.append("- 미평가 — Strategy bundle 없음")

    lines.extend(["", "### 최근 Observation history — 20거래일"])
    observations = sorted(
        (
            (bundle.strategy_id, episode)
            for bundle in bundles
            for episode in bundle.observation_history
            if detail or episode.started_on in recent or episode.ended_on in recent
        ),
        key=lambda item: (item[1].started_on, item[0], item[1].code),
        reverse=True,
    )
    for strategy_id, episode in observations:
        lines.extend(_observation_lines(strategy_id, episode, detail))
    if not observations:
        lines.append("- 최근 20거래일 Observation 기록 없음 — 평가 상태는 위 참조")

    lines.extend(["", "### 최근 Signal history — 20거래일"])
    signals = sorted(
        (
            signal
            for bundle in bundles
            for signal in bundle.signal_history
            if detail or signal.occurred_on in recent
        ),
        key=lambda signal: (signal.occurred_on, signal.strategy_id, signal.code),
        reverse=True,
    )
    performances = (
        {
            (
                item.signal_id,
                item.strategy_id,
                item.strategy_version,
                item.parameter_set_version,
                item.parameter_fingerprint,
            ): item
            for item in getattr(analysis, "signal_performances", ())
        }
        if analysis
        else {}
    )
    for signal in signals:
        direction = f" ({signal.direction.value})" if signal.direction else ""
        lines.append(
            f"- {signal.occurred_on} {signal.strategy_id} {signal.code} "
            f"[{signal.finality.value.upper()}]{direction} — 기준가 {signal.signal_price:g}"
        )
        lines.extend(_decision_evidence_lines(signal.evidence, first_label="발생 원인"))
        performance = performances.get(
            (
                signal.signal_id,
                signal.strategy_id,
                signal.strategy_version,
                signal.parameter_set_version,
                signal.parameter_fingerprint,
            )
        )
        if performance is not None:
            lines.extend(_performance_lines(performance, detail))
    if not signals:
        lines.append("- 없음 또는 평가 불가")

    lines.extend(["", "### 전략"])
    if analysis is None:
        lines.append(f"- {warning or 'Strategy section unavailable'}")
    else:
        for verdict in analysis.strategy_run.verdicts:
            lines.append(
                f"- {verdict.strategy_id}: entry={verdict.entry.intent.value}"
                f" ({verdict.entry.data_status.value}), exit={verdict.exit.intent.value}"
                f" ({verdict.exit.data_status.value})"
            )
            for reason in (*verdict.entry.reasons, *verdict.exit.reasons):
                if detail or reason.importance == Importance.HIGH:
                    lines.append(f"  - {reason.message}")
        for error in analysis.strategy_run.errors:
            lines.append(f"- {error}")
        for error in getattr(analysis.strategy_run, "diagnostic_errors", ()):
            lines.append(f"- Shadow 진단 오류: {error}")
        if warning:
            lines.append(f"- {warning}")

    lines.extend(["", "### 오늘 EntryOpportunity"])
    for bundle in bundles:
        opportunity = bundle.entry_opportunity
        status_label = (
            "EXECUTION_WATCH"
            if opportunity.status is EntryOpportunityStatus.WATCH
            else opportunity.status.value.upper()
        )
        parts = [
            f"- {bundle.strategy_id}: {status_label} [{opportunity.finality.value.upper()}]",
            f"현재가 {analysis.current_close:g}",
            f"market={opportunity.market_regime or 'unknown'}",
            f"structure={opportunity.structure_status.value}",
        ]
        if opportunity.entry_signal:
            parts.append(f"source={opportunity.entry_signal.code}")
            parts.append(f"발생일={opportunity.entry_signal.occurred_on}")
            parts.append(f"source finality={opportunity.entry_signal.finality.value.upper()}")
        parts.append(f"Production policy={opportunity.policy_version}")
        if opportunity.signal_price is not None:
            parts.append(f"Signal 기준가 {opportunity.signal_price:g}")
        if opportunity.execution_reference_price is not None:
            basis = "Signal 종가 추정" if opportunity.age_bars == 0 else "다음 실제 거래 가능 시가"
            parts.append(f"{basis} {opportunity.execution_reference_price:g}")
        if opportunity.age_bars is not None:
            parts.append(f"{opportunity.age_bars}거래일 전")
        if opportunity.extension_pct is not None:
            parts.append(f"확장 {opportunity.extension_pct * 100:+.1f}%")
        if opportunity.invalidated_by:
            parts.append(f"무효화 {opportunity.invalidated_by.code}")
        lines.append(" — ".join(parts))
        lines.append(f"  - 상태 원인: {_opportunity_reason(opportunity)}")
        lines.extend(_decision_evidence_lines(opportunity.evidence))
        if opportunity.terminal_on is not None:
            terminal_finality = opportunity.terminal_finality
            label = terminal_finality.value.upper() if terminal_finality else "UNKNOWN"
            lines.append(f"  - 종료일={opportunity.terminal_on} [{label}]")
        lines.extend(_shadow_lines(bundle, detail))
    if not bundles:
        lines.append("- 없음 또는 평가 불가")

    if analysis is not None and analysis.position_plan is not None:
        plan = analysis.position_plan
        lines.extend(
            [
                "",
                "### Position Plan",
                f"- {plan.directive.kind.value}: current={plan.current_quantity}, "
                f"target={plan.target_quantity}, buy={plan.buy_quantity}, sell={plan.sell_quantity} "
                f"({plan.quantity_status.value})",
            ]
        )
        if plan.signal_finality is not None:
            label = "장중 후보" if plan.signal_finality is SignalFinality.PROVISIONAL else "확정"
            lines.append(f"- signal_finality={plan.signal_finality.value.upper()} ({label})")
            if detail:
                calculated_at = plan.calculated_at.isoformat() if plan.calculated_at else "N/A"
                lines.extend(
                    [
                        f"  - calculated_at={calculated_at}",
                        f"  - market_snapshot_hash={plan.market_snapshot_hash or 'N/A'}",
                    ]
                )
    return "\n".join(lines)


def _shadow_lines(bundle, detail: bool) -> list[str]:
    shadow = getattr(bundle, "entry_shadow", None)
    if shadow is None:
        return ["  - Risk: 미평가 — Shadow 비활성 또는 이용 불가"]
    finality = shadow.finality.value.upper()
    policy = f"Shadow policy={shadow.policy_version}"
    if shadow.risk_level is None:
        lines = [f"  - Risk: 미평가 [{finality}] — {shadow.reason} — {policy}"]
    else:
        lines = [f"  - Risk: {shadow.risk_level.value} [{finality}] — {policy}"]
    lines.append("  - Shadow 진단은 Production·Position Plan을 변경하지 않습니다")
    for flag in shadow.risk_flags:
        lines.append(f"  - {flag.message} [{flag.finality.value.upper()}]")
        lines.extend(_decision_evidence_lines(flag.evidence))
    if detail:
        lines.append(
            f"  - Production fingerprint={bundle.parameter_fingerprint}, "
            f"Shadow fingerprint={shadow.parameter_fingerprint}, "
            f"data_status={shadow.data_status.value}, reason={shadow.reason}"
        )
        for code, state in (*shadow.breakout_states.items(), *shadow.pullback_states.items()):
            lines.append(f"  - {code}: {state.model_dump(mode='json')}")
    return lines


def _cycle_support_lines(bundle, detail: bool) -> list[str]:
    cycle = getattr(bundle, "up_cycle", None)
    reason = getattr(bundle, "pullback_policy_inactive_reason", None)
    tests = getattr(bundle, "support_tests", None)
    lines = []
    if cycle is None:
        lines.append(f"- {bundle.strategy_id}: cycle 미평가 — {reason or '정책 평가 정보 없음'}")
    else:
        lines.append(
            f"- {bundle.strategy_id}: cycle {cycle.status} [{cycle.finality.value.upper()}]"
            f" — 시작일={cycle.started_on or '없음'}, 평가일={cycle.status_as_of or '없음'}"
            f", 확인={cycle.confirmation_code or '없음'}@{cycle.confirmation_on or '없음'}"
        )
        if cycle.terminated_on is not None or cycle.terminal_reason:
            lines.append(
                f"  - 종료일={cycle.terminated_on or '없음'}, 원인={cycle.terminal_reason or '없음'}"
            )
        if reason:
            lines.append(f"  - 정책 미활성/미평가 사유: {reason}")
        if detail:
            lines.append(
                f"  - cycle_id={cycle.cycle_id}, above_sma150_count={cycle.above_sma150_count}"
            )
    if tests is None:
        lines.append("  - support 미평가 — ladder 정책 미활성 또는 평가 정보 없음")
    elif not tests:
        lines.append("  - support test 기록 없음")
    for test in tests or ():
        anchor = test.anchor
        lines.append(
            f"  - anchor={anchor.anchor_type} {'dynamic' if anchor.is_dynamic else 'frozen'}"
            f" — origin={anchor.origin_on}@{anchor.origin_price:g}"
            f", current_value={anchor.current_value if anchor.current_value is not None else 'N/A'}"
            f" — {test.status} [{test.finality.value.upper()}], 시작일={test.started_on}"
            f", 평가일={test.status_as_of}, 종료일={test.ended_on or '없음'}"
            f", below_count={test.below_count}, failure_latched={test.failure_latched}"
            f", reclaim일={test.reclaimed_on or '없음'}, source={anchor.source_signal_id or '없음'}"
        )
        if detail:
            lines.append(f"    - anchor_id={anchor.anchor_id}, cycle_id={anchor.cycle_id}")
    return lines


_OBSERVATION_LABELS = {
    "PULLBACK_WATCH": "눌림목 지지 관찰",
    "POST_OVERHEAT_RECOVERY_WATCH": "과열 조정 후 회복 관찰",
    "HIGHER_LOW": "직전 저점보다 높은 저점 확인",
    "HIGHER_HIGH": "직전 고점보다 높은 고점 확인",
    "BREAKOUT_RECLAIM": "이탈했던 돌파 기준선 회복",
    "SUPPORT_RECLAIM": "이탈했던 지지선 회복",
    "VOLUME_CONTRACTION": "조정 구간 거래량 축소",
    "UP_VOLUME_EXPANSION": "상승일 거래량 확대",
    "MOMENTUM_REACCELERATION": "상승 모멘텀 재가속",
    "BREAKOUT_LEVEL_BREACH": "돌파 기준선 이탈 지속",
    "SUPPORT_BREAK": "지지선 이탈 지속",
    "PULLBACK_LOW_BREACH": "눌림목 저점 이탈 지속",
    "LOWER_HIGH": "직전 고점보다 낮은 고점 확인",
    "LOWER_LOW": "직전 저점보다 낮은 저점 확인",
    "DOWN_VOLUME_EXPANSION": "하락일 거래량 확대",
    "MOMENTUM_DECELERATION": "상승 모멘텀 약화 지속",
}


def _observation_lines(strategy_id, episode, detail: bool) -> list[str]:
    end = str(episode.ended_on) if episode.ended_on else "현재"
    lines = [
        f"- {episode.started_on}~{end} {strategy_id} {episode.code} — "
        f"{_OBSERVATION_LABELS[episode.code]} — {episode.status.value.upper()}"
        f" [{episode.finality.value.upper()}] ({episode.direction.value})"
        f" {episode.temporal_type.value}, scopes={','.join(sorted(scope.value for scope in episode.scopes))}",
        f"  - 발생일={episode.started_on}, 확인일={episode.confirmed_on or '없음'}"
        f", 평가일={episode.status_as_of}, pivot={episode.pivot_date or '없음'}"
        f", anchor={episode.anchor_type or '없음'}"
        f", origin={episode.anchor_origin_on or '없음'}@"
        f"{episode.anchor_origin_price if episode.anchor_origin_price is not None else '없음'}"
        f", source={episode.source_signal_id or '없음'}",
    ]
    if episode.source_terminal:
        lines.append("  - source 종료 상태의 관측이며 과거 EntryOpportunity를 부활시키지 않습니다")
    if episode.code == "PULLBACK_WATCH" and episode.anchor_type == "SMA150":
        lines.append("  - SMA150 마지막 방어선의 지지 관찰이며 반등 Entry Signal은 별도 확인합니다")
    for index, item in enumerate(episode.evidence):
        current = item.code.endswith("_CURRENT")
        if (
            detail
            or index == 0
            or current
            or item.importance is Importance.HIGH
            or item.observed_value is not None
            or item.reference_value is not None
        ):
            lines.extend(
                _decision_evidence_lines(
                    [item], first_label="현재 실측" if current else "발생 근거"
                )
            )
    if detail:
        lines.append(
            f"  - observation_id={episode.observation_id}, anchor_id={episode.anchor_id}, "
            f"cycle_id={episode.cycle_id}, schema_version={episode.schema_version}, "
            f"parameter_fingerprint={episode.parameter_fingerprint}"
        )
        lines.extend(f"    - Evidence={item.model_dump(mode='json')}" for item in episode.evidence)
    return lines


def _observation_evaluation_lines(bundle, detail: bool) -> list[str]:
    params = getattr(bundle, "observation_parameters", None)
    enabled = getattr(bundle, "observations_enabled", None)
    settings = [f"- Observation 설정={params}"] if detail and params is not None else []
    if enabled is False:
        return [
            f"- {bundle.strategy_id}: 미평가 — Observation 비활성(OFF); SETUP은 기존 detector 결과"
        ] + settings
    if enabled is None or params is None:
        return [f"- {bundle.strategy_id}: 미평가 — 평가 설정 확인 불가"] + settings
    errors = [item for item in bundle.diagnostic_errors if item.startswith("observation")]
    if errors:
        return [f"- {bundle.strategy_id}: 미평가 — {error}" for error in errors] + settings
    break_reclaim_fields = ("break_buffer_atr", "reclaim_buffer_atr")
    fields = {
        "UP_VOLUME_EXPANSION": ("up_volume_ratio",),
        "DOWN_VOLUME_EXPANSION": ("down_volume_ratio",),
        "VOLUME_CONTRACTION": ("contraction_ratio",),
        "BREAKOUT_LEVEL_BREACH": break_reclaim_fields,
        "SUPPORT_BREAK": break_reclaim_fields,
        "PULLBACK_LOW_BREACH": break_reclaim_fields,
        "BREAKOUT_RECLAIM": break_reclaim_fields,
        "SUPPORT_RECLAIM": break_reclaim_fields,
        "MOMENTUM_REACCELERATION": ("reacceleration_mode",),
    }
    lines = []
    for definition in OBSERVATION_REGISTRY.values():
        prerequisites = fields.get(definition.code, ())
        setting = "".join(f", {field}={params.get(field)}" for field in prerequisites)
        if definition.detector_validity == "NOT_IMPLEMENTED":
            state = "미구현"
        elif any(params.get(field) is None for field in prerequisites):
            state = "미평가 — 설정 미선정(UNRESOLVED)"
        elif bundle.data_status.value != "complete":
            state = f"미평가/불완전 — data_status={bundle.data_status.value}"
        elif definition.source_dependency == "REQUIRED" and not any(
            signal.code in ENTRY_SIGNAL_CODES for signal in bundle.signal_history
        ):
            state = "미평가 — 필수 source 없음"
        else:
            state = (
                "관측 기록 있음 — 현재/당일/history 구분 참조"
                if any(item.code == definition.code for item in bundle.observation_history)
                else "발생 기록 없음"
            )
        lines.append(
            f"- {definition.code}: {state}{setting} — detector={definition.detector_validity}, "
            f"predictive usefulness={definition.predictive_usefulness}"
        )
    return lines + settings


def _performance_lines(performance: SignalPerformance, detail: bool) -> list[str]:
    lines = []
    for label, value, price, basis, status, reason in (
        (
            "Signal 종가 추정",
            performance.estimated_return_from_signal_close,
            performance.signal_price,
            performance.estimated_price_basis,
            performance.estimated_data_status,
            performance.estimated_status_reason,
        ),
        (
            "다음 실제 거래 가능 시가 체결",
            performance.executed_return_from_next_tradable_open,
            performance.execution_reference_price,
            performance.executed_price_basis,
            performance.executed_data_status,
            performance.executed_status_reason,
        ),
    ):
        rendered = f"{value * 100:+.1f}%" if value is not None else status.value.upper()
        reference = f"{price:g}" if price is not None else "N/A"
        lines.append(
            f"  - {performance.signal_occurred_on} {performance.signal_code}: {label} {rendered}"
            f" — basis={basis.value}, 기준가={reference}, {status.value.upper()} ({reason})"
            f", 평가일={performance.evaluation_as_of or 'N/A'}"
        )
    if performance.execution_as_of is not None:
        lines.append(
            f"  - 체결일={performance.execution_as_of}, "
            f"지연={performance.execution_delay_sessions} sessions"
        )
    if detail:
        lines.append(
            f"  - signal_id={performance.signal_id}, strategy_id={performance.strategy_id}, "
            f"strategy_version={performance.strategy_version}, "
            f"parameter_set_version={performance.parameter_set_version}, "
            f"parameter_fingerprint={performance.parameter_fingerprint}"
        )
    return lines


def _decision_evidence_lines(evidence, *, first_label: str = "근거") -> list[str]:
    lines = []
    for index, item in enumerate(evidence):
        label = first_label if index == 0 else "근거"
        values = []
        if item.observed_value is not None:
            values.append(f"관측값={item.observed_value:g}")
        if item.reference_value is not None:
            values.append(f"기준값={item.reference_value:g}")
        suffix = f" ({', '.join(values)})" if values else ""
        lines.append(f"  - {label}: {_evidence_message(item)}{suffix}")
    return lines


def _evidence_message(item) -> str:
    labels = {
        "TREND_BREAKOUT_ENTRY": "추세 돌파 진입 조건 충족",
        "DEEP_RECOVERY_ENTRY": "깊은 조정 후 회복 진입 조건 충족",
        "PULLBACK_REVERSAL_ENTRY": "눌림목 지지 후 반등 진입 조건 충족",
        "POST_OVERHEAT_RECOVERY_ENTRY": "과열 조정 후 회복 진입 조건 충족",
        "OVERHEAT": "SMA50 대비 과열 기준 도달",
        "OVERHEAT_CORRECTION": "과열 후 SMA20 이탈 조정 확인",
        "OVERHEAT_RESOLVED": "SMA50 이격 축소로 과열 해소",
        "OVERHEAT_EXPIRED": "과열 유효기간 만료",
        "SMA150_EXIT": "SMA150 연속 이탈로 청산 조건 충족",
        "SMA_20": "SMA20 지지 확인",
        "SMA_50": "SMA50 지지 확인",
        "SMA_150": "SMA150 지지 확인",
        "SMA_200": "SMA200 지지 확인",
        "SuperTrend_Up": "Supertrend 상승 지지 확인",
        "cRSI": "cRSI 위치",
        "MACD": "MACD 위치",
        "ENTRY_WITHIN_EXTENSION": "허용 이격 이내",
        "ENTRY_WATCH": "허용 이격 초과 또는 시장 조건 대기",
        "BEAR_MARKET": "하락장으로 신규 진입 차단",
        "ENTRY_INVALIDATED": "후속 청산 Signal로 진입 기회 무효화",
        "BREAKOUT_ATR_INVALIDATED": "돌파선에서 source ATR만큼 하락한 종가로 진입 허가 취소",
        "ENTRY_EXPIRED": "진입 Signal 유효기간 만료",
        "NO_ENTRY_SIGNAL": "최근 진입 Signal 없음",
        "CHART_OR_MARKET_INCOMPLETE": "종목 또는 benchmark 차트 불충분",
    }
    if item.code in labels:
        return labels[item.code]
    direction_suffixes = {
        "_DIRECTION_RISING": "방향 상승",
        "_DIRECTION_FALLING": "방향 하락",
        "_DIRECTION_FLAT": "방향 횟보",
        "_DIRECTION_UNKNOWN": "방향 확인 불가",
    }
    for suffix, direction in direction_suffixes.items():
        if item.code.endswith(suffix):
            base = item.code[: -len(suffix)]
            indicator = {
                "SMA_50_SLOPE": "SMA50 기울기",
                "SMA_150_SLOPE": "SMA150 기울기",
                "SMA_200_SLOPE": "SMA200 기울기",
                "cRSI": "cRSI",
                "MACD": "MACD",
                "SUPERTREND": "Supertrend",
            }.get(base, base.replace("_", " "))
            return f"{indicator} {direction}"
    return item.message


def _opportunity_reason(opportunity) -> str:
    status = opportunity.status
    extension = opportunity.extension_pct
    threshold = next(
        (
            item.reference_value
            for item in opportunity.evidence
            if item.code in {"ENTRY_WITHIN_EXTENSION", "ENTRY_WATCH"}
            and item.reference_value is not None
        ),
        None,
    )
    if status is EntryOpportunityStatus.ALLOW:
        if extension is not None and threshold is not None:
            return (
                f"상승장·구조 유효, 확장 {extension * 100:+.1f}%가 "
                f"허용 상한 {threshold * 100:+.1f}% 이내"
            )
        return "상승장·구조 유효, 진입 조건 충족"
    if status is EntryOpportunityStatus.WATCH:
        if (
            opportunity.market_regime == "bull"
            and opportunity.structure_status.value == "valid"
            and extension is not None
            and threshold is not None
            and float(extension) > threshold
        ):
            return (
                f"상승장·구조 유효, 확장 {extension * 100:+.1f}%가 "
                f"허용 상한 {threshold * 100:+.1f}% 초과"
            )
        return f"진입 조건 대기 — 시장={opportunity.market_regime or 'unknown'}, 구조={opportunity.structure_status.value}"
    if status is EntryOpportunityStatus.BLOCK:
        return f"시장 국면 {opportunity.market_regime or 'unknown'}에서 신규 진입 차단"
    if status is EntryOpportunityStatus.INVALIDATED:
        if any(item.code == "BREAKOUT_ATR_INVALIDATED" for item in opportunity.evidence):
            multiplier = next(
                item.observed_value
                for item in opportunity.evidence
                if item.code == "BREAKOUT_ATR_MULTIPLIER"
            )
            return f"종가가 Signal 당시 돌파선 − {multiplier:.1f} × ATR(14) 이하로 하락하여 진입 허가 취소"
        code = opportunity.invalidated_by.code if opportunity.invalidated_by else "unknown"
        return f"{code} Signal로 기존 진입 기회 무효화"
    if status is EntryOpportunityStatus.EXPIRED:
        age = (
            f"{opportunity.age_bars}거래일 경과"
            if opportunity.age_bars is not None
            else "유효기간 경과"
        )
        return f"Signal 후 {age}로 진입 기회 만료"
    if status is EntryOpportunityStatus.NO_RECENT_SIGNAL:
        return "최근 진입 Signal이 없음"
    code = opportunity.evidence[0].code if opportunity.evidence else "unknown"
    return f"필요 입력 또는 Signal 정합성을 확인할 수 없음 ({code})"


def _score_history_lines(analysis: AnalysisStrategyResult) -> list[str]:
    history = list(getattr(analysis, "score_history", ())[-5:])
    if not history:
        return ["- 없음 또는 평가 불가"]
    lines = []
    previous_score = None
    for point in history:
        delta = (
            "" if previous_score is None else f" (전일 {point.adjusted_score - previous_score:+d})"
        )
        lines.append(
            f"- {point.date}: {point.adjusted_score}점{delta} — {point.verdict_action}"
            f" (raw {point.component_raw_total}, 종가 {point.close:g})"
        )
        lines.append(f"  - 이유: {point.one_line_reason}")
        if point.driver_components:
            lines.append(f"  - 주요 구성: {', '.join(point.driver_components)}")
        if point.change_drivers:
            lines.append(f"  - 변화: {', '.join(point.change_drivers)}")
        if point.events:
            lines.append(f"  - 이벤트: {', '.join(point.events)}")
        if point.cautions:
            lines.append(f"  - 주의: {', '.join(point.cautions)}")
        if point.new_entry_allowed is not None:
            lines.append(f"  - 신규진입: {'가능' if point.new_entry_allowed else '대기'}")
        previous_score = point.adjusted_score
    warning = getattr(analysis, "score_history_warning", None)
    if warning:
        lines.append(f"- 경고: {warning}")
    return lines

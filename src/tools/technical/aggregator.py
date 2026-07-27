from dataclasses import dataclass, field

from src.tools.technical.models import (
    AggregationTraceEntry,
    ComponentSignal,
    MarketContext,
    TechnicalVerdict,
)


@dataclass
class ScoreAggregationResult:
    component_raw_total: int
    adjusted_score: int
    technical_verdict: TechnicalVerdict
    aggregation_trace: list[AggregationTraceEntry] = field(default_factory=list)


class ScoreAggregator:
    def aggregate(
        self,
        components: dict[str, dict],
        context: MarketContext,
    ) -> ScoreAggregationResult:
        raw_total = sum(int(component.get("score", 0)) for component in components.values())
        adjusted = raw_total
        trace: list[AggregationTraceEntry] = []
        metadata = _collect_metadata(components)
        reasons = _build_reasons(metadata, context, raw_total)
        cautions: list[str] = []
        new_entry_allowed = True
        forced_action: str | None = None

        if _has_volume_backed_breakdown(metadata, context):
            before = adjusted
            adjusted = min(adjusted, -40)
            forced_action = "avoid"
            new_entry_allowed = False
            trace.append(
                AggregationTraceEntry(
                    rule="volume_backed_breakdown_override",
                    before=before,
                    after=adjusted,
                    reason="거래량 동반 breakdown",
                )
            )
            cautions.append("거래량이 동반된 이탈로 신규 진입 금지")
        elif context.supertrend_sell_transition:
            before = adjusted
            adjusted = min(adjusted, -25)
            forced_action = "reduce"
            new_entry_allowed = False
            trace.append(
                AggregationTraceEntry(
                    rule="supertrend_sell_override",
                    before=before,
                    after=adjusted,
                    reason="Supertrend 매도 전환",
                )
            )
            cautions.append("Supertrend가 매도 전환")

        if context.is_downtrend and _has_bullish_reversal(metadata):
            before = adjusted
            adjusted = min(adjusted, 35)
            new_entry_allowed = False
            trace.append(
                AggregationTraceEntry(
                    rule="downtrend_reversal_cap",
                    before=before,
                    after=adjusted,
                    reason="하락 추세의 반전 신호는 watch로 제한",
                )
            )
            cautions.append("하락 추세의 반전 신호라 확인 전 신규 진입 제한")

        if context.is_overextended:
            before = adjusted
            adjusted -= 15
            new_entry_allowed = False
            trace.append(
                AggregationTraceEntry(
                    rule="overextended_penalty",
                    before=before,
                    after=adjusted,
                    reason="단기 과열로 신규 진입 제한",
                )
            )
            cautions.append("추세는 유지돼도 단기 과열 구간")

        action, entry_mode = _choose_action(
            adjusted=adjusted,
            context=context,
            metadata=metadata,
            forced_action=forced_action,
            new_entry_allowed=new_entry_allowed,
        )
        reasons = _prioritize_action_reasons(action, reasons, cautions, adjusted)
        if action in {"hold", "watch", "reduce", "avoid"}:
            new_entry_allowed = False

        verdict = TechnicalVerdict(
            action=action,
            entry_mode=entry_mode,
            confidence=_confidence(adjusted, trace),
            new_entry_allowed=new_entry_allowed,
            reasons=reasons[:5],
            cautions=cautions[:5],
            invalidation_level=context.nearest_support,
        )
        return ScoreAggregationResult(
            component_raw_total=raw_total,
            adjusted_score=adjusted,
            technical_verdict=verdict,
            aggregation_trace=trace,
        )


def _collect_metadata(components: dict[str, dict]) -> list[ComponentSignal]:
    collected: list[ComponentSignal] = []
    for component in components.values():
        for item in component.get("signal_metadata", []):
            if isinstance(item, ComponentSignal):
                collected.append(item)
            elif isinstance(item, dict):
                collected.append(ComponentSignal(**item))
    return collected


def _has_bullish_reversal(metadata: list[ComponentSignal]) -> bool:
    return any(signal.signal_type == "reversal" and signal.bias == "bullish" for signal in metadata)


def _has_volume_backed_breakdown(
    metadata: list[ComponentSignal],
    context: MarketContext,
) -> bool:
    return (
        context.is_breakdown
        and context.volume_ratio_20d is not None
        and context.volume_ratio_20d >= 1.3
        and any(
            signal.signal_type == "breakdown" and signal.severity == "high" for signal in metadata
        )
    )


def _has_entry_signal(metadata: list[ComponentSignal], signal_type: str) -> bool:
    return any(
        signal.entry_eligible and signal.intent == "entry" and signal.signal_type == signal_type
        for signal in metadata
    )


def _choose_action(
    *,
    adjusted: int,
    context: MarketContext,
    metadata: list[ComponentSignal],
    forced_action: str | None,
    new_entry_allowed: bool,
) -> tuple[str, str]:
    if forced_action is not None:
        return forced_action, "risk_override"
    if adjusted < -25:
        return "avoid", "risk_override"
    if adjusted < 0:
        return "reduce", "risk_control"
    if not new_entry_allowed and adjusted >= 45:
        return "hold", "extended_hold"
    if adjusted >= 75 and new_entry_allowed and _has_entry_signal(metadata, "breakout"):
        return "buy", "breakout_entry"
    if (
        adjusted >= 55
        and new_entry_allowed
        and not context.is_downtrend
        and (_has_entry_signal(metadata, "pullback") or _is_contextual_pullback_add(context))
    ):
        return "add", "pullback_add"
    if adjusted >= 40 and context.is_uptrend:
        return "hold", "trend_hold"
    return "watch", "confirmation_needed"


def _is_contextual_pullback_add(context: MarketContext) -> bool:
    if context.distance_from_20d_high_pct is None or context.ret_10d is None:
        return False
    return (
        not context.is_downtrend
        and context.close_above_sma20
        and context.supertrend_direction == 1
        and -8 <= context.distance_from_20d_high_pct <= -2
        and context.ret_10d > 0
        and not context.is_overextended
        and not context.is_breakdown
    )


def _confidence(adjusted: int, trace: list[AggregationTraceEntry]) -> str:
    if abs(adjusted) >= 55 and len(trace) <= 1:
        return "high"
    if abs(adjusted) >= 30:
        return "medium"
    return "low"


def _build_reasons(
    metadata: list[ComponentSignal],
    context: MarketContext,
    raw_total: int,
) -> list[str]:
    reasons: list[str] = []
    if context.is_uptrend:
        reasons.append("가격이 주요 이동평균 위에서 상승 추세를 유지")
    if context.volume_ratio_20d is not None and context.volume_ratio_20d >= 1.5:
        reasons.append(f"거래량이 20일 평균 대비 {context.volume_ratio_20d:.1f}배")
    for signal in metadata:
        if signal.reason and signal.bias == "bullish" and len(reasons) < 5:
            reasons.append(signal.reason)
    if not reasons:
        reasons.append(f"component raw total {raw_total}점")
    return reasons


def _prioritize_action_reasons(
    action: str,
    reasons: list[str],
    cautions: list[str],
    adjusted: int,
) -> list[str]:
    if action not in {"watch", "reduce", "avoid"}:
        return reasons

    action_reasons = [_normalize_caution_as_reason(caution) for caution in cautions]
    fallback = _negative_action_reason(action, adjusted)
    if fallback is not None:
        action_reasons.append(fallback)

    if not action_reasons:
        return reasons

    prioritized: list[str] = []
    for reason in [*action_reasons, *reasons]:
        if reason not in prioritized:
            prioritized.append(reason)
    return prioritized


def _normalize_caution_as_reason(caution: str) -> str:
    if caution.startswith("하락 추세의 반전 신호"):
        return "하락 추세의 반전 신호라 확인 필요"
    return caution


def _negative_action_reason(action: str, adjusted: int) -> str | None:
    if action == "avoid" and adjusted < -25:
        return "조정 점수가 -25점 미만으로 리스크 우위"
    if action == "reduce" and adjusted < 0:
        return "조정 점수가 0점 미만으로 리스크 관리 필요"
    return None

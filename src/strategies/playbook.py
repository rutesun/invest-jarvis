"""Chart-only adapter for the existing Playbook gate and exit rules."""

from __future__ import annotations

from types import SimpleNamespace

from src.strategies.models import (
    ChartBundle,
    EntryIntent,
    EntryVerdict,
    ExitIntent,
    ExitVerdict,
    StrategyVerdict,
)
from src.tools.playbook.accumulation import analyze_accumulation
from src.tools.playbook.common import (
    chart_frame as _frame,
)
from src.tools.playbook.common import (
    common_analysis_for_bundle,
    playbook_evidence,
    stock_is_ready,
    validate_playbook_scope,
)
from src.tools.playbook.exit_rules import evaluate_exit
from src.tools.playbook.gate import evaluate_gate
from src.tools.playbook.market_regime import assess_market_regime
from src.tools.playbook.relative_strength import _SLOPE_DAYS, compute_relative_strength
from src.tools.playbook.vcp import detect_vcp_breakout
from src.tools.technical.chart_analysis.models import ChartAnalysis, FactRef, FactSelection
from src.tools.technical.context import compatibility_rule_request, matches_common_request
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance


_ENTRY_RULES = frozenset(
    {"chart.market.regime", "chart.rs", "chart.stage2.minervini", "chart.vcp.playbook"}
)


def _gate_fact_usage(gate):
    consumed = dict.fromkeys(_ENTRY_RULES, "PLAYBOOK_ENTRY_CONSUMED")
    consumed["chart.rs"] = "PLAYBOOK_ENTRY_EXIT_CONSUMED"
    rejected = {}
    veto = None
    for check in gate.checklist:
        if veto is not None:
            if check.name == "C":
                consumed["chart.rs"] = f"PLAYBOOK_EXIT_CONSUMED_GATE_NOT_REACHED_{veto}_VETO"
            rule = {"B": "chart.stage2.minervini", "E": "chart.vcp.playbook"}.get(check.name)
            if rule is not None:
                consumed.pop(rule)
                rejected[rule] = f"PLAYBOOK_GATE_NOT_REACHED_{veto}_VETO"
        elif check.met is False or check.met is None:
            veto = check.name
    return consumed, rejected


def _fact_selections(analysis, consumed_rules, rejected_rules, rejection_reason):
    selections = []
    for item in analysis.items:
        known = item.rule_id in _ENTRY_RULES | {"chart.accumulation.days"}
        matches = known and matches_common_request(item, compatibility_rule_request(item.rule_id))
        consumed = matches and item.rule_id in consumed_rules
        if known and not matches:
            reason = "PLAYBOOK_FACT_VARIANT_NOT_SELECTED"
        elif consumed and item.state == "UNAVAILABLE":
            reason = "PLAYBOOK_FACT_" + item.evidence.get("reasons", ("UNAVAILABLE",))[0]
        elif consumed:
            reason = consumed_rules[item.rule_id]
        elif item.rule_id in rejected_rules:
            reason = rejected_rules[item.rule_id]
        elif item.rule_id in _ENTRY_RULES | {"chart.accumulation.days"}:
            reason = rejection_reason
        else:
            reason = "PLAYBOOK_RULE_NOT_USED"
        selections.append(
            FactSelection(
                FactRef(analysis.analysis_id, item.id),
                consumed and item.state != "UNAVAILABLE",
                reason,
            )
        )
    return tuple(selections)


def _reason(code: str, message: str) -> Evidence:
    return Evidence(
        code=code,
        message=message,
        observed_value=None,
        reference_value=None,
        importance=Importance.MEDIUM,
        source="PLAYBOOK_V1",
    )


class PlaybookStrategy:
    strategy_id = "PLAYBOOK_V1"
    strategy_version = "PLAYBOOK_V1_V1"

    def evaluate(
        self, bundle: ChartBundle, *, common_analysis: ChartAnalysis | None = None
    ) -> StrategyVerdict:
        instrument = bundle.instrument
        stock_ready = stock_is_ready(bundle)
        if not stock_ready:
            if common_analysis is not None:
                validate_playbook_scope(bundle, _frame(instrument), common_analysis)
            reason = [_reason("insufficient_chart", "Complete 221-bar instrument chart required")]
            return self._verdict(
                bundle,
                EntryIntent.NOT_EVALUATED,
                ExitIntent.NOT_EVALUATED,
                DataStatus.INSUFFICIENT_DATA,
                DataStatus.INSUFFICIENT_DATA,
                reason,
                reason,
                common_analysis=common_analysis,
            )

        stock = IndicatorCalculator().calculate(_frame(instrument))
        if common_analysis is None:
            common_analysis = common_analysis_for_bundle(bundle, stock_frame=stock)
        else:
            validate_playbook_scope(bundle, stock, common_analysis)
        common_kwargs = {"common_analysis": common_analysis}
        last = stock.iloc[-1]
        swing_lows = stock["Swing_Low"].dropna()
        snapshot = SimpleNamespace(
            high_52w=float(last["High_52w"]),
            swing_low=float(swing_lows.iloc[-1]) if not swing_lows.empty else None,
        )
        accumulation = analyze_accumulation(stock, **common_kwargs)
        market_ready = (
            bundle.market is not None
            and bundle.market_ticker is not None
            and bundle.market.coverage.complete
            and bundle.market.coverage.truncation_reason is None
            and len(bundle.market.bars) >= 221
            and bundle.market.bars[-1].session_date == bundle.as_of
        )
        common_sessions = (
            len(
                {bar.session_date for bar in instrument.bars}
                & {bar.session_date for bar in bundle.market.bars}
            )
            if market_ready
            else 0
        )
        rs_ready = market_ready and common_sessions >= _SLOPE_DAYS + 1
        consumed_rules = {"chart.accumulation.days": "PLAYBOOK_EXIT_CONSUMED"}
        rejected_rules = {}
        relative_strength = None
        if rs_ready:
            market = _frame(bundle.market)
            regime = assess_market_regime(market, bundle.market_ticker, **common_kwargs)
            relative_strength = compute_relative_strength(
                stock, market, bundle.market_ticker, **common_kwargs
            )
            stage2 = playbook_evidence(stock, common_analysis, "chart.stage2.minervini")["metrics"]
            gate = evaluate_gate(
                market_regime=regime,
                is_stage2=stage2.get("is_stage2"),
                relative_strength=relative_strength,
                sector_strength=None,
                vcp=detect_vcp_breakout(stock, **common_kwargs),
                canslim=None,
                flow=None,
                chart_only=True,
            )
            entry_consumed, rejected_rules = _gate_fact_usage(gate)
            consumed_rules.update(entry_consumed)
            entry = EntryIntent.ALLOW if gate.passed else EntryIntent.BLOCK
            entry_status = DataStatus.COMPLETE
            entry_reasons = [_reason("gate", gate.veto_reason or "Chart gate passed")]
        else:
            entry = EntryIntent.NOT_EVALUATED
            entry_status = DataStatus.INSUFFICIENT_DATA
            entry_reasons = [
                _reason(
                    "insufficient_rs_chart" if market_ready else "missing_market_chart",
                    "At least 21 common stock/market sessions required"
                    if market_ready
                    else "Complete market chart required",
                )
            ]

        exit_result = evaluate_exit(
            df=stock,
            snapshot=snapshot,
            relative_strength=relative_strength,
            accumulation=accumulation,
        )
        exit_intent = {
            "hold": ExitIntent.HOLD,
            "reduce": ExitIntent.REDUCE,
            "liquidate": ExitIntent.EXIT,
        }[exit_result.action]
        exit_status = DataStatus.COMPLETE if rs_ready else DataStatus.PARTIAL
        exit_reasons = [_reason(signal.code, signal.detail) for signal in exit_result.signals]
        if not rs_ready:
            exit_reasons.extend(entry_reasons)
        return self._verdict(
            bundle,
            entry,
            exit_intent,
            entry_status,
            exit_status,
            entry_reasons,
            exit_reasons,
            common_analysis=common_analysis,
            consumed_rules=consumed_rules,
            rejected_rules=rejected_rules,
            rejection_reason="PLAYBOOK_COMMON_SESSIONS_SHORT"
            if market_ready
            else "PLAYBOOK_MARKET_NOT_READY",
        )

    def _verdict(
        self,
        bundle,
        entry,
        exit_,
        entry_status,
        exit_status,
        entry_reasons,
        exit_reasons,
        *,
        common_analysis=None,
        consumed_rules=None,
        rejected_rules=None,
        rejection_reason="PLAYBOOK_INSTRUMENT_NOT_READY",
    ) -> StrategyVerdict:
        selections = None
        if common_analysis is not None:
            selections = _fact_selections(
                common_analysis, consumed_rules or {}, rejected_rules or {}, rejection_reason
            )
        return StrategyVerdict(
            chart_analysis_id=common_analysis.analysis_id if common_analysis is not None else None,
            fact_selections=selections,
            common_analyses=(common_analysis,) if common_analysis is not None else (),
            verdict_schema_version="1",
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            ticker=bundle.ticker,
            as_of=bundle.as_of,
            entry=EntryVerdict(
                intent=entry, opportunity=None, data_status=entry_status, reasons=entry_reasons
            ),
            exit=ExitVerdict(intent=exit_, data_status=exit_status, reasons=exit_reasons),
            events=[],
            strategy_state=None,
        )

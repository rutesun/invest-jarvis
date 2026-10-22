"""Append-only observed decision snapshots; never read by Strategy or Planner."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.storage.canonical import canonical_bytes, canonical_hash


if TYPE_CHECKING:
    from src.strategies.models import ChartBundle
    from src.strategies.runner import StrategyRunBundle


class EntryShadowJsonlRecorder:
    """Record only each run's represented source/day, without historical backfill.

    decision_key groups source/day and policy/parameter versions across finalities.
    snapshot_key identifies identical payloads (including finality, chart and pipeline),
    excluding recorded_at. Repeated calls intentionally append; consumers may dedupe
    by snapshot_key, then select FINAL within a decision_key without discarding other
    policy versions. Neither key is a database upsert or an execution authorization.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def record(self, run: StrategyRunBundle, bundle: ChartBundle, *, pipeline: str) -> None:
        for signals in getattr(run, "signal_bundles", ()):
            opportunity = signals.entry_opportunity
            source = opportunity.entry_signal
            shadow = signals.entry_shadow
            close = bundle.instrument.bars[-1].close
            reference = opportunity.execution_reference_price
            signal_price = opportunity.signal_price
            identity = {
                "ticker": run.ticker,
                "strategy_id": signals.strategy_id,
                "strategy_version": signals.strategy_version,
                "source_id": source.signal_id if source else None,
                "evaluation_as_of": opportunity.evaluation_as_of,
                "production_policy_version": opportunity.policy_version,
                "production_parameter_set_version": signals.parameter_set_version,
                "production_parameter_fingerprint": signals.parameter_fingerprint,
                "shadow_policy_version": shadow.policy_version if shadow else None,
                "shadow_parameter_fingerprint": shadow.parameter_fingerprint if shadow else None,
            }
            row = {
                "schema_version": "ENTRY_SHADOW_SNAPSHOT_V2",
                **identity,
                "decision_key": canonical_hash("jarvis:entry-shadow-decision:v1", identity),
                "pipeline": pipeline,
                "evaluation_finality": opportunity.finality,
                "chart_finality": bundle.instrument.bars[-1].finality,
                "source_type": source.code if source else None,
                "source_date": source.occurred_on if source else None,
                "source_age_bars": opportunity.age_bars,
                "source_finality": source.finality if source else None,
                "source_strategy_version": source.strategy_version if source else None,
                "source_parameter_set_version": source.parameter_set_version if source else None,
                "source_parameter_fingerprint": source.parameter_fingerprint if source else None,
                "source_evidence": source.evidence if source else [],
                "production_status": opportunity.status,
                "production_reason": "; ".join(item.message for item in opportunity.evidence),
                "production_evidence": opportunity.evidence,
                "production_data_status": signals.data_status,
                "terminal_on": opportunity.terminal_on,
                "terminal_finality": opportunity.terminal_finality,
                "invalidated_by_id": (
                    opportunity.invalidated_by.signal_id if opportunity.invalidated_by else None
                ),
                "anchors": opportunity.anchors,
                "signal_price": signal_price,
                "current_close": close,
                "market_ticker": bundle.market_ticker,
                "market_regime": opportunity.market_regime,
                "structure_status": opportunity.structure_status,
                "extension_pct": opportunity.extension_pct,
                "execution_reference_price": reference,
                "execution_reference_basis": (
                    "signal_close_estimate"
                    if reference is not None and opportunity.age_bars == 0
                    else "next_open_actual"
                    if reference is not None
                    and opportunity.age_bars is not None
                    and opportunity.age_bars > 0
                    else None
                ),
                # Opening gap from source close; not a future return or a fill.
                "execution_gap_pct": (
                    reference / signal_price - 1
                    if opportunity.age_bars is not None
                    and opportunity.age_bars > 0
                    and reference is not None
                    and reference > 0
                    and signal_price is not None
                    and signal_price > 0
                    else None
                ),
                "current_to_execution_reference_pct": (
                    close / reference - 1 if reference is not None and reference > 0 else None
                ),
                "risk_level": shadow.risk_level if shadow else None,
                "risk_flags": shadow.risk_flags if shadow else [],
                "shadow_finality": shadow.finality if shadow else None,
                "shadow_evaluation_as_of": shadow.evaluation_as_of if shadow else None,
                "shadow_data_status": shadow.data_status if shadow else "not_evaluated",
                "shadow_reason": shadow.reason if shadow else "DISABLED_OR_UNAVAILABLE",
                "shadow_anchors": shadow.anchors if shadow else None,
                "breakout_states": shadow.breakout_states if shadow else {},
                "pullback_states": shadow.pullback_states if shadow else {},
                "diagnostic_errors": signals.diagnostic_errors,
                "observation_history": signals.observation_history,
                "observations_enabled": signals.observations_enabled,
                "observation_parameters": signals.observation_parameters,
                "up_cycle": signals.up_cycle,
                "support_tests": signals.support_tests,
                "pullback_policy_inactive_reason": signals.pullback_policy_inactive_reason,
                "input_data_hash": run.input_data_hash,
                "strategy_input_hash": run.strategy_input_hashes.get(signals.strategy_id),
                "chart_profile_version": run.chart_profile_version,
                "chart_bundle_hash": run.chart_bundle_hash,
            }
            row["snapshot_key"] = canonical_hash("jarvis:entry-shadow-snapshot:v2", row)
            row["recorded_at"] = datetime.now(UTC)
            line = canonical_bytes(row) + b"\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("ab") as stream:
                stream.write(line)

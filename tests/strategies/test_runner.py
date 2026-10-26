"""Production strategy runner identities and failure slots."""

from datetime import date
from types import SimpleNamespace

import pytest

from src.storage.canonical import canonical_bytes
from src.strategies.runner import StrategyRunBundle, StrategyRunner
from src.tools.technical.models import TechnicalVerdict
from src.tools.technical.scorecard_models import (
    DataStatus,
    ScoreDimension,
    TechnicalScorecard,
)
from tests.strategies.test_playbook import _bundle


def _legacy_result(
    *,
    with_scorecard=True,
    action="buy",
    scorecard_ticker="AAPL",
    scorecard_as_of=date(2025, 12, 30),
):
    dimension = ScoreDimension(
        code="trend",
        score=50,
        raw_state_points=0,
        minimum_points=0,
        maximum_points=100,
        calculation_version="test",
        data_status=DataStatus.COMPLETE,
        coverage_pct=100,
        metrics={},
        observations=[],
        score_contributions=[],
    )
    scorecard = TechnicalScorecard(
        version="test",
        ticker=scorecard_ticker,
        as_of=scorecard_as_of,
        trend=dimension,
        structure=dimension.model_copy(update={"code": "structure"}),
        momentum=dimension.model_copy(update={"code": "momentum"}),
        demand=dimension.model_copy(update={"code": "demand"}),
        safety=dimension.model_copy(update={"code": "safety"}),
        legacy_raw_total=None,
        legacy_adjusted_score=None,
    )
    return SimpleNamespace(
        technical_verdict=TechnicalVerdict(
            action=action,
            entry_mode="test",
            confidence="medium",
            new_entry_allowed=True,
            reasons=["trend confirmed"],
            cautions=[],
        ),
        scorecard=scorecard if with_scorecard else None,
    )


def test_production_strategies_have_fixed_order():
    assert StrategyRunner.production_strategy_ids == (
        "TECHNICAL_LEGACY",
        "PLAYBOOK_V1",
        "SWING_W150",
    )


def test_explicit_swing_parameters_reach_production_runner():
    from src.strategies.swing_w150.parameters import SupportCycleParameters, SwingW150ParametersV2

    params = SwingW150ParametersV2(
        support_cycle=SupportCycleParameters(
            normal_failure_closes=2,
            immediate_failure_volume_ratio=2,
            immediate_failure_close_location=0.25,
            support_break_buffer_atr=0,
            restart_mode="D",
        )
    )
    default = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    selected = StrategyRunner(swing_parameters=params).run(
        _bundle(), legacy_result=_legacy_result()
    )
    assert not selected.errors
    assert selected.signal_bundles[0].parameter_fingerprint == params.parameter_fingerprint
    assert selected.signal_bundles[0].up_cycle is not None
    assert default.signal_bundles[0].up_cycle is None
    assert "UNRESOLVED" in default.signal_bundles[0].pullback_policy_inactive_reason
    assert selected.verdicts == default.verdicts
    assert selected.scorecard == default.scorecard
    assert (
        selected.strategy_input_hashes["SWING_W150"] != default.strategy_input_hashes["SWING_W150"]
    )


def test_production_registry_is_single_source_for_ids_and_versions():
    runner = StrategyRunner()
    registry = runner.production_strategy_registry()
    result = runner.run(_bundle(), legacy_result=_legacy_result())

    assert tuple(registry) == StrategyRunner.production_strategy_ids
    assert registry == result.strategy_versions
    assert registry["SWING_W150"] == "SWING_W150_V2"


def test_runner_produces_stable_verdicts_and_chart_identity_across_cache():
    bundle = _bundle()
    legacy = _legacy_result()
    cold = StrategyRunner().run(bundle, legacy_result=legacy)
    warm = StrategyRunner(cache={"unused": cold}).run(bundle, legacy_result=legacy)
    assert [verdict.strategy_id for verdict in cold.verdicts] == ["TECHNICAL_LEGACY", "PLAYBOOK_V1"]
    assert canonical_bytes(cold.verdicts) == canonical_bytes(warm.verdicts)
    assert cold.strategy_input_hashes == warm.strategy_input_hashes
    assert cold.chart_bundle_hash == bundle.bundle_hash
    assert [bundle.strategy_version for bundle in cold.signal_bundles] == ["SWING_W150_V2"]
    assert canonical_bytes(cold.signal_bundles) == canonical_bytes(warm.signal_bundles)


def test_signal_bundles_default_for_legacy_constructor():
    result = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    legacy_values = result.model_dump(exclude={"signal_bundles"})

    restored = StrategyRunBundle(**legacy_values)

    assert restored.signal_bundles == []


def test_swing_input_hash_includes_parameter_fingerprint_and_preserves_legacy_hashes():
    from src.storage.canonical import strategy_input_hash
    from src.strategies.swing_w150.parameters import SwingW150Parameters

    bundle = _bundle()
    result = StrategyRunner().run(bundle, legacy_result=_legacy_result())

    assert result.strategy_input_hashes["SWING_W150"] == strategy_input_hash(
        bundle,
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_fingerprint=SwingW150Parameters().parameter_fingerprint,
    )
    for strategy_id in ("TECHNICAL_LEGACY", "PLAYBOOK_V1"):
        assert result.strategy_input_hashes[strategy_id] == strategy_input_hash(
            bundle,
            strategy_id=strategy_id,
            strategy_version=result.strategy_versions[strategy_id],
        )


def test_legacy_opinion_cannot_change_chart_strategy_verdict():
    bundle = _bundle()
    buy = StrategyRunner().run(bundle, legacy_result=_legacy_result(action="buy"))
    avoid = StrategyRunner().run(bundle, legacy_result=_legacy_result(action="avoid"))
    assert canonical_bytes(buy.verdicts) == canonical_bytes(avoid.verdicts)
    assert canonical_bytes(buy.signal_bundles) == canonical_bytes(avoid.signal_bundles)
    assert buy.strategy_input_hashes == avoid.strategy_input_hashes


def test_runner_keeps_error_slot_when_a_strategy_fails(monkeypatch):
    from src.strategies.swing_w150.adapter import SwingW150SignalStrategy

    def fail(_self, _bundle):
        raise RuntimeError("sample failure")

    monkeypatch.setattr(SwingW150SignalStrategy, "evaluate_signals", fail)
    result = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    assert len(result.verdicts) == 2
    failed = result.signal_bundles[0]
    assert failed.strategy_id == "SWING_W150"
    assert failed.data_status is DataStatus.ERROR
    assert failed.entry_opportunity.status.value == "not_evaluated"
    assert failed.entry_opportunity.evidence[0].code == "strategy_error"
    assert "sample failure" in failed.entry_opportunity.evidence[0].message
    assert result.data_status is DataStatus.ERROR


def test_shadow_toggle_preserves_entire_production_run_and_input_hashes():
    enabled = StrategyRunner(shadow_enabled=True).run(_bundle(), legacy_result=_legacy_result())
    disabled = StrategyRunner(shadow_enabled=False).run(_bundle(), legacy_result=_legacy_result())
    assert enabled.signal_bundles[0].entry_shadow is not None
    assert disabled.signal_bundles[0].entry_shadow is None
    for result in (enabled, disabled):
        for signals in result.signal_bundles:
            signals.entry_shadow = None
    assert enabled.model_dump(mode="json") == disabled.model_dump(mode="json")


def test_shadow_error_is_separate_from_production_error_and_status(monkeypatch):
    from src.strategies.swing_w150 import adapter

    baseline = StrategyRunner(shadow_enabled=False).run(_bundle(), legacy_result=_legacy_result())

    def fail(*_args, **_kwargs):
        raise RuntimeError("diagnostic unavailable")

    monkeypatch.setattr(adapter, "evaluate_entry_shadow", fail, raising=False)
    result = StrategyRunner().run(_bundle(), legacy_result=_legacy_result())
    assert result.errors == baseline.errors
    assert result.data_status == baseline.data_status
    assert result.input_data_hash == baseline.input_data_hash
    assert result.strategy_input_hashes == baseline.strategy_input_hashes
    assert "diagnostic unavailable" in result.diagnostic_errors[0]
    signals = result.signal_bundles[0]
    assert signals.entry_shadow is None
    assert signals.entry_opportunity == baseline.signal_bundles[0].entry_opportunity
    assert signals.signal_history == baseline.signal_bundles[0].signal_history
    assert signals.observation_history == baseline.signal_bundles[0].observation_history


@pytest.mark.parametrize(
    ("result_options", "message"),
    [
        ({"with_scorecard": False}, "scorecard is required"),
        ({"scorecard_ticker": "MSFT"}, "scorecard ticker"),
        ({"scorecard_as_of": date(2025, 12, 29)}, "scorecard as_of"),
    ],
)
def test_runner_rejects_invalid_scorecard_at_boundary(result_options, message):
    with pytest.raises(ValueError, match=message):
        StrategyRunner().run(_bundle(), legacy_result=_legacy_result(**result_options))


def test_observation_toggle_and_parameters_preserve_production_run_identity():
    from dataclasses import asdict

    from src.strategies.observations.parameters import ObservationParameters

    parameters = ObservationParameters(
        break_buffer_atr=0, reclaim_buffer_atr=0, up_volume_ratio=0.5
    )
    off = StrategyRunner(observations_enabled=False).run(_bundle(), legacy_result=_legacy_result())
    on = StrategyRunner(observation_parameters=parameters).run(
        _bundle(), legacy_result=_legacy_result()
    )
    assert off.signal_bundles[0].observations_enabled is False
    assert on.signal_bundles[0].observations_enabled is True
    assert on.signal_bundles[0].observation_parameters == asdict(parameters)
    assert off.signal_bundles[0].observation_parameters != asdict(parameters)
    assert any(item.kind == "EVIDENCE" for item in on.signal_bundles[0].observation_history)
    for result in [off, on]:
        for signals in result.signal_bundles:
            signals.observation_history = [
                item for item in signals.observation_history if item.kind == "SETUP"
            ]
    outputs = [result.model_dump(mode="json") for result in (on, off)]
    for output in outputs:
        for signals in output["signal_bundles"]:
            signals.pop("observations_enabled")
            signals.pop("observation_parameters")
    assert outputs[0] == outputs[1]

import json
from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.storage.canonical import canonical_bytes
from src.tools.technical.scorecard_models import Evidence, Importance


def _observation(**context):
    from src.strategies.models import ObservationCode, ObservationStatus, SignalFinality
    from src.strategies.observations import make_observation
    from src.strategies.observations.parameters import ObservationParameters

    return make_observation(
        ticker="AAPL",
        code=context.pop("code", ObservationCode.SUPPORT_RECLAIM),
        origin=context.pop("origin", date(2026, 10, 1)),
        params=context.pop("params", ObservationParameters()),
        status=context.pop("status", ObservationStatus.RESOLVED),
        finality=context.pop("finality", SignalFinality.FINAL),
        evidence=[
            Evidence(
                code="support",
                message="support",
                importance=Importance.HIGH,
                observed_value=None,
                reference_value=None,
                source="OBSERVATION_V1",
            )
        ],
        **context,
    )


def test_observation_identity_distinguishes_anchors_and_replays():
    sma50 = _observation(anchor_id="sma50", anchor_type="SMA50")
    sma150 = _observation(anchor_id="sma150", anchor_type="SMA150")
    assert sma50.observation_id != sma150.observation_id
    assert (
        sma50.observation_id == _observation(anchor_id="sma50", anchor_type="SMA50").observation_id
    )
    assert (
        sma50.observation_id
        != _observation(
            anchor_id="sma50", anchor_type="SMA50", source_signal_id="new-source"
        ).observation_id
    )
    assert (
        sma50.observation_id
        != _observation(
            anchor_id="sma50", anchor_type="SMA50", origin=date(2026, 10, 2)
        ).observation_id
    )
    assert (
        sma50.observation_id
        == _observation(
            anchor_id="sma50", anchor_type="SMA50", status_as_of=date(2026, 10, 9)
        ).observation_id
    )


def test_scopes_roundtrip_as_sorted_values():
    from src.strategies.models import ObservationScope, StrategyObservationEpisode

    event = _observation()
    expected = frozenset({ObservationScope.ENTRY, ObservationScope.POSITION})
    assert type(event.scopes) is frozenset
    assert event.scopes == expected
    payload = event.model_dump(mode="python")
    assert payload["scopes"] == ["ENTRY", "POSITION"]
    assert all(type(scope) is str for scope in payload["scopes"])
    payload["scopes"] = ["POSITION", "ENTRY", "ENTRY"]
    restored = StrategyObservationEpisode.model_validate(payload)
    assert type(restored.scopes) is frozenset
    assert restored.scopes == expected
    assert all(type(scope) is ObservationScope for scope in restored.scopes)
    assert restored.model_dump(mode="python")["scopes"] == ["ENTRY", "POSITION"]
    assert json.loads(restored.model_dump_json())["scopes"] == ["ENTRY", "POSITION"]
    assert json.loads(canonical_bytes(restored))["scopes"] == ["ENTRY", "POSITION"]
    assert StrategyObservationEpisode.model_validate_json(restored.model_dump_json()) == event
    assert StrategyObservationEpisode.model_validate_json(canonical_bytes(restored)) == event
    for invalid in ("BOTH", "UNKNOWN"):
        with pytest.raises(ValidationError):
            StrategyObservationEpisode.model_validate({**payload, "scopes": [invalid]})


@pytest.mark.parametrize(
    "code,kind,direction,scopes,temporal",
    [
        ("PULLBACK_WATCH", "SETUP", "NEUTRAL", ["ENTRY"], "EPISODE"),
        ("POST_OVERHEAT_RECOVERY_WATCH", "SETUP", "NEUTRAL", ["ENTRY"], "EPISODE"),
        ("HIGHER_LOW", "EVIDENCE", "POSITIVE", ["ENTRY", "POSITION"], "EVENT"),
        ("HIGHER_HIGH", "EVIDENCE", "POSITIVE", ["ENTRY", "POSITION"], "EVENT"),
        ("BREAKOUT_RECLAIM", "EVIDENCE", "POSITIVE", ["ENTRY", "POSITION"], "EVENT"),
        ("SUPPORT_RECLAIM", "EVIDENCE", "POSITIVE", ["ENTRY", "POSITION"], "EVENT"),
        ("VOLUME_CONTRACTION", "EVIDENCE", "POSITIVE", ["ENTRY"], "EPISODE"),
        ("UP_VOLUME_EXPANSION", "EVIDENCE", "POSITIVE", ["ENTRY", "POSITION"], "EVENT"),
        ("MOMENTUM_REACCELERATION", "EVIDENCE", "POSITIVE", ["ENTRY", "POSITION"], "EVENT"),
        ("BREAKOUT_LEVEL_BREACH", "EVIDENCE", "RISK", ["ENTRY", "POSITION"], "EPISODE"),
        ("SUPPORT_BREAK", "EVIDENCE", "RISK", ["ENTRY", "POSITION"], "EPISODE"),
        ("PULLBACK_LOW_BREACH", "EVIDENCE", "RISK", ["ENTRY", "POSITION"], "EPISODE"),
        ("LOWER_HIGH", "EVIDENCE", "RISK", ["ENTRY", "POSITION"], "EVENT"),
        ("LOWER_LOW", "EVIDENCE", "RISK", ["ENTRY", "POSITION"], "EVENT"),
        ("DOWN_VOLUME_EXPANSION", "EVIDENCE", "RISK", ["ENTRY", "POSITION"], "EVENT"),
        ("MOMENTUM_DECELERATION", "EVIDENCE", "RISK", ["ENTRY", "POSITION"], "EPISODE"),
    ],
)
def test_registry_classifies_vocabulary_and_selected_detector_readiness(
    code, kind, direction, scopes, temporal
):
    from src.strategies.models import ObservationCode, ObservationScope
    from src.strategies.observations.registry import OBSERVATION_REGISTRY

    episode = _observation(code=ObservationCode(code))
    assert episode.kind == kind
    assert episode.direction == direction
    assert type(episode.scopes) is frozenset
    assert episode.scopes == frozenset(ObservationScope(scope) for scope in scopes)
    assert episode.temporal_type == temporal
    definition = OBSERVATION_REGISTRY[ObservationCode(code)]
    assert type(definition.scopes) is frozenset
    assert definition.scopes == episode.scopes
    assert definition.start and definition.maintain and definition.end and definition.reentry
    assert definition.detector_validity == (
        "UNRESOLVED"
        if code in {"VOLUME_CONTRACTION", "UP_VOLUME_EXPANSION", "DOWN_VOLUME_EXPANSION"}
        else "IMPLEMENTED"
    )
    assert definition.source_dependency == (
        "REQUIRED"
        if code in {"BREAKOUT_RECLAIM", "BREAKOUT_LEVEL_BREACH", "PULLBACK_LOW_BREACH"}
        else "OPTIONAL"
        if code in {"SUPPORT_RECLAIM", "SUPPORT_BREAK"}
        else "NONE"
    )
    assert definition.anchor_dependency == (
        "REQUIRED"
        if code
        in {
            "PULLBACK_WATCH",
            "BREAKOUT_RECLAIM",
            "SUPPORT_RECLAIM",
            "BREAKOUT_LEVEL_BREACH",
            "SUPPORT_BREAK",
            "PULLBACK_LOW_BREACH",
        }
        else "NONE"
    )
    assert definition.predictive_usefulness == "UNRESOLVED"


def test_unknown_observation_code_and_classification_override_are_rejected():
    with pytest.raises(ValueError):
        _observation(code="OLD_WATCH")
    with pytest.raises((TypeError, ValueError)):
        _observation(direction="RISK")


def test_observation_identity_carries_versions_and_optional_context():
    from src.strategies.observations.parameters import ObservationParameters

    event = _observation(
        anchor_id="frozen-breakout",
        anchor_type="PRIOR_BREAKOUT_LEVEL",
        anchor_origin_on=date(2026, 9, 1),
        anchor_origin_price=Decimal("105"),
        pivot_date=date(2026, 9, 28),
        confirmed_on=date(2026, 10, 1),
        source_terminal=True,
        cycle_id="cycle-1",
    )
    assert event.anchor_origin_price == Decimal("105")
    assert event.source_terminal is True
    assert event.pivot_date < event.confirmed_on
    assert (
        _observation().observation_id
        != _observation(
            params=replace(ObservationParameters(), version="OBSERVATION_PARAMS_CUSTOM")
        ).observation_id
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("up_volume_ratio", 0),
        ("down_volume_ratio", -1),
        ("contraction_ratio", float("nan")),
        ("break_buffer_atr", -0.1),
        ("reclaim_buffer_atr", -0.1),
        ("zone_distance_atr", -0.1),
    ],
)
def test_observation_parameters_reject_invalid_units(field, value):
    from src.strategies.observations.parameters import ObservationParameters

    with pytest.raises(ValueError):
        ObservationParameters(**{field: value})


def test_observation_settings_have_independent_identity_from_production_v1():
    from src.strategies.observations.parameters import ObservationParameters
    from src.strategies.swing_w150.parameters import SwingW150Parameters

    production = SwingW150Parameters()
    params = ObservationParameters()
    assert (
        replace(params, zone_distance_atr=0).parameter_fingerprint != params.parameter_fingerprint
    )
    assert (
        replace(params, up_volume_ratio=1.4).parameter_fingerprint != params.parameter_fingerprint
    )
    assert (
        production.parameter_fingerprint
        == "3dca481189c1263c57ac26544fceb43cb2447e17923f890f3f65a30b0b0342f2"
    )
    assert "support_cycle" not in asdict(production)


@pytest.mark.parametrize(
    "values",
    [
        {"normal_failure_closes": 0},
        {"normal_failure_closes": 1.5},
        {"immediate_failure_volume_ratio": 0, "immediate_failure_close_location": 0.25},
        {"immediate_failure_volume_ratio": 1.5},
        {"immediate_failure_close_location": 0.25},
        {"immediate_failure_volume_ratio": 1.5, "immediate_failure_close_location": 1.1},
        {"support_break_buffer_atr": -1},
    ],
)
def test_support_cycle_schema_rejects_invalid_or_partial_selection(values):
    from src.strategies.swing_w150.parameters import SupportCycleParameters

    with pytest.raises(ValueError):
        SupportCycleParameters(**values)


def test_v2_schema_is_explicit_and_decision_settings_enter_its_fingerprint():
    from src.strategies.swing_w150.parameters import (
        SWING_W150_PARAMETER_REGISTRY,
        SupportCycleParameters,
        SwingW150Parameters,
        SwingW150ParametersV2,
    )

    v2 = SwingW150ParametersV2()
    assert v2.parameter_set_version == "SWING_W150_V2_PARAMS_V2"
    assert v2.support_cycle.normal_failure_closes is None
    changed = replace(v2, support_cycle=SupportCycleParameters(normal_failure_closes=2))
    assert changed.parameter_fingerprint != v2.parameter_fingerprint
    assert type(SWING_W150_PARAMETER_REGISTRY.get("SWING_W150_V2_PARAMS_V1")) is SwingW150Parameters
    with pytest.raises(KeyError):
        SWING_W150_PARAMETER_REGISTRY.get("SWING_W150_V2_PARAMS_V2")


def test_parameter_modes_reject_unknown_values_and_keep_unresolved_distinct_from_zero():
    from src.strategies.observations.parameters import ObservationParameters
    from src.strategies.swing_w150.parameters import SupportCycleParameters

    with pytest.raises(ValueError):
        ObservationParameters(reacceleration_mode="OFF")
    with pytest.raises(ValueError):
        SupportCycleParameters(restart_mode="INITIAL")
    assert ObservationParameters(break_buffer_atr=0).break_buffer_atr == 0
    assert ObservationParameters().break_buffer_atr is None
    assert SupportCycleParameters(support_break_buffer_atr=0).support_break_buffer_atr == 0
    assert SupportCycleParameters().support_break_buffer_atr is None


def test_support_and_cycle_contracts_preserve_origin_and_terminal_context():
    from src.strategies.models import (
        BarFinality,
        ObservationSourceContext,
        SupportAnchor,
        SupportTestState,
        UpCycleState,
    )
    from tests.strategies.test_entry_anchors import _inputs

    anchor = SupportAnchor(
        anchor_id="sma50",
        anchor_type="SMA50",
        is_dynamic=True,
        origin_on=date(2026, 10, 1),
        origin_price=Decimal("100"),
        current_value=Decimal("110"),
        cycle_id="cycle-1",
    )
    changed = anchor.model_copy(update={"current_value": Decimal("120")})
    assert changed.origin_price == Decimal("100")
    assert changed.current_value == Decimal("120")
    state = SupportTestState(
        anchor=anchor,
        status="RECLAIMED",
        below_count=0,
        started_on=date(2026, 10, 1),
        status_as_of=date(2026, 10, 5),
        ended_on=None,
        finality=BarFinality.FINAL,
        failure_latched=True,
        reclaimed_on=date(2026, 10, 5),
    )
    assert state.failure_latched and state.reclaimed_on == date(2026, 10, 5)
    cycle = UpCycleState(finality=BarFinality.FINAL)
    assert cycle.status == "INACTIVE" and cycle.cycle_id is None
    assert cycle.above_sma150_count == 0
    source, *_ = _inputs()
    context = ObservationSourceContext(
        signal=source,
        terminal_status="expired",
        terminal_on=date(2026, 10, 1),
        terminal_reason="age",
        anchors=None,
    )
    assert context.signal.signal_id == "frozen-source"
    assert context.terminal_on == date(2026, 10, 1)

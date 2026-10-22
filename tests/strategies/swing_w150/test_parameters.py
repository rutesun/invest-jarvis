from dataclasses import replace
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from src.strategies.models import (
    EntryOpportunityStatus,
    SignalFinality,
    StrategySignal,
    StrategySignalBundle,
)
from src.strategies.swing_w150.parameters import (
    SWING_W150_PARAMETER_REGISTRY,
    parameter_fingerprint,
)
from src.strategies.swing_w150.rules import structure_breakdown
from src.tools.technical.scorecard_models import DataStatus, Direction, Evidence, Importance


def test_registered_version_has_one_canonical_payload():
    params = SWING_W150_PARAMETER_REGISTRY.get("SWING_W150_V2_PARAMS_V1")

    assert params.parameter_fingerprint == parameter_fingerprint(params)
    with pytest.raises(ValueError, match="registered parameter payload mismatch"):
        SWING_W150_PARAMETER_REGISTRY.validate(replace(params, overheat_extension=0.35))


@pytest.mark.parametrize(
    "missing",
    [
        "normal_failure_closes",
        "immediate_failure_volume_ratio",
        "immediate_failure_close_location",
        "support_break_buffer_atr",
        "restart_mode",
    ],
)
def test_product_v2_requires_every_policy_selection(missing):
    from src.strategies.swing_w150.parameters import (
        SupportCycleParameters,
        SwingW150ParametersV2,
        validate_pullback_policy,
    )

    values = {
        "normal_failure_closes": 2,
        "immediate_failure_volume_ratio": 2,
        "immediate_failure_close_location": 0.25,
        "support_break_buffer_atr": 0,
        "restart_mode": "D",
    }
    values[missing] = None
    if missing.startswith("immediate_"):
        values["immediate_failure_volume_ratio"] = None
        values["immediate_failure_close_location"] = None
    params = SwingW150ParametersV2(support_cycle=SupportCycleParameters(**values))
    with pytest.raises(ValueError, match=f"UNRESOLVED.*{missing}"):
        validate_pullback_policy(params)


def test_custom_parameters_get_distinct_fingerprint():
    base = SWING_W150_PARAMETER_REGISTRY.get("SWING_W150_V2_PARAMS_V1")
    custom = replace(base, parameter_set_version="CUSTOM", overheat_extension=0.35)

    assert parameter_fingerprint(custom) != parameter_fingerprint(base)


def test_overheat_reset_extension_uses_spec_field_name():
    params = SWING_W150_PARAMETER_REGISTRY.get("SWING_W150_V2_PARAMS_V1")
    customized = replace(params, overheat_reset_extension=0.19)

    with pytest.raises(ValueError, match="registered parameter payload mismatch"):
        SWING_W150_PARAMETER_REGISTRY.validate(customized)


def test_custom_weak_close_threshold_changes_breakdown_and_fingerprint():
    base = SWING_W150_PARAMETER_REGISTRY.get("SWING_W150_V2_PARAMS_V1")
    custom = replace(
        base, parameter_set_version="CUSTOM_WEAK_CLOSE", structure_weak_close_location=0.4
    )
    bars = pd.DataFrame(
        {
            "Close": [90.0],
            "High": [110.0],
            "Low": [80.0],
            "Volume": [200.0],
            "SMA_50": [100.0],
            "SMA_200": [85.0],
            "Vol_SMA_20_Prev": [100.0],
            "Low_20_Prev": [80.0],
        }
    )
    st = np.array([-1.0])
    lhll = np.array([False])

    assert not structure_breakdown(bars, st, lhll)[0]
    assert structure_breakdown(
        bars, st, lhll, weak_close_location=custom.structure_weak_close_location
    )[0]
    assert custom.parameter_fingerprint != base.parameter_fingerprint


def _signal_values():
    return {
        "signal_id": "signal-1",
        "strategy_id": "SWING_W150",
        "strategy_version": "SWING_W150_V2",
        "parameter_set_version": "SWING_W150_V2_PARAMS_V1",
        "parameter_fingerprint": "fingerprint-1",
        "code": "TREND_BREAKOUT_ENTRY",
        "occurred_on": date(2026, 10, 7),
        "finality": SignalFinality.FINAL,
        "direction": Direction.RISING,
        "signal_price": Decimal("100.25"),
        "evidence": [
            Evidence(
                code="breakout",
                message="Breakout confirmed",
                observed_value=100.25,
                reference_value=99.0,
                importance=Importance.HIGH,
                source="SWING_W150",
            )
        ],
        "data_status": DataStatus.COMPLETE,
    }


def _bundle_values(today_signal):
    return {
        "strategy_id": "SWING_W150",
        "strategy_version": "SWING_W150_V2",
        "parameter_set_version": "SWING_W150_V2_PARAMS_V1",
        "parameter_fingerprint": "fingerprint-1",
        "ticker": "AAPL",
        "as_of": date(2026, 10, 7),
        "observation_history": [],
        "signal_history": [today_signal],
        "current_signals": [],
        "entry_opportunity": {
            "evaluation_as_of": date(2026, 10, 7),
            "finality": SignalFinality.FINAL,
            "status": EntryOpportunityStatus.ALLOW,
            "entry_signal": today_signal,
            "invalidated_by": None,
            "age_bars": 0,
            "signal_price": Decimal("100.25"),
            "execution_reference_price": Decimal("100.25"),
            "extension_pct": Decimal("0.01"),
            "market_regime": "bull",
            "structure_status": "valid",
            "evidence": [
                Evidence(
                    code="entry_allowed",
                    message="Entry conditions are valid",
                    observed_value=None,
                    reference_value=None,
                    importance=Importance.MEDIUM,
                    source="SWING_W150",
                )
            ],
            "policy_version": "entry-policy-v1",
        },
        "data_status": DataStatus.COMPLETE,
    }


def test_current_signals_must_equal_today_history():
    today_signal = StrategySignal(**_signal_values())
    bundle_values = _bundle_values(today_signal)
    with pytest.raises(ValidationError):
        StrategySignalBundle(
            **{
                **bundle_values,
                "signal_history": [today_signal],
                "current_signals": [],
            }
        )


def test_signal_rejects_empty_evidence_and_uses_decimal_price():
    signal_values = _signal_values()
    with pytest.raises(ValidationError):
        StrategySignal(**{**signal_values, "evidence": []})

    signal = StrategySignal(**{**signal_values, "signal_price": Decimal("100.25")})
    assert signal.signal_price == Decimal("100.25")

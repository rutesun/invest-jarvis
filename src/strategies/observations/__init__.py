"""Typed chart observations with deterministic identities."""

from datetime import date

from src.storage.canonical import canonical_hash
from src.strategies.models import (
    ObservationCode,
    ObservationStatus,
    SignalFinality,
    StrategyObservationEpisode,
)
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.observations.registry import OBSERVATION_REGISTRY


OBSERVATION_SCHEMA_VERSION = "OBSERVATION_V1"
_CONTEXT_FIELDS = {
    "started_on",
    "status_as_of",
    "ended_on",
    "status",
    "evidence",
    "finality",
    "source_signal_id",
    "anchor_id",
    "anchor_type",
    "anchor_origin_on",
    "anchor_origin_price",
    "pivot_date",
    "confirmed_on",
    "source_terminal",
    "cycle_id",
}


def make_observation(
    *,
    ticker: str,
    code: ObservationCode,
    origin: date,
    params: ObservationParameters,
    **context,
) -> StrategyObservationEpisode:
    """Apply registry classification once; mutable status is excluded from identity."""
    code = ObservationCode(code)
    definition = OBSERVATION_REGISTRY[code]
    if unknown := context.keys() - _CONTEXT_FIELDS:
        raise ValueError(f"unknown observation context: {sorted(unknown)}")
    fingerprint = params.parameter_fingerprint
    identity = {
        "ticker": ticker,
        "code": code,
        "temporal_type": definition.temporal_type,
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "parameter_version": params.version,
        "parameter_fingerprint": fingerprint,
        "source_signal_id": context.get("source_signal_id"),
        "anchor_id": context.get("anchor_id"),
        "anchor_type": context.get("anchor_type"),
        "anchor_origin_on": context.get("anchor_origin_on"),
        "anchor_origin_price": context.get("anchor_origin_price"),
        "origin": origin,
    }
    return StrategyObservationEpisode(
        observation_id=canonical_hash("jarvis:observation:v1", identity),
        ticker=ticker,
        schema_version=OBSERVATION_SCHEMA_VERSION,
        parameter_fingerprint=fingerprint,
        code=code,
        kind=definition.kind,
        direction=definition.direction,
        scopes=definition.scopes,
        temporal_type=definition.temporal_type,
        **{
            "started_on": origin,
            "status_as_of": origin,
            "ended_on": None,
            "status": ObservationStatus.ACTIVE,
            "finality": SignalFinality.FINAL,
            **context,
        },
    )


__all__ = ["make_observation"]

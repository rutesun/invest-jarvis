"""Stable JSON bytes and domain-separated identities."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel


if TYPE_CHECKING:
    from src.strategies.models import ChartBundle


def _number(value: int | float | Decimal) -> str:
    decimal = Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError("Non-finite numbers cannot be canonicalized")
    if decimal == 0:
        return "0"
    fixed = format(decimal, "f")
    return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed


def _encode(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, Decimal)):
        return _number(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Naive datetime cannot be canonicalized")
        utc = value.astimezone(UTC)
        return json.dumps(utc.isoformat().replace("+00:00", "Z"), ensure_ascii=False)
    if isinstance(value, date):
        return json.dumps(value.isoformat())
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, BaseModel):
        return _encode(value.model_dump(mode="python"))
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Canonical object keys must be strings")
        return (
            "{" + ",".join(f"{_encode(key)}:{_encode(value[key])}" for key in sorted(value)) + "}"
        )
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    raise TypeError(f"Unsupported canonical value: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    return _encode(value).encode("utf-8")


def canonical_hash(domain: str, value: object) -> str:
    return hashlib.sha256(domain.encode("utf-8") + b"\0" + canonical_bytes(value)).hexdigest()


def strategy_input_hash(
    bundle: ChartBundle,
    *,
    strategy_id: str,
    strategy_version: str,
    parameter_fingerprint: str | None = None,
) -> str:
    identity = {
        "chart_bundle_hash": bundle.bundle_hash,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
    }
    if parameter_fingerprint is not None:
        identity["parameter_fingerprint"] = parameter_fingerprint
    return canonical_hash(
        "jarvis:strategy-input:v1",
        identity,
    )

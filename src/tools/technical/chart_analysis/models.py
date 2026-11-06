"""Tools-owned, immutable facts and input snapshots; no consumer policy types."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import date
from decimal import Decimal
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Any, Literal

import numpy as np
import pandas as pd

from src.storage.canonical import canonical_hash


def plain(value: Any) -> Any:
    """Normalize snapshots for canonical JSON, preserving missing cells explicitly."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((plain(item) for item in value), key=str)
    if isinstance(value, Enum):
        return plain(value.value)
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, float) and not isfinite(value):
        return {"nonfinite": str(value)}
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def freeze(value: Any) -> Any:
    """Own nested values rather than exposing aliases behind a frozen outer shell."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(freeze(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return freeze(plain(value))
    if isinstance(value, np.generic):
        return freeze(value.item())
    if isinstance(value, (str, int, float, bool, date, Decimal, Enum, type(None))):
        return value
    raise TypeError(f"Unsupported mutable snapshot value: {type(value).__name__}")


def content_hash(frame: pd.DataFrame) -> str:
    payload = {
        "columns": [plain(column) for column in frame.columns],
        "index": [plain(day) for day in frame.index],
        "rows": [plain(row) for row in frame.itertuples(index=False, name=None)],
    }
    return canonical_hash("jarvis:chart-series:v1", payload)


def _owned_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Pandas deep copies cells but can still alias mutable axis extension arrays."""
    frame = raw.copy(deep=True)
    frame.index = raw.index.copy(deep=True)
    frame.columns = raw.columns.copy(deep=True)
    for column in frame.select_dtypes(include="object"):
        frame[column] = [deepcopy(value) for value in raw[column]]
    return frame


@dataclass(frozen=True)
class InputManifest:
    ticker: str
    exchange: str
    as_of: date
    origin: str
    input_profile: str
    feature_version: str
    input_hash: str
    adjustment_policy: str
    calendar_version: str
    finality: str | Mapping[date, str]
    coverage: Any
    provider: str | None = None
    revision_if_known: str | None = None
    timezone: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "finality", freeze(self.finality))
        object.__setattr__(self, "coverage", freeze(self.coverage))


@dataclass(frozen=True)
class FeatureValue:
    value: float | None
    status: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))


@dataclass(frozen=True)
class RuleRequest:
    rule_id: str
    rule_version: str
    parameters: Mapping[str, Any]
    input_roles: tuple[str, ...]
    alignment_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", freeze(self.parameters))
        object.__setattr__(self, "input_roles", tuple(sorted(set(self.input_roles))))

    @property
    def parameter_id(self) -> str:
        return canonical_hash("jarvis:chart-parameters:v1", plain(self.parameters))


@dataclass(frozen=True)
class ChartItem:
    id: str
    evaluation_key: str
    kind: str
    rule_id: str
    rule_version: str
    parameter_id: str
    anchor_id: str | None
    occurred_on: date
    confirmed_on: date | None
    status_as_of: date
    state: str
    finality: str
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", freeze(self.evidence))

    @classmethod
    def create(
        cls,
        *,
        manifest: InputManifest,
        request: RuleRequest,
        anchor_id: str | None,
        occurred_on: date,
        **values: Any,
    ) -> ChartItem:
        identity = {
            "ticker": manifest.ticker,
            "exchange": manifest.exchange,
            "rule_id": request.rule_id,
            "rule_version": request.rule_version,
            "parameter_id": request.parameter_id,
            "feature_version": manifest.feature_version,
            "input_profile": manifest.input_profile,
            "anchor_id": anchor_id,
            "occurred_on": occurred_on,
        }
        return cls(
            id=canonical_hash("jarvis:chart-item:v1", identity),
            rule_id=request.rule_id,
            rule_version=request.rule_version,
            parameter_id=request.parameter_id,
            anchor_id=anchor_id,
            occurred_on=occurred_on,
            **values,
        )


@dataclass(frozen=True, init=False)
class SeriesInput:
    manifest: InputManifest
    _raw: pd.DataFrame

    def __init__(self, manifest: InputManifest, raw: pd.DataFrame):
        if not isinstance(raw.index, pd.DatetimeIndex):
            raise ValueError("SeriesInput requires a DatetimeIndex")
        if not raw.index.is_monotonic_increasing or not raw.index.is_unique:
            raise ValueError("SeriesInput sessions must be ascending and unique")
        if any(day.date() > manifest.as_of for day in raw.index):
            raise ValueError("SeriesInput contains rows after as_of")
        snapshot = _owned_frame(raw)
        digest = content_hash(snapshot)
        if manifest.input_hash and manifest.input_hash != digest:
            raise ValueError("input_hash does not match actual raw content")
        object.__setattr__(self, "manifest", replace(manifest, input_hash=digest))
        object.__setattr__(self, "_raw", snapshot)

    @property
    def raw(self) -> pd.DataFrame:
        return _owned_frame(self._raw)


@dataclass(frozen=True)
class CalculationScope:
    primary: SeriesInput
    related: Mapping[str, SeriesInput]

    def __post_init__(self) -> None:
        if "instrument" in self.related:
            raise ValueError("instrument role belongs to primary")
        object.__setattr__(self, "related", MappingProxyType(dict(self.related)))

    def series_for(self, role: str) -> SeriesInput:
        return self.primary if role == "instrument" else self.related[role]


@dataclass(frozen=True)
class ChartAnalysis:
    analysis_id: str
    manifest: InputManifest
    dependencies: Mapping[str, InputManifest]
    features: Mapping[str, FeatureValue]
    items: tuple[ChartItem, ...]
    requested_rules: tuple[RuleRequest, ...] = ()
    requested_anchors: tuple[ChartAnchor, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependencies", MappingProxyType(dict(self.dependencies)))
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "requested_rules", tuple(self.requested_rules))
        object.__setattr__(self, "requested_anchors", tuple(self.requested_anchors))
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate chart item identity in one analysis")

    def __deepcopy__(self, memo):
        """Share the recursively immutable snapshot through legacy result transports."""
        memo[id(self)] = self
        return self


@dataclass(frozen=True)
class FactRef:
    analysis_id: str
    item_id: str


@dataclass(frozen=True)
class FactSelection:
    ref: FactRef
    selected: bool
    reason_code: str


@dataclass(frozen=True)
class FixedPriceAnchor:
    id: str
    kind: str
    origin_on: date
    available_on: date
    origin_value: float
    value: float
    finality: str
    source_id: str

    def __post_init__(self) -> None:
        if self.value != self.origin_value:
            raise ValueError("FixedPriceAnchor value must equal origin_value")


@dataclass(frozen=True)
class FeatureAnchor:
    id: str
    kind: str
    origin_on: date
    available_on: date
    origin_value: float
    input_role: str
    feature_key: str
    feature_version: str
    active_when: Literal["ALWAYS", "SUPERTREND_UP"]
    source_id: str

    def __post_init__(self) -> None:
        if self.active_when not in ("ALWAYS", "SUPERTREND_UP"):
            raise ValueError("Unsupported FeatureAnchor active_when")


ChartAnchor = FixedPriceAnchor | FeatureAnchor


@dataclass(frozen=True)
class QualityParameters:
    """Fixed, experimental CHART_SCORE_V1 numerical payload; no trading policy."""

    score_version: str = field(default="CHART_SCORE_V1", init=False)
    axis_weights: tuple[float, ...] = field(default=(0.30, 0.25, 0.30, 0.15), init=False)
    trend_weights: tuple[float, ...] = field(default=(0.30, 0.45, 0.25), init=False)
    structure_weights: tuple[float, ...] = field(default=(0.40, 0.40, 0.20), init=False)
    momentum_weights: tuple[float, ...] = field(default=(0.20, 0.50, 0.30), init=False)
    momentum_lags: tuple[int, ...] = field(default=(5, 20, 60), init=False)
    normalization_center: float = field(default=50.0, init=False)
    distance_scale: float = field(default=25.0, init=False)
    return_scale: float = field(default=12.5, init=False)
    close_sma200_k: float = field(default=2.0, init=False)
    atr_period: int = field(default=14, init=False)
    window: int = field(default=20, init=False)
    calculation_min_bars: int = field(default=220, init=False)
    publication_min_final_bars: int = field(default=252, init=False)
    directional_min_samples: int = field(default=5, init=False)
    concentration_threshold: float = field(default=0.5, init=False)

    @property
    def parameter_id(self) -> str:
        return canonical_hash("jarvis:chart-quality-parameters:v1", plain(self))


@dataclass(frozen=True)
class QualityResult:
    as_of: date
    manifest: InputManifest
    score_version: str
    parameter_id: str
    axes: Mapping[str, float | None]
    quality: float | None
    reasons: tuple[str, ...]
    diagnostics: Mapping[str, Any]
    contributions: Mapping[str, float | None]

    def __post_init__(self) -> None:
        for name in ("axes", "diagnostics", "contributions"):
            object.__setattr__(self, name, freeze(getattr(self, name)))
        object.__setattr__(self, "reasons", tuple(self.reasons))

    def __deepcopy__(self, memo):
        memo[id(self)] = self
        return self


@dataclass(frozen=True)
class QualityDelta:
    before_as_of: date
    after_as_of: date
    quality: float | None
    axis_contributions: Mapping[str, float | None]
    subfeature_contributions: Mapping[str, float | None]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("axis_contributions", "subfeature_contributions"):
            object.__setattr__(self, name, freeze(getattr(self, name)))
        object.__setattr__(self, "reasons", tuple(self.reasons))


@dataclass(frozen=True)
class ChartAnalysisResult:
    """Immutable presentation envelope; requested date is outside calculation identity."""

    analysis: ChartAnalysis
    quality: QualityResult
    requested_as_of: date | None = None

    def __deepcopy__(self, memo):
        memo[id(self)] = self
        return self

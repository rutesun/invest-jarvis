"""Explicit daily-history range contracts shared by providers and chart tools.

Live transports remain gated until captured raw responses establish range and
adjustment semantics. Injected transports are for offline contract validation.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Protocol

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)
OHLCV = ("Open", "High", "Low", "Close", "Volume")


class HistoryFinality(StrEnum):
    FINAL = "FINAL"
    PROVISIONAL = "PROVISIONAL"
    UNKNOWN = "UNKNOWN"


class InputHistoryError(ValueError):
    """Malformed OHLCV must not become a usable chart prefix."""


class RangeHistoryUnavailableError(RuntimeError):
    """Captured raw range evidence is required before enabling live access."""


@dataclass(frozen=True)
class RangeCoverage:
    requested_start: date
    requested_end: date
    reached_start: bool
    observed_start: date | None = None
    observed_end: date | None = None
    expected_sessions: tuple[date, ...] = ()
    missing_sessions: tuple[date, ...] = ()
    missing_fields: dict[date, tuple[str, ...]] = field(default_factory=dict)
    provisional_sessions: tuple[date, ...] = ()
    unknown_finality_sessions: tuple[date, ...] = ()
    reasons: tuple[str, ...] = ()
    no_session_basis: str | None = None

    @property
    def complete(self) -> bool:
        return self.reached_start and not any(
            (
                self.missing_sessions,
                self.missing_fields,
                self.provisional_sessions,
                self.unknown_finality_sessions,
                self.reasons,
            )
        )


@dataclass(frozen=True)
class RawHistory:
    frame: pd.DataFrame
    provider: str
    adjustment_policy: str
    revision_if_known: str | None
    finality: dict[date, HistoryFinality]
    coverage: RangeCoverage


class PriceHistoryRangeProvider(Protocol):
    live_range_enabled: bool
    range_evidence_status: str

    async def get_price_history_range(
        self, ticker: str, *, start: date, end: date
    ) -> RawHistory: ...


def normalize_history(frame: pd.DataFrame, *, start: date, end: date) -> pd.DataFrame:
    """Copy, normalize session labels, and reject invalid supplied OHLCV.

    NaN remains missing. Equal overlapping records collapse with a warning;
    conflicting records never silently select one revision.
    """
    if start > end:
        raise InputHistoryError("range start must not follow end")
    result = frame.copy(deep=True)
    if not result.empty and not isinstance(result.index, pd.DatetimeIndex):
        raise InputHistoryError("history requires a DatetimeIndex")
    result.index = pd.DatetimeIndex([stamp.date() for stamp in result.index], name="Date")
    result = result.loc[(result.index.date >= start) & (result.index.date <= end)]
    for column in OHLCV:
        if column not in result:
            result[column] = np.nan
    result = result.loc[:, list(OHLCV)]
    try:
        result = result.astype(float)
    except (ValueError, TypeError) as exc:
        raise InputHistoryError("OHLCV must contain numeric values or NaN") from exc
    if result.index.has_duplicates:
        for day, group in result.groupby(level=0):
            if len(group) > 1 and (group.nunique(dropna=False) > 1).any():
                raise InputHistoryError(f"conflicting duplicate session: {day.date()}")
        logger.warning("collapsing identical overlapping daily history records")
        result = result.loc[~result.index.duplicated()]
    values = result.to_numpy()
    if np.isinf(values).any():
        raise InputHistoryError("infinite OHLCV value")
    if (result[list(OHLCV[:4])] <= 0).any().any():
        raise InputHistoryError("OHLC prices must be positive")
    if (result["Volume"] < 0).any():
        raise InputHistoryError("negative volume")
    # Each comparison remains meaningful even if an unrelated field is NaN.
    for lower, upper in (
        ("Low", "Open"),
        ("Low", "Close"),
        ("Low", "High"),
        ("Open", "High"),
        ("Close", "High"),
    ):
        if (result[lower] > result[upper]).any():
            raise InputHistoryError("inconsistent OHLC price order")
    return result.sort_index()


def unknown_history(
    frame: pd.DataFrame,
    *,
    provider: str,
    adjustment_policy: str,
    start: date,
    end: date,
    reached_start: bool,
    no_session_basis: str | None = None,
) -> RawHistory:
    """Range transports provide no verified bar-finality or revision evidence yet."""
    normalized = normalize_history(frame, start=start, end=end)
    observed = tuple(stamp.date() for stamp in normalized.index)
    # An empty provider response is not proof that the requested range has no
    # sessions. Only a separately verified calendar can establish that case.
    reached_start = reached_start and (bool(observed) or no_session_basis is not None)
    missing_fields = {
        stamp.date(): tuple(column for column in OHLCV if pd.isna(row[column]))
        for stamp, row in normalized.iterrows()
        if row.isna().any()
    }
    if missing_fields:
        logger.warning("%s range contains missing OHLCV fields: %s", provider, missing_fields)
    reasons = [] if reached_start else ["INCOMPLETE_PREFIX"]
    if not observed and no_session_basis is None:
        reasons.append("EMPTY_RESPONSE")
    if missing_fields and "INCOMPLETE_PREFIX" not in reasons:
        reasons.append("INCOMPLETE_PREFIX")
    if observed:
        reasons.append("UNKNOWN_FINALITY")
    return RawHistory(
        frame=normalized,
        provider=provider,
        adjustment_policy=adjustment_policy,
        revision_if_known=None,
        finality={stamp.date(): HistoryFinality.UNKNOWN for stamp in normalized.index},
        coverage=RangeCoverage(
            requested_start=start,
            requested_end=end,
            reached_start=reached_start,
            observed_start=normalized.index[0].date() if len(normalized) else None,
            observed_end=normalized.index[-1].date() if len(normalized) else None,
            missing_fields=missing_fields,
            unknown_finality_sessions=observed,
            reasons=tuple(reasons),
            no_session_basis=no_session_basis,
        ),
    )

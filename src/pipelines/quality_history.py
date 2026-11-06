"""Quality-only supplied-chart history; legacy strategy frames stay unchanged."""

from dataclasses import replace
from datetime import date

import pandas as pd

from src.providers.price_history_range import (
    OHLCV,
    HistoryFinality,
    InputHistoryError,
    RangeCoverage,
    RawHistory,
    normalize_history,
)


async def quality_history(ticker, technical, bundle, chart_service, as_of: date) -> RawHistory:
    supplied = getattr(technical, "quality_raw_dataframe", None)
    if supplied is None:
        supplied = technical.raw_dataframe
    if supplied is None or supplied.empty:
        raise InputHistoryError("Quality OHLCV unavailable")
    original = normalize_history(supplied, start=min(supplied.index.date), end=as_of)
    if original.empty:
        raise InputHistoryError("Quality OHLCV unavailable through evaluated day")
    session = original.index[-1].date()
    origin = (pd.Timestamp(session) - pd.DateOffset(years=2)).date()
    if chart_service.listing_first_session is not None:
        origin = max(origin, chart_service.listing_first_session)
    finality = {
        bar.session_date: HistoryFinality(bar.finality.value.upper())
        for bar in bundle.instrument.bars
    }
    source = "SUPPLIED_EXISTING_CHART"
    frame = original
    raw = RawHistory(
        frame=frame,
        provider=source,
        adjustment_policy="UNVERIFIED_EXISTING_CHART",
        revision_if_known=None,
        finality=finality,
        coverage=RangeCoverage(
            requested_start=frame.index[0].date(),
            requested_end=as_of,
            reached_start=True,
            observed_start=frame.index[0].date(),
            observed_end=frame.index[-1].date(),
        ),
    )
    return await extend_quality_history(ticker, technical, raw, origin=origin, as_of=as_of)


async def extend_quality_history(ticker, technical, raw, *, origin: date, as_of: date):
    """Use the existing one supplemental request for the earliest needed origin."""
    original = raw.frame
    finality = raw.finality
    provider = getattr(technical, "quality_history_provider", None)
    if (
        original.index[0].date() > origin
        and provider is not None
        and raw.provider != "SUPPLIED_EXISTING_CHART_3Y"
    ):
        extended = await provider.get_price_history(ticker, "3y")
        if extended.empty:
            raise InputHistoryError("Quality supplemental history empty")
        extended = normalize_history(extended, start=min(extended.index.date), end=as_of)
        overlap = original.index.intersection(extended.index)
        left, right = original.loc[overlap, list(OHLCV)], extended.loc[overlap, list(OHLCV)]
        valid = left.notna() & right.notna()
        if ((left != right) & valid).any().any():
            raise InputHistoryError("Quality supplemental overlap conflict: OHLCV revisions differ")
        if (left.isna() & right.notna()).any().any():
            raise InputHistoryError(
                "Quality supplemental overlap would conceal missing original OHLCV"
            )
        if not original.index.isin(extended.index).all():
            raise InputHistoryError("Quality supplemental history omits original sessions")
        frame = extended
        # Same supplied-chart convention as chart_bundle: older daily bars are
        # inferred FINAL, while the evaluated bar retains its observed finality.
        # This is not range-API captured/verified finality evidence.
        finality = {
            day: finality.get(
                day, HistoryFinality.FINAL if day < as_of else HistoryFinality.UNKNOWN
            )
            for day in frame.index.date
        }
        return replace(
            raw,
            frame=frame,
            provider="SUPPLIED_EXISTING_CHART_3Y",
            finality=finality,
            coverage=RangeCoverage(
                requested_start=frame.index[0].date(),
                requested_end=as_of,
                reached_start=True,
                observed_start=frame.index[0].date(),
                observed_end=frame.index[-1].date(),
            ),
        )
    return raw

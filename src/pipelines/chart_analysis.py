"""Request-local strict date/range chart analysis; no result persistence."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.providers.price_history_range import (
    HistoryFinality,
    InputHistoryError,
    PriceHistoryRangeProvider,
    RangeHistoryUnavailableError,
    RawHistory,
    normalize_history,
)
from src.tools.disclosure import is_korean_ticker
from src.tools.technical.chart_analysis.features import STRICT_VERSION
from src.tools.technical.chart_analysis.input import (
    ExchangeSessionCalendar,
    SessionCalendar,
    prepare_history,
)
from src.tools.technical.chart_analysis.models import (
    CalculationScope,
    ChartAnalysis,
    ChartAnalysisResult,
    ChartItem,
    FactRef,
    FactSelection,
    InputManifest,
    QualityParameters,
    SeriesInput,
    plain,
)
from src.tools.technical.chart_analysis.quality import score_quality
from src.tools.technical.chart_analysis.registry import rule_request
from src.tools.technical.chart_analysis.service import AnalysisRequestContext


def strict_rule_requests():
    return (
        rule_request("chart.features.strict"),
        rule_request("chart.pivot.span3"),
        *(rule_request("chart.close_breakout.strict", {"lookback": n}) for n in (20, 50)),
        *(
            rule_request(rule)
            for rule in (
                "chart.low_break_volume",
                "chart.down_volume_weak_close",
                "chart.extension.sma20",
                "chart.rsi.wilder",
            )
        ),
    )


class ChartAnalysisService:
    """Explicit raw/offline injection until captured live range evidence exists."""

    def __init__(
        self,
        range_provider: PriceHistoryRangeProvider | None = None,
        *,
        calendar: SessionCalendar | None = None,
        listing_first_session: date | None = None,
    ):
        self.range_provider = range_provider
        self.calendar = calendar
        self.listing_first_session = listing_first_session

    async def analyze_query(
        self,
        ticker: str,
        *,
        as_of: date | None = None,
        history: int | None = None,
        start: date | None = None,
        end: date | None = None,
        raw: RawHistory | None = None,
        today: date | None = None,
    ) -> tuple[ChartAnalysisResult, ...]:
        """Resolve display queries from observed raw sessions, without a second fetch.

        Latest/history require supplied raw: a calendar date is not evidence of an
        observed bar. The live range gate remains closed for those query modes.
        """
        today = today or date.today()
        if sum((as_of is not None, history is not None, start is not None or end is not None)) > 1:
            raise ValueError("조회 모드는 상호배타입니다")
        if history is not None and history <= 0:
            raise ValueError("history N은 1 이상이어야 합니다")
        if (start is None) != (end is None):
            raise ValueError("--from과 --to는 함께 지정해야 합니다")
        if any(day > today for day in (as_of, start, end) if day is not None):
            raise ValueError("미래 날짜는 조회할 수 없습니다")
        if start is not None and start > end:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다")
        if start is not None and raw is None:
            raw = await self._load_history(ticker, start, end)
        if as_of is not None:
            sessions = (as_of,)
        else:
            if raw is None:
                raise RangeHistoryUnavailableError(
                    "STUB_ONLY: latest/history require observed RawHistory; live range raw capture is pending"
                )
            observed = sorted(
                {
                    pd.Timestamp(day).date()
                    for day in raw.frame.index
                    if raw.coverage.requested_start
                    <= pd.Timestamp(day).date()
                    <= min(today, raw.coverage.requested_end)
                }
            )
            if start is not None:
                return await self.analyze(
                    ticker, sessions=tuple(day for day in observed if start <= day <= end), raw=raw
                )
            if not observed:
                raise ValueError("관측된 거래 세션이 없습니다")
            if history is not None and len(observed) < history:
                raise ValueError(f"관측된 거래 세션이 부족합니다: {len(observed)}/{history}")
            sessions = tuple(observed[-(history or 1) :])
        return await self.analyze(ticker, sessions=sessions, raw=raw)

    async def _load_history(self, ticker: str, start: date, end: date) -> RawHistory:
        if self.range_provider is None:
            raise RangeHistoryUnavailableError(
                "STUB_ONLY: live range raw capture is pending; supply RawHistory or an offline range provider"
            )
        origin = (pd.Timestamp(start) - pd.DateOffset(years=2)).date()
        raw = await self.range_provider.get_price_history_range(ticker, start=origin, end=end)
        frame = normalize_history(
            raw.frame, start=raw.coverage.requested_start, end=min(end, raw.coverage.requested_end)
        )
        prior = frame.loc[frame.index.date <= start]
        if prior.empty:
            return raw
        needed = (pd.Timestamp(prior.index[-1]) - pd.DateOffset(years=2)).date()
        if self.listing_first_session is not None:
            needed = max(needed, self.listing_first_session)
        if raw.coverage.requested_start <= needed:
            return raw
        # A delayed response may resolve arbitrarily far before the request.
        # Request its exact origin instead of guessing a holiday padding length.
        extended = await self.range_provider.get_price_history_range(ticker, start=needed, end=end)
        extra = normalize_history(
            extended.frame,
            start=extended.coverage.requested_start,
            end=min(end, extended.coverage.requested_end),
        )
        if not frame.index.isin(extra.index).all() or not frame.equals(extra.loc[frame.index]):
            raise InputHistoryError("supplemental response changes original OHLCV")
        if any(
            HistoryFinality(raw.finality.get(day, HistoryFinality.UNKNOWN))
            != HistoryFinality(extended.finality.get(day, HistoryFinality.UNKNOWN))
            for day in frame.index.date
        ):
            raise InputHistoryError("supplemental response changes original finality")
        if any(
            getattr(raw, key) != getattr(extended, key)
            for key in ("provider", "adjustment_policy", "revision_if_known")
        ):
            raise InputHistoryError("supplemental response changes original provenance")
        return extended

    async def analyze(
        self, ticker: str, *, sessions: tuple[date, ...], raw: RawHistory | None = None
    ) -> tuple[ChartAnalysisResult, ...]:
        if not sessions:
            return ()
        korean = is_korean_ticker(ticker)
        exchange = "XKRX" if korean else "XNYS"
        calendar = self.calendar or ExchangeSessionCalendar(
            exchange, "Asia/Seoul" if korean else "America/New_York"
        )
        if raw is None:
            raw = await self._load_history(ticker, min(sessions), max(sessions))
        context = AnalysisRequestContext()
        results = []
        for requested_day in sessions:
            prepared = prepare_history(
                raw,
                as_of=requested_day,
                calendar=calendar,
                listing_first_session=self.listing_first_session,
            )
            manifest = InputManifest(
                ticker=ticker,
                exchange=exchange,
                as_of=prepared.session,
                origin=str(prepared.frame.index[0].date()),
                input_profile=prepared.input_origin_policy,
                feature_version=STRICT_VERSION,
                input_hash="",
                adjustment_policy=prepared.adjustment_policy,
                calendar_version=prepared.calendar_version,
                finality=prepared.finality,
                coverage={
                    **plain(prepared.coverage),
                    "calendar_start": (
                        pd.Timestamp(prepared.session) - pd.DateOffset(years=2)
                    ).date(),
                    "input_start": prepared.input_start,
                    "listing_first_session": prepared.listing_first_session,
                },
                provider=prepared.provider,
                revision_if_known=prepared.revision_if_known,
                timezone=prepared.timezone,
            )
            analysis = context.get(
                CalculationScope(SeriesInput(manifest, prepared.frame), {}), strict_rule_requests()
            )
            results.append(
                ChartAnalysisResult(
                    analysis,
                    score_quality(analysis, parameters=QualityParameters()),
                    requested_as_of=requested_day,
                )
            )
        return tuple(results)


@dataclass(frozen=True)
class SelectedFactRow:
    """Display-only grouping; every source ref and consumer decision stays intact."""

    item: ChartItem
    refs: tuple[FactRef, ...]
    selections: tuple[FactSelection, ...]


def selected_fact_rows(
    analyses: Mapping[str, ChartAnalysis], selections: tuple[FactSelection, ...]
) -> tuple[SelectedFactRow, ...]:
    from src.storage.canonical import canonical_hash

    resolved = {}

    def resolve(ref):
        if ref not in resolved:
            analysis = analyses[ref.analysis_id]
            item = next((item for item in analysis.items if item.id == ref.item_id), None)
            if item is None:
                raise KeyError(f"Unknown chart item: {ref.item_id}")
            resolved[ref] = (canonical_hash("jarvis:chart-display-row:v1", plain(item)), item)
        return resolved[ref]

    selected = {resolve(selection.ref)[0] for selection in selections if selection.selected}
    if not selected:
        return ()
    selected_ids = {selection.ref.item_id for selection in selections if selection.selected}
    grouped = {}
    for selection in selections:
        if selection.ref.item_id not in selected_ids:
            continue
        key, item = resolve(selection.ref)
        if key not in selected:
            continue
        if key not in grouped:
            grouped[key] = (item, [], [])
        _, refs, reasons = grouped[key]
        if selection.ref not in refs:
            refs.append(selection.ref)
        reasons.append(selection)
    return tuple(
        SelectedFactRow(item, tuple(refs), tuple(reasons))
        for item, refs, reasons in grouped.values()
    )

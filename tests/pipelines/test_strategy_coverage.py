"""Coverage must come from exchange sessions, independently of price responses."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from src.pipelines.strategy_analysis import AnalysisStrategyService, ChartBundleLoader
from src.position.models import PositionSnapshot
from src.providers.exchange_calendar import exchange_sessions_for
from src.strategies.entry_opportunity import evaluate_signal_entry_opportunity
from src.strategies.models import EntryOpportunityStatus, SignalFinality, StrategySignal
from src.strategies.signal_performance import evaluate_signal_performance
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.tools.technical.scorecard_models import DataStatus, Evidence, Importance
from tests.strategies.test_runner import _legacy_result


class PriceResponse:
    def __init__(self, frame):
        self.frame = frame

    async def get_price_history(self, ticker, period):
        return self.frame


def prices(as_of=date(2026, 10, 8)):
    sessions = pd.bdate_range(as_of - timedelta(days=730), as_of)
    return pd.DataFrame(
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000.0},
        index=sessions,
    )


async def load(ticker, instrument, market):
    return await ChartBundleLoader(PriceResponse(market)).load(
        ticker=ticker,
        technical=SimpleNamespace(raw_dataframe=instrument),
        as_of=instrument.index[-1].date(),
        observed_at=datetime(2026, 10, 13, tzinfo=UTC),
    )


def entry_on_october_six():
    params = SwingW150Parameters()
    return StrategySignal(
        signal_id="SWING_W150_V2:TEST:2026-10-06:TREND_BREAKOUT_ENTRY",
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version=params.parameter_set_version,
        parameter_fingerprint=params.parameter_fingerprint,
        code="TREND_BREAKOUT_ENTRY",
        occurred_on=date(2026, 10, 6),
        finality=SignalFinality.FINAL,
        direction=None,
        signal_price=Decimal("100"),
        evidence=[
            Evidence(
                code="ENTRY",
                message="entry at 100",
                observed_value=100,
                reference_value=100,
                importance=Importance.HIGH,
                source="SWING_W150_V2",
            )
        ],
        data_status=DataStatus.COMPLETE,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["AAPL", "005930.KS"])
async def test_shared_provider_gap_is_missing_from_complete_instrument_coverage(ticker):
    sparse = prices().drop(pd.Timestamp("2026-10-07"))
    bundle = await load(ticker, sparse, sparse)
    assert date(2026, 10, 7) in bundle.exchange_sessions
    assert bundle.instrument.coverage.complete is False
    assert bundle.market.coverage.complete is False


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["AAPL", "005930.KS"])
async def test_shared_provider_gap_cannot_authorize_entry_opportunity(ticker):
    sparse = prices().drop(pd.Timestamp("2026-10-07"))
    bundle = await load(ticker, sparse, sparse)
    opportunity = evaluate_signal_entry_opportunity(
        [entry_on_october_six()], bundle, SwingW150Parameters()
    )
    assert opportunity.status is EntryOpportunityStatus.NOT_EVALUATED


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["AAPL", "005930.KS"])
async def test_shared_provider_gap_cannot_be_next_tradable_open(ticker):
    sparse = prices().drop(pd.Timestamp("2026-10-07"))
    bundle = await load(ticker, sparse, sparse)
    performance = evaluate_signal_performance(entry_on_october_six(), bundle)
    assert performance.executed_data_status is DataStatus.NOT_EVALUATED
    assert performance.executed_status_reason == "UNACCOUNTED_EXECUTION_SESSIONS"
    assert performance.execution_reference_price is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ticker", "as_of", "holiday"),
    [
        ("AAPL", date(2026, 7, 6), date(2026, 7, 3)),
        ("005930.KS", date(2026, 10, 12), date(2026, 10, 9)),
    ],
)
async def test_exchange_holiday_is_not_a_missing_provider_session(ticker, as_of, holiday):
    frame = prices(as_of).drop(pd.Timestamp(holiday))
    bundle = await load(ticker, frame, frame)
    assert holiday not in bundle.exchange_sessions
    assert bundle.instrument.coverage.complete is True


@pytest.mark.asyncio
async def test_market_unavailable_does_not_mark_complete_instrument_history_as_gapped():
    frame = prices()
    bundle = await load("AAPL", frame, pd.DataFrame())
    assert bundle.market is None
    assert bundle.instrument.coverage.complete is True
    assert date(2026, 10, 7) in bundle.exchange_sessions


def rising_prices():
    frame = prices()
    close = pd.Series([100 + bar * 0.1 for bar in range(len(frame))], index=frame.index)
    frame["Open"] = frame["Close"] = close
    frame["High"] = close + 1
    frame["Low"] = close - 1
    return frame


async def evaluate_with_five_shares(frame, market):
    technical = _legacy_result(scorecard_as_of=date(2026, 10, 8))
    technical.raw_dataframe = frame
    return await AnalysisStrategyService(ChartBundleLoader(PriceResponse(market))).evaluate(
        "AAPL",
        technical,
        as_of=date(2026, 10, 8),
        position=PositionSnapshot(quantity=5),
    )


@pytest.mark.asyncio
async def test_instrument_provider_gap_cannot_create_sma_exit_or_sell_real_holding():
    full = rising_prices()
    for day, close in [("2026-10-06", 120), ("2026-10-07", 200), ("2026-10-08", 120)]:
        full.loc[pd.Timestamp(day), ["Open", "High", "Low", "Close"]] = [
            close,
            close + 1,
            close - 1,
            close,
        ]
    result = await evaluate_with_five_shares(full.drop(pd.Timestamp("2026-10-07")), prices())
    assert result.position_plan.sell_quantity == 0
    swing = result.strategy_run.signal_bundles[0]
    assert swing.current_signals == []
    assert swing.data_status is DataStatus.PARTIAL
    assert swing.entry_opportunity.status is EntryOpportunityStatus.NOT_EVALUATED


@pytest.mark.asyncio
async def test_missing_market_chart_does_not_suppress_complete_instrument_exit():
    frame = rising_prices()
    frame.loc[frame.index[-2:], ["Open", "High", "Low", "Close"]] = [120, 121, 119, 120]
    result = await evaluate_with_five_shares(frame, pd.DataFrame())
    swing = result.strategy_run.signal_bundles[0]
    assert [signal.code for signal in swing.current_signals] == ["SMA150_EXIT"]
    assert swing.data_status is DataStatus.COMPLETE
    assert swing.entry_opportunity.status is EntryOpportunityStatus.NOT_EVALUATED
    assert result.position_plan.sell_quantity == 5


def live_two_year_prices():
    # Root's actual NVDA/SPY shape: nominal 2024-10-07, provider begins 2024-10-08.
    sessions = exchange_sessions_for("XNYS", date(2024, 10, 7), date(2026, 10, 7))
    assert len(sessions) == 502
    return pd.DataFrame(
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000.0},
        index=pd.DatetimeIndex(sessions),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("instrument_skip", "market_skip"), [(1, 1), (1, 0), (0, 1)])
async def test_live_two_year_first_session_boundary_is_complete(instrument_skip, market_skip):
    full = live_two_year_prices()
    bundle = await load("NVDA", full.iloc[instrument_skip:], full.iloc[market_skip:])
    assert bundle.exchange_sessions[0] == date(2024, 10, 7)
    assert len(bundle.exchange_sessions) == 502
    assert bundle.instrument.coverage.complete is True
    assert bundle.market.coverage.complete is True
    for series, skip in ((bundle.instrument, instrument_skip), (bundle.market, market_skip)):
        assert series.coverage.complete is True
        assert series.coverage.requested_start == date(2024, 10, 7)
        assert series.coverage.listing_first_session is None
        assert series.coverage.effective_start == (date(2024, 10, 8) if skip else None)
        assert series.coverage.expected_sessions[0] == (
            date(2024, 10, 8) if skip else date(2024, 10, 7)
        )
    assert bundle.has_complete_coverage(date(2024, 10, 7), bundle.as_of) == (instrument_skip == 0)
    prefix = bundle.prefix(date(2026, 10, 6))
    assert prefix.instrument.coverage.effective_start == bundle.instrument.coverage.effective_start
    assert prefix.instrument.coverage.complete is True
    rebased = bundle.prefix(date(2026, 10, 6), origin=date(2024, 10, 9))
    assert rebased.instrument.coverage.effective_start is None
    assert rebased.instrument.coverage.complete is True


@pytest.mark.asyncio
async def test_live_two_year_first_session_boundary_allows_v2_evaluation():
    frame = live_two_year_prices().iloc[1:]
    technical = _legacy_result(scorecard_as_of=date(2026, 10, 7), scorecard_ticker="NVDA")
    technical.raw_dataframe = frame
    result = await AnalysisStrategyService(ChartBundleLoader(PriceResponse(frame))).evaluate(
        "NVDA", technical, as_of=date(2026, 10, 7), position=PositionSnapshot(quantity=5)
    )
    swing = result.strategy_run.signal_bundles[0]
    assert swing.data_status is DataStatus.COMPLETE
    assert swing.entry_opportunity.status is EntryOpportunityStatus.NO_RECENT_SIGNAL


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["leading_two", "leading_one_and_internal", "internal_only"])
async def test_live_two_year_boundary_policy_does_not_hide_other_gaps(case):
    full = live_two_year_prices()
    sparse = (
        full.iloc[2:]
        if case == "leading_two"
        else full.iloc[1:].drop(pd.Timestamp("2026-10-06"))
        if case == "leading_one_and_internal"
        else full.drop(pd.Timestamp("2026-10-06"))
    )
    bundle = await load("NVDA", sparse, sparse)
    assert bundle.instrument.coverage.complete is False
    assert bundle.market.coverage.complete is False
    assert date(2024, 10, 7) in bundle.instrument.coverage.expected_sessions
    assert date(2026, 10, 6) in bundle.instrument.coverage.expected_sessions


@pytest.mark.asyncio
async def test_live_two_year_boundary_policy_does_not_hide_trailing_market_gap():
    full = live_two_year_prices()
    bundle = await load("NVDA", full.iloc[1:], full.iloc[1:-1])
    assert bundle.market.coverage.complete is False
    assert date(2026, 10, 7) in bundle.market.coverage.expected_sessions

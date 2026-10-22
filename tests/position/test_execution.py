from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.position.execution import check_entry_execution
from src.position.models import ExecutionResult, MarketOpenSnapshot


@pytest.mark.parametrize(
    "open_price,result",
    [
        ("105", ExecutionResult.PASS),
        ("105.01", ExecutionResult.GAP_LIMIT_EXCEEDED),
    ],
)
def test_dated_swing_event_checks_strict_five_percent_gap(open_price, result):
    check = check_entry_execution(
        strategy_run_id="run",
        source_event_id="swing-event",
        market_session=date(2026, 10, 2),
        market=MarketOpenSnapshot(date(2026, 10, 2), Decimal(open_price), "hash"),
        policy_version="v1",
        reference_entry=Decimal("100"),
        checked_at=datetime(2026, 10, 2, 14, tzinfo=UTC),
    )
    assert check.result is result


def test_playbook_without_source_event_never_gets_gap_result():
    check = check_entry_execution(
        strategy_run_id="run",
        source_event_id=None,
        market_session=date(2026, 10, 2),
        market=MarketOpenSnapshot(date(2026, 10, 2), Decimal("200"), "hash"),
        policy_version="v1",
        reference_entry=Decimal("100"),
        checked_at=datetime(2026, 10, 2, 14, tzinfo=UTC),
    )
    assert check.result is ExecutionResult.PASS


def test_stale_and_missing_market_data_are_separate_results():
    kwargs = {
        "strategy_run_id": "run",
        "source_event_id": None,
        "market_session": date(2026, 10, 2),
        "policy_version": "v1",
    }
    missing = check_entry_execution(market=None, **kwargs)
    stale = check_entry_execution(
        market=MarketOpenSnapshot(date(2026, 10, 1), Decimal("10"), "old"),
        **kwargs,
    )
    assert missing.result is ExecutionResult.MISSING_MARKET_DATA
    assert stale.result is ExecutionResult.STALE_SESSION


def test_check_identity_ignores_observation_time_and_result():
    kwargs = {
        "strategy_run_id": "run",
        "source_event_id": "event",
        "market_session": date(2026, 10, 2),
        "policy_version": "v1",
        "reference_entry": Decimal("100"),
    }
    first = check_entry_execution(
        market=MarketOpenSnapshot(date(2026, 10, 2), Decimal("105"), "same"),
        checked_at=datetime(2026, 10, 2, 14, tzinfo=UTC),
        **kwargs,
    )
    second = check_entry_execution(
        market=MarketOpenSnapshot(date(2026, 10, 2), Decimal("106"), "same"),
        checked_at=datetime(2026, 10, 2, 15, tzinfo=UTC),
        **kwargs,
    )
    assert first.check_id == second.check_id
    assert first.result is ExecutionResult.PASS
    assert second.result is ExecutionResult.GAP_LIMIT_EXCEEDED
    assert (
        check_entry_execution(
            market=MarketOpenSnapshot(date(2026, 10, 2), Decimal("105"), "changed"),
            **kwargs,
        ).check_id
        != first.check_id
    )

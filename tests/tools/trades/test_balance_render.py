"""현재 보유는 과거 투자 건의 계산·배정과 분리한다."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.providers.nhplug import NHBalanceSnapshot, NHHolding
from src.tools.trades import JournalError, TradeJournal, render_cases
from tests.tools.trades.test_journal import trade


def holding(**values):
    return NHHolding(
        **{
            "account_id": "nh-synthetic-account",
            "market": "US",
            "currency": "USD",
            "ticker": "AAPL",
            "name": "Apple",
            "quantity": Decimal("0.004552"),
            "avg_price": Decimal("100"),
            "current_price": Decimal("120"),
            "market_value": Decimal("0.54624"),
            "unrealized_pnl": Decimal("0.09104"),
            "credit_type": "현금",
            **values,
        }
    )


def snapshot(*rows, account="nh-synthetic-account"):
    return NHBalanceSnapshot(account, datetime(2026, 11, 6, 12, tzinfo=UTC), rows, ())


@pytest.mark.parametrize("detailed", [False, True])
def test_current_quantity_is_once_per_account_not_per_historical_case(tmp_path, detailed):
    journal = TradeJournal(tmp_path / "journal.sqlite3")
    journal.sync(
        [
            trade("buy", day="2026-10-01", quantity="2"),
            trade("sell", day="2026-10-02", quantity="2", side="sell"),
            trade("reentry", day="2026-11-01", quantity="1"),
        ]
    )
    cases = journal.cases()
    assert len(cases) == 2
    observed = snapshot(
        holding(),
        holding(credit_type="신용", loan_date=date(2026, 10, 1), quantity=Decimal("2")),
    )
    before = journal.path.read_bytes()
    rendered = render_cases(cases, detailed=detailed, snapshots=[observed])
    assert rendered.count("NH 현재 보유") == 1
    assert rendered.count("| AAPL | Apple |") == 2
    assert "| 현금 | - | 0.004552 |" in rendered
    assert "| 신용 | 2026-10-01 | 2 |" in rendered
    assert "2026-11-06T12:00:00+00:00" in rendered
    assert "투자 건에 배분하지 않습니다" in rendered
    if not detailed:
        assert "\n## 거래 이력\n" in rendered
        assert "\n### 선택 투자 건의 월별 거래금액\n" in rendered
    assert journal.path.read_bytes() == before


def test_empty_live_account_is_distinct_from_unqueried_balance(tmp_path):
    journal = TradeJournal(tmp_path / "journal.sqlite3")
    journal.sync([trade()])
    queried = render_cases(journal.cases(), snapshots=[snapshot()])
    offline = render_cases(journal.cases())
    assert "보유 내역 없음 (국내·미국 조회 완료)" in queried
    assert "NH 현재 잔고: 미조회" not in queried
    assert "NH 현재 잔고: 미조회" in offline
    assert "보유 내역 없음" not in offline


def test_balance_accounts_cannot_be_mixed_or_partially_missing(tmp_path):
    journal = TradeJournal(tmp_path / "journal.sqlite3")
    journal.sync([trade(), trade("other", account_id="other")])
    cases = journal.cases()
    with pytest.raises(JournalError):
        render_cases(cases, snapshots=[snapshot()])
    with pytest.raises(JournalError):
        render_cases(
            cases, snapshots=[snapshot(holding(account_id="other")), snapshot(account="other")]
        )
    with pytest.raises(JournalError):
        render_cases(cases, snapshots=[snapshot(), snapshot(), snapshot(account="other")])
    output = render_cases(cases, snapshots=[snapshot(holding()), snapshot(account="other")])
    assert output.count("NH 현재 보유") == 2
    assert output.count("| AAPL | Apple |") == 1
    assert "보유 내역 없음" in output


def test_export_preserves_live_section_without_changing_historical_quantity(tmp_path):
    journal = TradeJournal(tmp_path / "journal.sqlite3")
    journal.sync([trade(side="sell")])
    case = journal.cases()[0]
    assert case.quantity is None
    output = tmp_path / "journal.md"
    rendered = journal.export(snapshots=[snapshot(holding())], output=output)
    assert "0.004552" in rendered
    assert "이력 불완전" in rendered
    assert journal.show(case.case_id).quantity is None
    assert output.read_text() == rendered
    assert output.stat().st_mode & 0o777 == 0o600

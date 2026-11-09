"""실제 SQLite와 provider 모델로 장부의 보존/순서 경계를 검증한다."""

import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from src.providers.nhplug import NHTrade
from src.tools.trades import (
    JournalConflictError,
    JournalError,
    SourceLink,
    TradeJournal,
    render_case,
)


def trade(source_id="buy-1", day="2026-11-01", side="buy", quantity="2", **kwargs):
    values = {
        "account_id": "nh-synthetic-account",
        "market": "KR",
        "currency": "KRW",
        "ticker": "005930",
        "name": "삼성전자",
        "side": side,
        "quantity": Decimal(quantity),
        "price": Decimal("70000"),
        "amount": Decimal(quantity) * Decimal("70000"),
        "trade_date": date.fromisoformat(day),
        "query_date": date.fromisoformat(day),
        "source_id": source_id,
        "source": "kr_order_cumulative",
        "trade_date_basis": "order_date",
        "credit_type": "general",
    }
    values.update(kwargs)
    return NHTrade(**values)


def test_sync_cumulative_update_preserves_case_notes_and_exact_decimals(tmp_path):
    journal = TradeJournal(tmp_path / "private" / "trades.sqlite3")
    original = trade()
    first = journal.sync([original])
    case_id = journal.cases()[0].case_id
    journal.note(case_id, reason="실적 회복", strategy_label="swing", review="분할 완료")
    assert (first.inserted, first.updated, first.unchanged) == (1, 0, 0)
    assert journal.sync([original]).unchanged == 1
    update = replace(original, quantity=Decimal("5"), amount=Decimal("350000"))
    result = journal.sync([update])
    restored = TradeJournal(journal.path).show(case_id)
    assert (result.inserted, result.updated) == (0, 1)
    assert result.warnings
    assert len(restored.trades) == 1
    assert restored.quantity == Decimal("5")
    assert restored.notes.reason == "실적 회복"
    assert restored.notes.strategy_label == "swing"
    assert restored.notes.review == "분할 완료"
    assert (journal.path.stat().st_mode & 0o777) == 0o600
    assert (journal.path.parent.stat().st_mode & 0o777) == 0o700
    with sqlite3.connect(journal.path) as connection:
        assert connection.execute("SELECT typeof(payload) FROM trades").fetchone()[0] == "text"


def test_fractional_us_trade_roundtrip_render_and_export(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    item = trade(
        market="US",
        currency="USD",
        ticker="AAPL",
        name="Apple",
        quantity="0.004552",
        source="us_settled_transaction",
        price=Decimal("200.15"),
        amount=Decimal("0.9110828"),
        query_date=date(2026, 11, 3),
        trade_date_basis="actual_date",
        fee_fields={"fee_raw": Decimal("0.000001")},
        tax_fields={"tax_raw": Decimal("0.002")},
    )
    journal.sync([item])
    case = journal.cases()[0]
    assert case.quantity == Decimal("0.004552")
    assert case.trades[0].amount == Decimal("0.9110828")
    journal.note(
        case.case_id, source_links=(SourceLink("https://example.test/report", "retrospective"),)
    )
    output = tmp_path / "exports" / "notes.md"
    markdown = journal.export(case_id=case.case_id, output=output, detailed=True)
    assert "0.004552" in markdown
    assert "2026-11-01" in markdown and "2026-11-03" in markdown
    assert "결제" in markdown and "사후" in markdown
    assert "fee_raw=0.000001" in markdown and "tax_raw=0.002" in markdown
    assert output.read_text() == markdown
    assert (output.stat().st_mode & 0o777) == 0o600


def test_default_export_is_a_readable_summary_with_details_opt_in(tmp_path):
    journal = TradeJournal(tmp_path / "journal.sqlite3")
    item = trade(quantity="3", fee_fields={"fee_raw": Decimal("7")})
    journal.sync([item])
    case = journal.cases()[0]
    journal.note(case.case_id, reason="실적 회복 확인 후 진입")
    summary = journal.export()
    assert "## 선택 투자 건의 월별 거래금액" in summary and "## 투자 건 요약" in summary
    assert "실적 회복 확인 후 진입" in summary
    assert "미기록" not in summary and "fee_raw" not in summary
    assert case.case_id not in summary and item.trade_id not in summary
    assert f"계좌: {case.account_id}" in summary
    assert "### 거래 사실" not in summary
    assert len(summary.splitlines()) < 35
    detailed = journal.export(detailed=True)
    assert case.case_id in detailed and item.trade_id in detailed
    assert "fee_raw=7" in detailed


def test_summary_never_combines_accounts_or_currencies(tmp_path):
    journal = TradeJournal(tmp_path / "journal.sqlite3")
    journal.sync(
        [
            trade(amount=Decimal("1000")),
            trade(
                account_id="other", market="US", currency="USD", ticker="AAPL", amount=Decimal("25")
            ),
        ]
    )
    summary = journal.export()
    assert "KR/KRW" in summary and "US/USD" in summary
    assert "1,000" in summary and "25" in summary and "1,025" not in summary
    assert "other" in summary and "## 계좌" in summary


def test_month_selection_discloses_full_case_scope_and_partial_account_totals(tmp_path):
    from src.tools.trades.render import render_cases

    journal = TradeJournal(tmp_path / "journal.sqlite3")
    journal.sync(
        [
            trade("oct-buy", day="2026-10-01", quantity="10", amount=Decimal("1000")),
            trade("nov-sell", day="2026-11-01", side="sell", quantity="3", amount=Decimal("300")),
            trade(
                "other-oct",
                day="2026-10-01",
                ticker="000660",
                name="SK하이닉스",
                amount=Decimal("2000"),
            ),
        ]
    )
    for summary in (
        journal.export(month="2026-11"),
        render_cases(journal.cases(start=date(2026, 11, 1), end=date(2026, 11, 30))),
    ):
        assert "2026-10" in summary and "1,000" in summary
        assert "SK하이닉스" not in summary and "2,000" not in summary
        assert "선택 투자 건의 월별 거래금액" in summary
        assert "선택한 투자 건의 전체 거래 이력" in summary
        assert "계좌 전체의 월별 합계를 뜻하지 않습니다" in summary


def test_conflicting_or_stale_batch_rolls_back_every_fact(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    initial = trade(quantity="5")
    journal.sync([initial])
    case_id = journal.cases()[0].case_id
    journal.note(case_id, reason="보존")
    new = trade("new", day="2026-10-31")
    with pytest.raises(JournalConflictError):
        journal.sync([new, replace(initial, quantity=Decimal("2"))])
    assert len(journal.show(case_id).trades) == 1
    assert journal.show(case_id).quantity == Decimal("5")
    assert journal.show(case_id).notes.reason == "보존"
    with pytest.raises(JournalConflictError):
        journal.sync([new, replace(initial, ticker="000660")])
    assert len(journal.cases()) == 1
    assert len(journal.show(case_id).trades) == 1


def test_failed_input_iteration_never_commits_partial_results(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")

    def broken_collection():
        yield trade()
        raise RuntimeError("page failed")

    with pytest.raises(RuntimeError, match="page failed"):
        journal.sync(broken_collection())
    assert journal.cases() == []


def test_same_day_unknown_order_stays_together_then_later_reentry_opens_case(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    buy = trade(quantity="2")
    sell = trade("sell", side="sell", quantity="2")
    reentry = trade("new-buy", day="2026-11-02", quantity="3")
    journal.sync([sell, reentry, buy])
    cases = journal.cases()
    assert len(cases) == 2
    assert cases[0].quantity == Decimal("0")
    assert cases[0].status == "closed"
    assert any("순서" in warning for warning in cases[0].warnings)
    assert len(cases[0].trades) == 2
    assert cases[1].quantity == Decimal("3")
    assert cases[1].status == "open"


def test_sell_first_and_oversell_never_create_negative_or_fabricated_closed_position(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync([trade(side="sell", quantity="3"), trade("buy", "2026-11-02", quantity="3")])
    case = journal.cases()[0]
    assert case.incomplete is True
    assert case.quantity is None
    assert case.status == "incomplete"
    assert "불완전" in render_case(case)
    assert len(journal.cases()) == 1


def test_books_preserve_account_market_currency_credit_and_loan_boundaries(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade("1"),
            trade("2", account_id="nh-other"),
            trade("3", market="US", currency="USD"),
            trade("4", currency="USD"),
            trade("5", credit_type="financing"),
            trade("6", credit_type="financing", loan_date=date(2026, 10, 1)),
        ]
    )
    assert len(journal.cases()) == 6


def test_backfill_preserves_existing_case_ids_and_notes_with_warning(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    buy = trade("buy", "2026-11-03")
    exit_trade = trade("sell", "2026-11-04", "sell")
    reentry = trade("again", "2026-11-05")
    journal.sync([buy, exit_trade, reentry])
    first, second = journal.cases()
    journal.note(first.case_id, reason="첫 전략")
    journal.note(second.case_id, reason="두 번째 전략")
    journal.sync([trade("late", "2026-11-01")])
    assert journal.show(first.case_id).notes.reason == "첫 전략"
    assert journal.show(second.case_id).notes.reason == "두 번째 전략"
    assert journal.show(second.case_id).trades[0].source_id == "again"
    assert any("과거" in warning for warning in journal.show(first.case_id).warnings)
    assert len(journal.cases()) == 2


def test_split_boundary_and_untouched_notes_survive_resync_and_late_future_trade(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    first = trade("first", "2026-11-01")
    second = trade("second", "2026-11-02")
    last = trade("last", "2026-11-04")
    journal.sync([first, second, last])
    original_id = journal.cases()[0].case_id
    journal.note(original_id, reason="첫 아이디어", strategy_tags=("swing",))
    separated = journal.split(second.trade_id, title="별도 투자", strategy_label="momentum")
    journal.note(separated.case_id, reason="두 번째 아이디어")
    journal.sync([first, replace(second, quantity=Decimal("5"), amount=Decimal("350000")), last])
    journal.sync([trade("between", "2026-11-03")])
    assert journal.show(original_id).notes.reason == "첫 아이디어"
    assert [t.source_id for t in journal.show(original_id).trades] == ["first"]
    split_case = journal.show(separated.case_id)
    assert [t.source_id for t in split_case.trades] == ["second", "between", "last"]
    assert split_case.notes.title == "별도 투자"
    assert split_case.notes.strategy_label == "momentum"
    assert split_case.notes.reason == "두 번째 아이디어"
    assert split_case.quantity == Decimal("9")


def test_note_partial_updates_filters_and_month_export(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync([trade(), trade("later", "2026-12-01", ticker="000660")])
    case_id = journal.cases(ticker="005930")[0].case_id
    journal.note(
        case_id, reason="진입", invalidation="이탈", add_condition="눌림", strategy_tags=("trend",)
    )
    journal.note(case_id, review="복기", title="관찰")
    case = journal.show(case_id)
    assert (case.notes.reason, case.notes.invalidation, case.notes.add_condition) == (
        "진입",
        "이탈",
        "눌림",
    )
    assert (
        len(
            journal.cases(
                start=date(2026, 11, 1),
                end=date(2026, 11, 30),
                market="KR",
                reviewed=True,
                tags=("trend",),
            )
        )
        == 1
    )
    assert len(journal.cases(reviewed=False)) == 1
    assert "005930" in journal.export(month="2026-11")
    assert "000660" not in journal.export(month="2026-11")
    journal.note(case_id, review="", strategy_tags=())
    assert journal.cases(reviewed=True) == []
    with pytest.raises(JournalError):
        journal.note(case_id, unknown="bad")
    with pytest.raises(JournalError):
        journal.show("missing")
    with pytest.raises(JournalError):
        journal.note(case_id, source_links=(SourceLink("/local/file", "made_up"),))


def test_unknown_trade_date_discloses_query_basis(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade(
                market="US",
                currency="USD",
                trade_date=None,
                trade_date_basis="unknown",
                source="us_settled_transaction",
            )
        ]
    )
    case = journal.cases()[0]
    assert any("거래일" in warning for warning in case.warnings)
    assert "unknown" in render_case(case)


def test_missing_actual_date_does_not_prove_a_closed_case_boundary(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade("unknown", trade_date=None, trade_date_basis="unknown"),
            trade("exit", "2026-11-02", "sell"),
            trade("reentry", "2026-11-03"),
        ]
    )
    assert len(journal.cases()) == 1
    assert journal.cases()[0].quantity == Decimal("2")
    assert any("거래일" in warning for warning in journal.cases()[0].warnings)


def test_same_day_manual_boundary_routes_later_backfills_to_both_sides(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    before = trade("b")
    boundary = trade("c")
    after = trade("d")
    journal.sync([before, boundary, after])
    original_id = journal.cases()[0].case_id
    separated = journal.split(boundary.trade_id)
    journal.sync([trade("e"), trade("f")])
    assert {item.source_id for item in journal.show(original_id).trades} == {"b", "e"}
    assert {item.source_id for item in journal.show(separated.case_id).trades} == {"c", "d", "f"}


@pytest.mark.parametrize(
    "quantity,price,amount", [("0", "1", "0"), ("-1", "1", "1"), ("1", "NaN", "1")]
)
def test_invalid_financial_values_cannot_enter_journal(tmp_path, quantity, price, amount):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    with pytest.raises(JournalError):
        journal.sync([trade(quantity=quantity, price=Decimal(price), amount=Decimal(amount))])
    assert journal.cases() == []


@pytest.mark.parametrize("target_kind", ["database", "existing_notes", "symlink"])
def test_export_never_overwrites_existing_database_or_user_files(tmp_path, target_kind):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync([trade()])
    notes_path = tmp_path / "notebook.md"
    notes_path.write_text("사용자 원본\n")
    if target_kind == "database":
        output = journal.path
    elif target_kind == "symlink":
        output = tmp_path / "notes-link.md"
        output.symlink_to(notes_path)
    else:
        output = notes_path
    before = output.read_bytes()
    with pytest.raises(JournalError):
        journal.export(output=output)
    assert output.read_bytes() == before
    assert notes_path.read_text() == "사용자 원본\n"
    assert journal.cases()[0].quantity == Decimal("2")


def test_initial_same_day_collection_is_not_labeled_as_late_backfill(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync([trade("a"), trade("b")])
    assert not any("과거 거래" in warning for warning in journal.cases()[0].warnings)


def test_future_trade_follows_last_same_day_manual_case_when_earlier_case_closed(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync([trade("b"), trade("c", side="sell"), trade("h")])
    split_case = journal.split(trade("h").trade_id)
    journal.sync([trade("next", "2026-11-02")])
    assert len(journal.cases()) == 2
    assert {item.source_id for item in journal.show(split_case.case_id).trades} == {"h", "next"}


def test_positive_starting_balance_is_partial_history_not_a_new_position(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    item = trade(
        quantity="0.004552",
        market="US",
        currency="USD",
        ticker="GOOGL",
        source="us_settled_transaction",
        trade_date_basis="actual_date",
        balance_before=Decimal("0.158601"),
        balance_after=Decimal("0.163153"),
    )
    journal.sync([item])
    case = TradeJournal(journal.path).cases()[0]
    assert case.incomplete is True
    assert case.quantity is None
    assert case.status == "incomplete"
    assert case.trades[0].balance_before == Decimal("0.158601")
    assert case.trades[0].balance_after == Decimal("0.163153")
    assert any("시작 잔고" in warning for warning in case.warnings)
    rendered = render_case(case)
    assert "거래 전 잔고: 0.158601" in rendered
    assert "거래 후 잔고: 0.163153" in rendered
    assert "장부 잔여 수량: 미확인" in rendered


def test_zero_start_with_later_same_day_positive_balances_is_not_missing_history(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    # Stable trade IDs put b before a; that order cannot identify the first execution.
    journal.sync(
        [
            trade("a", quantity="2", balance_before=Decimal("0"), balance_after=Decimal("2")),
            trade("b", quantity="3", balance_before=Decimal("2"), balance_after=Decimal("5")),
        ]
    )
    case = journal.cases()[0]
    assert case.incomplete is False
    assert case.quantity == Decimal("5")
    assert case.status == "open"


def test_positive_start_remains_incomplete_after_exit_and_later_buy(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade("a", quantity="2", balance_before=Decimal("3"), balance_after=Decimal("5")),
            trade(
                "b",
                "2026-11-02",
                "sell",
                quantity="5",
                balance_before=Decimal("5"),
                balance_after=Decimal("0"),
            ),
            trade(
                "c",
                "2026-11-03",
                quantity="1",
                balance_before=Decimal("0"),
                balance_after=Decimal("1"),
            ),
        ]
    )
    assert len(journal.cases()) == 1
    assert journal.cases()[0].quantity is None
    assert journal.cases()[0].incomplete is True


def test_old_payload_without_balance_fields_still_reads_and_resyncs(tmp_path):
    import json

    journal = TradeJournal(tmp_path / "trades.sqlite3")
    item = trade()
    journal.sync([item])
    case_id = journal.cases()[0].case_id
    journal.note(case_id, reason="기존 메모")
    with sqlite3.connect(journal.path) as connection:
        payload = json.loads(connection.execute("SELECT payload FROM trades").fetchone()[0])
        payload.pop("balance_before", None)
        payload.pop("balance_after", None)
        connection.execute("UPDATE trades SET payload = ?", (json.dumps(payload),))
    restored = TradeJournal(journal.path).show(case_id)
    assert restored.trades[0].balance_before is None
    assert restored.trades[0].balance_after is None
    assert journal.sync([item]).unchanged == 1
    assert journal.show(case_id).notes.reason == "기존 메모"


def test_resync_can_enrich_previously_unknown_balances_without_losing_notes(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    item = trade()
    journal.sync([item])
    case_id = journal.cases()[0].case_id
    journal.note(case_id, reason="보존")
    result = journal.sync([replace(item, balance_before=Decimal("3"), balance_after=Decimal("5"))])
    assert result.updated == 1
    assert result.warnings
    assert journal.show(case_id).notes.reason == "보존"
    assert journal.show(case_id).incomplete is True
    with pytest.raises(JournalConflictError):
        journal.sync([replace(item, balance_before=Decimal("4"), balance_after=Decimal("6"))])
    assert journal.show(case_id).trades[0].balance_before == Decimal("3")


def test_source_balance_discontinuity_prevents_false_full_exit(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade("first", quantity="2", balance_before=Decimal("0"), balance_after=Decimal("2")),
            trade(
                "exit",
                "2026-11-03",
                "sell",
                quantity="2",
                balance_before=Decimal("5"),
                balance_after=Decimal("3"),
            ),
            trade(
                "next",
                "2026-11-04",
                quantity="1",
                balance_before=Decimal("3"),
                balance_after=Decimal("4"),
            ),
        ]
    )
    assert len(journal.cases()) == 1
    case = journal.cases()[0]
    assert case.incomplete is True
    assert case.quantity is None
    assert case.status == "incomplete"
    assert any("불일치" in warning for warning in case.warnings)
    assert all("입고" not in warning for warning in case.warnings)


def test_same_day_unordered_buy_sell_balances_can_match_observed_trades(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade("a", quantity="5", balance_before=Decimal("0"), balance_after=Decimal("5")),
            trade(
                "b",
                side="sell",
                quantity="2",
                balance_before=Decimal("5"),
                balance_after=Decimal("3"),
            ),
            trade("c", quantity="1", balance_before=Decimal("3"), balance_after=Decimal("4")),
        ]
    )
    case = journal.cases()[0]
    assert case.incomplete is False
    assert case.quantity == Decimal("4")
    assert not any("불일치" in warning for warning in case.warnings)
    assert any("순서" in warning for warning in case.warnings)


def test_branching_same_day_splits_route_backfill_by_latest_family_boundary(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")

    def entry(source_id):
        return trade(source_id, quantity="1", account_id="nh-synthetic")

    journal.sync([entry("0-18"), entry("0-2"), entry("0-9"), entry("0-7")])
    root_id = journal.cases()[0].case_id
    later = journal.split(entry("0-9").trade_id, title="later-boundary")
    earlier = journal.split(entry("0-2").trade_id, title="earlier-boundary")
    journal.note(root_id, reason="original notes")
    journal.note(later.case_id, reason="later notes")
    journal.note(earlier.case_id, reason="earlier notes")
    journal.sync([entry("0-13"), entry("0-19"), entry("0-23")])
    assert {item.source_id for item in journal.show(root_id).trades} == {"0-18", "0-13"}
    assert {item.source_id for item in journal.show(earlier.case_id).trades} == {"0-2", "0-19"}
    assert {item.source_id for item in journal.show(later.case_id).trades} == {"0-9", "0-23", "0-7"}
    assert journal.show(root_id).notes.reason == "original notes"
    assert journal.show(later.case_id).notes.reason == "later notes"
    assert journal.show(earlier.case_id).notes.reason == "earlier notes"
    assert journal.sync([entry("0-13"), entry("0-19"), entry("0-23")]).unchanged == 3
    assert len(journal.cases()) == 3


def test_old_manual_boundaries_do_not_capture_an_automatic_reentry_root(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    first = trade("b", quantity="1")
    second = trade("c", quantity="1")
    exit_trade = trade("exit", "2026-11-02", "sell", quantity="2")
    reentry = trade("entry", "2026-11-03", quantity="1")
    journal.sync([first, second, exit_trade, reentry])
    automatic_id = journal.cases()[1].case_id
    journal.note(automatic_id, reason="new investment")
    journal.split(second.trade_id, title="old manual strategy")
    journal.sync([trade("after", "2026-11-04", quantity="1")])
    case = journal.show(automatic_id)
    assert {item.source_id for item in case.trades} == {"entry", "after"}
    assert case.notes.reason == "new investment"
    assert case.quantity == Decimal("2")
    assert len(journal.cases()) == 3


def test_public_us_fixture_through_provider_and_sqlite_keeps_partial_history(tmp_path):
    import json
    from pathlib import Path

    import httpx

    from src.providers.nhplug import NHAccount, NHClient
    from tests.harness.nhplug_contract import validate_nh_fixture

    fixture_root = Path(__file__).parents[2] / "fixtures" / "nhplug"
    fixtures = {}
    for name in ("token", "kr_executions", "us_history"):
        body = json.loads((fixture_root / f"{name}.json").read_text(), parse_float=Decimal)
        validate_nh_fixture(name, body)
        fixtures[name] = body
    paths = {
        "/oauth2/token": "token",
        "/krstock/inquiry/v1/dailyOrderExecution": "kr_executions",
        "/gbstock/inquiry/v1/dailyTransaction": "us_history",
    }

    def respond(request):
        return httpx.Response(
            200,
            content=json.dumps(fixtures[paths[request.url.path]], default=str),
            headers={"cts_flag": "N"},
        )

    with NHClient(
        "synthetic-app",
        "synthetic-secret",
        cache_dir=tmp_path / "tokens",
        transport=httpx.MockTransport(respond),
    ) as client:
        trades = client.trades(NHAccount("SYNTHETIC", "01"), date(2025, 4, 21), date(2025, 4, 21))
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(trades)
    case = journal.cases(ticker="GOOGL")[0]
    assert case.trades[0].quantity == Decimal("0.004552")
    assert case.trades[0].balance_before == Decimal("0.158601")
    assert case.trades[0].balance_after == Decimal("0.163153")
    assert case.incomplete is True
    assert case.quantity is None
    assert "거래 전 잔고: 0.158601" in render_case(case)
    assert "거래 후 잔고: 0.163153" in render_case(case)
    assert journal.sync(trades).unchanged == 5


def test_same_day_missing_movement_cannot_pass_individual_balance_intervals(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade("first", quantity="2", balance_before=Decimal("0"), balance_after=Decimal("2")),
            trade("later", quantity="3", balance_before=Decimal("1"), balance_after=Decimal("4")),
        ]
    )
    case = journal.cases()[0]
    assert case.incomplete is True
    assert case.quantity is None
    assert any("연결" in warning for warning in case.warnings)
    assert "장부 잔여 수량: 미확인" in render_case(case)


def test_disconnected_balanced_cycles_are_not_a_complete_daily_ledger(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade(
                "cycle-a-buy", quantity="5", balance_before=Decimal("0"), balance_after=Decimal("5")
            ),
            trade(
                "cycle-a-sell",
                side="sell",
                quantity="5",
                balance_before=Decimal("5"),
                balance_after=Decimal("0"),
            ),
            trade(
                "cycle-b-buy", quantity="1", balance_before=Decimal("2"), balance_after=Decimal("3")
            ),
            trade(
                "cycle-b-sell",
                side="sell",
                quantity="1",
                balance_before=Decimal("3"),
                balance_after=Decimal("2"),
            ),
        ]
    )
    case = journal.cases()[0]
    assert case.incomplete is True
    assert case.quantity is None
    assert case.status == "incomplete"
    assert any("연결" in warning for warning in case.warnings)


def test_partial_balance_pairs_keep_necessary_checks_and_disclose_unverified_connectivity(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade("first", quantity="2", balance_before=Decimal("0"), balance_after=Decimal("2")),
            trade("later", quantity="3", balance_before=Decimal("2"), balance_after=None),
        ]
    )
    case = journal.cases()[0]
    assert case.incomplete is False
    assert case.quantity == Decimal("5")
    assert any("연결성 미확인" in warning for warning in case.warnings)


def test_connected_unordered_balance_cycle_can_close_without_choosing_execution_order(tmp_path):
    journal = TradeJournal(tmp_path / "trades.sqlite3")
    journal.sync(
        [
            trade(
                "a",
                side="sell",
                quantity="2",
                balance_before=Decimal("2"),
                balance_after=Decimal("0"),
            ),
            trade("b", quantity="2", balance_before=Decimal("0"), balance_after=Decimal("2")),
        ]
    )
    case = journal.cases()[0]
    assert case.incomplete is False
    assert case.quantity == Decimal("0")
    assert case.status == "closed"
    assert any("순서" in warning for warning in case.warnings)

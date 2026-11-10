"""Provider transport → SQLite → user-visible journal workflow."""

import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.tools.trades import TradeJournal
from tests.cli import test_broker_cli


nh_cli = test_broker_cli.nh_cli


runner = CliRunner()


def _sync(nh_cli, db):
    return runner.invoke(
        app,
        [
            "trades",
            "sync",
            "--account",
            nh_cli.account.account_id,
            "--from",
            "2025-04-21",
            "--to",
            "2025-04-21",
            "--db",
            str(db),
        ],
    )


def test_sync_list_show_note_and_resync_preserve_user_records(nh_cli, tmp_path):
    db = tmp_path / "journal.sqlite3"
    result = _sync(nh_cli, db)
    assert result.exit_code == 0, result.output
    assert "5" in result.output
    journal = TradeJournal(path=db)
    cases = journal.cases(ticker="GOOGL")
    assert len(cases) == 1
    case_id = cases[0].case_id
    result = runner.invoke(
        app,
        [
            "trades",
            "list",
            "--detail",
            "--db",
            str(db),
            "--ticker",
            "GOOGL",
            "--market",
            "US",
            "--from",
            "2025-04-21",
            "--to",
            "2025-04-21",
            "--not-reviewed",
        ],
    )
    assert result.exit_code == 0, result.output
    assert case_id in result.output and "0.004552" in result.output
    assert "NH 현재 보유" in result.output
    assert "결제" in result.output
    result = runner.invoke(
        app,
        [
            "trades",
            "note",
            case_id,
            "--db",
            str(db),
            "--reason",
            "분할 진입",
            "--review",
            "규칙 준수",
            "--tag",
            "swing",
            "--tag",
            "growth",
            "--source-link",
            "reports/past.md",
            "--provenance",
            "retrospective",
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app, ["trades", "note", case_id, "--db", str(db), "--title", "장기 관찰"]
    )
    assert result.exit_code == 0, result.output
    assert _sync(nh_cli, db).exit_code == 0
    result = runner.invoke(app, ["trades", "show", case_id, "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "분할 진입" in result.output and "장기 관찰" in result.output
    assert "사후 재계산" in result.output and "reports/past.md" in result.output
    assert "ACCOUNT NUMBER" not in result.output
    notes = journal.show(case_id).notes
    assert notes.strategy_tags == ("swing", "growth")
    assert notes.source_links[0].provenance == "retrospective"
    result = runner.invoke(
        app, ["trades", "list", "--detail", "--db", str(db), "--reviewed", "--tag", "growth"]
    )
    assert result.exit_code == 0 and case_id in result.output
    result = runner.invoke(app, ["trades", "list", "--db", str(db), "--tag", "missing"])
    assert result.exit_code == 0 and case_id not in result.output


def test_list_and_export_default_to_summary_with_explicit_details(nh_cli, tmp_path):
    db = tmp_path / "journal.sqlite3"
    assert _sync(nh_cli, db).exit_code == 0
    summary = runner.invoke(app, ["trades", "list", "--db", str(db)])
    assert summary.exit_code == 0
    assert "월별 거래금액" in summary.output and "nh-trade-" not in summary.output
    detail = runner.invoke(app, ["trades", "export", "--detail", "--db", str(db)])
    assert detail.exit_code == 0
    assert "nh-trade-" in detail.output and "거래 사실" in detail.output


@pytest.mark.parametrize("command", ["list", "show", "export"])
def test_current_balances_are_live_account_facts_separate_from_incomplete_history(
    nh_cli, tmp_path, command
):
    db = tmp_path / "journal.sqlite3"
    assert _sync(nh_cli, db).exit_code == 0
    journal = TradeJournal(db)
    case = journal.cases(ticker="GOOGL")[0]
    assert case.incomplete and case.quantity is None
    args = ["trades", command, "--db", str(db)]
    if command == "show":
        args.append(case.case_id)
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "NH 현재 보유" in result.output and "조회 완료:" in result.output
    assert "계좌 전체" in result.output and "투자 건에 배분하지 않습니다" in result.output
    assert "| GOOGL | 알파벳 Class A | US/USD | 현금 | - | 200 |" in result.output
    assert "이력 불완전" in result.output and journal.show(case.case_id).quantity is None
    assert nh_cli.clients[-1]._http.is_closed


@pytest.mark.parametrize("command", ["list", "show", "export"])
def test_no_balance_reads_only_local_journal_and_marks_balance_unqueried(nh_cli, tmp_path, command):
    db = tmp_path / "journal.sqlite3"
    assert _sync(nh_cli, db).exit_code == 0
    count = len(nh_cli.clients)
    args = ["trades", command, "--no-balance", "--db", str(db)]
    if command == "show":
        args.append(TradeJournal(db).cases()[0].case_id)
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "NH 현재 잔고: 미조회" in result.output
    assert len(nh_cli.clients) == count


def test_balance_failure_does_not_write_export_or_claim_no_holdings(nh_cli, tmp_path):
    db = tmp_path / "journal.sqlite3"
    assert _sync(nh_cli, db).exit_code == 0
    before = db.read_bytes()
    nh_cli.fail = "us_balance"
    output = tmp_path / "failed.md"
    result = runner.invoke(app, ["trades", "export", "--db", str(db), "--output", str(output)])
    assert result.exit_code == 1
    assert not output.exists() and before == db.read_bytes()
    assert "ACCOUNT NUMBER" not in result.output and "secret-token" not in result.output
    assert "보유 내역 없음" not in result.output


def test_empty_case_selection_does_not_query_balances(nh_cli, tmp_path):
    db = tmp_path / "journal.sqlite3"
    assert _sync(nh_cli, db).exit_code == 0
    count = len(nh_cli.clients)
    result = runner.invoke(app, ["trades", "export", "--month", "2020-01", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "조건에 맞는 투자 건이 없습니다" in result.output
    assert "NH 현재 잔고: 미조회" in result.output
    assert len(nh_cli.clients) == count


def test_split_and_markdown_export_stay_local(nh_cli, tmp_path):
    second = nh_cli.bodies["us_history"]["Output_0"][1]
    second["iem_cd"], second["iem_nm"] = "GOOGL US", "알파벳 Class A"
    db = tmp_path / "journal.sqlite3"
    assert _sync(nh_cli, db).exit_code == 0
    journal = TradeJournal(path=db)
    original = journal.cases(ticker="GOOGL")[0]
    result = runner.invoke(
        app,
        [
            "trades",
            "split",
            original.trades[1].trade_id,
            "--db",
            str(db),
            "--title",
            "별도 전략",
            "--strategy",
            "swing",
        ],
    )
    assert result.exit_code == 0, result.output
    case = next(case for case in journal.cases(ticker="GOOGL") if case.notes.title == "별도 전략")
    assert case.case_id != original.case_id
    assert case.notes.title == "별도 전략"
    output = tmp_path / "exports" / "journal.md"
    result = runner.invoke(
        app, ["trades", "export", "--db", str(db), "--case", case.case_id, "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    content = output.read_text()
    assert "별도 전략" in content and str(case.trades[0].quantity) in content
    assert not (tmp_path / "notebook").exists()


def test_sync_failure_does_not_create_partial_journal(nh_cli, tmp_path):
    db = tmp_path / "journal.sqlite3"
    nh_cli.fail = "us_history"
    result = _sync(nh_cli, db)
    assert result.exit_code == 1
    assert not db.exists()
    assert "ACCOUNT NUMBER" not in result.output and "secret-token" not in result.output
    assert nh_cli.clients[-1]._http.is_closed


@pytest.mark.parametrize("start,end", [("2025-04-22", "2025-04-21"), ("bad", "2025-04-21")])
def test_sync_rejects_bad_date_before_provider(nh_cli, tmp_path, start, end):
    result = runner.invoke(
        app, ["trades", "sync", "--from", start, "--to", end, "--db", str(tmp_path / "j.db")]
    )
    assert result.exit_code == 1
    assert not nh_cli.clients


def test_note_invalid_provenance_is_rejected_without_changing_notes(nh_cli, tmp_path):
    db = tmp_path / "journal.sqlite3"
    assert _sync(nh_cli, db).exit_code == 0
    journal = TradeJournal(path=db)
    case = journal.cases(ticker="GOOGL")[0]
    result = runner.invoke(
        app,
        [
            "trades",
            "note",
            case.case_id,
            "--db",
            str(db),
            "--reason",
            "preserved",
            "--source-link",
            "report.md",
            "--provenance",
            "unknown",
        ],
    )
    assert result.exit_code == 1
    assert journal.show(case.case_id).notes.reason == ""

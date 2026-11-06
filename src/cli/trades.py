"""NH 거래 수집 및 로컬 매매일지 CLI."""

from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from src.pipelines.broker_account import select_account
from src.providers.nhplug import NHClient, NHError
from src.tools.trades import JournalError, SourceLink, TradeJournal, render_case, render_cases


trades_app = typer.Typer(help="NH 거래 수집과 투자 건별 로컬 매매일지")
DEFAULT_DB = Path("data/broker/trades.sqlite3")
Database = Annotated[Path, typer.Option("--db", help="로컬 SQLite 장부 경로")]


def _date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError:
        raise JournalError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from None


def _range(start: str | None, end: str | None) -> tuple[date | None, date | None]:
    first, last = _date(start), _date(end)
    if first and last and first > last:
        raise JournalError("시작일은 종료일 이후일 수 없습니다.")
    return first, last


def _fail(error: Exception):
    if isinstance(error, JournalError):
        message = str(error)
    elif isinstance(error, NHError):
        message = "NH 거래 조회에 실패했습니다. 인증 설정 또는 연결 상태를 확인하세요."
    elif isinstance(error, ValueError):
        message = "계좌를 확인하세요: jarvis broker accounts 후 개인 실계좌 --account를 지정하세요."
    else:
        message = "장부 처리에 실패했습니다. 저장 경로와 입력을 확인하세요."
    typer.echo(f"매매일지 중단: {message}", err=True)
    raise typer.Exit(1) from None


@trades_app.command("sync")
def sync(
    start: Annotated[str, typer.Option("--from", help="조회 시작일 YYYY-MM-DD")],
    end: Annotated[str, typer.Option("--to", help="조회 종료일 YYYY-MM-DD")],
    account: Annotated[str | None, typer.Option("--account", help="공개 계좌 식별자")] = None,
    db: Database = DEFAULT_DB,
):
    """모든 시장·페이지 수집 성공 후 한 번에 장부에 반영한다."""
    try:
        first, last = _range(start, end)
        with NHClient.from_env() as client:
            selected = select_account(client.accounts(), account)
            collected = client.trades(selected, first, last)
        result = TradeJournal(path=db).sync(collected)
    except Exception as error:
        _fail(error)
    typer.echo(
        f"동기화 완료: 신규 {result.inserted} · 갱신 {result.updated} · 동일 {result.unchanged}"
    )
    typer.echo("미국 거래는 결제 반영 지연으로 최근 체결이 아직 없을 수 있습니다.")
    for warning in result.warnings:
        typer.echo(f"주의: {warning}")


@trades_app.command("list")
def list_cases(
    db: Database = DEFAULT_DB,
    detail: Annotated[bool, typer.Option("--detail", help="거래 ID·원문 필드·확인사항 전체 표시")] = False,
    ticker: Annotated[str | None, typer.Option("--ticker")] = None,
    start: Annotated[str | None, typer.Option("--from", help="YYYY-MM-DD")] = None,
    end: Annotated[str | None, typer.Option("--to", help="YYYY-MM-DD")] = None,
    market: Annotated[str | None, typer.Option("--market", help="KR 또는 US")] = None,
    reviewed: Annotated[
        bool | None, typer.Option("--reviewed/--not-reviewed", help="복기 기록 여부")
    ] = None,
    tag: Annotated[
        list[str] | None, typer.Option("--tag", help="전략 태그; 반복하면 모두 일치")
    ] = None,
):
    """종목·기간·시장·복기·태그로 투자 건을 찾는다."""
    try:
        first, last = _range(start, end)
        if market is not None:
            market = market.upper()
            if market not in ("KR", "US"):
                raise JournalError("시장은 KR 또는 US를 지정하세요.")
        cases = TradeJournal(path=db).cases(
            ticker=ticker,
            start=first,
            end=last,
            market=market,
            reviewed=reviewed,
            tags=tuple(tag) if tag is not None else None,
        )
        rendered = render_cases(cases, detailed=detail)
    except Exception as error:
        _fail(error)
    typer.echo(rendered)


@trades_app.command("show")
def show(case_id: str, db: Database = DEFAULT_DB):
    """투자 건의 거래 사실과 사용자 기록을 표시한다."""
    try:
        rendered = render_case(TradeJournal(path=db).show(case_id))
    except Exception as error:
        _fail(error)
    typer.echo(rendered)


@trades_app.command("note")
def note(
    case_id: str,
    db: Database = DEFAULT_DB,
    title: Annotated[str | None, typer.Option("--title")] = None,
    strategy: Annotated[str | None, typer.Option("--strategy")] = None,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    invalidation: Annotated[str | None, typer.Option("--invalidation")] = None,
    add_condition: Annotated[str | None, typer.Option("--add-condition")] = None,
    review: Annotated[str | None, typer.Option("--review")] = None,
    tag: Annotated[
        list[str] | None, typer.Option("--tag", help="전략 태그; 반복 가능, 지정 시 교체")
    ] = None,
    source_link: Annotated[
        list[str] | None, typer.Option("--source-link", help="로컬/URL 링크 기록만; 접속하지 않음")
    ] = None,
    provenance: Annotated[
        str | None,
        typer.Option(
            "--provenance", help="saved_at_trade(당시 저장) 또는 retrospective(사후 기록)"
        ),
    ] = None,
):
    """지정한 메모 필드만 갱신한다. 빈 문자열로 텍스트를 지운다."""
    try:
        if provenance is not None and provenance not in ("saved_at_trade", "retrospective"):
            raise JournalError("provenance는 saved_at_trade 또는 retrospective를 지정하세요.")
        if provenance is not None and not source_link:
            raise JournalError("--provenance는 --source-link와 함께 지정하세요.")
        fields = {
            key: value
            for key, value in (
                ("title", title),
                ("strategy_label", strategy),
                ("reason", reason),
                ("invalidation", invalidation),
                ("add_condition", add_condition),
                ("review", review),
            )
            if value is not None
        }
        if tag is not None:
            fields["strategy_tags"] = tuple(tag)
        if source_link is not None:
            fields["source_links"] = tuple(
                SourceLink(link, provenance or "saved_at_trade") for link in source_link
            )
        rendered = render_case(TradeJournal(path=db).note(case_id, **fields))
    except Exception as error:
        _fail(error)
    typer.echo(rendered)


@trades_app.command("split")
def split(
    trade_id: str,
    db: Database = DEFAULT_DB,
    title: Annotated[str | None, typer.Option("--title")] = None,
    strategy: Annotated[str | None, typer.Option("--strategy")] = None,
):
    """거래를 기준으로 투자 건을 수동 분리한다."""
    try:
        rendered = render_case(
            TradeJournal(path=db).split(trade_id, title=title, strategy_label=strategy)
        )
    except Exception as error:
        _fail(error)
    typer.echo(rendered)


@trades_app.command("export")
def export(
    db: Database = DEFAULT_DB,
    detail: Annotated[bool, typer.Option("--detail", help="요약 대신 거래 전체 내보내기")] = False,
    case_id: Annotated[str | None, typer.Option("--case", help="투자 건 ID")] = None,
    month: Annotated[str | None, typer.Option("--month", help="YYYY-MM")] = None,
    output: Annotated[Path | None, typer.Option("--output", help="로컬 Markdown 저장 경로")] = None,
):
    """Markdown으로 출력하거나 로컬 파일로 내보낸다."""
    try:
        rendered = TradeJournal(path=db).export(case_id=case_id, month=month, output=output, detailed=detail)
    except Exception as error:
        _fail(error)
    typer.echo(f"내보내기 완료: {output}" if output is not None else rendered)

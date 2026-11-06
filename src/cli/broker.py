"""NH 읽기 전용 계좌 CLI. 계좌 원문은 provider 경계 안에만 둔다."""

from typing import Annotated

import typer

from src.pipelines.broker_account import select_account
from src.providers.nhplug import NHBalanceSnapshot, NHClient


broker_app = typer.Typer(help="NH 연결 계좌와 국내·미국 잔고 조회")


def fetch_snapshot(selector: str | None = None) -> NHBalanceSnapshot:
    """계좌 선택과 양 시장 조회를 완료하고 연결을 닫는다."""
    with NHClient.from_env() as client:
        account = select_account(client.accounts(), selector)
        return client.balances(account)


@broker_app.command("accounts")
def accounts():
    """마스킹 계좌번호, 공개 식별자, 계좌유형을 표시한다."""
    try:
        with NHClient.from_env() as client:
            rows = client.accounts()
    except Exception:
        typer.echo("NH 계좌 조회 실패: 인증 설정 또는 연결 상태를 확인하세요.", err=True)
        raise typer.Exit(1) from None
    typer.echo("공개 계좌 식별자 | 마스킹 계좌번호 | 계좌유형 | 개인 실계좌")
    for row in rows:
        typer.echo(
            f"{row.account_id} | {row.masked_number} | {row.account_type} | {'예' if row.is_personal else '아니요'}"
        )
    if not rows:
        typer.echo("연결된 계좌가 없습니다.")


@broker_app.command("holdings")
def holdings(
    account: Annotated[
        str | None, typer.Option("--account", help="broker accounts의 공개 계좌 식별자")
    ] = None,
):
    """국내·미국 원본 구분별 잔고와 출처별 합계를 표시한다."""
    try:
        snapshot = fetch_snapshot(account)
    except ValueError:
        typer.echo(
            "NH 계좌 선택 실패: jarvis broker accounts 후 개인 실계좌 --account를 지정하세요.",
            err=True,
        )
        raise typer.Exit(1) from None
    except Exception:
        typer.echo("NH 잔고 조회 실패: 인증 설정 또는 연결 상태를 확인하세요.", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"NH 계좌: {snapshot.account_id} · 조회 완료: {snapshot.as_of.isoformat()}")
    typer.echo(
        "시장 | 통화 | 종목 | 이름 | 구분 | 수량 | 매입단가 | NH 평가가격 | 평가액 | 평가손익"
    )
    for row in snapshot.holdings:
        typer.echo(
            " | ".join(
                str(value)
                for value in (
                    row.market,
                    row.currency,
                    row.ticker,
                    row.name,
                    row.credit_type,
                    row.quantity,
                    row.avg_price,
                    row.current_price,
                    row.market_value,
                    row.unrealized_pnl,
                )
            )
        )
        typer.echo(f"가격 기준: {row.price_basis} · 가격일: {row.price_date or '미확인'}")
        if row.loan_date or row.expiry_date:
            typer.echo(f"대출일: {row.loan_date or '-'} · 만기일: {row.expiry_date or '-'}")
        if row.settled_quantity is not None or row.unsettled_quantity is not None:
            typer.echo(f"결제 수량: {row.settled_quantity} · 미결제 수량: {row.unsettled_quantity}")
    typer.echo("출처별 합계: 총자산 범위가 겹칠 수 있어 시장·통화 간 합산하지 않습니다.")
    for summary in snapshot.summaries:
        typer.echo(f"{summary.market}/{summary.currency} · 출처: {summary.source}")
        typer.echo(
            f"총자산: {summary.total_assets} · 평가액: {summary.market_value} · 평가손익: {summary.unrealized_pnl} · 현금: {summary.cash}"
        )
        typer.echo(f"자산 범위: {summary.assets_scope}")

"""NH 사실 표기. 환산·수익률 재계산이나 시장별 총자산 합산을 하지 않는다."""

from collections.abc import Sequence
from decimal import Decimal

from src.providers.nhplug import NHBalanceSnapshot, NHHolding
from src.tools.disclosure import is_korean_ticker


def _number(value: Decimal) -> str:
    return format(value, ",f").rstrip("0").rstrip(".") if "." in str(value) else format(value, ",f")


def supports_stock_analysis(holding: NHHolding) -> bool:
    """국내 전체 잔고에 섞인 RP 등 비주식 코드를 시세 provider에 보내지 않는다."""
    return holding.market != "KR" or is_korean_ticker(holding.ticker)


def render_broker_header(snapshot: NHBalanceSnapshot | None) -> list[str]:
    if snapshot is None:
        return []
    lines = [
        "## NH 실제 계좌",
        f"계좌 식별자: {snapshot.account_id} · 조회 완료: {snapshot.as_of.isoformat(timespec='seconds')}",
        "조회 시각은 가격 거래일이 아닙니다. 국내·해외 총자산은 범위 중복 가능성이 있어 합산하지 않습니다.",
        "",
        "| 시장 / 통화 | NH 총자산 | 평가액 | 평가손익 | 예수금 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for summary in snapshot.summaries:
        lines.append(
            f"| {summary.market} / {summary.currency} | {_number(summary.total_assets)} | "
            f"{_number(summary.market_value)} | {_number(summary.unrealized_pnl)} | {_number(summary.cash)} |"
        )
    lines.append("")
    excluded = [row for row in snapshot.holdings if not supports_stock_analysis(row)]
    if excluded:
        lines.extend([
            "### 주식 분석 제외 자산",
            "국내 주식 코드 형식을 지원하지 않는 자산은 잔고만 표시합니다. 수량 단위는 NH 제공 기준입니다.",
            "",
            "| 자산 | 코드 | 수량 | 평가액 | 평가손익 |",
            "| --- | --- | ---: | ---: | ---: |",
        ])
        for row in excluded:
            lines.append(
                f"| {row.name} | {row.ticker} | {_number(row.quantity)} | "
                f"{_number(row.market_value)} {row.currency} | "
                f"{_number(row.unrealized_pnl)} {row.currency} |"
            )
        lines.append("")
    if not snapshot.holdings:
        lines.extend(["NH 조회 보유 종목이 없습니다.", ""])
    return lines


def render_broker_holding(rows: Sequence[NHHolding]) -> list[str]:
    lines = []
    for row in rows:
        price_day = row.price_date.isoformat() if row.price_date else "가격 거래일 미제공"
        lines.append(
            f"- NH 보유 ({row.credit_type}): {_number(row.quantity)}주 · "
            f"매입단가 {_number(row.avg_price)} {row.currency} · "
            f"평가액 {_number(row.market_value)} {row.currency} · "
            f"평가손익 {_number(row.unrealized_pnl)} {row.currency}"
        )
        lines.append(
            f"- NH 평가 기준가: {_number(row.current_price)} {row.currency} · {row.price_basis} · {price_day}"
        )
        if row.unrealized_pnl_krw is not None:
            lines.append(f"- NH 원화 평가손익: {_number(row.unrealized_pnl_krw)} KRW")
    return lines

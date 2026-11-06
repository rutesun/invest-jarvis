"""거래 사실·사용자 기록을 함께 보여 주되 손익을 추정하지 않는다."""

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from src.providers.nhplug import NHBalanceSnapshot

from .journal import JournalError, TradeCase


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_case(case: TradeCase) -> str:
    notes = case.notes
    title = notes.title or f"{case.name} ({case.ticker})"
    status = {"open": "진행 중", "closed": "장부상 청산", "incomplete": "이력 불완전"}[case.status]
    lines = [
        f"## {title}",
        f"투자 건: {case.case_id}",
        f"계좌: {case.account_id} · {case.market}/{case.currency} · {case.ticker} · {case.credit_type}",
        f"기간: {case.start_date} ~ {case.end_date} · 상태: {status}",
        f"장부 잔여 수량: {case.quantity if case.quantity is not None else '미확인'}",
    ]
    if case.loan_date:
        lines.append(f"대출일: {case.loan_date}")
    if case.market == "US":
        lines.append(
            "미국 거래는 결제 반영 거래 장부입니다. 결제 지연으로 최근 체결이 아직 없을 수 있습니다. 실제 거래일과 조회 거래일을 구분합니다."
        )
    lines.extend(f"주의: {warning}" for warning in case.warnings)
    lines.extend(
        [
            "",
            "### 거래 사실",
            "날짜 | 조회 거래일 | 날짜 기준 | 매매 | 수량 | 가격 | 금액 | 거래 ID",
            "--- | --- | --- | --- | --- | --- | --- | ---",
        ]
    )
    for trade in case.trades:
        lines.append(
            " | ".join(
                _cell(value)
                for value in (
                    trade.trade_date or "미확인",
                    trade.query_date,
                    trade.trade_date_basis,
                    "매수" if trade.side == "buy" else "매도",
                    trade.quantity,
                    trade.price,
                    trade.amount,
                    trade.trade_id,
                )
            )
        )
        if trade.amount_krw is not None:
            lines.append(f"원화 환산 거래금액: {trade.amount_krw} KRW")
        if trade.balance_before is not None:
            lines.append(f"NH source 거래 전 잔고: {trade.balance_before}")
        if trade.balance_after is not None:
            lines.append(f"NH source 거래 후 잔고: {trade.balance_after}")
        for label, values in (("수수료", trade.fee_fields), ("세금", trade.tax_fields)):
            if values:
                lines.append(
                    f"{label}(NH 제공 필드, 통화 추정 없음): "
                    + ", ".join(f"{name}={value}" for name, value in values.items())
                )
    lines.extend(["", "### 사용자 기록"])
    for label, value in (
        ("이름", notes.title),
        ("전략", notes.strategy_label),
        ("진입 이유", notes.reason),
        ("무효화·손절 조건", notes.invalidation),
        ("추가매수 조건", notes.add_condition),
        ("전략 태그", ", ".join(notes.strategy_tags)),
        ("복기", notes.review),
    ):
        lines.append(f"{label}: {value or '미기록'}")
    for link in notes.source_links:
        provenance = "당시 저장" if link.provenance == "saved_at_trade" else "사후 재계산·기록"
        lines.append(f"분석 링크 ({provenance}): {link.path}")
    return "\n".join(lines) + "\n"


def _number(value: Decimal | None) -> str:
    if value is None:
        return "미확인"
    text = format(value, ",f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _summary(cases: list[TradeCase], level: int) -> list[str]:
    heading = "#" * level
    trades = [trade for case in cases for trade in case.trades]
    dates = [trade.trade_date or trade.query_date for trade in trades]
    months = defaultdict(lambda: [Decimal(0), Decimal(0), 0])
    for trade in trades:
        day = trade.trade_date or trade.query_date
        key = (day.strftime("%Y-%m"), trade.market, trade.currency)
        row = months[key]
        row[0 if trade.side == "buy" else 1] += trade.amount
        row[2] += 1
    lines = [
        f"기록 기간: {min(dates)} ~ {max(dates)} · 거래 {len(trades)}건 · 투자 건 {len(cases)}개",
        "",
        "집계 범위: 선택한 투자 건의 전체 거래 이력입니다. 기간 필터는 투자 건을 선택하며, 표는 계좌 전체의 월별 합계를 뜻하지 않습니다.",
        "",
        f"{heading} 선택 투자 건의 월별 거래금액",
        "",
        "| 월 | 시장/통화 | 매수 금액 | 매도 금액 | 거래 수 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for (month, market, currency), (buy, sell, count) in sorted(months.items()):
        lines.append(f"| {month} | {market}/{currency} | {_number(buy)} | {_number(sell)} | {count} |")
    lines.extend([
        "",
        "금액은 NH 거래금액 합계이며 실현손익이 아닙니다.",
        "",
        f"{heading} 투자 건 요약",
        "",
        "| 종목 | 시장/통화·구분 | 기록 기간 | 매수 수량 | 매도 수량 | 장부 잔여 | 상태 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ])
    for case in sorted(cases, key=lambda item: (item.end_date, item.case_id), reverse=True):
        bought = sum((t.quantity for t in case.trades if t.side == "buy"), Decimal(0))
        sold = sum((t.quantity for t in case.trades if t.side == "sell"), Decimal(0))
        status = {"open": "진행 중", "closed": "장부상 청산", "incomplete": "이력 불완전"}[case.status]
        category = case.credit_type if case.credit_type != "unspecified" else "구분 미제공"
        if case.loan_date:
            category += f" / 대출 {case.loan_date}"
        cells = (
            f"{case.name} ({case.ticker})", f"{case.market}/{case.currency} · {category}",
            f"{case.start_date} ~ {case.end_date}", _number(bought), _number(sold),
            _number(case.quantity), status,
        )
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    incomplete = sum(case.incomplete for case in cases)
    flagged = sum(bool(case.warnings) for case in cases)
    lines.append("")
    if incomplete:
        lines.append(f"- 이력 불완전 {incomplete}건은 장부 잔여 수량을 확정하지 않습니다.")
    if flagged:
        lines.append(f"- {flagged}개 투자 건에 날짜·체결 순서·이력 경계 등의 확인사항이 있습니다. 세부 사유는 `--detail`로 확인하세요.")
    if any(trade.market == "US" for trade in trades):
        lines.append("- 미국 거래는 결제 반영이 늦을 수 있습니다. 실거래일 미제공 시 조회일 기준으로 표시합니다.")
    notes_lines = []
    for case in cases:
        notes = case.notes
        values = [(label, value) for label, value in (
            ("전략", notes.strategy_label), ("진입 이유", notes.reason),
            ("무효화·손절", notes.invalidation), ("추가매수 조건", notes.add_condition),
            ("태그", ", ".join(notes.strategy_tags)), ("복기", notes.review),
        ) if value]
        if not (notes.title or values or notes.source_links):
            continue
        notes_lines.extend(["", f"{heading}# {_cell(notes.title or f'{case.name} ({case.ticker})')}", ""])
        notes_lines.extend(f"- {label}: {value}" for label, value in values)
        for link in notes.source_links:
            provenance = "당시 저장" if link.provenance == "saved_at_trade" else "사후 재계산·기록"
            notes_lines.append(f"- 분석 링크 ({provenance}): {link.path}")
    if notes_lines:
        lines.extend(["", f"{heading} 투자 메모", *notes_lines])
    return lines


def _current_holdings(snapshot: NHBalanceSnapshot, level: int) -> list[str]:
    lines = [
        f"{'#' * level} NH 현재 보유",
        "",
        f"계좌: {snapshot.account_id} · 조회 완료: {snapshot.as_of.isoformat(timespec='seconds')}",
        "계좌 전체 보유이며 기간 필터와 무관합니다. 과거 투자 건에 배분하지 않습니다.",
        "",
        "| 종목 | 이름 | 시장/통화 | 구분 | 대출일 | NH 보유 수량 |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for row in snapshot.holdings:
        cells = (row.ticker, row.name, f"{row.market}/{row.currency}", row.credit_type,
                 row.loan_date or "-", _number(row.quantity))
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    if not snapshot.holdings:
        lines.append("보유 내역 없음 (국내·미국 조회 완료).")
    lines.extend(["", "수량은 NH 제공 기준입니다. 미국은 체결 기준 잔고이며, 거래 장부는 결제 반영이 늦을 수 있습니다.", ""])
    return lines


def render_cases(
    cases: Iterable[TradeCase], *, detailed: bool = False,
    snapshots: Iterable[NHBalanceSnapshot] = (),
) -> str:
    selected = list(cases)
    if not selected:
        return "# NH 매매일지\n\nNH 현재 잔고: 미조회\n\n조건에 맞는 투자 건이 없습니다.\n"
    accounts = sorted({case.account_id for case in selected})
    observed = {}
    for snapshot in snapshots:
        if snapshot.account_id in observed or any(row.account_id != snapshot.account_id for row in snapshot.holdings):
            raise JournalError("현재 잔고의 계좌가 중복되거나 일치하지 않습니다.")
        observed[snapshot.account_id] = snapshot
    if observed and set(observed) != set(accounts):
        raise JournalError("선택한 장부 계좌와 현재 잔고의 계좌가 일치하지 않습니다.")
    lines = ["# NH 매매일지", ""]
    if not observed:
        lines.extend(["NH 현재 잔고: 미조회", ""])
    if detailed:
        for account in accounts:
            if account in observed:
                lines.extend(_current_holdings(observed[account], 2))
        lines.extend(render_case(case) for case in selected)
        return "\n".join(lines)
    if len(accounts) == 1:
        lines.extend([f"계좌: {accounts[0]}", ""])
    for account in accounts:
        multiple = len(accounts) > 1
        if multiple:
            lines.extend([f"## 계좌 {account}", ""])
        level = 3 if multiple else 2
        if account in observed:
            lines.extend(_current_holdings(observed[account], level))
            lines.extend([f"{'#' * level} 거래 이력", ""])
            level += 1
        lines.extend(_summary([case for case in selected if case.account_id == account], level))
        lines.append("")
    return "\n".join(lines)

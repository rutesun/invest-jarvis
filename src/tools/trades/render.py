"""거래 사실·사용자 기록을 함께 보여 주되 손익을 추정하지 않는다."""

from collections.abc import Iterable

from .journal import TradeCase


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


def render_cases(cases: Iterable[TradeCase]) -> str:
    contents = [render_case(case) for case in cases]
    return "# NH 매매일지\n\n" + (
        "\n".join(contents) if contents else "조건에 맞는 투자 건이 없습니다.\n"
    )

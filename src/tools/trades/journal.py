"""NH 거래 사실과 사용자 기록을 분리하는 로컬 SQLite 장부."""

import json
import os
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields, replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from src.providers.nhplug import NHTrade


class JournalError(ValueError):
    """장부 입력이나 투자 건을 확인할 수 없다."""


class JournalConflictError(JournalError):
    """동일한 거래 identity의 사실이 충돌하거나 누적 체결이 과거로 돌아갔다."""


@dataclass(frozen=True)
class SourceLink:
    path: str
    provenance: str = "saved_at_trade"


@dataclass(frozen=True)
class CaseNotes:
    title: str = ""
    strategy_label: str = ""
    reason: str = ""
    invalidation: str = ""
    add_condition: str = ""
    strategy_tags: tuple[str, ...] = ()
    review: str = ""
    source_links: tuple[SourceLink, ...] = ()


@dataclass(frozen=True)
class TradeCase:
    case_id: str
    account_id: str
    market: str
    currency: str
    ticker: str
    name: str
    credit_type: str
    loan_date: date | None
    trades: tuple[NHTrade, ...]
    notes: CaseNotes
    warnings: tuple[str, ...]
    quantity: Decimal | None
    incomplete: bool

    @property
    def start_date(self) -> date:
        return min(_day(trade) for trade in self.trades)

    @property
    def end_date(self) -> date:
        return max(_day(trade) for trade in self.trades)

    @property
    def status(self) -> str:
        if self.incomplete:
            return "incomplete"
        return "closed" if self.quantity == 0 else "open"


@dataclass(frozen=True)
class SyncResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    warnings: tuple[str, ...] = ()


def _day(trade: NHTrade) -> date:
    return trade.trade_date or trade.query_date


def _sort(trade: NHTrade) -> tuple[date, str]:
    # This is stable display order, never execution-order evidence.
    return _day(trade), trade.trade_id


def _book(trade: NHTrade) -> str:
    return json.dumps(
        [
            trade.account_id,
            trade.market,
            trade.currency,
            trade.ticker,
            trade.credit_type,
            trade.loan_date.isoformat() if trade.loan_date else None,
        ],
        ensure_ascii=False,
    )


def _known_exit(case: TradeCase) -> bool:
    return case.status == "closed" and all(trade.trade_date is not None for trade in case.trades)


def _balances_connect(trades: list[NHTrade], start: Decimal, end: Decimal) -> bool:
    """Check Euler-trail existence without selecting an execution sequence."""
    degrees = defaultdict(int)
    neighbours = defaultdict(set)
    for trade in trades:
        before, after = trade.balance_before, trade.balance_after
        degrees[before] += 1
        degrees[after] -= 1
        neighbours[before].add(after)
        neighbours[after].add(before)
    if start not in neighbours:
        return False
    for vertex, degree in degrees.items():
        if degree != int(vertex == start) - int(vertex == end):
            return False
    # Degree balance alone admits disconnected cycles. Every observed edge
    # must also belong to the weakly connected component of the opening balance.
    seen = set()
    pending = [start]
    while pending:
        vertex = pending.pop()
        if vertex not in seen:
            seen.add(vertex)
            pending.extend(neighbours[vertex] - seen)
    return len(seen) == len(neighbours)


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _trade_payload(trade: NHTrade) -> str:
    values = asdict(trade)
    for key in ("quantity", "price", "amount", "amount_krw", "balance_before", "balance_after"):
        values[key] = str(values[key]) if values[key] is not None else None
    for key in ("trade_date", "query_date", "loan_date"):
        values[key] = values[key].isoformat() if values[key] else None
    for key in ("fee_fields", "tax_fields"):
        values[key] = {name: str(value) for name, value in values[key].items()}
    return _dump(values)


def _read_trade(payload: str) -> NHTrade:
    values = json.loads(payload)
    for key in ("quantity", "price", "amount", "amount_krw", "balance_before", "balance_after"):
        values[key] = Decimal(values[key]) if values.get(key) is not None else None
    for key in ("trade_date", "query_date", "loan_date"):
        values[key] = date.fromisoformat(values[key]) if values[key] else None
    for key in ("fee_fields", "tax_fields"):
        values[key] = {name: Decimal(value) for name, value in values[key].items()}
    return NHTrade(**values)


def _read_notes(payload: str) -> CaseNotes:
    values = json.loads(payload)
    values["strategy_tags"] = tuple(values.get("strategy_tags", ()))
    values["source_links"] = tuple(SourceLink(**link) for link in values.get("source_links", ()))
    return CaseNotes(**values)


def _private_parent(path: Path) -> None:
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)


class TradeJournal:
    def __init__(self, path: Path = Path("data/broker/trades.sqlite3")):
        self.path = Path(path)
        _private_parent(self.path)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    book_key TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    warnings TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS trades_case ON trades(case_id);
                CREATE TABLE IF NOT EXISTS boundaries (
                    trade_id TEXT PRIMARY KEY REFERENCES trades(trade_id),
                    source_case_id TEXT NOT NULL REFERENCES cases(case_id),
                    target_case_id TEXT NOT NULL REFERENCES cases(case_id),
                    boundary_date TEXT NOT NULL,
                    book_key TEXT NOT NULL
                );
            """)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _case(self, connection, case_id: str) -> TradeCase:
        row = connection.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            raise JournalError("투자 건을 찾을 수 없습니다.")
        trades = tuple(
            sorted(
                (
                    _read_trade(item["payload"])
                    for item in connection.execute(
                        "SELECT payload FROM trades WHERE case_id = ?", (case_id,)
                    )
                ),
                key=_sort,
            )
        )
        if not trades:
            raise JournalError("거래가 없는 투자 건입니다.")
        warnings = list(json.loads(row["warnings"]))
        days = defaultdict(list)
        for trade in trades:
            days[_day(trade)].append(trade)
            if trade.trade_date is None:
                warnings.append("실제 거래일 미확인: 조회 거래일을 임시 정렬 기준으로 사용합니다.")
        quantity = Decimal("0")
        incomplete = False
        initial_balances = [
            trade.balance_before for trade in days[min(days)] if trade.balance_before is not None
        ]
        # Do not call every positive intermediate balance a missing opening
        # position: same-day ledger/display order is not execution order. A zero
        # opening observation can precede the other positive balances that day.
        if initial_balances and min(initial_balances) > 0:
            incomplete = True
            warnings.append(
                "시작 잔고 확인 필요: 첫 날짜의 관측 거래 전 잔고가 양수입니다. 수집 범위·수동 분리 여부를 확인하세요."
            )
        for daily in days.values():
            buy = sum((trade.quantity for trade in daily if trade.side == "buy"), Decimal("0"))
            sell = sum((trade.quantity for trade in daily if trade.side == "sell"), Decimal("0"))
            for trade in daily:
                delta = trade.quantity if trade.side == "buy" else -trade.quantity
                # Bound every possible same-day order, excluding this row
                # from the amount that could have happened before it. This is
                # a necessary consistency check, not an inferred execution order.
                low = quantity - sell + (trade.quantity if trade.side == "sell" else 0)
                high = quantity + buy - (trade.quantity if trade.side == "buy" else 0)
                inconsistent = (
                    (trade.balance_before is not None and not low <= trade.balance_before <= high)
                    or (
                        trade.balance_after is not None
                        and not low + delta <= trade.balance_after <= high + delta
                    )
                    or (
                        trade.balance_before is not None
                        and trade.balance_after is not None
                        and trade.balance_after - trade.balance_before != delta
                    )
                )
                if inconsistent:
                    incomplete = True
                    warnings.append(
                        "source 거래 전·후 잔고와 수집 매매 장부의 수량 불일치: 이력 범위·수동 전략 분리 등을 확인하세요. 원인은 확정하지 않습니다."
                    )
            if all(
                trade.balance_before is not None and trade.balance_after is not None
                for trade in daily
            ):
                if not _balances_connect(daily, quantity, quantity + buy - sell):
                    incomplete = True
                    warnings.append(
                        "source 일중 잔고 전이를 장부 시작·종료 수량에 맞게 연결할 수 없습니다. 이력 범위·수동 전략 분리 등을 확인하세요."
                    )
            elif any(
                trade.balance_before is not None or trade.balance_after is not None
                for trade in daily
            ):
                warnings.append(
                    "source 거래 전·후 잔고 일부 미제공: 일중 연결성 미확인, 개별 수량 범위만 검사했습니다."
                )
            if buy and sell:
                warnings.append(
                    "같은 날짜 매수·매도 체결 순서 미확인: 전량 청산·재진입을 확정하지 않습니다."
                )
            quantity += buy - sell
            if quantity < 0:
                incomplete = True
        if incomplete:
            warnings.append("시작 잔고 또는 거래 이력 불완전: 잔여 수량을 확정할 수 없습니다.")
        first = trades[0]
        return TradeCase(
            case_id,
            first.account_id,
            first.market,
            first.currency,
            first.ticker,
            first.name,
            first.credit_type,
            first.loan_date,
            trades,
            _read_notes(row["notes"]),
            tuple(dict.fromkeys(warnings)),
            None if incomplete else quantity,
            incomplete,
        )

    def _warn(self, connection, case_id: str, warning: str) -> None:
        row = connection.execute(
            "SELECT warnings FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        warnings = json.loads(row["warnings"])
        if warning not in warnings:
            warnings.append(warning)
            connection.execute(
                "UPDATE cases SET warnings = ? WHERE case_id = ?", (_dump(warnings), case_id)
            )

    def _new_case(self, connection, trade: NHTrade, *, split: bool = False) -> str:
        digest = sha256(
            (trade.account_id + "\0" + trade.trade_id + ("\0split" if split else "")).encode()
        ).hexdigest()[:24]
        case_id = "nh-case-" + digest
        # Repeated manual split at a former boundary must not reuse an old case.
        suffix = 1
        base = case_id
        while connection.execute("SELECT 1 FROM cases WHERE case_id = ?", (case_id,)).fetchone():
            case_id = f"{base}-{suffix}"
            suffix += 1
        connection.execute(
            "INSERT INTO cases VALUES (?, ?, ?, ?)",
            (case_id, _book(trade), _dump(asdict(CaseNotes())), "[]"),
        )
        return case_id

    def _assign(self, connection, trade: NHTrade, *, backfill: bool) -> str:
        case_ids = [
            row["case_id"]
            for row in connection.execute(
                "SELECT case_id FROM cases WHERE book_key = ?", (_book(trade),)
            )
        ]
        cases = sorted(
            (self._case(connection, case_id) for case_id in case_ids),
            key=lambda case: (case.start_date, case.case_id),
        )
        if not cases:
            return self._new_case(connection, trade)
        day = _day(trade)
        latest = max(cases, key=lambda case: _sort(case.trades[-1]))
        if day > latest.end_date:
            if _known_exit(latest):
                return self._new_case(connection, trade)
            candidate = latest
        else:
            covering = [case for case in cases if case.start_date <= day <= case.end_date]
            if covering:
                candidate = covering[-1]
            elif day < cases[0].start_date:
                candidate = cases[0]
            else:
                previous = [case for case in cases if case.end_date < day]
                prior = max(previous, key=lambda case: case.end_date)
                following = [case for case in cases if case.start_date > day]
                candidate = following[0] if _known_exit(prior) and following else prior
        case_id = candidate.case_id
        boundaries = list(
            connection.execute(
                "SELECT * FROM boundaries WHERE book_key = ? ORDER BY boundary_date, trade_id",
                (_book(trade),),
            )
        )
        # Repeated splits can branch (A -> B at a later key, A -> C at an
        # earlier key). Pick the latest boundary in the entire manual family,
        # not merely the first path through a candidate case's parent chain.
        parents = {
            boundary["target_case_id"]: boundary["source_case_id"] for boundary in boundaries
        }

        def root(identifier):
            while identifier in parents:
                identifier = parents[identifier]
            return identifier

        family = root(case_id)
        case_id = family
        for boundary in boundaries:
            if root(boundary["source_case_id"]) == family and _sort(trade) >= (
                date.fromisoformat(boundary["boundary_date"]),
                boundary["trade_id"],
            ):
                case_id = boundary["target_case_id"]
        if backfill:
            self._warn(
                connection,
                case_id,
                "과거 거래 추가: 기존 투자 건 배정을 유지했습니다. 경계 확인 후 필요하면 수동 분리하세요.",
            )
        return case_id

    def sync(self, trades: Iterable[NHTrade]) -> SyncResult:
        # Consume fully before any transaction; an upstream pagination error commits nothing.
        batch = sorted(trades, key=_sort)
        counts = {"inserted": 0, "updated": 0, "unchanged": 0}
        warnings = []
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous_latest = {}
            for row in connection.execute("SELECT payload FROM trades"):
                previous = _read_trade(row["payload"])
                key = _book(previous)
                previous_latest[key] = max(previous_latest.get(key, date.min), _day(previous))
            for trade in batch:
                if (
                    trade.side not in ("buy", "sell")
                    or any(
                        not value.is_finite() or value < 0
                        for value in (trade.quantity, trade.price, trade.amount)
                    )
                    or trade.quantity == 0
                ):
                    raise JournalError(
                        "거래 수량·가격·금액 또는 매수·매도 구분이 유효하지 않습니다."
                    )
                payload = _trade_payload(trade)
                existing = connection.execute(
                    "SELECT * FROM trades WHERE trade_id = ?", (trade.trade_id,)
                ).fetchone()
                if existing is not None:
                    previous = _read_trade(existing["payload"])
                    before, after = asdict(previous), asdict(trade)
                    for key in ("quantity", "price", "amount"):
                        before.pop(key)
                        after.pop(key)
                    for key in ("balance_before", "balance_after"):
                        # Older payloads did not record these optional facts.
                        # Permit unknown -> observed, but never overwrite or
                        # erase a previously observed source balance silently.
                        if before[key] is None:
                            before.pop(key)
                            after.pop(key)
                    if before != after:
                        raise JournalConflictError(
                            "동일 거래 ID의 고정 사실이 변경되었습니다. 원본 확인이 필요합니다."
                        )
                    if trade.source == "kr_order_cumulative" and trade.quantity < previous.quantity:
                        raise JournalConflictError(
                            "누적 체결 수량이 감소했습니다. 과거 응답 또는 정정 여부를 확인하세요."
                        )
                    if previous == trade:
                        counts["unchanged"] += 1
                        continue
                    connection.execute(
                        "UPDATE trades SET payload = ? WHERE trade_id = ?",
                        (payload, trade.trade_id),
                    )
                    warning = "기존 거래 사실이 갱신되었습니다. 투자 건 배정과 메모는 보존했습니다."
                    self._warn(connection, existing["case_id"], warning)
                    warnings.append(warning)
                    counts["updated"] += 1
                else:
                    case_id = self._assign(
                        connection,
                        trade,
                        backfill=_day(trade) <= previous_latest.get(_book(trade), date.min),
                    )
                    connection.execute(
                        "INSERT INTO trades VALUES (?, ?, ?)", (trade.trade_id, case_id, payload)
                    )
                    counts["inserted"] += 1
            # Return warnings visible on all affected cases, including ambiguity/backfill.
            affected = {
                row[0]
                for trade in batch
                for row in connection.execute(
                    "SELECT case_id FROM trades WHERE trade_id = ?", (trade.trade_id,)
                )
            }
            for case_id in affected:
                warnings.extend(self._case(connection, case_id).warnings)
        return SyncResult(**counts, warnings=tuple(dict.fromkeys(warnings)))

    def show(self, case_id: str) -> TradeCase:
        with self._connection() as connection:
            return self._case(connection, case_id)

    def cases(
        self,
        *,
        ticker: str | None = None,
        start: date | None = None,
        end: date | None = None,
        market: str | None = None,
        reviewed: bool | None = None,
        tags: tuple[str, ...] | None = None,
    ) -> list[TradeCase]:
        if start and end and start > end:
            raise JournalError("시작일은 종료일 이후일 수 없습니다.")
        with self._connection() as connection:
            cases = [
                self._case(connection, row[0])
                for row in connection.execute("SELECT case_id FROM cases")
            ]
        result = [
            case
            for case in cases
            if (ticker is None or case.ticker == ticker)
            and (market is None or case.market == market)
            and (reviewed is None or bool(case.notes.review.strip()) == reviewed)
            and (not tags or set(tags) <= set(case.notes.strategy_tags))
            and any(
                (start is None or _day(trade) >= start) and (end is None or _day(trade) <= end)
                for trade in case.trades
            )
        ]
        return sorted(result, key=lambda case: (case.start_date, case.case_id))

    def note(self, case_id: str, **specified_fields) -> TradeCase:
        allowed = {field.name for field in fields(CaseNotes)}
        if set(specified_fields) - allowed:
            raise JournalError("지원하지 않는 메모 필드입니다.")
        for key, value in specified_fields.items():
            if key == "strategy_tags":
                if (
                    isinstance(value, str)
                    or not isinstance(value, (tuple, list))
                    or any(not isinstance(tag, str) for tag in value)
                ):
                    raise JournalError("전략 태그는 문자열 목록이어야 합니다.")
                specified_fields[key] = tuple(value)
            elif key == "source_links":
                if not isinstance(value, (tuple, list)) or any(
                    not isinstance(link, SourceLink)
                    or not isinstance(link.path, str)
                    or link.provenance not in ("saved_at_trade", "retrospective")
                    for link in value
                ):
                    raise JournalError("분석 링크와 저장 시점 구분이 유효하지 않습니다.")
                specified_fields[key] = tuple(value)
            elif not isinstance(value, str):
                raise JournalError("메모는 문자열이어야 합니다.")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            notes = replace(self._case(connection, case_id).notes, **specified_fields)
            connection.execute(
                "UPDATE cases SET notes = ? WHERE case_id = ?", (_dump(asdict(notes)), case_id)
            )
            return self._case(connection, case_id)

    def split(
        self, trade_id: str, *, title: str | None = None, strategy_label: str | None = None
    ) -> TradeCase:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM trades WHERE trade_id = ?", (trade_id,)
            ).fetchone()
            if row is None:
                raise JournalError("분리할 거래를 찾을 수 없습니다.")
            trade = _read_trade(row["payload"])
            original = self._case(connection, row["case_id"])
            selected = [item for item in original.trades if _sort(item) >= _sort(trade)]
            if len(selected) == len(original.trades):
                raise JournalError("첫 거래 앞에서는 투자 건을 분리할 수 없습니다.")
            if (
                title is not None
                and not isinstance(title, str)
                or strategy_label is not None
                and not isinstance(strategy_label, str)
            ):
                raise JournalError("투자 건 이름과 전략은 문자열이어야 합니다.")
            case_id = self._new_case(connection, trade, split=True)
            connection.executemany(
                "UPDATE trades SET case_id = ? WHERE trade_id = ?",
                [(case_id, item.trade_id) for item in selected],
            )
            connection.execute(
                "INSERT OR REPLACE INTO boundaries VALUES (?, ?, ?, ?, ?)",
                (trade_id, original.case_id, case_id, _day(trade).isoformat(), _book(trade)),
            )
            notes = CaseNotes(title=title or "", strategy_label=strategy_label or "")
            connection.execute(
                "UPDATE cases SET notes = ? WHERE case_id = ?", (_dump(asdict(notes)), case_id)
            )
            warning = "사용자 수동 분리: 날짜와 거래 ID 표시순의 경계이며 같은 날 실제 체결 순서를 증명하지 않습니다."
            self._warn(connection, original.case_id, warning)
            self._warn(connection, case_id, warning)
            return self._case(connection, case_id)

    def export(
        self, *, case_id: str | None = None, month: str | None = None, output: Path | None = None
    ) -> str:
        from .render import render_cases

        selected = [self.show(case_id)] if case_id else self.cases()
        if month is not None:
            try:
                first = date.fromisoformat(month + "-01")
            except (ValueError, TypeError) as error:
                raise JournalError("월은 YYYY-MM 형식이어야 합니다.") from error
            selected = [
                case
                for case in selected
                if any(
                    _day(trade).year == first.year and _day(trade).month == first.month
                    for trade in case.trades
                )
            ]
        markdown = render_cases(selected)
        if output is not None:
            path = Path(output)
            _private_parent(path)
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as error:
                raise JournalError(
                    "기존 파일은 내보내기로 덮어쓸 수 없습니다. 새 출력 경로를 지정하세요."
                ) from error
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(markdown)
        return markdown

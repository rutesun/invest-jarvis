from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


LABEL = "SWING_W150"


@dataclass(frozen=True)
class SwingTrade:
    kind: str
    entry_date: date
    exit_date: date
    entry: float
    exit: float
    stop: float
    risk: float
    r_multiple: float
    why: str
    n_partial: int


class SwingStatus(StrEnum):
    HOLDING = "보유"
    SIGNAL = "신호"
    WAITING = "대기"
    NOT_ELIGIBLE = "대상아님"


@dataclass(frozen=True)
class SwingState:
    status: SwingStatus
    as_of: date | None = None
    kind: str | None = None
    reason: str | None = None
    # HOLDING
    entry_date: date | None = None
    entry: float | None = None
    stop: float | None = None
    risk: float | None = None
    current_r: float | None = None
    graduated: bool | None = None
    overheat_armed: bool | None = None
    awaiting_rebuy: bool | None = None
    # SIGNAL: 마지막 종가를 진입가 대용으로 쓴 손절
    expected_stop: float | None = None
    # WAITING
    breakout_level: float | None = None
    volume_multiple: float | None = None
    # 오늘 이미 기준 위에서 마감 → 규칙상 '첫 돌파'가 아니므로 기준 아래로 되돌린 뒤에야 신호가 난다.
    breakout_blocked: bool | None = None

    def summary_line(self, price_decimals: int = 2) -> str:
        def p(x: float) -> str:
            return f"{x:,.{price_decimals}f}"

        if self.status is SwingStatus.NOT_ELIGIBLE:
            return f"{LABEL} {self.status.value}"
        head = f"{LABEL} {self.status.value}({self.kind})"
        if self.status is SwingStatus.HOLDING:
            return (
                f"{head} — {self.entry_date.isoformat()} {p(self.entry)} 진입, "
                f"손절 {p(self.stop)}, 현재 {self.current_r:+.1f}R"
            )
        if self.status is SwingStatus.SIGNAL:
            return f"{head} — 내일 시가 진입, 예상 손절 {p(self.expected_stop)}"
        if self.breakout_blocked:
            return (
                f"{head} — 이미 {p(self.breakout_level)} 위(첫 돌파 아님), "
                "기준 아래로 되돌린 뒤 재돌파 필요"
            )
        volume = f" + 거래량 {self.volume_multiple:.1f}배" if self.volume_multiple else ""
        return f"{head} — {p(self.breakout_level)} 위 마감{volume}"

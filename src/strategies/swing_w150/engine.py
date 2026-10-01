"""SWING_W150 v3 매매 재생과 오늘 상태 판정.

한 종목에 포지션은 하나다. 매매는 경로 의존적이라(이전 청산일 다음 봉부터 다시 탐색)
오늘 상태도 전체 기간을 처음부터 재생해서 구한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.strategies.swing_w150 import rules
from src.strategies.swing_w150.models import SwingState, SwingStatus, SwingTrade
from src.tools.disclosure import is_korean_ticker
from src.tools.technical.indicators import IndicatorCalculator


logger = logging.getLogger(__name__)


@dataclass
class _Run:
    """한 매매의 재생 결과. 열린 매매(why='end')면 마지막 봉 시점의 포지션 상태."""

    kind: str
    entry_index: int
    exit_index: int
    entry: float
    exit: float
    stop: float
    risk: float
    pnl: float
    why: str
    n_partial: int
    graduated: bool
    armed: bool
    flat: bool

    def to_trade(self, f: rules.SwingFeatures) -> SwingTrade:
        return SwingTrade(
            kind=self.kind,
            entry_date=f.dates[self.entry_index],
            exit_date=f.dates[self.exit_index],
            entry=self.entry,
            exit=self.exit,
            stop=self.stop,
            risk=self.risk,
            r_multiple=self.pnl / self.risk,
            why=self.why,
            n_partial=self.n_partial,
        )


def _features(df: pd.DataFrame) -> rules.SwingFeatures:
    return rules.build_features(IndicatorCalculator().calculate(df.copy()))


def _walk(f: rules.SwingFeatures, kind: str, entry_index: int, entry: float, stop: float) -> _Run:
    c, low = f.close, f.low
    n = len(c)
    risk = entry - stop
    graduated = kind == "S"
    prev_below = False
    armed = False
    held = True
    basis = entry
    realized = 0.0
    n_partial = 0

    def finish(k: int, price: float, why: str) -> _Run:
        pnl = realized + (price - basis if held else 0.0)
        return _Run(
            kind=kind,
            entry_index=entry_index,
            exit_index=k,
            entry=entry,
            exit=price,
            stop=stop,
            risk=risk,
            pnl=pnl,
            why=why,
            n_partial=n_partial,
            graduated=graduated,
            armed=armed,
            flat=not held,
        )

    for k in range(entry_index, n):
        # 과열 매도로 비어 있어도 손절선은 살아 있다(기준 동작).
        if low[k] <= stop:
            return finish(k, stop, "stop")
        if rules.overheat_armed(f, k):
            armed = True
        if held and armed and rules.overheat_sell(f, k):
            realized += float(c[k]) - basis
            held = False
            armed = False
            n_partial += 1
        elif not held and rules.overheat_rebuy(f, k):
            basis = float(c[k])
            held = True
            n_partial += 1
        if not graduated and rules.graduates(f, k):
            graduated = True
        if graduated:
            below = rules.below_exit_line(f, k)
            hit = rules.exit_150(f, k, below, prev_below, risk)
            prev_below = below
            if hit:
                return finish(k, float(c[k]), "sma150")
    return finish(n - 1, float(c[-1]), "end")


def _replay(f: rules.SwingFeatures) -> list[_Run]:
    n = len(f.close)
    runs: list[_Run] = []
    t = rules.WARMUP_BARS
    while t < n - 1:
        kind = rules.trigger_kind(f, t)
        if kind is None:
            t += 1
            continue
        entry = float(f.open[t + 1])
        if np.isnan(entry) or np.isnan(f.atr[t]):
            t += 1
            continue
        stop = rules.initial_stop(kind, entry, f, t)
        if not stop < entry:
            t += 1
            continue
        run = _walk(f, kind, t + 1, entry, stop)
        runs.append(run)
        t = run.exit_index + 1
    return runs


def replay(df: pd.DataFrame) -> list[SwingTrade]:
    """df: 원본 OHLCV(날짜 오름차순). 마지막 매매가 열려 있으면 마지막 종가로 why='end'."""
    f = _features(df)
    return [run.to_trade(f) for run in _replay(f)]


def _breakout_reference(f: rules.SwingFeatures, lookback: int) -> dict:
    """내일 종가가 넘어야 할 기준(오늘 포함 N봉 고가)과, 오늘 이미 직전 N봉 고가 위라 막혔는지."""
    prior_high = float(f.high[-lookback - 1 : -1].max())
    if f.close[-1] > prior_high:
        return {"breakout_level": prior_high, "breakout_blocked": True}
    return {"breakout_level": float(f.high[-lookback:].max()), "breakout_blocked": False}


def current_state(df: pd.DataFrame) -> SwingState:
    """마지막 봉 종가 기준 상태. SIGNAL은 다음 봉 시가 진입을 뜻한다."""
    if len(df) < rules.WARMUP_BARS + 1:
        return SwingState(
            status=SwingStatus.NOT_ELIGIBLE,
            reason=f"데이터 부족({len(df)}봉 < {rules.WARMUP_BARS + 1}봉)",
        )
    f = _features(df)
    last = len(f.close) - 1
    as_of = f.dates[last]
    runs = _replay(f)

    if runs and runs[-1].why == "end":
        run = runs[-1]
        return SwingState(
            status=SwingStatus.HOLDING,
            as_of=as_of,
            kind=run.kind,
            entry_date=f.dates[run.entry_index],
            entry=run.entry,
            stop=run.stop,
            risk=run.risk,
            current_r=run.pnl / run.risk,
            graduated=run.graduated,
            overheat_armed=run.armed,
            awaiting_rebuy=run.flat,
        )

    # 마지막 봉에서 막 청산됐으면 재생은 다음 봉부터 다시 탐색하므로 오늘 신호는 없다.
    exited_today = bool(runs) and runs[-1].exit_index == last
    kind = None if exited_today else rules.trigger_kind(f, last)
    if kind is not None:
        close = float(f.close[last])
        return SwingState(
            status=SwingStatus.SIGNAL,
            as_of=as_of,
            kind=kind,
            expected_stop=rules.initial_stop(kind, close, f, last),
        )

    close = f.close[last]
    if close > f.sma150[last] and f.slope150[last] > 0:
        return SwingState(
            status=SwingStatus.WAITING,
            as_of=as_of,
            kind="S",
            **_breakout_reference(f, rules.S_BREAKOUT_LOOKBACK),
            volume_multiple=rules.S_VOLUME_MULT,
        )
    if f.deep[last]:
        return SwingState(
            status=SwingStatus.WAITING,
            as_of=as_of,
            kind="D",
            **_breakout_reference(f, rules.D_BREAKOUT_LOOKBACK),
        )
    return SwingState(status=SwingStatus.NOT_ELIGIBLE, as_of=as_of, reason="진입 경로 전제 미충족")


def summarize(df: pd.DataFrame | None, ticker: str = "") -> str | None:
    """화면 표시용 한 줄. 참고 정보라 계산이 실패해도 호출한 화면은 멈추지 않는다."""
    if df is None:
        return None
    try:
        # 원화는 소수점 아래가 없다.
        decimals = 0 if ticker and is_korean_ticker(ticker) else 2
        return current_state(df).summary_line(price_decimals=decimals)
    except Exception as e:
        logger.warning("SWING_W150 상태 계산 실패 %s: %s", ticker, e)
        return None

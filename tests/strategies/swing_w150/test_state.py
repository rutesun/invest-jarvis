from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.strategies.swing_w150.engine import current_state
from src.strategies.swing_w150.models import SwingState, SwingStatus


def _through(df: pd.DataFrame, day: str) -> pd.DataFrame:
    return df.loc[: pd.Timestamp(day)]


def _before(df: pd.DataFrame, day: str) -> pd.DataFrame:
    return df.loc[: pd.Timestamp(day)].iloc[:-1]


def test_open_trade_is_holding(pypl):
    df, trades = pypl
    last = trades[-1]
    assert last["why"] == "end"

    state = current_state(df)

    assert state.status is SwingStatus.HOLDING
    assert state.kind == last["kind"]
    assert state.entry_date.isoformat() == last["entry_date"]
    assert state.entry == pytest.approx(last["entry"], rel=1e-9)
    assert state.current_r == pytest.approx(last["R"], rel=1e-9)
    assert state.risk == pytest.approx(state.entry - state.stop)
    assert state.graduated is True
    assert state.overheat_armed is False
    assert state.awaiting_rebuy is False
    assert (
        state.summary_line() == "SWING_W150 보유(D) — 2026-07-06 44.34 진입, 손절 39.40, 현재 +2.0R"
    )


def test_day_before_each_golden_entry_is_signal(pypl):
    df, trades = pypl
    for trade in trades:
        state = current_state(_before(df, trade["entry_date"]))
        assert state.status is SwingStatus.SIGNAL, trade
        assert state.kind == trade["kind"], trade
        assert state.expected_stop < df.loc[: pd.Timestamp(trade["entry_date"])]["Close"].iloc[-2]


def test_signal_summary_line(pypl):
    df, _ = pypl
    state = current_state(_through(df, "2017-04-27"))

    assert state.summary_line() == "SWING_W150 신호(S) — 내일 시가 진입, 예상 손절 40.83"


def test_waiting_on_s_path_shows_50_bar_high_and_volume(pypl):
    df, _ = pypl
    cut = _through(df, "2018-05-11")
    state = current_state(cut)

    assert state.status is SwingStatus.WAITING
    assert state.kind == "S"
    assert state.breakout_level == pytest.approx(cut["High"].iloc[-50:].max())
    assert state.volume_multiple == 1.4
    assert state.breakout_blocked is False
    assert state.summary_line() == "SWING_W150 대기(S) — 83.06 위 마감 + 거래량 1.4배"


def test_waiting_after_breakout_without_trigger_needs_pullback_first(pypl):
    # 오늘 이미 직전 50봉 고가 위에서 마감했으면 내일은 '첫 돌파'가 될 수 없다.
    df, _ = pypl
    state = current_state(_through(df, "2017-02-24"))

    assert state.status is SwingStatus.WAITING
    assert state.kind == "S"
    assert state.breakout_blocked is True
    assert state.summary_line() == (
        "SWING_W150 대기(S) — 이미 42.20 위(첫 돌파 아님), 기준 아래로 되돌린 뒤 재돌파 필요"
    )


def test_waiting_on_d_path_shows_20_bar_high(pypl):
    df, _ = pypl
    cut = _through(df, "2019-11-20")
    state = current_state(cut)

    assert state.status is SwingStatus.WAITING
    assert state.kind == "D"
    assert state.breakout_level == pytest.approx(cut["High"].iloc[-20:].max())
    assert state.volume_multiple is None
    assert state.summary_line() == "SWING_W150 대기(D) — 107.26 위 마감"


def test_no_path_premise_is_not_eligible(pypl):
    df, _ = pypl
    state = current_state(_through(df, "2018-05-04"))

    assert state.status is SwingStatus.NOT_ELIGIBLE
    assert state.as_of == date(2018, 5, 4)
    assert state.reason == "진입 경로 전제 미충족"
    assert state.summary_line() == "SWING_W150 대상아님"


def test_short_history_is_not_eligible(pypl):
    df, _ = pypl
    state = current_state(df.iloc[:250])

    assert state.status is SwingStatus.NOT_ELIGIBLE
    assert "250봉" in state.reason
    assert state.summary_line() == "SWING_W150 대상아님"


def test_summary_line_formats_negative_r_and_two_decimal_prices():
    state = SwingState(
        status=SwingStatus.HOLDING,
        kind="S",
        entry_date=date(2026, 8, 14),
        entry=140.2,
        stop=128.0,
        current_r=-0.44,
    )

    assert (
        state.summary_line()
        == "SWING_W150 보유(S) — 2026-08-14 140.20 진입, 손절 128.00, 현재 -0.4R"
    )


def test_summary_line_uses_thousands_separator_and_given_decimals():
    state = SwingState(
        status=SwingStatus.WAITING,
        kind="S",
        breakout_level=288000.0,
        volume_multiple=1.4,
        breakout_blocked=False,
    )

    assert (
        state.summary_line(price_decimals=0)
        == "SWING_W150 대기(S) — 288,000 위 마감 + 거래량 1.4배"
    )

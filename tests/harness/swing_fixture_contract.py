"""SWING_W150 정답지(원본 OHLCV CSV + 매매 목록 JSON) 형식 계약.

엔진은 250봉 워밍업 뒤부터 경로 의존적으로 매매를 재생한다. 날짜가 뒤섞이거나
OHLC에 빈 값이 있으면 오류 없이 다른 매매가 나오므로, 로드 시점에 가정을 확인한다.
"""

from __future__ import annotations

import pandas as pd


OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
MIN_ROWS = 251
TRADE_KEYS = {"kind", "entry_date", "exit_date", "entry", "exit", "R", "why", "n_partial"}
TRADE_KINDS = {"S", "D"}
EXIT_REASONS = {"stop", "sma150", "end"}


def assert_swing_price_contract(df: pd.DataFrame) -> None:
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    assert not missing, f"필수 컬럼 누락: {missing}"
    assert isinstance(df.index, pd.DatetimeIndex), "인덱스가 DatetimeIndex가 아님"
    assert df.index.is_monotonic_increasing, "날짜가 오름차순이 아님"
    assert not df.index.has_duplicates, "중복 날짜 존재"
    nan_cols = [c for c in ("Open", "High", "Low", "Close") if df[c].isna().any()]
    assert not nan_cols, f"OHLC에 NaN 존재: {nan_cols}"
    assert len(df) >= MIN_ROWS, f"행 수 부족: {len(df)} < {MIN_ROWS}"


def assert_swing_trades_contract(trades: list[dict], df: pd.DataFrame) -> None:
    assert isinstance(trades, list) and trades, "매매 목록이 비었음"
    dates = {d.date().isoformat() for d in df.index}
    prev_exit = ""
    for i, tr in enumerate(trades):
        assert set(tr) == TRADE_KEYS, f"{i}번 매매 키 불일치: {sorted(tr)}"
        assert tr["kind"] in TRADE_KINDS, f"{i}번 kind: {tr['kind']}"
        assert tr["why"] in EXIT_REASONS, f"{i}번 why: {tr['why']}"
        assert tr["entry_date"] in dates and tr["exit_date"] in dates, f"{i}번 날짜가 CSV에 없음"
        assert tr["entry_date"] <= tr["exit_date"], f"{i}번 진입일이 청산일보다 늦음"
        assert tr["entry_date"] > prev_exit, f"{i}번 매매가 이전 매매와 겹침"
        assert isinstance(tr["n_partial"], int) and tr["n_partial"] >= 0
        prev_exit = tr["exit_date"]
    assert all(tr["why"] != "end" for tr in trades[:-1]), "미종료 매매는 마지막에만 올 수 있음"

"""엔진 replay가 기준 백테스트(v3, jarvis 지표판)와 같은 매매를 내는지 고정한다."""

from __future__ import annotations

import pytest

from src.strategies.swing_w150.engine import replay


EXACT = ("kind", "entry_date", "exit_date", "why", "n_partial")
APPROX = ("entry", "exit", "R")


def _as_row(trade) -> dict:
    return {
        "kind": trade.kind,
        "entry_date": trade.entry_date.isoformat(),
        "exit_date": trade.exit_date.isoformat(),
        "why": trade.why,
        "n_partial": trade.n_partial,
        "entry": trade.entry,
        "exit": trade.exit,
        "R": trade.r_multiple,
    }


def test_replay_matches_golden_trades(golden_case):
    ticker, df, expected = golden_case
    actual = [_as_row(t) for t in replay(df)]

    # 건수보다 첫 불일치 매매가 원인 추적에 유용하므로 길이는 마지막에 본다.
    for i, (a, e) in enumerate(zip(actual, expected, strict=False)):
        context = f"{ticker} {i}번 매매\n  actual={a}\n  expected={e}"
        assert {k: a[k] for k in EXACT} == {k: e[k] for k in EXACT}, context
        for k in APPROX:
            assert a[k] == pytest.approx(e[k], rel=1e-9, abs=1e-9), f"{k}: {context}"
    assert len(actual) == len(expected), f"{ticker} 매매 건수 {len(actual)} != {len(expected)}"

"""엔진 replay가 기준 백테스트(v3, jarvis 지표판)와 같은 매매를 내는지 고정한다."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
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


def test_v2_raw_signal_execution_golden():
    from src.backtest.swing_w150 import (
        SwingExecutionPolicy,
        SwingRiskPolicy,
        simulate_swing_v2,
    )
    from src.strategies.swing_w150.parameters import SwingW150Parameters

    fixtures = Path(__file__).resolve().parents[2] / "fixtures" / "swing_w150"
    expected = json.loads((fixtures / "v2_backtest_expected.json").read_text())
    # Reuse the chart warmup fixture; the independently specified tail creates
    # a breakout, correction and recovery with an actual following open.
    raw = pd.read_csv(fixtures / "v2_signal_path.csv", index_col=0, parse_dates=True).iloc[:250]
    for row in expected["raw_tail"]:
        raw.loc[pd.Timestamp(row["date"])] = row["ohlcv"]
    result = simulate_swing_v2(
        raw,
        SwingW150Parameters(),
        SwingExecutionPolicy(**expected["execution_policy"]),
        risk_policy=SwingRiskPolicy(**expected["risk_policy"]),
        ticker="TEST",
        warmup_start=raw.index[0].date(),
        expected_sessions=tuple(pd.bdate_range(raw.index[0], raw.index[-1]).date),
        test_start=raw.index[250].date(),
        test_end=raw.index[-1].date(),
    )
    assert [signal.code for signal in result.signal_history] == expected["signals"]
    assert [
        {
            "date": order.date.isoformat(),
            "side": order.side,
            "reason": order.reason,
            "price": order.price,
            "quantity": order.quantity,
            "fee": order.fee,
        }
        for order in result.orders
    ] == expected["orders"]
    assert len(result.open_lots) == 2
    for lot, wanted in zip(result.open_lots, expected["open_lots"], strict=True):
        assert lot.entry_price == wanted["entry_price"]
        assert lot.quantity == wanted["quantity"]
        assert lot.stop == pytest.approx(wanted["stop"], abs=1e-10)
        assert lot.initial_risk_capital == pytest.approx(wanted["risk_capital"], abs=1e-10)
    assert result.closed_lots[0].realized_pnl == -186
    assert result.closed_lots[0].initial_risk_capital == pytest.approx(245.6)
    assert result.aggregate_r == pytest.approx(expected["aggregate_r"])


@pytest.mark.parametrize("policy", ["V1", "EXPLICIT_V2"])
def test_observation_toggle_preserves_final_signal_backtest(tmp_path, policy):
    from scripts.research_trading_observations import (
        build_product_record,
        explicit_research_parameters,
    )
    from src.backtest.swing_w150 import SwingExecutionPolicy, SwingRiskPolicy, simulate_swing_v2
    from src.strategies.models import ChartBundle
    from src.strategies.swing_w150.adapter import SwingW150SignalStrategy
    from src.strategies.swing_w150.parameters import SwingW150Parameters

    fixture = Path(__file__).resolve().parents[2] / "fixtures/swing_w150"
    expected = json.loads((fixture / "v2_backtest_expected.json").read_text())
    raw = pd.read_csv(fixture / "v2_signal_path.csv", index_col=0, parse_dates=True).iloc[:250]
    for row in expected["raw_tail"]:
        raw.loc[pd.Timestamp(row["date"])] = row["ohlcv"]
    csv = tmp_path / "chart.csv"
    raw.to_csv(csv, index_label="Date")
    record = build_product_record(
        ticker="TEST",
        instrument_path=csv,
        market_path=csv,
        cutoff=raw.index[-1].date(),
        calendar_name="fixture_sessions",
        include_projection=False,
    )
    chart = ChartBundle.model_validate(record["inputs"]["chart_bundle"])
    params = SwingW150Parameters() if policy == "V1" else explicit_research_parameters()
    executions = []
    for enabled in (True, False):
        signals = SwingW150SignalStrategy(
            params=params, observations_enabled=enabled
        ).evaluate_signals(chart)
        executions.append(
            simulate_swing_v2(
                raw,
                params,
                SwingExecutionPolicy(**expected["execution_policy"]),
                risk_policy=SwingRiskPolicy(**expected["risk_policy"]),
                ticker="TEST",
                warmup_start=raw.index[0].date(),
                expected_sessions=chart.exchange_sessions,
                test_start=raw.index[250].date(),
                test_end=raw.index[-1].date(),
                signal_history=signals.signal_history,
            )
        )
    assert executions[0].orders
    assert executions[0] == executions[1]

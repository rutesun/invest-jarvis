from __future__ import annotations

import logging

import pandas as pd

from src.strategies.swing_w150.engine import current_state, summarize


def test_summarize_matches_state_summary_line(pypl):
    df, _ = pypl
    assert summarize(df) == current_state(df).summary_line()


def test_summarize_without_data_is_none():
    assert summarize(None) is None


def test_summarize_failure_is_logged_not_raised(caplog):
    broken = pd.DataFrame({"Close": [1.0] * 300})

    with caplog.at_level(logging.WARNING):
        assert summarize(broken, ticker="XYZ") is None

    assert "SWING_W150" in caplog.text
    assert "XYZ" in caplog.text


def test_korean_ticker_prices_have_no_decimals(pypl):
    df, _ = pypl
    line = summarize(df, ticker="005930.KS")

    assert line == current_state(df).summary_line(price_decimals=0)
    assert "44 진입" in line

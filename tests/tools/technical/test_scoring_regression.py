from pathlib import Path

import pandas as pd

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer


FIXTURE_DIR = Path("tests/fixtures/technical/scoring")


def _load_fixture(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURE_DIR / name, parse_dates=["Date"], index_col="Date")


def _score_until(df: pd.DataFrame, date: str):
    sliced = IndicatorCalculator().calculate(df.loc[: pd.Timestamp(date)])
    return TechnicalScorer().score(sliced, include_history=False)


def test_panw_entry_window_regression():
    df = _load_fixture("panw_2026-03-01_2026-05-14.csv")

    april_22 = _score_until(df, "2026-04-22")
    april_30 = _score_until(df, "2026-04-30")

    assert april_22.technical_verdict.action in {"buy", "add"}
    assert april_22.technical_verdict.new_entry_allowed is True
    assert april_30.technical_verdict.action == "watch"
    assert april_30.technical_verdict.new_entry_allowed is False
    assert april_30.adjusted_score == 55


def test_be_overextension_then_breakdown_regression():
    df = _load_fixture("be_2026-06-01_2026-07-15.csv")

    june_18 = _score_until(df, "2026-06-18")
    june_26 = _score_until(df, "2026-06-26")

    assert june_18.technical_verdict.action in {"hold", "watch"}
    assert june_18.technical_verdict.new_entry_allowed is False
    assert june_26.technical_verdict.action in {"reduce", "avoid", "watch"}


def test_samsung_breakdown_regression():
    df = _load_fixture("005930_ks_2026-06-01_2026-07-16.csv")

    july_02 = _score_until(df, "2026-07-02")

    assert july_02.technical_verdict.action in {"reduce", "avoid", "watch"}
    assert july_02.technical_verdict.new_entry_allowed is False

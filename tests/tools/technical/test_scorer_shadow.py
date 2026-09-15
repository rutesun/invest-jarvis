"""A′ cutover — scorer가 shadow_v2(점수 vs 게이트 분리 산출)를 TechnicalResult에 담는지 검증."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.scorer import TechnicalScorer


FIXTURE_DIR = Path("tests/fixtures/technical/scoring")


def _score(name: str, until: str):
    df = pd.read_csv(FIXTURE_DIR / name, parse_dates=["Date"], index_col="Date")
    sliced = IndicatorCalculator().calculate(df.loc[: pd.Timestamp(until)])
    return TechnicalScorer().score(sliced, include_history=False)


def test_scorer_attaches_shadow_v2():
    result = _score("panw_2024-01-01_2026-05-20.csv", "2026-05-07")
    assert result.shadow_v2 is not None
    for key in ("setup_score", "regime", "action_v2", "new_entry_allowed_v2", "bottoming_watch"):
        assert key in result.shadow_v2
    # PANW 5/7은 초기 recovery 돌파 → buy.
    assert result.shadow_v2["action_v2"] == "buy"
    assert result.shadow_v2["regime"] == "trend"

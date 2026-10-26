from datetime import date

import pandas as pd
import pytest

from src.strategies.chart_bundle import chart_bundle_from_dataframes
from src.strategies.legacy_technical import LegacyTechnicalStrategy
from src.strategies.models import (
    EntryIntent,
    ExitIntent,
    StrategyVerdict,
    SwingRuntimeState,
)
from src.tools.technical.models import TechnicalVerdict
from src.tools.technical.scorecard_models import DataStatus


def make_legacy_verdict(action: str) -> TechnicalVerdict:
    return TechnicalVerdict(
        action=action,
        entry_mode="test",
        confidence="medium",
        new_entry_allowed=action in {"buy", "add"},
        reasons=["trend confirmed"],
        cautions=["extension risk"],
    )


@pytest.mark.parametrize(
    ("action", "entry", "exit"),
    [
        ("buy", EntryIntent.ALLOW, ExitIntent.HOLD),
        ("add", EntryIntent.ALLOW, ExitIntent.HOLD),
        ("hold", EntryIntent.WATCH, ExitIntent.HOLD),
        ("watch", EntryIntent.WATCH, ExitIntent.HOLD),
        ("accumulate", EntryIntent.WATCH, ExitIntent.HOLD),
        ("reduce", EntryIntent.BLOCK, ExitIntent.REDUCE),
        ("avoid", EntryIntent.BLOCK, ExitIntent.NOT_EVALUATED),
    ],
)
def test_legacy_mapping(action, entry, exit):
    verdict = LegacyTechnicalStrategy().from_legacy(make_legacy_verdict(action))
    assert (verdict.entry.intent, verdict.exit.intent) == (entry, exit)
    assert verdict.entry.data_status is DataStatus.COMPLETE
    assert verdict.exit.data_status is DataStatus.COMPLETE
    assert {item.message for item in verdict.entry.reasons + verdict.exit.reasons} == {
        "trend confirmed",
        "extension risk",
    }


def test_strategy_state_rehydrates_as_typed_swing_state():
    state = SwingRuntimeState(
        state_type="swing_w150",
        state_version="v1",
        lifecycle="active",
        cycle_phase="signal",
        kind="S",
        entry=None,
        stop=None,
        risk=None,
        graduated=None,
        overheat_armed=None,
        previous_below_exit_line=None,
    )
    verdict = LegacyTechnicalStrategy().from_legacy(make_legacy_verdict("buy"))
    restored = StrategyVerdict.model_validate(
        {**verdict.model_dump(), "strategy_state": state.model_dump()}
    )
    assert isinstance(restored.strategy_state, SwingRuntimeState)


def test_evaluate_reuses_legacy_technical_path_from_chart_only_prefix():
    from src.strategies.models import CoverageManifest
    from src.tools.technical.indicators import IndicatorCalculator
    from src.tools.technical.scorer import TechnicalScorer

    index = pd.bdate_range("2025-01-01", periods=260)
    close = [100 + i * 0.2 for i in range(260)]
    frame = pd.DataFrame(
        {
            "Open": [value - 0.5 for value in close],
            "High": [value + 1 for value in close],
            "Low": [value - 1 for value in close],
            "Close": close,
            "Volume": [1_000_000 + i * 100 for i in range(260)],
        },
        index=index,
    )
    sessions = tuple(day.date() for day in index)
    bundle = chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker="AAPL",
        as_of=sessions[-1],
        instrument=frame,
        instrument_coverage=CoverageManifest(
            requested_start=sessions[0],
            actual_start=sessions[0],
            actual_end=sessions[-1],
            expected_sessions=sessions,
            complete=True,
        ),
        exchange_sessions=sessions,
    )
    legacy = (
        TechnicalScorer()
        .score(IndicatorCalculator().calculate(frame), ticker="AAPL", include_history=False)
        .technical_verdict
    )
    assert legacy is not None

    strategy = LegacyTechnicalStrategy()
    actual = strategy.evaluate(bundle)
    expected = strategy.from_legacy(legacy, ticker="AAPL", as_of=sessions[-1])
    assert actual == expected
    assert actual == strategy.evaluate(bundle)
    assert actual.ticker == "AAPL"
    assert actual.as_of == date(2025, 12, 30)

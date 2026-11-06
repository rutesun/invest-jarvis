"""Public compatibility callers use the common numerical boundary after gates."""

import importlib

import pytest

from tests.tools.technical.chart_analysis.test_features import bars


class OwnerCalledError(RuntimeError):
    pass


def fail(*args, **kwargs):
    raise OwnerCalledError("common numerical owner")


@pytest.mark.parametrize("entry", ["indicators", "pivots", "triggers"])
def test_public_helpers_delegate_to_common_owner(monkeypatch, entry):
    frame = bars([100.0] * 60)
    if entry == "indicators":
        owner = importlib.import_module("src.tools.technical.chart_analysis.legacy_features")
        monkeypatch.setattr(owner, "calculate_legacy_features", fail)
        from src.tools.technical.indicators import IndicatorCalculator

        def call():
            return IndicatorCalculator().calculate(frame)
    elif entry == "pivots":
        owner = importlib.import_module("src.tools.technical.chart_analysis.pivots")
        monkeypatch.setattr(owner, "confirmed_pivot_events", fail)
        from src.tools.technical.pivots import confirmed_pivot_events

        def call():
            return confirmed_pivot_events(frame.High.to_numpy(), frame.Low.to_numpy())
    else:
        owner = importlib.import_module("src.tools.technical.chart_analysis.trigger_events")
        monkeypatch.setattr(owner, "detect_trigger_events", fail)
        from src.tools.technical.triggers import detect_analysis_triggers

        def call():
            return detect_analysis_triggers(frame)

    with pytest.raises(OwnerCalledError):
        call()


@pytest.mark.parametrize(
    "module,function,rule",
    [
        ("crsi", "analyze_crsi", "chart.crsi.legacy"),
        ("minervini", "analyze_minervini", "chart.stage2.minervini"),
        ("velocity", "analyze_velocity", "chart.velocity.legacy"),
        ("supertrend", "analyze_supertrend", "chart.supertrend.legacy"),
        ("patterns", "analyze_patterns", "chart.vcp.legacy"),
        ("volume", "analyze_volume", "chart.legacy.volume_extra"),
        ("risk", "analyze_risk", "legacy.confluence"),
        ("divergence", "analyze_divergence", "legacy.divergence"),
    ],
)
def test_direct_components_use_common_frame_owner_even_without_dates(
    monkeypatch, module, function, rule
):
    from src.tools.technical.chart_analysis.legacy_facts import FRAME_FAMILIES

    monkeypatch.setitem(FRAME_FAMILIES, rule, fail)
    frame = bars([100.0] * 60).reset_index(drop=True)
    consumer = importlib.import_module("src.tools.technical.components." + module)
    with pytest.raises(OwnerCalledError):
        getattr(consumer, function)(frame)


def test_calculator_subclass_crsi_hook_is_preserved():
    from src.tools.technical.indicators import IndicatorCalculator

    class Customized(IndicatorCalculator):
        def _calculate_crsi(self, frame):
            frame = super()._calculate_crsi(frame)
            frame["custom_crsi_hook"] = 7
            return frame

    result = Customized().calculate(bars([100.0] * 60))
    assert result.custom_crsi_hook.eq(7).all()


def test_direct_pocket_helper_uses_explicit_latest_row():
    from src.tools.technical.components.volume import _detect_pocket_pivot

    frame = bars([100.0] * 11).reset_index(drop=True)
    frame["Open"], frame["SMA_50"], frame["Volume"] = 101, 100, 100
    latest = frame.iloc[-1].copy()
    latest["Volume"] = 1000
    assert _detect_pocket_pivot(frame, latest)["score"] == 25
    assert _detect_pocket_pivot(frame, frame.iloc[-1])["score"] == 0


def test_direct_tennis_helper_needs_no_volume_average_column_and_keeps_flag():
    from src.tools.technical.components.volume import _detect_tennis_ball_egg

    frame = bars([100.0] * 6).reset_index(drop=True)
    frame["Open"], frame["Volume"] = 101, 100
    latest = frame.iloc[-1].copy()
    latest["Volume"] = 10
    assert "Vol_SMA_20" not in frame
    assert _detect_tennis_ball_egg(frame, latest, True)["score"] == 15
    assert _detect_tennis_ball_egg(frame, latest, False)["score"] == 0


@pytest.mark.parametrize("rows,has_columns", [(1, True), (10, False)])
def test_direct_weakness_zero_threshold_keeps_input_guard(rows, has_columns):
    import pandas as pd

    from src.tools.technical.shadow_v2 import _established_weakness

    frame = pd.DataFrame({"Close": [1.0] * rows})
    if has_columns:
        frame["SMA_50"] = 2.0
    assert not _established_weakness(frame, need=0)


@pytest.mark.parametrize("close,expected", [([1.0], True), ([1.0, 3.0], False), ([], True)])
def test_direct_zero_day_streak_keeps_supplied_slice_meaning(close, expected):
    import pandas as pd

    from src.tools.technical.shadow_v2 import _close_below_sma20_streak

    frame = pd.DataFrame({"Close": close, "SMA_20": [2.0] * len(close)})
    assert _close_below_sma20_streak(frame, 0) is expected


def test_runner_playbook_calculates_features_once_and_retains_market_refs(monkeypatch):
    from src.strategies.playbook import PlaybookStrategy
    from src.strategies.runner import StrategyRunner
    from src.tools.playbook.common import chart_frame
    from src.tools.technical.chart_analysis.models import content_hash
    from src.tools.technical.indicators import IndicatorCalculator
    from tests.strategies.test_playbook import _bundle
    from tests.strategies.test_runner import _legacy_result

    bundle = _bundle()
    strategy = PlaybookStrategy()
    expected = strategy.evaluate(bundle).model_dump()
    runner = StrategyRunner()
    runner._strategies = (strategy,)
    original = IndicatorCalculator.calculate
    calls = []

    def counted(self, frame):
        calls.append(frame)
        return original(self, frame)

    monkeypatch.setattr(IndicatorCalculator, "calculate", counted)
    run = runner.run(bundle, legacy_result=_legacy_result())
    assert not run.errors
    assert len(calls) == 1
    assert run.verdicts[0].model_dump() == expected
    analysis = run.common_analyses[run.verdicts[0].chart_analysis_id]
    assert analysis.dependencies["market"].input_hash == content_hash(chart_frame(bundle.market))
    for selection in run.verdicts[0].fact_selections:
        retained = run.common_analyses[selection.ref.analysis_id]
        assert any(item.id == selection.ref.item_id for item in retained.items)


@pytest.mark.parametrize(
    "parameters",
    [
        {"frame_policy": "SUPPLIED_AS_IS", "display_bars": 5},
        {"frame_policy": "SUPPLIED_AS_IS", "display_bars": 20},
        {"frame_policy": "PREPARED", "display_bars": 20},
        {},
    ],
)
def test_scorecard_trigger_variant_union_keeps_payload_and_selected_audit(parameters):
    import pandas as pd

    from src.tools.technical.chart_analysis.registry import rule_request
    from src.tools.technical.context import common_analysis_for_frame
    from src.tools.technical.indicators import IndicatorCalculator
    from src.tools.technical.scorecard import build_scorecard
    from src.tools.technical.scorer import TechnicalScorer, technical_rule_requests
    from src.tools.technical.trigger_registry import TRIGGER_RULES

    raw = pd.read_csv("tests/fixtures/chart_analysis/seed_path.csv", index_col=0, parse_dates=True)
    frame = IndicatorCalculator().calculate(raw)
    # A current supplied crossover makes every display-window variant non-empty.
    frame["MACD"], frame["MACD_Signal"] = -1.0, 0.0
    frame.iloc[-1, frame.columns.get_loc("MACD")] = 1.0
    required = technical_rule_requests()
    extra = tuple(rule_request(rule.code, parameters) for rule in TRIGGER_RULES)
    base = common_analysis_for_frame(frame, ticker="TEST", rules=required)
    union = common_analysis_for_frame(frame, ticker="TEST", rules=required + extra)
    legacy = TechnicalScorer().score(frame, ticker="TEST", include_history=False)
    expected = build_scorecard(
        frame, legacy, ticker="TEST", as_of=frame.index[-1].date(), common_analysis=base
    )
    actual = build_scorecard(
        frame, legacy, ticker="TEST", as_of=frame.index[-1].date(), common_analysis=union
    )
    assert expected.triggers
    assert actual.model_dump() == expected.model_dump()
    expected_selected = {
        (s.ref.item_id, s.reason_code) for s in expected.fact_selections if s.selected
    }
    assert {
        (s.ref.item_id, s.reason_code) for s in actual.fact_selections if s.selected
    } == expected_selected
    base_ids = {item.id for item in base.items}
    extra_selections = [s for s in actual.fact_selections if s.ref.item_id not in base_ids]
    assert extra_selections
    assert all(
        not s.selected and s.reason_code == "SCORECARD_TRIGGER_VARIANT_NOT_SELECTED"
        for s in extra_selections
    )


def swing_direct_inputs():
    import numpy as np
    import pandas as pd

    frame = pd.DataFrame(
        {
            "Close": [float("nan"), 101.0, 102.0, 99.0, 101.0],
            "High": [110.0] * 5,
            "Low": [80.0] * 5,
            "Volume": [200.0] * 5,
            "SMA_20": [80.0] * 5,
            "SMA_50": [100.0] * 5,
            "SMA_150": [90.0] * 5,
            "SMA_200": [110.0] * 5,
            "SMA_150_Slope_21": [1.0] * 5,
            "SMA_20_Slope_5": [1.0] * 5,
            "High_50_Prev": [100.0] * 5,
            "High_20_Prev": [100.0] * 5,
            "Low_20_Prev": [80.0] * 5,
            "Vol_SMA_20": [100.0] * 5,
            "Vol_SMA_20_Prev": [100.0] * 5,
        }
    )
    return frame, np.ones(5), np.zeros(5, dtype=bool), np.ones(5, dtype=bool)


@pytest.mark.parametrize(
    "entry,owner",
    [
        ("close_location", "close_location_values"),
        ("s_trigger", "swing_s01_array_values"),
        ("structure_breakdown", "swing_structure_values"),
        ("deep_recovery", "swing_deep_recovery_values"),
        ("d_trigger", "swing_d_trigger_array_values"),
    ],
)
def test_swing_direct_rules_delegate_to_common_owner(monkeypatch, entry, owner):
    from src.strategies.swing_w150 import rules
    from src.tools.technical.chart_analysis import _legacy_structure

    monkeypatch.setattr(_legacy_structure, owner, fail, raising=False)
    frame, st, hb, higher_low = swing_direct_inputs()
    calls = {
        "close_location": lambda: rules.close_location(
            frame.High.to_numpy(), frame.Low.to_numpy(), frame.Close.to_numpy()
        ),
        "s_trigger": lambda: rules.s_trigger(frame),
        "structure_breakdown": lambda: rules.structure_breakdown(frame, st, hb),
        "deep_recovery": lambda: rules.deep_recovery(frame, st, hb, higher_low),
        "d_trigger": lambda: rules.d_trigger(frame, higher_low),
    }
    with pytest.raises(OwnerCalledError):
        calls[entry]()


def test_swing_direct_breakout_helpers_keep_replay_nan_and_strict_volume():
    from src.strategies.swing_w150 import rules

    frame, _, _, deep = swing_direct_inputs()
    s_columns = ["Close", "Volume", "SMA_150", "SMA_150_Slope_21", "High_50_Prev", "Vol_SMA_20"]
    assert rules.s_trigger(frame[s_columns]).tolist() == [False, True, False, False, True]
    frame.loc[4, "Volume"] = 140.0
    assert rules.s_trigger(frame[s_columns]).tolist() == [False, True, False, False, False]
    assert rules.d_trigger(frame[["Close", "High_20_Prev", "SMA_50"]], deep).tolist() == [
        False,
        True,
        False,
        False,
        True,
    ]


def test_swing_direct_structure_helper_keeps_sparse_inputs_and_custom_thresholds():
    import numpy as np
    import pandas as pd

    from src.strategies.swing_w150 import rules

    frame = pd.DataFrame(
        {
            "Close": [90.0, 90.0, 90.0, float("nan")],
            "High": [110.0] * 4,
            "Low": [80.0] * 4,
            "Volume": [200.0] * 4,
            "SMA_50": [100.0] * 4,
            "SMA_200": [85.0, 85.0, 100.0, 100.0],
            "Vol_SMA_20_Prev": [100.0] * 4,
            "Low_20_Prev": [80.0, 95.0, 80.0, 80.0],
        }
    )
    st, lhll = np.array([-1.0]), np.array([False, False, True, True])
    assert rules.structure_breakdown(frame, st, lhll).tolist() == [False, True, True, False]
    assert rules.structure_breakdown(frame, st, lhll, weak_close_location=0.4).tolist() == [
        True,
        True,
        True,
        False,
    ]
    assert rules.structure_breakdown(frame, st, lhll, volume_multiple=3).tolist() == [
        False,
        False,
        True,
        False,
    ]
    assert rules.structure_breakdown(frame, st, lhll, volume_multiple=2).tolist() == [
        False,
        True,
        True,
        False,
    ]


def test_swing_direct_deep_helper_keeps_supplied_breakdown_and_broadcasting():
    import numpy as np

    from src.strategies.swing_w150 import rules

    frame, _, _, _ = swing_direct_inputs()
    columns = ["Close", "SMA_20", "SMA_50", "SMA_200", "SMA_20_Slope_5"]
    frame = frame[columns]
    assert rules.deep_recovery(
        frame, np.array([1.0]), np.array([False]), np.array([True])
    ).tolist() == [False, True, True, False, True]
    assert not rules.deep_recovery(frame, np.array([1.0]), np.array([True]), np.array([True])).any()


def test_swing_direct_close_location_keeps_degenerate_range_and_nan():
    import numpy as np

    from src.strategies.swing_w150 import rules

    actual = rules.close_location(
        np.array([11.0, 5.0, 5.0, np.nan]),
        np.array([1.0, 5.0, 6.0, 0.0]),
        np.array([6.0, 7.0, 9.0, 1.0]),
    )
    assert actual.tolist() == [0.5, 0.5, 0.5, 0.5]


def test_swing_direct_helpers_keep_missing_column_and_dtype_errors():
    from src.strategies.swing_w150 import rules

    frame, st, hb, higher_low = swing_direct_inputs()
    for call in (
        lambda: rules.s_trigger(frame.drop(columns="High_50_Prev")),
        lambda: rules.structure_breakdown(frame.drop(columns="Low_20_Prev"), st, hb),
        lambda: rules.deep_recovery(frame.drop(columns="SMA_20_Slope_5"), st, hb, higher_low),
        lambda: rules.d_trigger(frame.drop(columns="High_20_Prev"), higher_low),
    ):
        with pytest.raises(KeyError):
            call()
    frame["SMA_150"] = "90.0"
    with pytest.raises(TypeError):
        rules.s_trigger(frame)


def test_swing_direct_deep_helper_keeps_original_error_order():
    from src.strategies.swing_w150 import rules

    frame, st, hb, higher_low = swing_direct_inputs()
    with pytest.raises(ValueError, match="broadcast"):
        rules.deep_recovery(frame.drop(columns="SMA_20"), st, hb[:-1], higher_low)


@pytest.mark.parametrize("last_close,expected", [(110.0, 0), (float("nan"), -10)])
def test_aprime_velocity_keeps_last_valid_sma_and_original_close(last_close, expected):
    import numpy as np
    import pandas as pd

    from src.tools.technical.chart_analysis._legacy_components import velocity_values
    from src.tools.technical.chart_analysis.registry import rule_request
    from src.tools.technical.context import common_analysis_for_frame
    from src.tools.technical.shadow_v2 import _velocity_state, setup_state_score

    frame = pd.DataFrame(
        {
            "SMA_20": list(np.arange(100.0, 85.0, -1.0)) + [np.nan],
            "Close": [110.0] * 15 + [last_close],
        },
        index=pd.bdate_range("2026-01-01", periods=16),
    )
    assert _velocity_state(frame) == expected
    assert setup_state_score(frame, {}) == expected
    analysis = common_analysis_for_frame(
        frame,
        ticker="TEST",
        rules=tuple(
            rule_request(rule)
            for rule in (
                "chart.velocity.legacy",
                "chart.legacy.state_windows",
                "chart.vcp.legacy",
            )
        ),
    )
    assert setup_state_score(frame, {}, common_analysis=analysis) == expected
    assert velocity_values(frame)["price_above_sma20"]  # Legacy uses last valid Close.


def test_higher_low_reads_only_its_low_window():
    import pandas as pd

    from src.tools.technical.bottoming import _detect_higher_low

    frame = pd.DataFrame({"Low": [1.0] * 30 + [2.0] * 10, "Volume": ["bad"] * 40})
    assert _detect_higher_low(frame)


def test_volume_dry_reads_only_its_volume_window():
    import pandas as pd

    from src.tools.technical.bottoming import _detect_volume_dry

    frame = pd.DataFrame({"Low": ["bad"] * 40, "Volume": [100.0] * 35 + [10.0] * 5})
    assert _detect_volume_dry(frame)


def test_directional_metric_does_not_read_other_state_columns():
    import pandas as pd

    from src.tools.technical.scorecard import _metric

    frame = pd.DataFrame(
        {"Close": [10.0, 10.0], "SMA_20": [9.0, 9.0], "SuperTrend_Dir": ["bad"] * 2}
    )
    assert _metric(frame, "SMA_20", "x", 1).value == 9.0


def test_direct_breakout_keeps_short_history_guard_before_candles():
    import pandas as pd

    from src.tools.technical.components.patterns import _detect_breakout

    frame = pd.DataFrame(
        {"Close": [10.0] * 2, "High": [11.0] * 2, "Low": [9.0] * 2, "Open": ["bad"] * 2}
    )
    assert _detect_breakout(frame) == {"signals": [], "evidence": [], "metrics": {}, "score": 0}


def test_direct_candles_do_not_read_breakout_columns():
    import pandas as pd

    from src.tools.technical.components.patterns import _detect_candlestick_patterns

    frame = pd.DataFrame(
        {
            "Close": [10.0] * 21,
            "High": [11.0] * 21,
            "Low": [8.0] * 21,
            "Open": [9.0] * 21,
            "Swing_High": ["bad"] * 21,
        }
    )
    assert _detect_candlestick_patterns(frame) == {
        "signals": [],
        "evidence": [],
        "metrics": {},
        "score": 0,
    }


@pytest.mark.parametrize(
    "helper,columns,expected",
    [
        ("_buy_flip_age", {"SuperTrend_Dir": [-1.0, 1.0], "Volume": ["bad"] * 2}, (True, 0)),
        (
            "_close_below_sma20_streak",
            {"Close": [1.0, 1.0], "SMA_20": [2.0, 2.0], "Volume": ["bad"] * 2},
            True,
        ),
        (
            "_established_weakness",
            {"Close": [1.0, 1.0], "SMA_50": [2.0, 2.0], "SuperTrend_Dir": ["bad"] * 2},
            True,
        ),
        (
            "_crsi_state",
            {
                "cRSI": [5.0, 5.0],
                "cRSI_HighBand": [80.0, 80.0],
                "cRSI_LowBand": [20.0, 20.0],
                "Close": ["bad"] * 2,
            },
            10,
        ),
    ],
)
def test_shadow_direct_helpers_read_only_their_own_columns(helper, columns, expected):
    import pandas as pd

    from src.tools.technical import shadow_v2

    kwargs = (
        {"days": 2}
        if helper == "_close_below_sma20_streak"
        else {"need": 1, "lookback": 2}
        if helper == "_established_weakness"
        else {}
    )
    assert getattr(shadow_v2, helper)(pd.DataFrame(columns), **kwargs) == expected


def test_swing_s_trigger_converts_volume_before_reading_missing_reference():
    import pandas as pd

    from src.strategies.swing_w150 import rules

    frame = pd.DataFrame(
        {
            "Close": [100.0, 101.0],
            "Volume": ["bad"] * 2,
            "SMA_150": [90.0] * 2,
            "SMA_150_Slope_21": [1.0] * 2,
            "Vol_SMA_20": [100.0] * 2,
        }
    )
    with pytest.raises(ValueError, match="could not convert string to float"):
        rules.s_trigger(frame)

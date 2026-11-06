"""Pre-extraction payloads: wrong windows, policies or evidence must break parity.

Expected JSON is a reviewed capture of ad880af, never computed by these tests.
The smaller literal assertions name the branches hidden inside the large payloads.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.util
import json
import tomllib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.pipelines.analyze_decision import AnalyzeDecisionSummary, apply_playbook_veto
from src.pipelines.strategy_analysis import AnalysisStrategyService, ChartBundleLoader
from src.storage.entry_shadow import EntryShadowJsonlRecorder
from src.strategies.chart_bundle import chart_bundle_from_dataframes
from src.strategies.models import BarFinality, CoverageManifest
from src.strategies.observations.detectors import evaluate_observations
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.playbook import PlaybookStrategy
from src.strategies.runner import StrategyRunner
from src.strategies.swing_w150.adapter import SwingW150SignalStrategy, SwingW150Strategy
from src.strategies.swing_w150.engine import current_state, replay, replay_trace
from src.strategies.swing_w150.features import SwingFeatureFrame
from src.strategies.swing_w150.parameters import SwingW150Parameters
from src.strategies.swing_w150.signals import detect_swing
from src.tools.playbook.accumulation import analyze_accumulation
from src.tools.playbook.exit_rules import evaluate_exit
from src.tools.playbook.gate import evaluate_gate
from src.tools.playbook.market_regime import assess_market_regime
from src.tools.playbook.models import PlaybookVerdict
from src.tools.playbook.relative_strength import compute_relative_strength
from src.tools.playbook.vcp import detect_vcp_breakout
from src.tools.technical.components.minervini import analyze_minervini
from src.tools.technical.indicators import IndicatorCalculator
from src.tools.technical.pivots import confirmed_pivot_events
from src.tools.technical.scorecard_models import DataStatus
from src.tools.technical.scorer import TechnicalScorer
from src.tools.technical.shadow_v2 import ShadowScoreV2, _fresh_close_breakout, apply_hysteresis
from src.tools.technical.triggers import detect_analysis_triggers
from tests.harness.chart_analysis_contract import (
    assert_chart_fixture_contract,
    baseline_payload,
    seeded_consumer_payload,
)
from tests.strategies.swing_w150.conftest import SignalFactory


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/chart_analysis"
TECHNICAL_CASES = {
    "G2_panw_breakout": ("panw_long", "2026-05-07", "PANW"),
    "G2_panw_overheat": ("panw_long", "2026-05-08", "PANW"),
    "G2_be_bottoming": ("be_long", "2026-08-18", "BE"),
    "G2_nvda_trend": ("nvda", "2026-09-09", "NVDA"),
    "G2_lulu_downtrend": ("lulu", "2026-05-15", "LULU"),
    "G2_arm_collapse": ("arm", "2026-07-22", "ARM"),
    "G2_samsung_short": ("samsung", "2026-07-02", "005930.KS"),
}
CASES = (
    "G0_seed",
    "G0_missing",
    "G1_boundaries",
    *TECHNICAL_CASES,
    "G2_hysteresis",
    "G2_playbook",
    "G3_swing_final",
    "G3_swing_preview",
    "G3_swing_explicit_v2",
    "G3_swing_breakout",
    "G3_entry_lifecycle",
    "G3_state_branches",
    "G3_anchors_shadow",
    "G3_replay_COIN",
    "G3_replay_AMAT",
    "G3_replay_PYPL",
    "G3_replay_UPST",
    "G4_runner",
    "G4_coverage_extrema",
    "G4_service",
)


def _bundle(
    raw, *, ticker="TEST", market=None, market_ticker="^GSPC", provisional=False, listing=False
):
    def coverage(frame):
        days = tuple(frame.index.date)
        return CoverageManifest(
            requested_start=days[0],
            actual_start=days[0],
            actual_end=days[-1],
            expected_sessions=days,
            complete=True,
            listing_first_session=days[0] if listing else None,
        )

    day = raw.index[-1].date()
    return chart_bundle_from_dataframes(
        profile_version="chart-v1",
        ticker=ticker,
        as_of=day,
        instrument=raw,
        instrument_coverage=coverage(raw),
        exchange_sessions=tuple(raw.index.date),
        market=market,
        market_coverage=coverage(market) if market is not None else None,
        market_ticker=market_ticker if market is not None else None,
        observed_at=datetime(day.year, day.month, day.day, 12 if provisional else 23, tzinfo=UTC),
    )


def _technical(raw, ticker):
    return TechnicalScorer().score(IndicatorCalculator().calculate(raw), ticker=ticker)


def _trigger_frame():
    dates = pd.bdate_range("2025-01-01", periods=230)
    return pd.DataFrame(
        {
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.0,
            "Volume": 100.0,
            "Vol_SMA_20": 100.0,
            "High_20_Prev": 102.0,
            "SMA_20": 100.0,
            "SMA_50": 100.0,
        },
        index=dates,
    )


def _triggers(frame):
    return detect_analysis_triggers(frame, as_of=frame.index[-1].date())


def _boundary_payload():
    frame = _trigger_frame()
    frame.loc[frame.index[-1], "High"] = 105
    wick = _triggers(frame)
    wick_close = _fresh_close_breakout(frame)
    frame.loc[frame.index[-1], "Close"] = 104
    close = _triggers(frame)
    close_breakout = _fresh_close_breakout(frame)
    ttl = _trigger_frame()
    ttl.loc[ttl.index[-7], ["Open", "High", "Close", "Volume"]] = [106, 107, 106, 400]
    ttl.loc[ttl.index[-6] :, "Close"] = 106
    cross = _trigger_frame()
    cross.loc[cross.index[-1], "SMA_20"] = 101
    cross_up = _triggers(cross)
    cross.loc[cross.index[-1], "SMA_20"] = 100
    low = np.array([5, 6, 7, 10, 10, 8, 6, 3, 7, 8, 9, 10, 10, 8, 7, 3, 8, 9, 10.0])
    mask = np.ones(len(low), dtype=bool)
    mask[11] = False
    observations = {}
    for count in (2, 3, 4):
        features = SwingFeatureFrame(
            pd.DataFrame(
                {"Close": [101, 99, 100, 101][:count], "ATR": 2, "SMA_50": 100},
                index=pd.bdate_range("2024-01-02", periods=count),
            ),
            DataStatus.COMPLETE,
            (BarFinality.FINAL,) * count,
        )
        observations[f"anchor_{count}"] = evaluate_observations(
            "TEST",
            features,
            [],
            [],
            source_contexts=[],
            params=ObservationParameters(break_buffer_atr=0, reclaim_buffer_atr=0),
        )
    return {
        "wick": wick,
        "wick_close_breakout": wick_close,
        "close": close,
        "close_breakout": close_breakout,
        "ttl5": _triggers(ttl.iloc[:-1]),
        "ttl6": _triggers(ttl),
        "equal_to_above_sma": cross_up,
        "equal_sma": _triggers(cross),
        "equal_pivots": confirmed_pivot_events(low + 1, low),
        "masked_pivots": confirmed_pivot_events(low + 1, low, final_mask=mask),
        **observations,
    }


def _state_branches():
    factory = SignalFactory()
    params = SwingW150Parameters()
    volume = factory.make(
        [{"Close": 150, "High": 151, "Volume": 145, "Vol_SMA_20": 105, "Vol_SMA_20_Prev": 100}]
    )
    prev_volume = replace(volume, frame=volume.frame.copy())
    prev_volume.frame.loc[prev_volume.frame.index[-1], "Vol_SMA_20"] = 100
    equal = factory.make(
        [
            {"Close": 108, "Low": 107},
            {"Close": 110},
            {"Close": 108, "Low": 107},
            {"Close": 107, "Low": 106},
        ]
    )
    return {
        name: detect_swing("TEST", features, params)
        for name, features in {
            "volume_incl20": volume,
            "volume_prev20_mutant": prev_volume,
            "sma150_equal_resets": equal,
            "same_day_exit_entry": factory.same_day_exit_and_entry(),
            "same_day_exit_correction": factory.same_day_exit_and_overheat_correction(),
            "pullback": factory.pullback_reversal("SMA_50"),
            "pullback_expired": factory.pullback_expired_then_breakout(),
        }.items()
    }


def _hysteresis():
    # Hand specified raw states: weak positive -> negative for 1/2 days -> recovery.
    rows = [
        ShadowScoreV2(score, band, "weak", True, None, False, False, action, False)
        for score, band, action in [
            (5, "중", "watch"),
            (-10, "음", "reduce"),
            (-10, "음", "reduce"),
            (5, "중", "watch"),
        ]
    ]
    rows += [
        replace(rows[1], volume_breakdown=True, action_v2="avoid"),
        replace(rows[0], regime="above50"),
        replace(rows[1], st_up=False),
    ]
    return {"raw": rows, "effective": apply_hysteresis(rows)}


def _playbook(raw, market):
    stock = IndicatorCalculator().calculate(raw)
    regime = assess_market_regime(market, "^GSPC")
    rs = compute_relative_strength(stock, market, "^GSPC")
    accumulation = analyze_accumulation(stock)
    vcp = detect_vcp_breakout(stock)
    gate = evaluate_gate(
        market_regime=regime,
        is_stage2=analyze_minervini(stock).metrics.get("is_stage2"),
        relative_strength=rs,
        sector_strength=None,
        vcp=vcp,
        canslim=None,
        flow=None,
        chart_only=True,
    )
    lows = stock["Swing_Low"].dropna()
    exit_ = evaluate_exit(
        df=stock,
        snapshot=SimpleNamespace(
            high_52w=float(stock.iloc[-1]["High_52w"]),
            swing_low=float(lows.iloc[-1]) if len(lows) else None,
        ),
        relative_strength=rs,
        accumulation=accumulation,
    )
    summary = AnalyzeDecisionSummary(
        leader="technical",
        core_variables=["가격 모멘텀"],
        action="매수",
        timing="조정_대기",
        action_sentence="눌림 후 접근",
    )

    def veto(holding):
        verdict = PlaybookVerdict(
            ticker="TEST",
            holding=holding,
            market_regime=regime,
            relative_strength=rs,
            sector_strength=None,
            canslim=None,
            gate=gate,
            position_plan=None,
            exit_verdict=exit_ if holding else None,
            headline="offline baseline",
        )
        return apply_playbook_veto(summary, verdict)

    return {
        "regime": regime,
        "rs": rs,
        "accumulation": accumulation,
        "vcp": vcp,
        "gate": gate,
        "exit": exit_,
        "veto_flat": veto(False),
        "veto_holding": veto(True),
        "complete": PlaybookStrategy().evaluate(_bundle(raw, market=market)),
        "partial": PlaybookStrategy().evaluate(_bundle(raw)),
        "short": PlaybookStrategy().evaluate(_bundle(raw.iloc[-200:], market=market)),
    }


async def _service_payload(raw):
    # The same local stock prices act as a synthetic benchmark proxy, not SPY data.
    class LocalMarketProvider:
        async def get_price_history(self, ticker, period):
            assert (ticker, period) == ("SPY", "2y")
            return raw.copy()

    technical = _technical(raw, "PANW")
    day = raw.index[-1].date()
    technical.timestamp = datetime(day.year, day.month, day.day, 23, tzinfo=UTC)
    loader = ChartBundleLoader(LocalMarketProvider())
    chart = await loader.load(ticker="PANW", technical=technical, as_of=day)
    with TemporaryDirectory(prefix="jarvis-chart-baseline-") as directory:
        recorder = EntryShadowJsonlRecorder(Path(directory) / "shadow.jsonl")
        service = AnalysisStrategyService(chart_loader=loader, shadow_recorder=recorder)
        pipelines = {
            pipeline: await service.evaluate("PANW", technical, as_of=day, pipeline=pipeline)
            for pipeline in ("check", "analyze", "brief")
        }
        rows = [json.loads(line) for line in recorder.path.read_text().splitlines()]
        for row in rows:
            del row["recorded_at"]  # Execution wall clock; snapshot_key already excludes it.
    return {
        "chart": chart,
        "pipelines": pipelines,
        "recorder": rows,
        "v1_3y": SwingW150Strategy().evaluate(chart),
    }


def capture_case(case, load, *, common_analysis=False):
    """Run current consumers; the caller supplies the separate frozen expected JSON."""
    if case in {"G0_seed", "G0_missing"}:
        raw = load("seed")
        if case == "G0_missing":
            raw.loc[raw.index[31], "Close"] = np.nan
            raw.loc[raw.index[43], "Volume"] = np.nan
        result = IndicatorCalculator().calculate(raw)
    elif case == "G1_boundaries":
        result = _boundary_payload()
    elif case in TECHNICAL_CASES:
        name, cutoff, ticker = TECHNICAL_CASES[case]
        if common_analysis:
            from tests.tools.technical.chart_analysis.test_legacy_consumers import analysis_for

            frame = IndicatorCalculator().calculate(load(name).loc[:cutoff])
            analysis = analysis_for(frame, ticker=ticker)
            result = TechnicalScorer().score(frame, ticker=ticker, common_analysis=analysis)
        else:
            result = _technical(load(name).loc[:cutoff], ticker)
    elif case == "G2_hysteresis":
        result = _hysteresis()
    elif case == "G2_playbook":
        result = _playbook(load("seed"), load("seed"))
    elif case in {"G3_swing_final", "G3_swing_preview", "G3_swing_explicit_v2"}:
        from scripts.research_trading_observations import explicit_research_parameters

        params = explicit_research_parameters() if case.endswith("explicit_v2") else None
        result = SwingW150SignalStrategy(params).evaluate_signals(
            _bundle(load("v2"), provisional=case.endswith("preview"))
        )
    elif case in {"G3_swing_breakout", "G3_entry_lifecycle"}:
        root = FIXTURES.parent / "swing_w150"
        tail = json.loads((root / "v2_backtest_expected.json").read_text())["raw_tail"]
        raw = load("v2").iloc[:250].copy()
        for row in tail:
            raw.loc[pd.Timestamp(row["date"])] = row["ohlcv"]
        if case == "G3_swing_breakout":
            result = SwingW150SignalStrategy().evaluate_signals(_bundle(raw))
        else:
            result = {
                str(count): SwingW150SignalStrategy().evaluate_signals(
                    _bundle(raw.iloc[:count], market=raw.iloc[:count], market_ticker="SPY")
                )
                for count in (251, 252, 255)
            }
    elif case == "G3_state_branches":
        result = _state_branches()
    elif case == "G3_anchors_shadow":
        from src.strategies.entry_anchors import build_entry_source_anchors
        from src.strategies.entry_shadow import evaluate_entry_shadow
        from tests.strategies.test_entry_anchors import _inputs as anchor_inputs
        from tests.strategies.test_entry_shadow import _inputs as shadow_inputs

        source, chart, features, episode = anchor_inputs()
        opportunity, shadow_chart = shadow_inputs((110, 99, 100))
        result = {
            "anchors": build_entry_source_anchors(source, chart, features, [episode]),
            "source": source,
            "shadow_source": opportunity,
            "breach": evaluate_entry_shadow(
                opportunity, shadow_chart.prefix(shadow_chart.exchange_sessions[1])
            ),
            "equal_reclaim": evaluate_entry_shadow(opportunity, shadow_chart),
        }
    elif case.startswith("G3_replay_"):
        raw = load(case.removeprefix("G3_replay_"))
        result = {"trace": replay_trace(raw), "trades": replay(raw), "current": current_state(raw)}
    elif case == "G4_runner":
        raw = load("v2")
        result = StrategyRunner().run(
            _bundle(raw, market=raw), legacy_result=_technical(raw, "TEST")
        )
    elif case == "G4_coverage_extrema":
        raw = load("seed")
        # A 2y-style request cannot silently satisfy the V1 adapter's 3y contract.
        chart = _bundle(raw)
        listed = _bundle(raw, listing=True)
        prefix = raw.iloc[:-2]
        result = {
            "unproven_3y": SwingW150Strategy().evaluate(chart),
            "listing_coverage": SwingW150Strategy().evaluate(listed),
            "bundle_hash": chart.bundle_hash,
            "prefix_hash": chart.prefix(prefix.index[-1].date()).bundle_hash,
            "prefix_extrema": IndicatorCalculator().calculate(prefix)[["Swing_High", "Swing_Low"]],
            "full_extrema": IndicatorCalculator().calculate(raw)[["Swing_High", "Swing_Low"]],
        }
    elif case == "G4_service":
        raw = load("panw_long").loc["2024-05-07":"2026-05-07"]
        result = asyncio.run(_service_payload(raw))
    else:
        raise AssertionError(case)
    return baseline_payload(result, consumer=case)


def _first_difference(actual, expected, path="payload"):
    if isinstance(actual, dict) and isinstance(expected, dict) and actual.keys() == expected.keys():
        for key in actual:
            if actual[key] != expected[key]:
                return _first_difference(actual[key], expected[key], f"{path}.{key}")
    if isinstance(actual, list) and isinstance(expected, list) and len(actual) == len(expected):
        for index, (item, wanted) in enumerate(zip(actual, expected, strict=True)):
            if item != wanted:
                return _first_difference(item, wanted, f"{path}[{index}]")
    return path, actual, expected


@pytest.mark.parametrize("case", CASES)
def test_complete_existing_consumer_payload_is_preserved(case, chart_fixture):
    """Catch changed values, evidence, IDs, dates, order, nulls and status together."""
    expected = json.loads((FIXTURES / "consumer_expected.json").read_text())
    actual = (
        seeded_consumer_payload(case)
        if case in TECHNICAL_CASES or case == "G4_service"
        else capture_case(case, chart_fixture)
    )
    if case == "G4_service":
        # The new API is checked explicitly; every pre-existing field stays frozen.
        pipelines = actual["payload"]["pipelines"]
        assert set(pipelines) == {"check", "analyze", "brief"}
        for pipeline in ("check", "analyze", "brief"):
            assert pipelines[pipeline].pop("position_plans") == {}
    assert actual == expected[case], _first_difference(actual, expected[case])


def test_backend_and_fixture_identity_are_explicit(chart_fixture):
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    for name in manifest["inputs"]:
        chart_fixture(name)
    lock = tomllib.loads(Path("uv.lock").read_text())
    locked_packages = {(package["name"], package["version"]) for package in lock["package"]}
    for name, version in manifest["environment"]["packages"].items():
        assert importlib.metadata.version(name) == version
        assert (name, version) in locked_packages, (
            f"Backend pin missing from uv.lock: {name}=={version}"
        )
    assert (importlib.util.find_spec("talib") is not None) == manifest["environment"][
        "talib_installed"
    ]


def test_wick_only_and_close_breakout_keep_distinct_branches():
    result = _boundary_payload()
    assert result["wick_close_breakout"] is False
    assert result["close_breakout"] is True
    assert any(item.code == "analysis.price.high_20_breakout" for item in result["wick"])


def test_ttl_equality_and_sma_equality_do_not_shift_one_session():
    result = _boundary_payload()

    def power(rows):
        return next(row for row in rows if row.code == "analysis.volume.power_gap_up")

    assert (power(result["ttl5"]).bars_ago, power(result["ttl5"]).status.value) == (5, "active")
    assert (power(result["ttl6"]).bars_ago, power(result["ttl6"]).status.value) == (6, "expired")
    assert any(
        item.code == "analysis.sma.20_50.golden_cross" for item in result["equal_to_above_sma"]
    )
    assert not result["equal_sma"]


def test_anchor_equal_price_stays_breached_until_strict_reclaim():
    result = _boundary_payload()
    assert [item.status.value for item in result["anchor_2"]] == ["active"]
    assert [item.status.value for item in result["anchor_3"]] == ["active"]
    assert [item.status.value for item in result["anchor_4"]] == ["resolved", "resolved"]


def test_preview_signal_becomes_final_without_rewriting_older_signals(chart_fixture):
    preview = SwingW150SignalStrategy().evaluate_signals(
        _bundle(chart_fixture("v2"), provisional=True)
    )
    final = SwingW150SignalStrategy().evaluate_signals(_bundle(chart_fixture("v2")))
    assert [signal.finality.value for signal in preview.signal_history] == [
        "final",
        "final",
        "provisional",
    ]
    assert [signal.finality.value for signal in final.signal_history] == ["final", "final", "final"]
    assert preview.signal_history[:-1] == final.signal_history[:-1]


def test_swing_volume_and_same_day_order_are_consumer_policy():
    result = _state_branches()
    assert not result["volume_incl20"].current_signals
    assert [s.code for s in result["volume_prev20_mutant"].current_signals] == [
        "TREND_BREAKOUT_ENTRY"
    ]
    assert [s.code for s in result["same_day_exit_entry"].current_signals] == [
        "SMA150_EXIT",
        "PULLBACK_REVERSAL_ENTRY",
    ]
    exits = [
        s.occurred_on.isoformat()
        for s in result["sma150_equal_resets"].signal_history
        if s.code == "SMA150_EXIT"
    ]
    assert exits == ["2024-12-20"]


def test_hysteresis_confirms_second_demotion_and_immediate_hard_override():
    result = _hysteresis()
    assert [r.setup_score for r in result["raw"]] == [5, -10, -10, 5, -10, 5, -10]
    assert [r.setup_score for r in result["effective"]] == [5, 5, -10, 5, -10, 5, -10]
    assert [r.action_v2 for r in result["effective"]] == [
        "watch",
        "watch",
        "reduce",
        "watch",
        "avoid",
        "watch",
        "reduce",
    ]


def test_fixture_contract_rejects_ohlcv_mutation(chart_fixture):
    raw = chart_fixture("seed")
    manifest = json.loads((FIXTURES / "manifest.json").read_text())["inputs"]["seed"]
    raw.loc[raw.index[-1], "High"] = raw.iloc[-1]["Low"] - 1
    with pytest.raises(AssertionError):
        assert_chart_fixture_contract(raw, manifest)


def test_changed_raw_price_fails_the_frozen_feature_baseline(chart_fixture):
    raw = chart_fixture("seed")
    raw.loc[raw.index[-1], "Close"] += 0.5
    expected = json.loads((FIXTURES / "consumer_expected.json").read_text())["G0_seed"]
    with pytest.raises(AssertionError):
        assert capture_case("G0_seed", lambda _: raw) == expected


def test_pivot_equality_keeps_original_indices_and_three_final_bar_confirmation():
    result = _boundary_payload()
    assert [(p.pivot_index, p.confirmed_index, p.relation) for p in result["equal_pivots"]] == [
        (3, 6, None),
        (7, 10, None),
        (11, 14, None),
        (15, 18, None),
    ]
    assert [(p.pivot_index, p.confirmed_index) for p in result["masked_pivots"]] == [
        (3, 6),
        (7, 10),
        (12, 15),
        (15, 18),
    ]


@pytest.mark.parametrize("case", TECHNICAL_CASES)
def test_legacy_full_payload_parity(case):
    """Common facts must preserve every Legacy field, trace and history reason."""
    actual = seeded_consumer_payload(case, common_analysis=True)
    expected = json.loads((FIXTURES / "consumer_expected.json").read_text())[case]
    for payload in (actual["payload"], expected["payload"]):
        payload.pop("shadow_v2")
        payload.pop("scorecard")
    assert actual == expected, _first_difference(actual, expected)


@pytest.mark.parametrize("case", TECHNICAL_CASES)
def test_aprime_raw_and_hysteresis_parity(case, chart_fixture):
    from src.tools.technical.context import build_market_context
    from src.tools.technical.shadow_v2 import compute_shadow_v2
    from tests.tools.technical.chart_analysis.test_legacy_consumers import analysis_for

    name, cutoff, ticker = TECHNICAL_CASES[case]
    frame = IndicatorCalculator().calculate(chart_fixture(name).loc[:cutoff])
    legacy = TechnicalScorer().score(frame, ticker=ticker, include_history=False)
    common = analysis_for(frame)
    result = compute_shadow_v2(
        frame, legacy.components, build_market_context(frame), common_analysis=common
    )
    expected = json.loads((FIXTURES / "consumer_expected.json").read_text())[case]["payload"][
        "shadow_v2"
    ]
    assert baseline_payload(result, consumer=case)["payload"] == expected
    old_rows, common_rows = [], []
    for count in range(max(1, len(frame) - 3), len(frame) + 1):
        prefix = frame.iloc[:count]
        context = build_market_context(prefix)
        old_rows.append(compute_shadow_v2(prefix, legacy.components, context))
        common_rows.append(
            compute_shadow_v2(
                prefix, legacy.components, context, common_analysis=analysis_for(prefix)
            )
        )
    assert apply_hysteresis(common_rows) == apply_hysteresis(old_rows)


@pytest.mark.parametrize("case", TECHNICAL_CASES)
def test_scorecard_full_payload_parity(case, chart_fixture):
    from src.tools.technical.scorecard import build_scorecard
    from tests.tools.technical.chart_analysis.test_legacy_consumers import analysis_for

    name, cutoff, ticker = TECHNICAL_CASES[case]
    frame = IndicatorCalculator().calculate(chart_fixture(name).loc[:cutoff])
    legacy = TechnicalScorer().score(frame, ticker=ticker, include_history=False)
    common = analysis_for(frame, ticker=ticker)
    result = build_scorecard(
        frame, legacy, ticker=ticker, as_of=frame.index[-1].date(), common_analysis=common
    )
    expected = json.loads((FIXTURES / "consumer_expected.json").read_text())[case]["payload"][
        "scorecard"
    ]
    assert baseline_payload(result, consumer=case)["payload"] == expected


def _assert_playbook_policy_parity(bundle, common):
    """Independent old numerical bodies feed unchanged gate/exit policy."""
    from src.strategies.models import EntryIntent, ExitIntent
    from src.strategies.playbook import _frame

    result = PlaybookStrategy().evaluate(bundle, common_analysis=common)
    instrument = bundle.instrument
    if not (
        instrument.coverage.complete
        and instrument.coverage.truncation_reason is None
        and len(instrument.bars) >= 221
    ):
        assert result.entry.intent is EntryIntent.NOT_EVALUATED
        assert result.exit.intent is ExitIntent.NOT_EVALUATED
        assert [reason.code for reason in result.entry.reasons] == ["insufficient_chart"]
        return result
    stock = IndicatorCalculator().calculate(_frame(instrument))
    market_ready = (
        bundle.market is not None
        and bundle.market.coverage.complete
        and bundle.market.coverage.truncation_reason is None
        and len(bundle.market.bars) >= 221
        and bundle.market.bars[-1].session_date == bundle.as_of
    )
    ready = (
        market_ready
        and len(set(stock.index.date) & {bar.session_date for bar in bundle.market.bars}) >= 21
    )
    rs = None
    if ready:
        market = _frame(bundle.market)
        rs = compute_relative_strength(stock, market, bundle.market_ticker)
        gate = evaluate_gate(
            market_regime=assess_market_regime(market, bundle.market_ticker),
            is_stage2=analyze_minervini(stock).metrics.get("is_stage2"),
            relative_strength=rs,
            sector_strength=None,
            vcp=detect_vcp_breakout(stock),
            canslim=None,
            flow=None,
            chart_only=True,
        )
        assert [check.name for check in gate.checklist] == ["A", "B", "C", "E"]
        assert result.entry.intent is (EntryIntent.ALLOW if gate.passed else EntryIntent.BLOCK)
        assert [(reason.code, reason.message) for reason in result.entry.reasons] == [
            ("gate", gate.veto_reason or "Chart gate passed")
        ]
        assert result.entry.data_status is DataStatus.COMPLETE
    else:
        assert result.entry.intent is EntryIntent.NOT_EVALUATED
        assert result.entry.data_status is DataStatus.INSUFFICIENT_DATA
        assert [reason.code for reason in result.entry.reasons] == [
            "insufficient_rs_chart" if market_ready else "missing_market_chart"
        ]
    lows = stock.Swing_Low.dropna()
    exit_ = evaluate_exit(
        df=stock,
        snapshot=SimpleNamespace(
            high_52w=float(stock.iloc[-1].High_52w),
            swing_low=float(lows.iloc[-1]) if len(lows) else None,
        ),
        relative_strength=rs,
        accumulation=analyze_accumulation(stock),
    )
    assert (
        result.exit.intent
        is {"hold": ExitIntent.HOLD, "reduce": ExitIntent.REDUCE, "liquidate": ExitIntent.EXIT}[
            exit_.action
        ]
    )
    expected = [(signal.code, signal.detail) for signal in exit_.signals]
    if not ready:
        expected += [(reason.code, reason.message) for reason in result.entry.reasons]
    assert [(reason.code, reason.message) for reason in result.exit.reasons] == expected
    assert result.exit.data_status is (DataStatus.COMPLETE if ready else DataStatus.PARTIAL)
    assert PlaybookStrategy().evaluate(bundle).model_dump() == result.model_dump()
    return result


@pytest.mark.parametrize("count", [220, 221, 260])
@pytest.mark.parametrize("market", [True, False])
def test_playbook_gate_exit_evidence_parity(count, market):
    from src.tools.playbook.common import common_analysis_for_bundle
    from tests.strategies.test_playbook import _bundle as boundary_bundle

    bundle = boundary_bundle(count=count, market=market)
    _assert_playbook_policy_parity(bundle, common_analysis_for_bundle(bundle))


@pytest.mark.parametrize(
    "case", ["original", "market_only", "missing", "stale", "shared20", "shared21"]
)
def test_playbook_market_dependency_parity(case, chart_fixture):
    from src.tools.playbook.common import common_analysis_for_bundle
    from tests.strategies.test_playbook import _bundle as boundary_bundle

    if case.startswith("shared"):
        bundle = boundary_bundle(common_sessions=int(case[-2:]))
    else:
        stock = chart_fixture("nvda")
        # Existing local real-stock capture is an explicit benchmark proxy, not index data.
        market = chart_fixture("lulu").loc[: stock.index[-1]].copy()
        if case == "market_only":
            market.loc[market.index[-30:], "Close"] *= 0.8
        if case == "missing":
            market = None
        if case == "stale":
            market = market.iloc[:-1]
        bundle = _bundle(stock, market=market, market_ticker="LULU_PROXY")
    common = common_analysis_for_bundle(bundle)
    result = _assert_playbook_policy_parity(bundle, common)
    selected = {item.id: item.rule_id for item in common.items}
    consumed = {
        selected[selection.ref.item_id]
        for selection in result.fact_selections
        if selection.selected
    }
    assert ("chart.rs" in consumed) is (case not in {"missing", "stale", "shared20"})


@pytest.mark.parametrize(
    "case",
    [
        "G3_swing_final",
        "G3_swing_preview",
        "G3_swing_explicit_v2",
        "G3_swing_breakout",
        "G3_entry_lifecycle",
    ],
)
def test_swing_v2_full_history_parity(case, chart_fixture, monkeypatch):
    from src.strategies.swing_w150.adapter import _frame
    from src.strategies.swing_w150.common import raw_swing_analysis

    original = SwingW150SignalStrategy.evaluate_signals

    def common(self, bundle, **kwargs):
        analysis = raw_swing_analysis(
            _frame(bundle),
            self.parameters,
            ticker=bundle.ticker,
            finalities=[bar.finality for bar in bundle.instrument.bars],
            coverage=bundle.instrument.coverage,
            bundle=bundle,
        )
        return original(self, bundle, common_analysis=analysis)

    monkeypatch.setattr(SwingW150SignalStrategy, "evaluate_signals", common)
    expected = json.loads((FIXTURES / "consumer_expected.json").read_text())[case]
    actual = capture_case(case, chart_fixture)
    assert actual == expected, _first_difference(actual, expected)


@pytest.mark.parametrize("ticker", ["COIN", "AMAT", "PYPL", "UPST"])
def test_swing_v1_replay_trace_parity(ticker, chart_fixture):
    from src.strategies.swing_w150.common import raw_swing_analysis

    raw = chart_fixture(ticker)
    analysis = raw_swing_analysis(raw, SwingW150Parameters())
    actual = baseline_payload(
        {
            "trace": replay_trace(raw, common_analysis=analysis),
            "trades": replay(raw, common_analysis=analysis),
            "current": current_state(raw, common_analysis=analysis),
        },
        consumer=f"G3_replay_{ticker}",
    )
    expected = json.loads((FIXTURES / "consumer_expected.json").read_text())[f"G3_replay_{ticker}"]
    assert actual == expected, _first_difference(actual, expected)


def test_observation_and_shadow_evidence_parity(chart_fixture, monkeypatch):
    import src.strategies.observations.detectors as detectors
    from src.strategies.observations.common import observation_analysis

    original = detectors.evaluate_observations

    def common(ticker, features, signals, setups, *, source_contexts, params, **kwargs):
        analysis = observation_analysis(ticker, features, source_contexts, params)
        return original(
            ticker,
            features,
            signals,
            setups,
            source_contexts=source_contexts,
            params=params,
            common_analysis=analysis,
        )

    monkeypatch.setattr(
        __import__(__name__, fromlist=["evaluate_observations"]), "evaluate_observations", common
    )
    expected = json.loads((FIXTURES / "consumer_expected.json").read_text())
    for case in ("G1_boundaries", "G3_anchors_shadow", "G3_state_branches"):
        actual = capture_case(case, chart_fixture)
        assert actual == expected[case], _first_difference(actual, expected[case])

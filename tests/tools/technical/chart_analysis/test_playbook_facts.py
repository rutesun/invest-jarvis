"""Playbook adapters consume request-scoped facts without changing policy."""

from dataclasses import replace
from importlib import import_module

import pandas as pd
import pytest

from src.tools.playbook.accumulation import analyze_accumulation
from src.tools.playbook.market_regime import assess_market_regime
from src.tools.playbook.relative_strength import compute_relative_strength
from src.tools.playbook.vcp import detect_vcp_breakout
from src.tools.technical.chart_analysis import AnalysisRequestContext
from src.tools.technical.chart_analysis.models import CalculationScope
from src.tools.technical.chart_analysis.registry import rule_request
from tests.tools.technical.chart_analysis.test_features import bars, scope_for


def analysis_for(stock, market=None, rules=None):
    scope = scope_for(stock, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF")
    related = {}
    if market is not None:
        related["market"] = scope_for(
            market, feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF"
        ).primary
    return AnalysisRequestContext().get(
        CalculationScope(scope.primary, related),
        tuple(
            rule_request(rule)
            for rule in rules
            or ("chart.vcp.playbook", "chart.accumulation.days", "chart.market.regime", "chart.rs")
        ),
    )


def vcp_frame():
    frame = bars([100.0] * 29 + [102.0])
    frame["ATR"] = [10.0] * 26 + [7.996] * 4
    frame["Vol_SMA_50"] = 100.0
    frame.loc[frame.index[-1], "Volume"] = 150.0
    return frame


@pytest.mark.parametrize("volume,breakout", [(149.99, False), (150.0, True)])
def test_playbook_vcp_consumes_raw_contraction_and_inclusive_volume(volume, breakout):
    frame = vcp_frame()
    frame.loc[frame.index[-1], "Volume"] = volume
    old = detect_vcp_breakout(frame)
    common = analysis_for(frame, rules=("chart.vcp.playbook",))
    assert detect_vcp_breakout(frame, common_analysis=common) == old
    assert old.in_vcp is True
    assert old.breakout is breakout
    assert old.pivot == 101.0


@pytest.mark.parametrize("case", ["zero", "flat_range", "mixed"])
def test_playbook_accumulation_preserves_zero_denominator_and_flat_range(case):
    frame = bars([100.0] * 26)
    if case != "zero":
        frame.loc[frame.index[-1], ["High", "Low", "Close", "Volume"]] = [101, 101, 101, 20]
    if case == "mixed":
        frame.loc[frame.index[-3], ["Close", "Volume"]] = [99, 20]
    old = analyze_accumulation(frame)
    common = analysis_for(frame, rules=("chart.accumulation.days",))
    assert analyze_accumulation(frame, common_analysis=common) == old
    if case == "zero":
        assert old.accumulation_ratio == 0
    else:
        assert old.accumulation_days == 1


def test_market_regime_preserves_lag20_endpoint_and_details():
    frame = bars(list(range(100, 321)))
    old = assess_market_regime(frame, "TEST")
    common = analysis_for(frame, frame, ("chart.market.regime",))
    result = assess_market_regime(frame, "TEST", common_analysis=common)
    assert result == old
    item = common.items[0]
    assert item.evidence["sma_200_lag20"] == frame.Close.rolling(200).mean().iloc[-21]


def test_rs_adapter_uses_both_frames_and_original_rounding():
    stock = bars(list(range(100, 361)))
    market = bars(list(range(200, 461)))
    common = analysis_for(stock, market, ("chart.rs",))
    assert compute_relative_strength(
        stock, market, "TEST", common_analysis=common
    ) == compute_relative_strength(stock, market, "TEST")
    changed = market.copy()
    changed.loc[changed.index[-1], "Close"] *= 1.02
    with pytest.raises(ValueError, match="scope"):
        compute_relative_strength(stock, changed, "TEST", common_analysis=common)


def test_common_adapters_bypass_old_numerical_bodies(monkeypatch):
    stock = vcp_frame()
    market = bars(list(range(100, 321)))
    stock = pd.concat([bars([100.0] * 191), stock.set_axis(market.index[-30:])])
    # Avoid overlapping sessions while retaining the supplied final VCP window.
    stock.index = market.index
    expected = (
        detect_vcp_breakout(stock),
        analyze_accumulation(stock),
        assess_market_regime(market, "TEST"),
        compute_relative_strength(stock, market, "TEST"),
    )
    common = analysis_for(stock, market)

    def forbidden(*args, **kwargs):
        raise AssertionError("old numerical body called")

    monkeypatch.setattr(import_module("src.tools.playbook.vcp"), "_detect_vcp", forbidden)
    monkeypatch.setattr(pd.DataFrame, "tail", forbidden)
    monkeypatch.setattr(pd.Series, "rolling", forbidden)
    actual = (
        detect_vcp_breakout(stock, common_analysis=common),
        analyze_accumulation(stock, common_analysis=common),
        assess_market_regime(market, "TEST", common_analysis=common),
        compute_relative_strength(stock, market, "TEST", common_analysis=common),
    )
    assert actual == expected


def test_vcp_compatibility_alias_is_retained_but_default_uses_common_owner(monkeypatch):
    from src.tools.playbook import vcp
    from src.tools.technical.components.patterns import _detect_vcp

    assert vcp._detect_vcp is _detect_vcp
    frame = vcp_frame()
    expected = vcp.detect_vcp_breakout(frame)

    def forbidden(*args, **kwargs):
        raise AssertionError("compatibility alias must not own the new calculation")

    monkeypatch.setattr(vcp, "_detect_vcp", forbidden)
    assert vcp.detect_vcp_breakout(frame) == expected


def test_public_rs_short_window_exception_is_preserved():
    frame = bars([100] * 19)
    with pytest.raises(ValueError, match="min_periods"):
        compute_relative_strength(frame, frame, "TEST")


def rs_analysis_for(stock, market):
    from src.tools.technical.chart_analysis.models import SeriesInput

    template = scope_for(
        stock if not stock.empty else bars([100.0]),
        feature_version="SUPPLIED_LEGACY_FEATURE_AD880AF",
    ).primary.manifest
    primary = SeriesInput(replace(template, input_hash=""), stock)
    benchmark = SeriesInput(replace(template, input_hash=""), market)
    return AnalysisRequestContext().get(
        CalculationScope(primary, {"market": benchmark}), (rule_request("chart.rs"),)
    )


@pytest.mark.parametrize("count", [0, 1, 2, 19, 20, 21])
def test_common_rs_preserves_exact_short_return_exception_contract(count):
    stock = bars(list(range(100, 100 + count)))
    market = bars(list(range(200, 200 + count)))
    common = rs_analysis_for(stock, market)
    if 2 <= count < 20:
        with pytest.raises(ValueError, match="min_periods") as original:
            compute_relative_strength(stock, market, "TEST")
        with pytest.raises(ValueError, match="min_periods") as injected:
            compute_relative_strength(stock, market, "TEST", common_analysis=common)
        assert str(injected.value) == str(original.value)
    else:
        original = compute_relative_strength(stock, market, "TEST")
        assert compute_relative_strength(stock, market, "TEST", common_analysis=common) == original
        if count < 2:
            assert (original.mansfield_rs, original.outperform_6m, original.rp_slope_4w) == (
                0,
                0,
                0,
            )


@pytest.mark.parametrize("count", [0, 1, 2, 19, 20, 21])
def test_common_rs_uses_effective_dropna_intersection_count_without_realigning(count, monkeypatch):
    stock = bars(list(range(100, 125)))
    market = bars(list(range(200, 225))).iloc[-(count + 2) :].copy()
    stock.loc[market.index[0], "Close"] = float("nan")
    market.loc[market.index[1], "Close"] = float("nan")
    common = rs_analysis_for(stock, market)
    expected = None
    if 2 <= count < 20:
        with pytest.raises(ValueError, match="min_periods") as original:
            compute_relative_strength(stock, market, "TEST")
        error_message = str(original.value)
    else:
        expected = compute_relative_strength(stock, market, "TEST")

    def forbidden(*args, **kwargs):
        raise AssertionError("RS adapter recalculated alignment or rolling")

    monkeypatch.setattr(pd.Series, "dropna", forbidden)
    monkeypatch.setattr(pd.Series, "rolling", forbidden)
    if 2 <= count < 20:
        with pytest.raises(ValueError, match="min_periods") as injected:
            compute_relative_strength(stock, market, "TEST", common_analysis=common)
        assert str(injected.value) == error_message
    else:
        assert compute_relative_strength(stock, market, "TEST", common_analysis=common) == expected
    if count < 20:
        assert common.items[0].state == "UNAVAILABLE"
        assert common.items[0].evidence["reasons"] == ("HISTORY_SHORT",)
        assert common.items[0].evidence["valid_common_count"] == count


def test_common_rs_count_excludes_undefined_zero_over_zero_relative_prices():
    stock = bars([100.0] * 21)
    market = bars([200.0] * 21)
    stock.loc[stock.index[-2:], "Close"] = 0.0
    market.loc[market.index[-2:], "Close"] = 0.0
    common = rs_analysis_for(stock, market)
    with pytest.raises(ValueError, match="min_periods 20 must be <= window 19"):
        compute_relative_strength(stock, market, "TEST")
    with pytest.raises(ValueError, match="min_periods 20 must be <= window 19"):
        compute_relative_strength(stock, market, "TEST", common_analysis=common)
    assert common.items[0].evidence["valid_common_count"] == 19


@pytest.mark.parametrize("mismatch", ["stock_hash", "market_hash", "request", "fact_date"])
def test_empty_common_rs_still_validates_matching_scope_and_request(mismatch):
    stock = market = bars([])
    common = rs_analysis_for(stock, market)
    if mismatch == "stock_hash":
        stock = stock.assign(extra=pd.Series(dtype=float))
    elif mismatch == "market_hash":
        market = market.assign(extra=pd.Series(dtype=float))
    elif mismatch == "request":
        common = replace(common, requested_rules=())
    else:
        from datetime import timedelta

        common = replace(
            common,
            items=tuple(
                replace(item, status_as_of=item.status_as_of + timedelta(days=1))
                for item in common.items
            ),
        )
    with pytest.raises(ValueError):
        compute_relative_strength(stock, market, "TEST", common_analysis=common)


@pytest.mark.parametrize("role", ["stock", "market"])
def test_common_rs_missing_close_remains_input_missing_not_short_zero(role):
    stock = bars([100.0])
    market = bars([200.0])
    if role == "stock":
        stock = stock.drop(columns="Close")
    else:
        market = market.drop(columns="Close")
    common = rs_analysis_for(stock, market)
    assert common.items[0].evidence["reasons"] == ("INPUT_MISSING",)
    assert "valid_common_count" not in common.items[0].evidence
    with pytest.raises(KeyError, match="Close"):
        compute_relative_strength(stock, market, "TEST")
    with pytest.raises(KeyError, match="Close"):
        compute_relative_strength(stock, market, "TEST", common_analysis=common)


def test_bundle_scope_retains_real_roles_metadata_and_references():
    from src.strategies.playbook import PlaybookStrategy
    from src.tools.playbook.common import common_analysis_for_bundle
    from tests.strategies.test_playbook import _bundle

    bundle = _bundle()
    common = common_analysis_for_bundle(bundle)
    result = PlaybookStrategy().evaluate(bundle, common_analysis=common)
    assert result.common_analyses == (common,)
    assert result.chart_analysis_id == common.analysis_id
    for selection in result.fact_selections:
        assert selection.ref.analysis_id == common.analysis_id
        assert any(item.id == selection.ref.item_id for item in common.items)
        item = next(item for item in common.items if item.id == selection.ref.item_id)
        if item.rule_id == "chart.vcp.playbook":
            assert not selection.selected
            assert selection.reason_code == "PLAYBOOK_GATE_NOT_REACHED_C_VETO"
        else:
            assert selection.selected
            expected_reason = (
                "PLAYBOOK_EXIT_CONSUMED"
                if item.rule_id == "chart.accumulation.days"
                else "PLAYBOOK_ENTRY_EXIT_CONSUMED"
                if item.rule_id == "chart.rs"
                else "PLAYBOOK_ENTRY_CONSUMED"
            )
            assert selection.reason_code == expected_reason
    assert common.manifest.origin == str(bundle.instrument.bars[0].session_date)
    assert common.dependencies["market"].ticker == bundle.market_ticker
    assert common.manifest.coverage["requested_start"] == bundle.instrument.coverage.requested_start
    assert (
        common.manifest.finality[bundle.as_of] == bundle.instrument.bars[-1].finality.value.upper()
    )
    assert (
        not {"fact_selections", "chart_analysis_id", "common_analyses"} & result.model_dump().keys()
    )


@pytest.mark.parametrize(
    "change", ["ticker", "market", "market_ticker", "as_of", "finality", "coverage", "calendar"]
)
def test_bundle_injected_scope_rejects_different_dependencies(change):
    from src.strategies.models import BarFinality, ChartBundle
    from src.strategies.playbook import PlaybookStrategy
    from src.tools.playbook.common import common_analysis_for_bundle
    from tests.strategies.test_playbook import _bundle

    bundle = _bundle()
    common = common_analysis_for_bundle(bundle)
    if change == "as_of":
        changed = bundle.prefix(bundle.exchange_sessions[-2])
    else:
        values = bundle.model_dump(mode="python", exclude={"bundle_hash"})
        if change in {"ticker", "market_ticker"}:
            values[change] = "OTHER"
        elif change == "market":
            values["market"]["bars"][-1]["close"] += 1
        elif change == "finality":
            values["instrument"]["bars"][-1]["finality"] = BarFinality.PROVISIONAL
        elif change == "coverage":
            values["market"]["coverage"]["complete"] = False
        else:
            from datetime import timedelta

            values["exchange_sessions"] = (
                values["exchange_sessions"][0] - timedelta(days=1),
            ) + values["exchange_sessions"]
        changed = ChartBundle(**values)
    with pytest.raises(ValueError, match="scope"):
        PlaybookStrategy().evaluate(changed, common_analysis=common)


def test_missing_market_does_not_select_prepared_entry_facts():
    from src.strategies.playbook import PlaybookStrategy
    from src.tools.playbook.common import common_analysis_for_bundle
    from tests.strategies.test_playbook import _bundle

    bundle = _bundle(market=False)
    common = common_analysis_for_bundle(bundle)
    result = PlaybookStrategy().evaluate(bundle, common_analysis=common)
    selected = {item.id: item.rule_id for item in common.items}
    assert {selected[s.ref.item_id] for s in result.fact_selections if s.selected} == {
        "chart.accumulation.days"
    }
    assert all(
        s.reason_code == "PLAYBOOK_MARKET_NOT_READY"
        for s in result.fact_selections
        if not s.selected
    )


def test_strategy_consumes_injected_accumulation_fact_not_available_copy():
    from src.strategies.playbook import PlaybookStrategy
    from src.tools.playbook.common import common_analysis_for_bundle
    from tests.strategies.test_playbook import _bundle

    bundle = _bundle()
    common = common_analysis_for_bundle(bundle)
    changed = replace(
        common,
        items=tuple(
            replace(item, evidence={**item.evidence, "accumulation_ratio": 0.0})
            if item.rule_id == "chart.accumulation.days"
            else item
            for item in common.items
        ),
    )
    old = PlaybookStrategy().evaluate(bundle, common_analysis=common)
    actual = PlaybookStrategy().evaluate(bundle, common_analysis=changed)
    assert old.exit.reasons != actual.exit.reasons
    assert any(reason.code == "DISTRIBUTION" for reason in actual.exit.reasons)


def test_default_strategy_uses_common_facts_and_bypasses_old_detector_bodies(monkeypatch):
    from src.strategies.playbook import PlaybookStrategy
    from tests.strategies.test_playbook import _bundle

    bundle = _bundle()
    expected = PlaybookStrategy().evaluate(bundle).model_dump()

    def forbidden(*args, **kwargs):
        raise AssertionError("old numerical body called")

    monkeypatch.setattr(import_module("src.tools.playbook.vcp"), "_detect_vcp", forbidden)
    monkeypatch.setattr(
        import_module("src.tools.technical.components.minervini"), "analyze_minervini", forbidden
    )
    result = PlaybookStrategy().evaluate(bundle)
    assert result.model_dump() == expected
    assert len(result.common_analyses) == 1
    assert len(result.fact_selections) == 5


def test_request_context_market_revision_changes_only_dependent_evaluations():
    from src.strategies.models import ChartBundle
    from src.strategies.playbook import PlaybookStrategy
    from src.tools.playbook.common import common_analysis_for_bundle
    from tests.strategies.test_playbook import _bundle

    original = _bundle()
    values = original.model_dump(mode="python", exclude={"bundle_hash"})
    values["market"]["bars"][-1]["close"] *= 2
    changed = ChartBundle(**values)
    context = AnalysisRequestContext()
    first = common_analysis_for_bundle(original, context=context)
    second = common_analysis_for_bundle(changed, context=context)
    assert first.analysis_id != second.analysis_id
    previous = {item.rule_id: item for item in first.items}
    current = {item.rule_id: item for item in second.items}
    for rule in previous:
        assert (previous[rule].evaluation_key == current[rule].evaluation_key) is (
            rule not in {"chart.rs", "chart.market.regime"}
        )
    assert (
        previous["chart.rs"].evidence["mansfield_rs"]
        != current["chart.rs"].evidence["mansfield_rs"]
    )
    strategy = PlaybookStrategy()
    assert (
        strategy.evaluate(original, common_analysis=first).model_dump()
        != strategy.evaluate(changed, common_analysis=second).model_dump()
    )
    assert (
        strategy.evaluate(original, common_analysis=first).model_dump()
        == strategy.evaluate(original).model_dump()
    )


def test_common_adapter_rejects_different_evaluation_date():
    from datetime import timedelta

    frame = vcp_frame()
    common = analysis_for(frame, rules=("chart.vcp.playbook",))
    later_day = common.manifest.as_of + timedelta(days=1)
    later = replace(
        common,
        manifest=replace(common.manifest, as_of=later_day),
        items=tuple(replace(item, status_as_of=later_day) for item in common.items),
    )
    with pytest.raises(ValueError, match="scope"):
        detect_vcp_breakout(frame, common_analysis=later)


def test_playbook_rejects_missing_required_rule_inventory():
    from src.strategies.playbook import PlaybookStrategy
    from src.tools.playbook.common import common_analysis_for_bundle
    from tests.strategies.test_playbook import _bundle

    bundle = _bundle()
    common = common_analysis_for_bundle(bundle)
    missing = replace(
        common,
        requested_rules=tuple(
            rule for rule in common.requested_rules if rule.rule_id != "chart.rs"
        ),
    )
    with pytest.raises(ValueError, match="request contract"):
        PlaybookStrategy().evaluate(bundle, common_analysis=missing)


@pytest.mark.parametrize("veto", ["A", "B", "C", "E"])
def test_fact_selection_distinguishes_gate_veto_precedence_from_exit_consumption(veto):
    from src.strategies.playbook import PlaybookStrategy
    from src.tools.playbook.common import common_analysis_for_bundle
    from tests.strategies.test_playbook import _bundle

    bundle = _bundle()
    common = common_analysis_for_bundle(bundle)
    items = []
    for item in common.items:
        values = dict(item.evidence)
        if item.rule_id == "chart.market.regime" and veto == "A":
            values.update(above=False, regime="하락")
        if item.rule_id == "chart.stage2.minervini" and veto == "B":
            values["metrics"] = {**values["metrics"], "is_stage2": 0.0}
        if item.rule_id == "chart.rs" and veto == "E":
            values.update(mansfield_rs=1.0, rp_slope_4w=0.1)
        items.append(replace(item, evidence=values))
    injected = replace(common, items=tuple(items))
    result = PlaybookStrategy().evaluate(bundle, common_analysis=injected)
    assert result.entry.reasons[0].message.startswith(veto + ":")
    by_id = {item.id: item.rule_id for item in common.items}
    selections = {by_id[selection.ref.item_id]: selection for selection in result.fact_selections}
    for rule in ("chart.accumulation.days", "chart.rs", "chart.market.regime"):
        assert selections[rule].selected is True
    assert selections["chart.accumulation.days"].reason_code == "PLAYBOOK_EXIT_CONSUMED"
    assert selections["chart.rs"].reason_code == (
        f"PLAYBOOK_EXIT_CONSUMED_GATE_NOT_REACHED_{veto}_VETO"
        if veto in {"A", "B"}
        else "PLAYBOOK_ENTRY_EXIT_CONSUMED"
    )
    assert selections["chart.stage2.minervini"].selected is (veto != "A")
    assert selections["chart.vcp.playbook"].selected is (veto == "E")
    for rule in ("chart.stage2.minervini", "chart.vcp.playbook"):
        if not selections[rule].selected:
            assert selections[rule].reason_code == f"PLAYBOOK_GATE_NOT_REACHED_{veto}_VETO"

"""Append-only research snapshots contain decisions, never positions or outcomes."""

import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.strategies.entry_shadow import evaluate_entry_shadow
from src.strategies.models import StrategySignalBundle
from src.strategies.runner import StrategyRunBundle
from tests.strategies.test_entry_shadow import _inputs
from tests.strategies.test_runner import _legacy_result


def decision_inputs(*, provisional=False, code="TREND_BREAKOUT_ENTRY", closes=(110, 99)):
    opportunity, chart = _inputs(closes, provisional=provisional, code=code)
    opportunity.execution_reference_price = (
        opportunity.signal_price if opportunity.age_bars == 0 else Decimal("111.125")
    )
    opportunity.extension_pct = Decimal("-0.1")
    signals = StrategySignalBundle(
        strategy_id="SWING_W150",
        strategy_version="SWING_W150_V2",
        parameter_set_version="production",
        parameter_fingerprint="production-fingerprint",
        ticker=chart.ticker,
        as_of=chart.as_of,
        observation_history=[],
        signal_history=[opportunity.entry_signal],
        current_signals=(
            [opportunity.entry_signal]
            if opportunity.entry_signal.occurred_on == chart.as_of
            else []
        ),
        entry_opportunity=opportunity,
        entry_shadow=evaluate_entry_shadow(opportunity, chart),
        data_status="complete",
    )
    run = StrategyRunBundle(
        ticker=chart.ticker,
        as_of=chart.as_of,
        input_data_hash="run-input",
        strategy_versions={"SWING_W150": "SWING_W150_V2"},
        chart_profile_version=chart.profile_version,
        chart_bundle_hash=chart.bundle_hash,
        strategy_input_hashes={"SWING_W150": "swing-input"},
        scorecard=_legacy_result(scorecard_as_of=chart.as_of).scorecard,
        verdicts=[],
        signal_bundles=[signals],
        data_status="complete",
        errors=[],
    )
    return run, chart


def test_recorder_serializes_complete_decision_without_position_or_future_fields(tmp_path):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    run, chart = decision_inputs(provisional=True)
    opportunity = run.signal_bundles[0].entry_opportunity
    opportunity.terminal_on = chart.as_of
    opportunity.terminal_finality = opportunity.finality
    before = run.model_dump(mode="json")
    path = tmp_path / "research" / "entry-shadow.jsonl"
    EntryShadowJsonlRecorder(path).record(run, chart, pipeline="analyze")

    row = json.loads(path.read_text(), parse_float=Decimal)
    assert row["schema_version"] == "ENTRY_SHADOW_SNAPSHOT_V2"
    assert row["pipeline"] == "analyze"
    assert row["ticker"] == "AAPL"
    assert row["evaluation_as_of"] == "2026-09-02"
    assert row["evaluation_finality"] == "provisional"
    assert row["source_id"] == "source"
    assert row["source_type"] == "TREND_BREAKOUT_ENTRY"
    assert row["source_date"] == "2026-09-01"
    assert row["source_age_bars"] == 1
    assert row["source_finality"] == "final"
    assert row["production_status"] == "allow"
    assert row["production_policy_version"] == "production"
    assert row["production_reason"] == "entry"
    assert row["production_evidence"][0]["observed_value"] == 110
    assert row["terminal_on"] == "2026-09-02"
    assert row["terminal_finality"] == "provisional"
    assert row["anchors"] == {
        "source_id": "source",
        "source_date": "2026-09-01",
        "source_type": "TREND_BREAKOUT_ENTRY",
        "signal_price": 110,
        "atr_at_signal": 5,
        "breakout_level": 100,
        "origin_support": 100,
        "pullback_low": 95,
        "anchor_finality": "final",
        "policy_version": "production",
    }
    assert row["current_close"] == 99
    assert row["market_regime"] == "RISK_ON"
    assert row["extension_pct"] == Decimal("-0.1")
    assert row["execution_reference_price"] == Decimal("111.125")
    assert row["execution_gap_pct"] == Decimal("111.125") / Decimal("110") - 1
    assert row["current_to_execution_reference_pct"] == Decimal("99") / Decimal("111.125") - 1
    assert row["risk_level"] == "CAUTION"
    assert row["risk_flags"][0]["finality"] == "provisional"
    assert row["risk_flags"][0]["message"]
    assert row["risk_flags"][0]["evidence"][0]["reference_value"] == 100
    assert row["shadow_policy_version"] == "WATCH_RECLAIM_SHADOW_V1"
    assert row["shadow_parameter_fingerprint"]
    assert row["shadow_finality"] == "provisional"
    assert row["shadow_data_status"] == "complete"
    assert row["shadow_reason"] == "EVALUATED"
    assert row["breakout_states"]["B1"]["status"] == "BREACHED"
    assert "confirmed_as_of" in row["breakout_states"]["B1"]
    assert "candidate_finality" in row["breakout_states"]["B4"]
    assert row["production_parameter_fingerprint"] == "production-fingerprint"
    assert row["strategy_input_hash"] == "swing-input"
    assert row["chart_bundle_hash"] == chart.bundle_hash
    assert row["chart_profile_version"] == "chart-v1"
    assert datetime.fromisoformat(row["recorded_at"]).utcoffset() == timedelta(0)
    for forbidden in ("position", "holdings", "quantity", "avg_price", "stop", "outcome", "return"):
        assert not any(forbidden in key for key in row)
    assert run.model_dump(mode="json") == before


def test_recorder_appends_repeated_and_final_snapshots_without_overwriting_policy(tmp_path):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    path = tmp_path / "entry-shadow.jsonl"
    recorder = EntryShadowJsonlRecorder(path)
    provisional, provisional_chart = decision_inputs(provisional=True)
    final, final_chart = decision_inputs()
    recorder.record(provisional, provisional_chart, pipeline="check")
    first_line = path.read_text()
    recorder.record(provisional, provisional_chart, pipeline="check")
    recorder.record(final, final_chart, pipeline="brief")
    final.signal_bundles[0].entry_opportunity.policy_version = "production-v2"
    recorder.record(final, final_chart, pipeline="check")

    assert path.read_text().splitlines()[0] == first_line.strip()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 4
    assert rows[0]["decision_key"] == rows[1]["decision_key"] == rows[2]["decision_key"]
    assert rows[0]["snapshot_key"] == rows[1]["snapshot_key"]
    assert rows[0]["snapshot_key"] != rows[2]["snapshot_key"]
    assert rows[2]["decision_key"] != rows[3]["decision_key"]
    assert [row["production_policy_version"] for row in rows] == [
        "production",
        "production",
        "production",
        "production-v2",
    ]
    assert {row["evaluation_as_of"] for row in rows} == {"2026-09-02"}


@pytest.mark.parametrize("mode", ["unsupported", "disabled", "no_source"])
def test_recorder_preserves_explicit_unevaluated_risk(tmp_path, mode):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    run, chart = decision_inputs(
        code="DEEP_RECOVERY_ENTRY" if mode == "unsupported" else "TREND_BREAKOUT_ENTRY"
    )
    signals = run.signal_bundles[0]
    if mode == "disabled":
        signals.entry_shadow = None
    elif mode == "no_source":
        signals.entry_opportunity.entry_signal = None
        signals.entry_opportunity.anchors = None
        signals.entry_shadow = evaluate_entry_shadow(signals.entry_opportunity, chart)
    path = tmp_path / "entry-shadow.jsonl"
    EntryShadowJsonlRecorder(path).record(run, chart, pipeline="check")
    row = json.loads(path.read_text())
    assert row["risk_level"] is None
    assert row["shadow_data_status"] == "not_evaluated"
    assert (
        row["shadow_reason"]
        == {
            "unsupported": "UNSUPPORTED_SOURCE",
            "disabled": "DISABLED_OR_UNAVAILABLE",
            "no_source": "NO_SOURCE",
        }[mode]
    )


def test_recorder_retains_io_error_for_service_to_surface(tmp_path):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    run, chart = decision_inputs()
    with pytest.raises(OSError):
        EntryShadowJsonlRecorder(tmp_path).record(run, chart, pipeline="check")


@pytest.mark.parametrize("provisional", [False, True])
def test_signal_day_has_no_actual_open_gap_or_future_fill(tmp_path, provisional):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    run, chart = decision_inputs(closes=(110,), provisional=provisional)
    path = tmp_path / "entry-shadow.jsonl"
    EntryShadowJsonlRecorder(path).record(run, chart, pipeline="check")
    row = json.loads(path.read_text())
    assert row["source_date"] == row["evaluation_as_of"] == "2026-09-01"
    assert row["source_age_bars"] == 0
    assert row["execution_reference_price"] == 110
    assert row["execution_reference_basis"] == "signal_close_estimate"
    assert row["execution_gap_pct"] is None
    assert row["current_to_execution_reference_pct"] == 0
    assert len(path.read_text().splitlines()) == 1


def test_policy_or_strategy_version_changes_do_not_collapse_decision_identity(tmp_path):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    run, chart = decision_inputs()
    path = tmp_path / "entry-shadow.jsonl"
    recorder = EntryShadowJsonlRecorder(path)
    recorder.record(run, chart, pipeline="check")
    run.signal_bundles[0].strategy_version = "SWING_W150_V3"
    recorder.record(run, chart, pipeline="check")
    old, new = [json.loads(line) for line in path.read_text().splitlines()]
    assert old["decision_key"] != new["decision_key"]
    assert old["execution_reference_basis"] == "next_open_actual"


def test_v2_snapshot_appends_observations_cycle_support_and_keeps_legacy_bytes(tmp_path):
    from dataclasses import asdict
    from datetime import date

    from src.storage.entry_shadow import EntryShadowJsonlRecorder
    from src.strategies.models import (
        BarFinality,
        ObservationCode,
        SupportAnchor,
        SupportTestState,
        UpCycleState,
    )
    from src.strategies.observations import make_observation
    from src.strategies.observations.parameters import PRODUCT_OBSERVATION_PARAMETERS

    run, chart = decision_inputs()
    bundle = run.signal_bundles[0]
    bundle.observations_enabled = True
    bundle.observation_parameters = asdict(PRODUCT_OBSERVATION_PARAMETERS)
    bundle.observation_history = [
        make_observation(
            ticker="AAPL",
            code=ObservationCode.SUPPORT_BREAK,
            origin=date(2026, 9, 1),
            params=PRODUCT_OBSERVATION_PARAMETERS,
            status_as_of=chart.as_of,
            anchor_type="SMA150",
            anchor_origin_on=date(2026, 8, 3),
            anchor_origin_price=Decimal("95"),
            evidence=bundle.entry_opportunity.evidence,
        )
    ]
    bundle.up_cycle = UpCycleState(
        cycle_id="cycle",
        started_on=date(2026, 8, 3),
        status="ACTIVE",
        status_as_of=chart.as_of,
        finality=BarFinality.FINAL,
    )
    bundle.support_tests = [
        SupportTestState(
            anchor=SupportAnchor(
                anchor_id="sma150",
                anchor_type="SMA150",
                is_dynamic=True,
                origin_on=date(2026, 8, 3),
                origin_price=Decimal("95"),
                current_value=Decimal("100"),
                cycle_id="cycle",
            ),
            status="SOFT_BREACH",
            below_count=1,
            started_on=chart.as_of,
            status_as_of=chart.as_of,
            ended_on=None,
            finality=BarFinality.FINAL,
        )
    ]
    path = tmp_path / "entry-shadow.jsonl"
    legacy = '{"schema_version":"ENTRY_SHADOW_SNAPSHOT_V1","untouched":true}\n'
    path.write_text(legacy)
    before = run.model_dump(mode="json")
    EntryShadowJsonlRecorder(path).record(run, chart, pipeline="brief")
    assert path.read_text().startswith(legacy)
    old, row = [json.loads(line) for line in path.read_text().splitlines()]
    assert old["schema_version"] == "ENTRY_SHADOW_SNAPSHOT_V1"
    assert row["schema_version"] == "ENTRY_SHADOW_SNAPSHOT_V2"
    assert row["observation_history"][0]["scopes"] == ["ENTRY", "POSITION"]
    assert row["observation_history"][0]["anchor_origin_price"] == 95
    assert row["up_cycle"]["status"] == "ACTIVE"
    assert row["support_tests"][0]["anchor"]["current_value"] == 100
    assert row["observations_enabled"] is True
    assert row["observation_parameters"]["down_volume_ratio"] is None
    assert row["risk_level"] == "CAUTION"
    assert run.model_dump(mode="json") == before


def test_v2_snapshot_retains_inactive_policy_and_unknown_observation_settings(tmp_path):
    from src.storage.entry_shadow import EntryShadowJsonlRecorder

    run, chart = decision_inputs()
    run.signal_bundles[0].pullback_policy_inactive_reason = "V2_UNRESOLVED"
    path = tmp_path / "entry-shadow.jsonl"
    EntryShadowJsonlRecorder(path).record(run, chart, pipeline="check")
    row = json.loads(path.read_text())
    assert row["up_cycle"] is None and row["support_tests"] is None
    assert row["observations_enabled"] is None and row["observation_parameters"] is None
    assert row["pullback_policy_inactive_reason"] == "V2_UNRESOLVED"

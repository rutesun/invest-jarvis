import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest


def test_next_open_is_outcome_anchor():
    from src.backtest.observation_calibration import future_outcome

    frame = pd.DataFrame(
        {
            "Open": [90, 100, 105],
            "Close": [90, 105, 110],
            "High": [91, 106, 112],
            "Low": [89, 99, 104],
        },
        index=pd.bdate_range("2024-01-02", periods=3),
    )
    result = future_outcome(frame, 0, 2)
    assert result["return"] == pytest.approx(0.10)
    assert result["mfe"] == pytest.approx(0.12)
    assert result["mae"] == pytest.approx(-0.01)
    assert future_outcome(frame, 0, 3)["return"] is None


def test_unmatured_labels_are_null_at_fold_boundary():
    from src.backtest.observation_calibration import future_outcome

    frame = pd.DataFrame(
        {"Open": [90, 100], "Close": [90, 110], "High": [91, 112], "Low": [89, 99]},
        index=pd.to_datetime(["2023-12-29", "2024-01-02"]),
    )
    result = future_outcome(frame, 0, 1)
    assert result["return"] is None
    assert result["reason"] == "FOLD_BOUNDARY"


def test_current_volume_is_not_reference():
    from src.strategies.swing_w150.features import observation_feature_columns

    frame = pd.DataFrame(
        {
            "Close": [100] * 25,
            "High": [101] * 25,
            "Volume": [100] * 24 + [1000],
            "SMA_150": [90] * 25,
            "SMA_150_Slope_21": [0] * 25,
            "SMA_20": [99] * 25,
            "SMA_20_Slope_5": [0] * 25,
        }
    )
    out = observation_feature_columns(frame)
    assert out.iloc[-1]["Volume_Ratio_Prev20"] == 10
    assert out.iloc[-1]["Volume_Contraction_Ratio"] == 2.8


def test_protocol_freezes_39_candidates_before_labels(tmp_path):
    from src.backtest.observation_calibration import freeze_protocol

    protocol = json.loads(Path("research/trading_observation_v1/protocol.json").read_text())
    cache = tmp_path / "cache"
    cache.mkdir()
    pd.DataFrame(
        {
            "Date": ["2024-01-02"],
            "Open": [100],
            "High": [101],
            "Low": [99],
            "Close": [100],
            "Volume": [100],
        }
    ).to_csv(cache / "SPY.csv", index=False)
    digest = freeze_protocol(protocol, cache_dir=cache, output=tmp_path / "frozen")
    manifest = json.loads((tmp_path / "frozen/freeze-manifest.json").read_text())
    assert manifest["candidate_count"] == 39
    assert manifest["family_count"] == 10
    assert manifest["protocol_sha256"] == digest
    assert len(manifest["inventory"]) == 21
    assert not (tmp_path / "frozen/outcomes.json").exists()


def test_comparator_uses_nearest_prior_nonoccurrence_same_fold_regime_and_sma_state():
    from src.backtest.observation_calibration import match_comparator

    frame = pd.DataFrame(
        {"Close": [110, 110, 110, 90, 110], "SMA_150": [100] * 5},
        index=pd.bdate_range("2024-01-02", periods=5),
    )
    regimes = pd.Series(["bull", "bull", "bear", "bull", "bull"], index=frame.index)
    assert match_comparator(frame, 4, {1, 4}, regimes) == 0
    assert match_comparator(frame, 0, {0}, regimes) is None


def test_ticker_cluster_bootstrap_repeats_complete_clusters():
    from src.backtest.observation_calibration import ticker_bootstrap_ci

    # Every cluster mean is1: within-cluster row resampling would incorrectly widen this CI.
    assert ticker_bootstrap_ci([("A", 0), ("A", 2), ("B", 1)]) == pytest.approx((1, 1))


def test_freeze_rejects_executable_source_drift(tmp_path):
    from src.backtest.observation_calibration import verify_frozen_protocol

    protocol = {"schema_version": "test"}
    import hashlib

    from src.storage.canonical import canonical_bytes

    (tmp_path / "freeze-manifest.json").write_text(
        json.dumps(
            {
                "protocol_sha256": hashlib.sha256(canonical_bytes(protocol)).hexdigest(),
                "executable_sources": {"src/strategies/swing_w150/up_cycle.py": "wrong"},
                "specifications": {},
                "inventory": {},
            }
        )
    )
    with pytest.raises(ValueError, match="source drift"):
        verify_frozen_protocol(protocol, output=tmp_path)


def test_raw_fixture_preparation_uses_chart_only_source_anchors():
    from src.backtest.observation_calibration import _prepare

    protocol = json.loads(Path("research/trading_observation_v1/protocol.json").read_text())
    raw, features, detected, contexts = _prepare(
        Path("tests/fixtures/swing_w150/v2_signal_path.csv"), "TEST", protocol
    )
    assert len(raw) == len(features.frame)
    assert detected.signal_history
    assert contexts
    assert all(context.terminal_status is None for context in contexts)


def test_no_validation_utility_does_not_disqualify_development_detector_plateau():
    from src.backtest.observation_calibration import select_detector_default

    family = {
        "id": "UP_VOLUME_EXPANSION",
        "candidate_values": [1.4, 1.5, 1.7],
        "selection": "detector_plateau",
    }
    summaries = [
        {"value": value, "development_count": count}
        for value, count in [(1.4, 100), (1.5, 95), (1.7, 90)]
    ]
    result = select_detector_default(family, summaries, {"up_volume_ratio": 1.5})
    assert result["value"] == 1.5
    assert result["predictive_status_affects_selection"] is False


def test_no_plateau_has_no_detector_default():
    from src.backtest.observation_calibration import select_detector_default

    family = {
        "id": "UP_VOLUME_EXPANSION",
        "candidate_values": [1.2, 2.0],
        "selection": "detector_plateau",
    }
    summaries = [{"value": 1.2, "development_count": 100}, {"value": 2.0, "development_count": 10}]
    assert select_detector_default(family, summaries, {"up_volume_ratio": 1.5})["value"] is None


def test_frozen_synthetic_run_keeps_39_candidates_and_v1_default(tmp_path):
    import shutil

    from src.backtest.observation_calibration import freeze_protocol, run_calibration

    protocol = json.loads(Path("research/trading_observation_v1/protocol.json").read_text())
    protocol["universe"] = ["TEST"]
    cache = tmp_path / "cache"
    cache.mkdir()
    for ticker in ["TEST", "SPY"]:
        shutil.copyfile("tests/fixtures/swing_w150/v2_signal_path.csv", cache / f"{ticker}.csv")
    frozen = tmp_path / "frozen"
    freeze_protocol(protocol, cache_dir=cache, output=frozen)
    result = run_calibration(frozen / "protocol.json", output=frozen)
    assert result["candidate_count"] == 39
    assert result["production_default"] == "V1"
    assert result["provider_calls"] == result["llm_calls"] == 0
    selection = json.loads((frozen / "selection.json").read_text())
    assert selection["RESTART"]["value"] is None
    assert selection["NORMAL_FAILURE"]["value"] is None
    summaries = json.loads((frozen / "summaries.json").read_text())
    assert len(summaries) == 40  # 39 candidates plus fixed-formula structure diagnostics.


def test_support_origin_is_first_gap_breach_not_held_registration():
    from types import SimpleNamespace

    from src.backtest.observation_calibration import first_cycle_risk_set
    from src.strategies.models import BarFinality
    from src.strategies.swing_w150.features import SwingFeatureFrame
    from src.tools.technical.scorecard_models import DataStatus

    frame = pd.DataFrame(
        {
            "History_Bars": range(1, 253),
            "Close": [101] * 250 + [90, 89],
            "High": [102] * 252,
            "Low": [100.8] * 250 + [89, 88],
            "SMA_150": [100] * 252,
            "SMA_150_Slope_21": [0] * 252,
            "ATR": [1] * 252,
            "Price_Breakout_Event": [True] * 252,
        },
        index=pd.bdate_range("2024-01-02", periods=252),
    )
    features = SwingFeatureFrame(frame, DataStatus.COMPLETE, (BarFinality.FINAL,) * 252)
    risk = first_cycle_risk_set("TEST", features, SimpleNamespace(signal_history=[]), [])
    assert len(risk["origins"]) == 1
    assert risk["origins"][0]["origin_index"] == 250
    assert risk["origins"][0]["origin_kind"] == "GAP_BREACH"
    assert risk["cycle"].terminated_on == frame.index[251].date()


def test_fixed_cohort_includes_repeated_dynamic_retouch_after_each_reclaim():
    from types import SimpleNamespace

    from src.backtest.observation_calibration import first_cycle_risk_set
    from src.strategies.models import BarFinality
    from src.strategies.swing_w150.features import SwingFeatureFrame
    from src.tools.technical.scorecard_models import DataStatus

    closes = [111] * 249 + [109, 111, 109, 109, 111, 109, 109, 111, 109]
    frame = pd.DataFrame(
        {
            "History_Bars": range(1, len(closes) + 1),
            "Close": closes,
            "High": [120] * len(closes),
            "Low": [close - 0.2 for close in closes],
            "SMA_50": [110] * len(closes),
            "SMA_150": [100] * len(closes),
            "SMA_150_Slope_21": [0] * len(closes),
            "ATR": [1] * len(closes),
            "Price_Breakout_Event": [True] * len(closes),
        },
        index=pd.bdate_range("2024-01-02", periods=len(closes)),
    )
    features = SwingFeatureFrame(frame, DataStatus.COMPLETE, (BarFinality.FINAL,) * len(frame))
    risk = first_cycle_risk_set("TEST", features, SimpleNamespace(signal_history=[]), [])
    origins = [
        row["origin_index"] for row in risk["origins"] if row["anchor"]["anchor_type"] == "SMA50"
    ]
    assert origins == [249, 251, 254, 257]
    assert risk["cycle"].status == "ACTIVE"


@pytest.mark.parametrize(
    "family,codes",
    [
        ("UP_VOLUME_EXPANSION", {"UP_VOLUME_EXPANSION"}),
        ("DOWN_VOLUME_EXPANSION", {"DOWN_VOLUME_EXPANSION"}),
        ("VOLUME_CONTRACTION", {"VOLUME_CONTRACTION"}),
        ("MOMENTUM_REACCELERATION", {"MOMENTUM_REACCELERATION"}),
        ("MOMENTUM_DECELERATION", {"MOMENTUM_DECELERATION"}),
        (
            "SUPPORT_BREAK_RECLAIM",
            {
                "SUPPORT_BREAK",
                "BREAKOUT_LEVEL_BREACH",
                "PULLBACK_LOW_BREACH",
                "SUPPORT_RECLAIM",
                "BREAKOUT_RECLAIM",
            },
        ),
        ("STRUCTURE", {"HIGHER_HIGH", "HIGHER_LOW", "LOWER_HIGH", "LOWER_LOW"}),
    ],
)
def test_target_replay_equals_filtered_full_observations_including_identity(family, codes):
    from dataclasses import replace
    from decimal import Decimal
    from types import SimpleNamespace

    from src.backtest.observation_calibration import _prepare, _target_observations
    from src.strategies.models import BarFinality, ObservationSourceContext
    from src.strategies.observations.detectors import evaluate_observations
    from src.strategies.observations.parameters import ObservationParameters

    protocol = json.loads(Path("research/trading_observation_v1/protocol.json").read_text())
    _, base_features, _, contexts = _prepare(
        Path("tests/fixtures/swing_w150/v2_signal_path.csv"), "TEST", protocol
    )
    highs = [111, 112, 113, 116, 113, 112, 111, 112, 113, 118, 113, 112, 111] * 3
    closes = [99 if i % 2 == 0 else 101 for i in range(len(highs))]
    frame = pd.DataFrame(
        {
            "High": highs,
            "Low": [90] * len(highs),
            "Close": closes,
            "Previous_Close": [100, *closes[:-1]],
            "Volume_Ratio_Prev20": [2] * len(highs),
            "Contraction_Context": [True] * len(highs),
            "Volume_Contraction_Ratio": [0.6, 0.6, 0.9] * 13,
            "SMA_20": [100] * len(highs),
            "SMA_20_Slope_5": [-1 if i % 2 == 0 else 1 for i in range(len(highs))],
            "Previous_SMA20_Slope": [0, *[-1 if i % 2 == 0 else 1 for i in range(len(highs) - 1)]],
            "Prior_Trend_Context": [True] * len(highs),
            "Prior_Below_SMA20": [True] * len(highs),
            "ATR": [2] * len(highs),
            "SMA_50": [100] * len(highs),
            "SMA_150": [95] * len(highs),
        },
        index=pd.bdate_range("2024-12-19", periods=len(highs)),
    )
    features = replace(base_features, frame=frame, finalities=(BarFinality.FINAL,) * len(frame))
    context = contexts[-1]
    context = ObservationSourceContext(
        signal=context.signal.model_copy(
            update={
                "signal_id": "frozen-source",
                "code": "TREND_BREAKOUT_ENTRY",
                "occurred_on": frame.index[0].date(),
            }
        ),
        anchors=context.anchors.model_copy(
            update={
                "source_id": "frozen-source",
                "source_date": frame.index[0].date(),
                "breakout_level": Decimal(100),
            }
        ),
    )
    params = ObservationParameters(
        up_volume_ratio=1.5,
        down_volume_ratio=1.5,
        contraction_ratio=0.7,
        break_buffer_atr=0,
        reclaim_buffer_atr=0,
        reacceleration_mode="SMA20_TURN",
        zone_distance_atr=0.5,
    )
    full = evaluate_observations("TEST", features, [], [], source_contexts=[context], params=params)
    expected = [episode.model_dump(mode="json") for episode in full if episode.code in codes]
    assert expected
    target = _target_observations(
        "TEST", features, SimpleNamespace(signal_history=[]), [context], params, family
    )
    assert [episode.model_dump(mode="json") for episode in target] == expected


@pytest.fixture(autouse=True)
def _no_chart_open():
    # This module runs only local git/replay commands, never a chart viewer.
    yield


def test_baseline_preserves_dirty_and_untracked_inputs(tmp_path):
    """Losing untracked bytes or replacing an existing baseline must fail."""
    from scripts.research_trading_observations import capture_baseline

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    source = root / "src/strategies"
    source.mkdir(parents=True)
    tracked = source / "models.py"
    tracked.write_bytes(b"original\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Baseline Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )
    tracked.write_bytes(b"dirty working copy\n")
    untracked = source / "untracked.py"
    untracked.write_bytes(b"untracked implementation\n")
    (root / ".env").write_text("SECRET=do-not-copy\n")
    (root / "playbook.yaml").write_text("private: do-not-copy\n")
    (root / "notebooks").mkdir()
    (root / "notebooks/private.md").write_text("personal holdings\n")
    output = tmp_path / "baseline"

    hashes = capture_baseline(root, output)

    for path in (tracked, untracked):
        relative = path.relative_to(root).as_posix()
        assert hashes[relative] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert (output / "sources" / relative).read_bytes() == path.read_bytes()
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["files"] == hashes
    assert (
        manifest["head"]
        == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    )
    assert " M src/strategies/models.py" in manifest["git_status"]
    assert "?? src/strategies/untracked.py" in manifest["git_status"]
    assert not (output / "sources/.env").exists()
    assert not (output / "sources/playbook.yaml").exists()
    assert not (output / "sources/notebooks").exists()
    before = (output / "manifest.json").read_bytes()
    tracked.write_bytes(b"later edit\n")
    with pytest.raises(FileExistsError):
        capture_baseline(root, output)
    assert (output / "manifest.json").read_bytes() == before
    assert (output / "sources/src/strategies/models.py").read_bytes() == b"dirty working copy\n"


def test_baseline_product_replays_saved_inputs_and_sizes_only_fake_account(tmp_path, monkeypatch):
    """Dropping source/terminal data or changing saved planner inputs breaks replay."""
    from scripts.research_trading_observations import (
        build_product_record,
        replay_product_projection,
    )

    def reject_network(*args, **kwargs):
        raise AssertionError("baseline research must stay offline")

    monkeypatch.setattr("socket.socket.connect", reject_network)
    fixture = Path(__file__).resolve().parents[1] / "fixtures/swing_w150/v2_signal_path.csv"
    frame = pd.read_csv(fixture)
    frame[["Open", "High", "Low", "Close"]] = [[50 + index / 5] * 4 for index in range(len(frame))]
    spy = tmp_path / "SPY.csv"
    frame.to_csv(spy, index=False)

    record = build_product_record(
        ticker="TEST",
        instrument_path=fixture,
        market_path=spy,
        cutoff=date(2024, 12, 19),
        calendar_name="fixture_sessions",
    )

    output = record["projection"]
    assert [item["code"] for item in output["signal_history"]] == [
        "OVERHEAT",
        "OVERHEAT_CORRECTION",
        "POST_OVERHEAT_RECOVERY_ENTRY",
    ]
    assert output["entry_opportunity"]["status"] == "allow"
    assert output["entry_opportunity"]["entry_signal"] == output["current_signals"][0]
    assert output["entry_opportunity"]["anchors"]["source_date"] == "2024-12-19"
    assert output["entry_opportunity"]["terminal_on"] is None
    assert output["entry_opportunity"]["terminal_finality"] is None
    assert output["planner"]["directive"]["kind"] == "build_only_to_risk_target"
    assert output["planner"]["current_quantity"] == 7
    assert output["planner"]["buy_quantity"] == 93
    assert output["planner"]["sell_quantity"] == 0
    assert record["inputs"]["account"] == {
        "capital": "100000",
        "risk_budget": "1000",
        "per_share_risk": "10",
    }
    assert record["inputs"]["chart_bundle"]["market_ticker"] == "SPY"
    assert record["inputs"]["chart_bundle"]["instrument"]["bars"][-1]["finality"] == "final"
    assert record["inputs"]["parameter_fingerprint"] == (
        "3dca481189c1263c57ac26544fceb43cb2447e17923f890f3f65a30b0b0342f2"
    )
    assert replay_product_projection(json.loads(json.dumps(record))) == output


def test_baseline_product_records_calendar_gaps_without_filling(tmp_path):
    """Treating observed dates as a real exchange calendar hides missing data."""
    from scripts.research_trading_observations import build_product_record

    csv = tmp_path / "chart.csv"
    csv.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2025-01-02,100,101,99,100,100\n"
        "2025-01-06,100,101,99,100,100\n"
        "2025-01-07,100,101,99,100,100\n"
    )
    record = build_product_record(
        ticker="TEST",
        instrument_path=csv,
        market_path=csv,
        cutoff=date(2025, 1, 6),
        calendar_name="XNYS",
    )
    assert record["coverage"]["instrument"]["missing_sessions"] == ["2025-01-03"]
    assert record["input_status"] == "INCOMPLETE_COVERAGE"
    bundle = record["inputs"]["chart_bundle"]
    assert bundle["as_of"] == "2025-01-06"
    assert len(bundle["instrument"]["bars"]) == 2
    assert bundle["instrument"]["coverage"]["complete"] is False
    assert bundle["exchange_sessions"] == ["2025-01-02", "2025-01-03", "2025-01-06"]
    assert record["projection"]["entry_opportunity"]["status"] == "not_evaluated"


def test_baseline_product_missing_local_data_is_explicit(tmp_path):
    from scripts.research_trading_observations import build_product_record

    record = build_product_record(
        ticker="MISSING",
        instrument_path=tmp_path / "missing.csv",
        market_path=tmp_path / "SPY.csv",
        cutoff=date(2025, 12, 31),
        calendar_name="XNYS",
    )
    assert record["input_status"] == "MISSING_LOCAL_DATA"
    assert "projection" not in record
    assert len(record["missing_files"]) == 2


@pytest.mark.parametrize(
    "damage", ["missing", "corrupt", "unexpected", "receipt", "nested_sources"]
)
def test_verify_baseline_rejects_incomplete_or_damaged_artifacts(tmp_path, damage):
    """A missing/tampered snapshot must fail before any product replay."""
    from scripts.research_trading_observations import _verify_products

    products = tmp_path / "products"
    products.mkdir()
    product = products / "TEST.json"
    product.write_text(json.dumps({"input_status": "MISSING_LOCAL_DATA"}))
    kept = products / "KEPT.json"
    kept.write_text(product.read_text())
    receipt = tmp_path / "verification.txt"
    receipt.write_text("preserved verification")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "products": {"TEST": "MISSING_LOCAL_DATA", "KEPT": "MISSING_LOCAL_DATA"},
                "artifacts": {
                    "products/TEST.json": hashlib.sha256(product.read_bytes()).hexdigest(),
                    "products/KEPT.json": hashlib.sha256(kept.read_bytes()).hexdigest(),
                    "verification.txt": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                },
            }
        )
    )
    if damage == "missing":
        product.unlink()
    elif damage == "corrupt":
        product.write_text(json.dumps({"input_status": "changed"}))
    elif damage == "unexpected":
        (products / "EXTRA.json").write_text(product.read_text())
    elif damage == "receipt":
        receipt.write_text("changed receipt")
    else:
        nested = tmp_path / "foo/sources/extra.txt"
        nested.parent.mkdir(parents=True)
        nested.write_text("unexpected artifact")

    with pytest.raises(ValueError, match="baseline (artifact|product)"):
        _verify_products(tmp_path)


def test_comparison_keeps_observation_out_of_decisions_and_discloses_research_profile(tmp_path):
    from scripts.research_trading_observations import build_product_record, run_comparison

    fixture = Path("tests/fixtures/swing_w150/v2_signal_path.csv")
    record = build_product_record(
        ticker="TEST",
        instrument_path=fixture,
        market_path=fixture,
        cutoff=date(2025, 12, 31),
        calendar_name="fixture_sessions",
    )
    baseline = tmp_path / "baseline"
    (baseline / "products").mkdir(parents=True)
    product = baseline / "products/fixture.json"
    product.write_text(json.dumps(record))
    (baseline / "manifest.json").write_text(
        json.dumps(
            {
                "products": {"fixture": "COMPLETE"},
                "artifacts": {
                    "products/fixture.json": hashlib.sha256(product.read_bytes()).hexdigest()
                },
            }
        )
    )
    result = run_comparison(
        baseline,
        Path("research/trading_observation_v1/protocol.json"),
        output=tmp_path / "comparison",
    )
    assert result["research_status"] == "RESEARCH_ONLY_NOT_PRODUCTION_DEFAULT"
    assert result["production_default"] == "V1"
    assert result["same_policy_matches"] == {"V1": 1, "EXPLICIT_V2": 1}
    assert result["baseline_matches"] == 1
    assert result["provider_calls"] == result["llm_calls"] == 0
    profile = result["explicit_v2_parameters"]["support_cycle"]
    assert profile == {
        "normal_failure_closes": 2,
        "support_break_buffer_atr": 0,
        "immediate_failure_volume_ratio": 1.5,
        "immediate_failure_close_location": 0.25,
        "restart_mode": "A",
    }
    rows = json.loads((tmp_path / "comparison/policy-comparison.json").read_text())
    assert rows[0]["exit_semantics_equal"] is True
    assert rows[0]["input_kind"] == "SYNTHETIC_FIXTURE"
    assert (tmp_path / "comparison/comparison.md").is_file()


def test_future_evaluator_columns_never_enter_strategy_payload():
    from scripts.research_trading_observations import explicit_research_parameters
    from src.strategies.swing_w150.features import build_swing_features
    from src.strategies.swing_w150.signals import detect_swing

    frame = pd.read_csv(
        "tests/fixtures/swing_w150/v2_signal_path.csv", index_col="Date", parse_dates=True
    )
    params = explicit_research_parameters()
    clean = detect_swing("TEST", build_swing_features(frame, params), params)
    frame["future_winner"] = True
    frame["mfe"] = 999
    frame["mae"] = -999
    frame["return"] = 999
    tainted = detect_swing("TEST", build_swing_features(frame, params), params)
    assert tainted.model_dump(mode="json") == clean.model_dump(mode="json")
    assert "future_winner" not in json.dumps(tainted.model_dump(mode="json"))


def test_case_discovery_uses_final_kernel_and_keeps_synthetic_provenance():
    from scripts.research_trading_observations import (
        explicit_research_parameters,
        find_case_candidates,
    )
    from src.strategies.models import BarFinality
    from tests.strategies.swing_w150.conftest import SignalFactory

    params = explicit_research_parameters()
    features = SignalFactory().make([{"Close": 121, "Low": 120, "High": 123, "Volume": 50}])
    frame = features.frame
    frame["History_Bars"] = range(1, len(frame) + 1)
    frame["Volume_Ratio_Prev20"] = 0.5
    frame["Price_Breakout_Event"] = False
    frame.loc[frame.index[249], "Price_Breakout_Event"] = True
    # The tail is hypothetical: discovery must not promote it to a FINAL real case.
    from dataclasses import replace

    preview = replace(features, finalities=(BarFinality.PROVISIONAL,) * len(frame))
    assert find_case_candidates("TEST", preview, params, evaluation_start=date(2017, 1, 1)) == {}
    actual = find_case_candidates("TEST", features, params, evaluation_start=date(2017, 1, 1))
    assert actual["HEALTHY_SMA50"]["dates"] == [str(frame.index[-1].date())]
    assert all(item["input_kind"] == "SYNTHETIC_FIXTURE" for item in actual.values())

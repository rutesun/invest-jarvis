"""Preserve offline inputs and product projections before Observation research."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LOCAL_TICKERS = (
    "AMD",
    "AMAT",
    "AMZN",
    "AVGO",
    "CAT",
    "COIN",
    "CRWD",
    "INTC",
    "JNJ",
    "JPM",
    "KO",
    "META",
    "MSFT",
    "MU",
    "NVDA",
    "QCOM",
    "SHOP",
    "TSLA",
    "WMT",
    "XOM",
)


SNAPSHOT_SCOPE = (
    "src/strategies",
    "src/position",
    "src/backtest",
    "src/tools/technical",
    "src/tools/brief",
    "src/providers/exchange_calendar.py",
    "src/storage/canonical.py",
    "src/pipelines/strategy_analysis.py",
    "src/pipelines/strategy_render.py",
    "src/pipelines/quick_check.py",
    "src/pipelines/brief.py",
    "tests/strategies",
    "tests/position",
    "tests/backtest",
    "tests/fixtures/swing_w150",
    "tests/harness/swing_fixture_contract.py",
    "tests/conftest.py",
    "tests/pipelines/test_strategy_analysis.py",
    "tests/pipelines/test_strategy_coverage.py",
    "tests/pipelines/test_technical_contract_parity.py",
    "tests/pipelines/test_quick_check.py",
    "tests/pipelines/test_brief.py",
    "tests/pipelines/test_deep_dive.py",
    "tests/pipelines/test_entry_shadow_render.py",
    "docs/CLI_USAGE.md",
    "docs/FEATURES.md",
    "docs/active-context.md",
    "docs/changes/INDEX.md",
    "docs/changes/scorecard-strategy-position-separation.md",
    "docs/superpowers/specs/2026-10-01-scorecard-strategy-position-separation-design.md",
    "docs/superpowers/plans/2026-10-21-trading-observation-v1-pullback.md",
    "docs/references/2026-10-20-trading-observation-model-v1-review-feedback.md",
    "docs/references/2026-10-20-trading-observation-model-v1-review-feedback-v2.md",
    "docs/worklog/swing-w150-engine.md",
    "docs/worklog/entry-opportunity-production-shadow.md",
    "docs/worklog/trading-observation-v1.md",
    "scripts/research_trading_observations.py",
    "AGENTS.md",
    "CLAUDE.md",
    "pyproject.toml",
    "uv.lock",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _json_value(payload: object) -> object:
    def encode(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(f"unsupported JSON value: {type(value).__name__}")

    return json.loads(json.dumps(payload, default=encode))


def capture_baseline(root: Path, output: Path) -> dict[str, str]:
    """Copy current scoped bytes, including untracked files, without overwriting."""
    root, output = root.resolve(), output.resolve()
    # Capture git metadata before creating any output inside the checkout.
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(
        ["git", "status", "--short", "--untracked-files=all"], cwd=root, text=True
    )
    files = {}
    for item in SNAPSHOT_SCOPE:
        source = root / item
        candidates = source.rglob("*") if source.is_dir() else (source,)
        for path in candidates:
            if path.is_symlink():
                raise ValueError(f"baseline scope cannot contain a symlink: {path}")
            if path.is_file() and path.suffix in {".py", ".csv", ".json", ".md", ".toml", ".lock"}:
                files[path.relative_to(root).as_posix()] = _sha256(path)
    output.mkdir(parents=True, exist_ok=False)
    for relative, digest in sorted(files.items()):
        destination = output / "sources" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
        if _sha256(destination) != digest:
            raise RuntimeError(f"source changed during baseline capture: {relative}")
    _write_json(
        output / "manifest.json",
        {
            "schema_version": "trading-observation-baseline-v1",
            "head": head,
            "git_status": status,
            "files": dict(sorted(files.items())),
            "review_boundary": "Current working bytes; HEAD is metadata, not the comparison policy.",
            "excluded": [".env", "playbook.yaml", "personal holdings", "notebooks", "credentials"],
            "provider_calls": 0,
            "llm_calls": 0,
        },
    )
    return dict(sorted(files.items()))


def replay_product_projection(
    record: dict, *, params=None, observations_enabled: bool = True
) -> dict:
    """Recompute only the product fields from the exact saved V1 inputs."""
    from src.strategies.models import ChartBundle
    from src.strategies.swing_w150.adapter import SwingW150SignalStrategy
    from src.strategies.swing_w150.parameters import SwingW150Parameters

    inputs = record["inputs"]
    payload = dict(inputs["parameter_payload"])
    payload["pullback_support_sma_periods"] = tuple(payload["pullback_support_sma_periods"])
    saved_params = SwingW150Parameters(**payload)
    if saved_params.parameter_fingerprint != inputs["parameter_fingerprint"]:
        raise ValueError("baseline parameter payload/fingerprint mismatch")
    chart = ChartBundle.model_validate(inputs["chart_bundle"])
    if chart.bundle_hash != inputs["chart_bundle"]["bundle_hash"]:
        raise ValueError("baseline chart payload/hash mismatch")
    signals = SwingW150SignalStrategy(
        params=params or saved_params, observations_enabled=observations_enabled
    ).evaluate_signals(chart)
    return _decision_projection(signals, inputs)


def _decision_projection(signals, inputs: dict) -> dict:
    from src.position.models import AccountSnapshot, MarketSnapshot, PositionSnapshot
    from src.position.planner import plan_position_from_signals

    account = AccountSnapshot(**{key: Decimal(value) for key, value in inputs["account"].items()})
    snapshot = inputs["market_snapshot"]
    plan = plan_position_from_signals(
        signals,
        PositionSnapshot(**inputs["position"]),
        account,
        MarketSnapshot(
            session=date.fromisoformat(snapshot["session"]),
            price=Decimal(snapshot["price"]),
            snapshot_hash=snapshot["snapshot_hash"],
        ),
        calculated_at=datetime.fromisoformat(inputs["calculated_at"]),
    )
    return {
        "signal_history": [signal.model_dump(mode="json") for signal in signals.signal_history],
        "current_signals": [signal.model_dump(mode="json") for signal in signals.current_signals],
        "entry_opportunity": signals.entry_opportunity.model_dump(mode="json"),
        "planner": _json_value(asdict(plan)),
    }


def build_product_record(
    *,
    ticker: str,
    instrument_path: Path,
    market_path: Path,
    cutoff: date,
    calendar_name: str,
    include_projection: bool = True,
) -> dict:
    """Freeze a local instrument/SPY prefix; report gaps without filling bars."""
    import pandas as pd

    from src.providers.exchange_calendar import exchange_sessions_for
    from src.storage.canonical import canonical_hash
    from src.strategies.chart_bundle import chart_series_from_dataframe
    from src.strategies.models import ChartBundle, CoverageManifest
    from src.strategies.swing_w150.parameters import SwingW150Parameters

    sources = {"instrument": instrument_path, "SPY": market_path}
    record = {"ticker": ticker, "cutoff": cutoff.isoformat(), "calendar": calendar_name}
    missing = [str(path) for path in sources.values() if not path.is_file()]
    if missing:
        return {**record, "input_status": "MISSING_LOCAL_DATA", "missing_files": missing}
    frames = {
        key: pd.read_csv(path, index_col="Date", parse_dates=True).sort_index()
        for key, path in sources.items()
    }
    for frame in frames.values():
        if frame.empty or frame.index.has_duplicates:
            raise ValueError("baseline CSV must contain unique, nonempty dated bars")
    common = frames["instrument"].index.intersection(frames["SPY"].index)
    common = common[common.date <= cutoff]
    if common.empty:
        return {**record, "input_status": "NO_COMMON_SESSION"}
    as_of = common[-1].date()
    frames = {key: frame.loc[frame.index.date <= as_of] for key, frame in frames.items()}
    start = min(frame.index[0].date() for frame in frames.values())
    sessions = (
        tuple(sorted({day.date() for frame in frames.values() for day in frame.index}))
        if calendar_name == "fixture_sessions"
        else exchange_sessions_for(calendar_name, start, as_of)
    )
    coverage = {}
    series = {}
    for key, frame in frames.items():
        first = frame.index[0].date()
        observed = set(frame.index.date)
        expected = tuple(day for day in sessions if first <= day <= as_of)
        missing_days = sorted(set(expected) - observed)
        unexpected = sorted(observed - set(expected))
        complete = not missing_days and not unexpected
        coverage[key] = {
            "actual_start": first.isoformat(),
            "actual_end": as_of.isoformat(),
            "bar_count": len(frame),
            "complete": complete,
            "missing_sessions": [day.isoformat() for day in missing_days],
            "unexpected_sessions": [day.isoformat() for day in unexpected],
        }
        series[key] = chart_series_from_dataframe(
            frame,
            CoverageManifest(
                requested_start=first,
                actual_start=first,
                actual_end=as_of,
                expected_sessions=expected,
                complete=complete,
                truncation_reason=None if complete else "local_csv_calendar_mismatch",
            ),
        )
    chart = ChartBundle(
        profile_version="observation-baseline-chart-v1",
        ticker=ticker,
        as_of=as_of,
        instrument=series["instrument"],
        market=series["SPY"],
        market_ticker="SPY",
        exchange_sessions=sessions,
    )
    params = SwingW150Parameters()
    price = chart.instrument.bars[-1].close
    record.update(
        {
            "as_of": as_of.isoformat(),
            "input_status": "COMPLETE"
            if all(item["complete"] for item in coverage.values())
            else "INCOMPLETE_COVERAGE",
            "coverage": coverage,
            "sources": {
                key: {"path": str(path), "raw_sha256": _sha256(path)}
                for key, path in sources.items()
            },
            "inputs": {
                "chart_bundle": chart.model_dump(mode="json"),
                "parameter_payload": _json_value(asdict(params)),
                "parameter_fingerprint": params.parameter_fingerprint,
                "account": {"capital": "100000", "risk_budget": "1000", "per_share_risk": "10"},
                "position": {"quantity": 7},
                "market_snapshot": {
                    "session": as_of.isoformat(),
                    "price": str(price),
                    "snapshot_hash": canonical_hash(
                        "jarvis:fake-baseline-market:v1",
                        {
                            "ticker": ticker,
                            "session": as_of,
                            "price": price,
                        },
                    ),
                },
                "calculated_at": datetime.combine(
                    as_of, datetime.min.time(), tzinfo=UTC
                ).isoformat(),
                "account_provenance": "synthetic constants; no personal configuration loaded",
            },
        }
    )
    if include_projection:
        record["projection"] = replay_product_projection(record)
    return record


@contextmanager
def _offline_network():
    """A baseline command fails if any imported code attempts network egress."""
    message = "network connections are forbidden in offline baseline research"
    with (
        patch("socket.socket.connect", side_effect=RuntimeError(message)),
        patch("socket.socket.connect_ex", side_effect=RuntimeError(message)),
        patch("socket.create_connection", side_effect=RuntimeError(message)),
    ):
        yield


def _capture_products(root: Path, output: Path) -> dict:
    products = {}
    spy = root / "tmp/bt_cache_long/SPY.csv"
    for ticker in LOCAL_TICKERS:
        record = build_product_record(
            ticker=ticker,
            instrument_path=root / f"tmp/bt_cache_long/{ticker}.csv",
            market_path=spy,
            cutoff=date(2025, 12, 31),
            calendar_name="XNYS",
        )
        _write_json(output / f"products/{ticker}.json", record)
        products[ticker] = record["input_status"]
    fixture = root / "tests/fixtures/swing_w150/v2_signal_path.csv"
    # Its synthetic business-day bars intentionally include exchange holidays.
    # Keep that fixture's explicit session domain, separately from real charts.
    record = build_product_record(
        ticker="TEST",
        instrument_path=fixture,
        market_path=fixture,
        cutoff=date(2025, 12, 31),
        calendar_name="fixture_sessions",
    )
    record["fixture_market_provenance"] = "synthetic fixture reused as SPY, not market data"
    _write_json(output / "products/fixture-v2-signal-path.json", record)
    products["fixture-v2-signal-path"] = record["input_status"]
    return products


def _verify_baseline_artifacts(output: Path) -> dict:
    manifest = json.loads((output / "manifest.json").read_text())
    expected_products = {f"products/{name}.json" for name in manifest["products"]}
    actual_products = {
        path.relative_to(output).as_posix()
        for path in (output / "products").rglob("*")
        if path.is_file()
    }
    if actual_products != expected_products:
        raise ValueError(
            "baseline product set differs: "
            f"missing={sorted(expected_products - actual_products)}, "
            f"unexpected={sorted(actual_products - expected_products)}"
        )
    expected = manifest["artifacts"]
    actual = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
        and path != output / "manifest.json"
        and path.relative_to(output).parts[0] != "sources"
    }
    if actual != set(expected) or not expected_products <= set(expected):
        raise ValueError(
            "baseline artifact set differs: "
            f"missing={sorted(set(expected) - actual)}, "
            f"unexpected={sorted(actual - set(expected))}"
        )
    for relative, digest in expected.items():
        path = output / relative
        if path.is_symlink() or _sha256(path) != digest:
            raise ValueError(f"baseline artifact hash differs: {relative}")
    return manifest


def _verify_products(output: Path, *, verify_artifacts: bool = True) -> dict:
    if verify_artifacts:
        _verify_baseline_artifacts(output)
    results = {}
    for path in sorted((output / "products").glob("*.json")):
        record = json.loads(path.read_text())
        if "projection" not in record:
            results[path.stem] = record["input_status"]
        elif replay_product_projection(record) != record["projection"]:
            raise ValueError(f"product projection differs: {path.name}")
        else:
            results[path.stem] = "MATCH"
    if not results:
        raise ValueError("baseline contains no product records")
    return results


def explicit_research_parameters():
    """One predeclared diagnostic profile; never a production selection."""
    from src.strategies.swing_w150.parameters import SupportCycleParameters, SwingW150ParametersV2

    return SwingW150ParametersV2(
        support_cycle=SupportCycleParameters(
            normal_failure_closes=2,
            support_break_buffer_atr=0,
            immediate_failure_volume_ratio=1.5,
            immediate_failure_close_location=0.25,
            restart_mode="A",
        )
    )


def _research_manifest(protocol_path: Path) -> dict:
    from src.strategies.observations.parameters import PRODUCT_OBSERVATION_PARAMETERS

    params = explicit_research_parameters()
    root = Path(__file__).resolve().parents[1]
    paths = set((root / "src").rglob("*.py")) | {Path(__file__).resolve(), root / "uv.lock"}
    return {
        "research_status": "RESEARCH_ONLY_NOT_PRODUCTION_DEFAULT",
        "production_default": "V1",
        "selection_status": "failure/immediate/restart UNRESOLVED; separate protocol/sample/policy decision required",
        "explicit_v2_parameters": asdict(params),
        "explicit_v2_fingerprint": params.parameter_fingerprint,
        "observation_parameters": asdict(PRODUCT_OBSERVATION_PARAMETERS),
        "observation_fingerprint": PRODUCT_OBSERVATION_PARAMETERS.parameter_fingerprint,
        "protocol_sha256": _sha256(protocol_path),
        "executable_sources": {
            path.relative_to(root).as_posix(): _sha256(path) for path in sorted(paths)
        },
        "provider_calls": 0,
        "llm_calls": 0,
        "network_policy": "socket connections rejected; no research JSONL or future labels read",
        "performance_claim": "offline diagnostic only; no strategy-performance optimization or production latency benchmark",
    }


def _signal_lineage(signal) -> dict | None:
    if signal is None:
        return None
    value = signal.model_dump(mode="json") if hasattr(signal, "model_dump") else signal
    return {key: value[key] for key in ("occurred_on", "code", "finality", "signal_price")}


def _opportunity_summary(opportunity) -> dict:
    return {
        "source": _signal_lineage(opportunity.entry_signal),
        "status": opportunity.status.value,
        "cause": [item.code for item in opportunity.evidence],
        "invalidator": _signal_lineage(opportunity.invalidated_by),
        "terminal_on": str(opportunity.terminal_on) if opportunity.terminal_on else None,
    }


def _dated_inputs(inputs, chart):
    from src.storage.canonical import canonical_hash

    snapshot = {"session": str(chart.as_of), "price": str(chart.instrument.bars[-1].close)}
    snapshot["snapshot_hash"] = canonical_hash(
        "jarvis:fake-comparison-market:v1", {"ticker": chart.ticker, **snapshot}
    )
    return {
        **inputs,
        "market_snapshot": snapshot,
        "calculated_at": datetime.combine(chart.as_of, datetime.min.time(), tzinfo=UTC).isoformat(),
    }


def _dated_policy_comparison(
    chart, features, old_params, new_params, inputs, *, evaluation_start, evaluation_end
) -> list[dict]:
    """Compare causal daily kernels; adapters/renderers are reserved for selected cases."""
    from src.strategies.entry_opportunity import evaluate_signal_entry_opportunity
    from src.strategies.models import StrategySignalBundle
    from src.strategies.swing_w150.signals import iter_swing_detection

    rows = []
    previous = None
    previous_kernel = None
    for old, new in zip(
        iter_swing_detection(chart.ticker, features, old_params),
        iter_swing_detection(chart.ticker, features, new_params),
        strict=True,
    ):
        if not evaluation_start <= old.as_of <= evaluation_end:
            continue
        states = []
        for detection in (old, new):
            watches = [
                item
                for item in detection.observation_history
                if item.code == "PULLBACK_WATCH" and item.status == "active"
            ]
            states.append(
                {
                    "watch": [
                        {
                            "started_on": str(item.started_on),
                            "anchor": item.anchor_type,
                            "evidence": [e.model_dump(mode="json") for e in item.evidence],
                        }
                        for item in watches
                    ],
                    "signals": [_signal_lineage(item) for item in detection.current_signals],
                    "source": next(
                        (
                            _signal_lineage(item)
                            for item in reversed(detection.signal_history)
                            if item.code.endswith("ENTRY")
                        ),
                        None,
                    ),
                }
            )
        # Evidence changes on an open WATCH are represented by the event's latest snapshot.
        signature = [
            {
                **state,
                "watch": [
                    {k: v for k, v in item.items() if k != "evidence"} for item in state["watch"]
                ],
            }
            for state in states
        ]
        fresh_different_source = signature[0]["source"] != signature[1]["source"] and any(
            0
            <= features.frame.index.get_loc(str(old.as_of))
            - features.frame.index.get_loc(source["occurred_on"])
            <= new_params.entry_opportunity_max_age_bars + 1
            for source in (signature[0]["source"], signature[1]["source"])
            if source is not None
        )
        if signature[0] == signature[1] or (
            signature == previous_kernel and not fresh_different_source
        ):
            continue
        previous_kernel = signature
        prefix = chart.prefix(old.as_of)
        dated_inputs = _dated_inputs(inputs, prefix)
        for state, detection, params in zip(
            states, (old, new), (old_params, new_params), strict=True
        ):
            opportunity = evaluate_signal_entry_opportunity(
                detection.signal_history, prefix, params, features=features
            )
            bundle = StrategySignalBundle(**detection.model_dump(), entry_opportunity=opportunity)
            projection = _decision_projection(bundle, dated_inputs)
            state["opportunity"] = _opportunity_summary(opportunity)
            state["planner"] = projection["planner"]
        complete_signature = [
            {**sig, "opportunity": state["opportunity"], "planner": state["planner"]["directive"]}
            for sig, state in zip(signature, states, strict=True)
        ]
        if complete_signature == previous:
            continue
        previous = complete_signature
        rows.append(
            {
                "ticker": chart.ticker,
                "date": str(old.as_of),
                "close": str(prefix.instrument.bars[-1].close),
                "V1": states[0],
                "EXPLICIT_V2": states[1],
                "cause": "support-ladder WATCH/reversal/source ancestry; versioned IDs are not equated",
            }
        )
    return rows


def run_comparison(baseline: Path, protocol_path: Path, *, output: Path) -> dict:
    from src.strategies.models import ChartBundle
    from src.strategies.swing_w150.adapter import SwingW150SignalStrategy, _frame
    from src.strategies.swing_w150.features import build_swing_features
    from src.strategies.swing_w150.parameters import SwingW150Parameters

    manifest = _verify_baseline_artifacts(baseline)
    protocol = json.loads(protocol_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    result = _research_manifest(protocol_path)
    result.update(
        {
            "baseline_manifest_sha256": _sha256(baseline / "manifest.json"),
            "baseline_artifacts": manifest["artifacts"],
            "same_policy_matches": {"V1": 0, "EXPLICIT_V2": 0},
            "baseline_matches": 0,
            "input_records": len(manifest["products"]),
        }
    )
    # Persist the profile before observing any comparison output.
    _write_json(output / "run-input-manifest.json", result)
    comparisons, isolation, dated = [], [], []
    started = time.perf_counter()
    for name in sorted(manifest["products"]):
        record = json.loads((baseline / f"products/{name}.json").read_text())
        if "projection" not in record:
            comparisons.append({"record": name, "input_status": record["input_status"]})
            continue
        chart = ChartBundle.model_validate(record["inputs"]["chart_bundle"])
        bundles, projections = {}, {}
        for policy, params in (
            ("V1", SwingW150Parameters()),
            ("EXPLICIT_V2", explicit_research_parameters()),
        ):
            pair = []
            for enabled in (True, False):
                signals = SwingW150SignalStrategy(
                    params=params, observations_enabled=enabled
                ).evaluate_signals(chart)
                if signals.diagnostic_errors:
                    raise ValueError(f"{name}/{policy}: {signals.diagnostic_errors}")
                pair.append(_decision_projection(signals, record["inputs"]))
                if enabled:
                    bundles[policy] = signals
            if pair[0] != pair[1]:
                raise ValueError(f"Observation isolation failed: {name}/{policy}")
            result["same_policy_matches"][policy] += 1
            projections[policy] = pair[0]
            isolation.append(
                {
                    "record": name,
                    "policy": policy,
                    "status": "MATCH",
                    "fields": list(pair[0]),
                    "source_anchors_included": True,
                }
            )
        if projections["V1"] != record["projection"]:
            raise ValueError(f"saved V1 baseline differs: {name}")
        result["baseline_matches"] += 1
        exit_lists = [
            [
                _signal_lineage(item)
                for item in bundles[policy].signal_history
                if item.code == "SMA150_EXIT"
            ]
            for policy in bundles
        ]
        if exit_lists[0] != exit_lists[1]:
            raise ValueError(f"exit semantics changed: {name}")
        features = build_swing_features(
            _frame(chart),
            SwingW150Parameters(),
            finalities=[item.finality for item in chart.instrument.bars],
            coverage=chart.instrument.coverage,
        )
        dates = _dated_policy_comparison(
            chart,
            features,
            SwingW150Parameters(),
            explicit_research_parameters(),
            record["inputs"],
            evaluation_start=date.fromisoformat(protocol["periods"]["evaluation_start"]),
            evaluation_end=date.fromisoformat(protocol["periods"]["evaluation_end"]),
        )
        dated.extend(dates)
        comparisons.append(
            {
                "record": name,
                "ticker": chart.ticker,
                "as_of": str(chart.as_of),
                "input_kind": "SYNTHETIC_FIXTURE"
                if record["calendar"] == "fixture_sessions"
                else "HISTORICAL_LOCAL_REAL_OHLCV",
                "exit_semantics_equal": True,
                "dated_difference_count": len(dates),
                "counts": {
                    policy: {
                        "PULLBACK_WATCH": sum(
                            item.code == "PULLBACK_WATCH" for item in bundle.observation_history
                        ),
                        "PULLBACK_REVERSAL_ENTRY": sum(
                            item.code == "PULLBACK_REVERSAL_ENTRY" for item in bundle.signal_history
                        ),
                    }
                    for policy, bundle in bundles.items()
                },
                "projections": projections,
            }
        )
        print(
            f"compare {name}: V1 baseline + V1/V2 ON/OFF MATCH; dated differences={len(dates)}",
            flush=True,
        )
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    result["dated_difference_count"] = len(dated)
    _write_json(output / "observation-isolation.json", isolation)
    _write_json(output / "policy-comparison.json", comparisons)
    _write_json(output / "dated-policy-differences.json", dated)
    lines = [
        "# Trading Observation 비교",
        "",
        result["research_status"],
        "",
        "제품 기본값 V1. 명시 V2는 사전 고정 진단 예시이며 운영 선정·성과 검증이 아닙니다.",
        "",
        "## A. 같은 정책의 Observation ON/OFF",
        "",
        "| 정책 | MATCH |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {policy} | {count} |" for policy, count in result["same_policy_matches"].items()
    )
    lines.extend(
        [
            "",
            "Signal/source anchors/Opportunity/Planner 전체 JSON을 비교했습니다.",
            "",
            "## B. V1 / 명시 V2 Pullback",
            "",
            "| 자료 | WATCH V1/V2 | reversal V1/V2 | 날짜별 차이 |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in comparisons:
        if "counts" in row:
            a, b = row["counts"]["V1"], row["counts"]["EXPLICIT_V2"]
            lines.append(
                f"| {row['record']} ({row['input_kind']}) | {a['PULLBACK_WATCH']}/{b['PULLBACK_WATCH']} | {a['PULLBACK_REVERSAL_ENTRY']}/{b['PULLBACK_REVERSAL_ENTRY']} | {row['dated_difference_count']} |"
            )
    lines.extend(
        [
            "",
            "날짜·가격·Evidence·source 계보·Opportunity 원인·가짜 계좌 Planner는 dated-policy-differences.json에 보존했습니다.",
            "동일한 사건의 버전 간 Signal ID 일치는 요구하지 않습니다. SMA150_EXIT의 날짜·가격·finality는 동일합니다.",
            "Backtest FINAL-only / t+1 open은 별도 실행 계약 테스트로 검증하며 이 표는 수익성 비교가 아닙니다.",
        ]
    )
    (output / "comparison.md").write_text("\n".join(lines) + "\n")
    result["artifacts"] = {
        path.name: _sha256(path) for path in sorted(output.iterdir()) if path.is_file()
    }
    _write_json(output / "comparison-manifest.json", result)
    return result


CASE_KINDS = (
    "HEALTHY_SMA50",
    "ST_DOWN_SMA150_WATCH",
    "ONE_DAY_SHAKEOUT_RECLAIM",
    "SMA150_TERMINATION_NEW_CYCLE",
    "TERMINAL_AFTER_RECLAIM",
)


def find_case_candidates(
    ticker, features, params, *, evaluation_start, input_kind="SYNTHETIC_FIXTURE"
) -> dict:
    return _scan_case_candidates(
        ticker, features, params, evaluation_start=evaluation_start, input_kind=input_kind
    )[0]


def _scan_case_candidates(ticker, features, params, *, evaluation_start, input_kind):
    """Find bounded candidate prefixes using one causal FINAL kernel replay."""
    from src.strategies.models import BarFinality
    from src.strategies.swing_w150.signals import iter_swing_detection

    found, prior_tests = {}, {}
    ended_cycle = None
    previous_cycle = None
    for bar, snapshot in enumerate(iter_swing_detection(ticker, features, params)):
        if features.finalities[bar] != BarFinality.FINAL or snapshot.as_of < evaluation_start:
            continue
        row = features.frame.iloc[bar]
        day = str(snapshot.as_of)

        def save(kind, dates):
            found.setdefault(kind, {"ticker": ticker, "dates": dates, "input_kind": input_kind})

        for watch in snapshot.observation_history:
            if watch.code != "PULLBACK_WATCH" or watch.status != "active":
                continue
            if (
                watch.anchor_type == "SMA50"
                and row.get("SuperTrend_Dir") == 1
                and row.get("SMA_50_Slope_21", -1) >= 0
                and row.get("Volume_Ratio_Prev20", 2) <= 1
            ):
                save("HEALTHY_SMA50", [day])
            if watch.anchor_type == "SMA150" and row.get("SuperTrend_Dir") == -1:
                save("ST_DOWN_SMA150_WATCH", [day])
        for state in snapshot.support_tests or ():
            prior = prior_tests.get(state.anchor.anchor_id)
            if (
                state.status == "RECLAIMED"
                and state.reclaimed_on == snapshot.as_of
                and prior is not None
                and prior.status == "SOFT_BREACH"
                and prior.below_count == 1
                and not state.failure_latched
            ):
                save("ONE_DAY_SHAKEOUT_RECLAIM", [str(prior.status_as_of), day])
        cycle = snapshot.up_cycle
        if cycle is not None:
            if (
                cycle.status == "TERMINATED"
                and previous_cycle is not None
                and previous_cycle.status == "ACTIVE"
            ):
                ended_cycle = (cycle.cycle_id, day)
            if (
                cycle.status == "ACTIVE"
                and ended_cycle is not None
                and cycle.cycle_id != ended_cycle[0]
                and cycle.started_on == snapshot.as_of
            ):
                save("SMA150_TERMINATION_NEW_CYCLE", [ended_cycle[1], day])
        previous_cycle = cycle
        prior_tests = {
            state.anchor.anchor_id: state.model_copy(deep=True)
            for state in snapshot.support_tests or ()
        }
    return found, snapshot


def _find_terminal_reclaim(chart, features, detected, params, evaluation_start):
    from src.strategies.entry_anchors import build_entry_source_anchors
    from src.strategies.entry_opportunity import evaluate_signal_entry_opportunity
    from src.strategies.models import EntryOpportunityStatus, ObservationSourceContext
    from src.strategies.observations.detectors import evaluate_observations
    from src.strategies.observations.parameters import PRODUCT_OBSERVATION_PARAMETERS

    sources = [item for item in detected.signal_history if item.code.endswith("ENTRY")]
    invalidators = [item for item in detected.signal_history if not item.code.endswith("ENTRY")]
    contexts = []
    for source in sources:
        opportunity = evaluate_signal_entry_opportunity(
            [source, *invalidators], chart, params, features=features
        )
        terminal = opportunity.status in {
            EntryOpportunityStatus.INVALIDATED,
            EntryOpportunityStatus.EXPIRED,
        }
        contexts.append(
            ObservationSourceContext(
                signal=source,
                anchors=build_entry_source_anchors(
                    source, chart, features, detected.observation_history
                ),
                terminal_status=opportunity.status if terminal else None,
                terminal_on=opportunity.terminal_on if terminal else None,
                terminal_reason=(
                    opportunity.invalidated_by.code
                    if opportunity.invalidated_by
                    else opportunity.evidence[0].code
                )
                if terminal
                else None,
            )
        )
    observations = evaluate_observations(
        chart.ticker,
        features,
        detected.signal_history,
        detected.observation_history,
        source_contexts=contexts,
        params=PRODUCT_OBSERVATION_PARAMETERS,
    )
    event = next(
        (
            item
            for item in observations
            if item.code in {"BREAKOUT_RECLAIM", "SUPPORT_RECLAIM"}
            and item.source_terminal is True
            and item.started_on >= evaluation_start
        ),
        None,
    )
    if event is None:
        return None
    context = next(item for item in contexts if item.signal.signal_id == event.source_signal_id)
    return {
        "ticker": chart.ticker,
        "dates": [str(event.started_on)],
        "input_kind": "HISTORICAL_LOCAL_REAL_OHLCV",
        "source_signal_id": event.source_signal_id,
        "source_terminal_on": str(context.terminal_on),
        "source_terminal_status": context.terminal_status.value,
    }


def run_cases(protocol_path: Path, *, root: Path, output: Path) -> dict:
    from src.pipelines.strategy_analysis import AnalysisStrategyResult
    from src.pipelines.strategy_render import render_strategy_sections
    from src.strategies.models import ChartBundle
    from src.strategies.runner import StrategyRunner
    from src.strategies.swing_w150.adapter import _frame
    from src.strategies.swing_w150.features import build_swing_features
    from src.tools.technical.scorer import TechnicalScorer

    protocol = json.loads(protocol_path.read_text())
    params = explicit_research_parameters()
    output.mkdir(parents=True, exist_ok=False)
    manifest = _research_manifest(protocol_path)
    manifest.update(
        {
            "current_market_data": "NOT_COLLECTED",
            "synthetic_fixtures": "tests/fixtures/swing_w150 only; not real cases",
            "evaluation_period": protocol["periods"],
            "inputs": {},
            "case_results": {},
        }
    )
    _write_json(output / "run-input-manifest.json", manifest)
    found, prepared = {}, {}
    start = date.fromisoformat(protocol["periods"]["evaluation_start"])
    end = date.fromisoformat(protocol["periods"]["evaluation_end"])
    started = time.perf_counter()
    for ticker in protocol["universe"]:
        record = build_product_record(
            ticker=ticker,
            instrument_path=root / protocol["cache_dir"] / f"{ticker}.csv",
            market_path=root / protocol["cache_dir"] / f"{protocol['market']}.csv",
            cutoff=end,
            calendar_name="XNYS",
            include_projection=False,
        )
        manifest["inputs"][ticker] = {
            "status": record["input_status"],
            "sources": record.get("sources", {}),
        }
        if record["input_status"] != "COMPLETE":
            continue
        chart = ChartBundle.model_validate(record["inputs"]["chart_bundle"])
        features = build_swing_features(_frame(chart), params, coverage=chart.instrument.coverage)
        candidates, detected = _scan_case_candidates(
            ticker,
            features,
            params,
            evaluation_start=start,
            input_kind="HISTORICAL_LOCAL_REAL_OHLCV",
        )
        if "TERMINAL_AFTER_RECLAIM" not in found:
            terminal = _find_terminal_reclaim(chart, features, detected, params, start)
            if terminal:
                candidates["TERMINAL_AFTER_RECLAIM"] = terminal
        for kind, candidate in candidates.items():
            if kind not in found:
                found[kind] = candidate
                prepared[ticker] = (chart, features, record["inputs"])
        print(f"cases {ticker}: found={sorted(found)}", flush=True)
        if set(found) == set(CASE_KINDS):
            break
    lines = [
        "# 로컬 실제 OHLCV 사례",
        "",
        manifest["research_status"],
        "",
        "제품 기본값 V1, 아래는 명시 V2 진단 예시입니다. 자료는 2017~2025년 과거 로컬 차트이며 현재 시장 데이터는 수집하지 않았습니다.",
    ]
    for kind in CASE_KINDS:
        lines.extend(["", f"## {kind}", ""])
        if kind not in found:
            manifest["case_results"][kind] = {"status": "NOT_FOUND_IN_LOCAL_DATA"}
            lines.append("해당 조건의 실제 사례를 로컬 자료에서 찾지 못했습니다.")
            continue
        candidate = found[kind]
        chart, features, inputs = prepared[candidate["ticker"]]
        prefix_results = []
        for day_text in candidate["dates"]:
            day = date.fromisoformat(day_text)
            prefix = chart.prefix(day)
            technical = TechnicalScorer().score(
                features.frame.loc[:day_text], ticker=chart.ticker, include_history=False
            )
            run = StrategyRunner(swing_parameters=params).run(prefix, legacy_result=technical)
            if run.errors or run.diagnostic_errors:
                raise ValueError(f"case {kind}: {run.errors} {run.diagnostic_errors}")
            signals = run.signal_bundles[0]
            dated_inputs = _dated_inputs(inputs, prefix)
            projection = _decision_projection(signals, dated_inputs)
            analysis = AnalysisStrategyResult(
                technical.scorecard,
                run,
                prefix.exchange_sessions,
                float(prefix.instrument.bars[-1].close),
            )
            rendered = render_strategy_sections(technical.scorecard, analysis, detail=True)
            filename = f"{kind.lower()}-{chart.ticker}-{day_text}.md"
            (output / filename).write_text(rendered + "\n")
            payload = {
                "date": day_text,
                "close": str(prefix.instrument.bars[-1].close),
                "bundle_hash": prefix.bundle_hash,
                "strategy": signals.model_dump(mode="json"),
                "projection": projection,
                "rendered_markdown": filename,
            }
            if kind in {"HEALTHY_SMA50", "ST_DOWN_SMA150_WATCH"}:
                anchor = "SMA50" if kind == "HEALTHY_SMA50" else "SMA150"
                if not any(
                    item.code == "PULLBACK_WATCH"
                    and item.status == "active"
                    and item.anchor_type == anchor
                    for item in signals.observation_history
                ):
                    raise ValueError(f"case {kind}: WATCH not reproduced by actual adapter")
            if kind == "TERMINAL_AFTER_RECLAIM":
                from src.strategies.entry_opportunity import evaluate_signal_entry_opportunity

                events = [
                    item
                    for item in signals.observation_history
                    if item.code in {"BREAKOUT_RECLAIM", "SUPPORT_RECLAIM"}
                    and item.started_on == day
                    and item.source_terminal is True
                    and item.source_signal_id == candidate["source_signal_id"]
                ]
                if not events:
                    raise ValueError("terminal reclaim candidate not reproduced by actual adapter")
                payload["terminal_reclaim_observation"] = [
                    item.model_dump(mode="json") for item in events
                ]
                source_history = [
                    item
                    for item in signals.signal_history
                    if not item.code.endswith("ENTRY")
                    or item.signal_id == candidate["source_signal_id"]
                ]
                old_source = evaluate_signal_entry_opportunity(
                    source_history, prefix, params, features=features
                )
                if old_source.status.value != candidate["source_terminal_status"]:
                    raise ValueError("terminal source revived after reclaim")
                payload["original_source_opportunity"] = old_source.model_dump(mode="json")
            prefix_results.append(payload)
            lines.append(
                f"- {chart.ticker} {day_text}, 종가 {payload['close']}, [실제 adapter/renderer 출력]({filename})"
            )
        if kind == "ONE_DAY_SHAKEOUT_RECLAIM":
            old_tests, new_tests = [item["strategy"]["support_tests"] for item in prefix_results]
            if not any(
                old["anchor"]["anchor_id"] == new["anchor"]["anchor_id"]
                and old["status"] == "SOFT_BREACH"
                and old["below_count"] == 1
                and new["status"] == "RECLAIMED"
                and not new["failure_latched"]
                for old in old_tests
                for new in new_tests
            ):
                raise ValueError("one-day shakeout/reclaim not reproduced by actual adapter")
        if kind == "SMA150_TERMINATION_NEW_CYCLE":
            old_cycle, new_cycle = [item["strategy"]["up_cycle"] for item in prefix_results]
            if not (
                old_cycle["status"] == "TERMINATED"
                and new_cycle["status"] == "ACTIVE"
                and old_cycle["cycle_id"] != new_cycle["cycle_id"]
            ):
                raise ValueError("termination/new cycle not reproduced by actual adapter")
        manifest["case_results"][kind] = {
            "status": "REPRODUCED_ACTUAL_ADAPTER_RENDERER",
            **candidate,
        }
        _write_json(output / f"{kind.lower()}.json", {**candidate, "prefixes": prefix_results})
    lines.extend(
        [
            "",
            "ALAB/COHR는 이 protocol의 로컬 universe에 없습니다. 추가하려면 별도 범위로 두 종목과 SPY의 2014~2025 일봉 수집·상장일/결측 검증이 필요합니다. 이번 실행의 신규 요청 수는 0입니다.",
            "명시 profile 하나는 failure/restart 미선정 상태를 해소하지 않습니다. 운영 승격에는 별도 연구 protocol·표본·정책 결정이 필요합니다.",
        ]
    )
    (output / "cases.md").write_text("\n".join(lines) + "\n")
    manifest["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    manifest["artifacts"] = {
        path.name: _sha256(path) for path in sorted(output.iterdir()) if path.is_file()
    }
    _write_json(output / "cases-manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("baseline", "verify-baseline", "freeze", "calibrate", "compare", "cases"),
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verification", type=Path, action="append", default=[])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--protocol", type=Path, default=Path("research/trading_observation_v1/protocol.json")
    )
    args = parser.parse_args()
    with _offline_network():
        if args.command == "compare":
            if args.baseline is None:
                parser.error("compare requires --baseline")
            print(json.dumps(run_comparison(args.baseline, args.protocol, output=args.output)))
            return
        if args.command == "cases":
            print(json.dumps(run_cases(args.protocol, root=args.root, output=args.output)))
            return
        if args.command in {"freeze", "calibrate"}:
            from src.backtest.observation_calibration import (
                freeze_protocol,
                risk_set_inventory,
                run_calibration,
            )

            if args.command == "calibrate":
                print(json.dumps(run_calibration(args.protocol, output=args.output)))
                return
            protocol = json.loads(args.protocol.read_text())
            digest = freeze_protocol(
                protocol, cache_dir=args.root / protocol["cache_dir"], output=args.output
            )
            risk_set = risk_set_inventory(protocol, cache_dir=args.root / protocol["cache_dir"])
            _write_json(args.output / "risk-set-inventory.json", _json_value(risk_set))
            print(
                json.dumps(
                    {
                        "protocol_sha256": digest,
                        "candidate_count": 39,
                        "family_count": 10,
                        "restart_origins_in_period": risk_set["restart_origins_in_period"],
                        "labels_opened": False,
                    }
                )
            )
            return
        if args.command == "verify-baseline":
            print(json.dumps(_verify_products(args.output)))
            return
        hashes = capture_baseline(args.root, args.output)
        products = _capture_products(args.root, args.output)
        verified = _verify_products(args.output, verify_artifacts=False)
        for index, path in enumerate(args.verification):
            shutil.copyfile(path, args.output / f"verification-{index}-{path.name}")
        manifest_path = args.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest.update(
            {
                "products": products,
                "initial_v1_replay": verified,
                "network_policy": "socket connections rejected during capture/replay",
                "artifacts": {
                    path.relative_to(args.output).as_posix(): _sha256(path)
                    for path in sorted(args.output.rglob("*"))
                    if path.is_file()
                    and path != manifest_path
                    and path.relative_to(args.output).parts[0] != "sources"
                },
            }
        )
        _write_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "source_files": len(hashes),
                "output": str(args.output),
                "products": products,
                "initial_v1_replay": verified,
            }
        )
    )


if __name__ == "__main__":
    main()

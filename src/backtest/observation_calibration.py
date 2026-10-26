"""Frozen, local-only Observation calibration. Never imported by Strategy modules."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.storage.canonical import canonical_bytes
from src.strategies.models import BarFinality, ObservationSourceContext, SupportAnchor, UpCycleState
from src.strategies.observations.detectors import evaluate_observations
from src.strategies.observations.parameters import ObservationParameters
from src.strategies.swing_w150.features import build_swing_features
from src.strategies.swing_w150.parameters import (
    SupportCycleParameters,
    SwingW150Parameters,
    SwingW150ParametersV2,
)
from src.strategies.swing_w150.signals import detect_swing
from src.strategies.swing_w150.support_ladder import (
    advance_support_tests,
    anchor_value,
    cluster_supports,
    number,
)
from src.strategies.swing_w150.up_cycle import advance_up_cycle
from src.tools.technical.pivots import confirmed_pivot_events


ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = (
    "src/backtest/observation_calibration.py",
    "scripts/research_trading_observations.py",
    "uv.lock",
    "src/storage/canonical.py",
    "src/strategies/models.py",
    "src/strategies/entry_anchors.py",
    "src/strategies/observations/__init__.py",
    "src/strategies/observations/detectors.py",
    "src/strategies/observations/parameters.py",
    "src/strategies/observations/registry.py",
    "src/strategies/swing_w150/features.py",
    "src/strategies/swing_w150/parameters.py",
    "src/strategies/swing_w150/support_ladder.py",
    "src/strategies/swing_w150/up_cycle.py",
    "src/strategies/swing_w150/signals.py",
    "src/strategies/swing_w150/rules.py",
    "src/tools/technical/indicators.py",
    "src/tools/technical/pivots.py",
)


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n"
    )


def _read_frame(path):
    frame = pd.read_csv(path, index_col="Date", parse_dates=True).sort_index()
    if frame.empty or frame.index.has_duplicates:
        raise ValueError(f"nonempty unique sessions required: {path}")
    return frame


def freeze_protocol(protocol: dict, *, cache_dir: Path, output: Path) -> str:
    """Hash protocol, raw inputs/specs and executable sources before opening labels."""
    if (output / "freeze-manifest.json").exists():
        raise FileExistsError("frozen manifest exists; use a new output directory")
    candidates = [
        {"family": family["id"], "index": i, "value": value, "candidate_id": f"{family['id']}:{i}"}
        for family in protocol["families"]
        for i, value in enumerate(family["candidate_values"])
    ]
    if len(candidates) != 39 or len(protocol["families"]) != 10:
        raise ValueError("only the prespecified 39 candidates across10 families are allowed")
    from src.providers.exchange_calendar import exchange_sessions_for

    inventory = {}
    for ticker in [*protocol["universe"], protocol["market"]]:
        path = (cache_dir / f"{ticker}.csv").resolve()
        if not path.is_file():
            inventory[ticker] = {"path": str(path), "status": "MISSING"}
            continue
        frame = _read_frame(path)
        start, end = frame.index[0].date(), frame.index[-1].date()
        expected = {
            day
            for day in exchange_sessions_for("XNYS", start, end + timedelta(days=1))
            if day <= end
        }
        observed = set(frame.index.date)
        inventory[ticker] = {
            "path": str(path),
            "sha256": _hash(path),
            "status": "PRESENT",
            "start": str(start),
            "end": str(end),
            "bars": len(frame),
            "null_values": {key: int(value) for key, value in frame.isna().sum().items()},
            "missing_sessions": [str(day) for day in sorted(expected - observed)],
            "unexpected_sessions": [str(day) for day in sorted(observed - expected)],
        }
    digest = hashlib.sha256(canonical_bytes(protocol)).hexdigest()
    _write(output / "protocol.json", protocol)
    specification_snapshots = {}
    for index, path in enumerate(protocol["specifications"]):
        relative = f"authority-snapshots/{index}.md"
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(Path(path).read_bytes())
        specification_snapshots[path] = relative
    _write(
        output / "freeze-manifest.json",
        {
            "schema_version": "observation-freeze-v1",
            "protocol_sha256": digest,
            "candidate_count": len(candidates),
            "family_count": len(protocol["families"]),
            "candidates": candidates,
            "inventory": inventory,
            "specifications": {path: _hash(path) for path in protocol["specifications"]},
            "specification_snapshots": specification_snapshots,
            "executable_sources": {path: _hash(ROOT / path) for path in PROVENANCE},
            "provider_calls": 0,
            "llm_calls": 0,
            "labels_opened": False,
            "baseline_parameters": asdict(SwingW150Parameters()),
            "baseline_parameter_fingerprint": SwingW150Parameters().parameter_fingerprint,
        },
    )
    return digest


def future_outcome(frame: pd.DataFrame, origin: int, horizon: int) -> dict:
    """Origin+H close and intervening extremes, anchored at origin+1 open."""
    empty = {"return": None, "mfe": None, "mae": None, "future_winner": None}
    end = origin + horizon
    if end >= len(frame):
        return {**empty, "reason": "UNMATURED"}
    if frame.index[end].year != frame.index[origin].year:
        return {**empty, "reason": "FOLD_BOUNDARY"}
    window = frame.iloc[origin + 1 : end + 1]
    prices = window[["Open", "High", "Low", "Close"]].to_numpy(float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        return {**empty, "reason": "MISSING_PRICE"}
    anchor = float(window.iloc[0]["Open"])
    result = float(window.iloc[-1]["Close"]) / anchor - 1
    return {
        "return": result,
        "mfe": float(window["High"].max()) / anchor - 1,
        "mae": float(window["Low"].min()) / anchor - 1,
        "future_winner": result > 0,
        "reason": None,
    }


def verify_frozen_protocol(protocol, *, output):
    manifest = json.loads((output / "freeze-manifest.json").read_text())
    if hashlib.sha256(canonical_bytes(protocol)).hexdigest() != manifest["protocol_sha256"]:
        raise ValueError("protocol drift invalidates calibration")
    for relative, digest in manifest["executable_sources"].items():
        if _hash(ROOT / relative) != digest:
            raise ValueError(f"source drift invalidates calibration: {relative}")
    for path, digest in manifest["specifications"].items():
        if _hash(path) != digest:
            if path == "docs/worklog/trading-observation-v1.md":
                snapshot = output / manifest["specification_snapshots"][path]
                if _hash(snapshot) == digest and Path(path).read_bytes().startswith(
                    snapshot.read_bytes()
                ):
                    continue
            raise ValueError(f"specification drift: {path}")
    for ticker, item in manifest["inventory"].items():
        if item["status"] != "PRESENT" or _hash(item["path"]) != item["sha256"]:
            raise ValueError(f"input missing or drift: {ticker}")
    return manifest


def match_comparator(frame, origin, occurrence_indexes, regimes):
    """Prior20 risk set; an active episode is an occurrence on every active date."""
    regime = regimes.get(frame.index[origin])
    close, sma = (number(frame.iloc[origin], column) for column in ("Close", "SMA_150"))
    if regime is None or pd.isna(regime) or close is None or sma is None:
        return None
    above = close > sma
    for candidate in range(origin - 1, max(-1, origin - 21), -1):
        day = frame.index[candidate]
        candidate_close, candidate_sma = (
            number(frame.iloc[candidate], column) for column in ("Close", "SMA_150")
        )
        if (
            candidate not in occurrence_indexes
            and day.year == frame.index[origin].year
            and regimes.get(day) == regime
            and candidate_close is not None
            and candidate_sma is not None
            and (candidate_close > candidate_sma) == above
        ):
            return candidate
    return None


def ticker_bootstrap_ci(pairs):
    """Resample ticker clusters with replacement, retaining every row in each cluster."""
    clusters = defaultdict(list)
    for ticker, value in pairs:
        if value is not None and np.isfinite(value):
            clusters[ticker].append(value)
    if not clusters:
        return None
    arrays = [np.asarray(values, dtype=float) for _, values in sorted(clusters.items())]
    sums, counts = (
        np.array([values.sum() for values in arrays]),
        np.array([len(values) for values in arrays]),
    )
    draws = np.random.default_rng(21).integers(0, len(arrays), size=(2000, len(arrays)))
    means = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return tuple(float(value) for value in np.percentile(means, [2.5, 97.5]))


def _is_evaluation(day, protocol):
    return (
        protocol["periods"]["evaluation_start"] <= str(day) <= protocol["periods"]["evaluation_end"]
    )


def _regimes(frame):
    close, sma50, sma200 = frame["Close"], frame["SMA_50"], frame["SMA_200"]
    values = pd.Series("sideways", index=frame.index, dtype=object)
    values[(close > sma50) & (sma50 > sma200)] = "bull"
    values[(close < sma50) & (sma50 < sma200)] = "bear"
    values[sma50.isna() | sma200.isna() | close.isna()] = None
    return values


def _labels(frame, origin, protocol, detected):
    result = {}
    allowed = set(protocol["outcome"]["future_entry_codes"])
    for horizon in protocol["outcome"]["horizons"]:
        label = future_outcome(frame, origin, horizon)
        label["future_entry_count"] = (
            None
            if label["reason"]
            else sum(
                signal.code in allowed
                and frame.index[origin].date()
                < signal.occurred_on
                <= frame.index[origin + horizon].date()
                and signal.finality.value == "final"
                for signal in detected.signal_history
            )
        )
        result[str(horizon)] = label
    return result


def _target_observations(ticker, features, detected, contexts, params, family):
    """Skip source replay only where the selected observations never consume it."""
    episodes = evaluate_observations(
        ticker,
        features,
        detected.signal_history,
        [],
        source_contexts=contexts if family == "SUPPORT_BREAK_RECLAIM" else [],
        params=params,
    )
    wanted = {family}
    if family == "SUPPORT_BREAK_RECLAIM":
        wanted = {
            "SUPPORT_BREAK",
            "BREAKOUT_LEVEL_BREACH",
            "PULLBACK_LOW_BREACH",
            "SUPPORT_RECLAIM",
            "BREAKOUT_RECLAIM",
        }
    if family == "STRUCTURE":
        wanted = {"HIGHER_HIGH", "HIGHER_LOW", "LOWER_HIGH", "LOWER_LOW"}
    return [episode for episode in episodes if episode.code in wanted]


def _observation_rows(ticker, features, detected, contexts, params, candidate, protocol, regimes):
    frame = features.frame
    episodes = _target_observations(
        ticker, features, detected, contexts, params, candidate["family"]
    )
    occupied = defaultdict(set)
    for episode in episodes:
        start = frame.index.get_loc(pd.Timestamp(episode.started_on))
        end = (
            frame.index.get_loc(pd.Timestamp(episode.ended_on)) if episode.ended_on else len(frame)
        )
        occupied[episode.code].update(
            range(start, end) if episode.temporal_type.value == "EPISODE" else [start]
        )
    rows = []
    for episode in episodes:
        if not _is_evaluation(episode.started_on, protocol):
            continue
        origin = frame.index.get_loc(pd.Timestamp(episode.started_on))
        comparator = match_comparator(frame, origin, occupied[episode.code], regimes)
        outcome = _labels(frame, origin, protocol, detected)
        comparison = (
            _labels(frame, comparator, protocol, detected) if comparator is not None else None
        )
        paired = {
            key: outcome[key]["return"] - comparison[key]["return"]
            if comparison
            and outcome[key]["return"] is not None
            and comparison[key]["return"] is not None
            else None
            for key in outcome
        }
        rows.append(
            {
                **candidate,
                "ticker": ticker,
                "origin": str(episode.started_on),
                "fold": episode.started_on.year,
                "code": episode.code.value,
                "direction": episode.direction.value,
                "temporal_type": episode.temporal_type.value,
                "observation": episode.model_dump(mode="json"),
                "origin_index": origin,
                "anchor_class": "dynamic"
                if episode.anchor_type in {"SMA50", "SMA150", "SUPERTREND"}
                else "frozen"
                if episode.anchor_id
                else None,
                "comparator_index": comparator,
                "comparator": str(frame.index[comparator].date())
                if comparator is not None
                else None,
                "comparator_status": "MATCHED" if comparator is not None else "UNMATCHED",
                "outcome": outcome,
                "comparator_outcome": comparison,
                "paired_return": paired,
                "signed_primary": paired["20"] * (-1 if episode.direction.value == "RISK" else 1)
                if paired["20"] is not None
                else None,
            }
        )
    return rows


def evaluate_support_candidate(frame, origin, params):
    """Fixed-origin20-bar support cohort row, including every unconfirmed test."""
    index = origin["origin_index"]
    anchor = SupportAnchor.model_validate(origin["anchor"])
    states = []
    breach = confirmation = None
    last = min(index + 20, len(frame) - 1)
    for current in range(index, last + 1):
        if frame.index[current].year != frame.index[index].year:
            break
        row, day = frame.iloc[current], frame.index[current].date()
        level = anchor_value(anchor, row)
        if (
            level is not None
            and number(row, "Close") is not None
            and number(row, "ATR") is not None
            and row["Close"] < float(level) - params.support_break_buffer_atr * row["ATR"]
        ):
            breach = current if breach is None else breach
        states = advance_support_tests(
            states,
            row,
            new_anchors=[anchor] if current == index else [],
            day=day,
            finality=BarFinality.FINAL,
            params=params,
        )
        if any(state.status == "FAILED" and state.ended_on == day for state in states):
            confirmation = current
            break
    whipsaw = None
    reason = "UNCONFIRMED" if confirmation is None else None
    if confirmation is not None:
        mature = future_outcome(frame, confirmation, 5)
        if mature["reason"]:
            reason = mature["reason"]
        else:
            levels = [
                anchor_value(anchor, frame.iloc[current])
                for current in range(confirmation + 1, confirmation + 6)
            ]
            if all(level is not None for level in levels):
                whipsaw = any(
                    frame.iloc[confirmation + 1 + j]["Close"] > float(level)
                    for j, level in enumerate(levels)
                )
            else:
                reason = "MISSING_ANCHOR"
    return {
        "confirmation_index": confirmation,
        "confirmed_on": str(frame.index[confirmation].date()) if confirmation is not None else None,
        "first_breach_index": breach,
        "delay": confirmation - breach if confirmation is not None and breach is not None else None,
        "whipsaw": whipsaw,
        "followup_reason": reason,
        "fixed_origin_outcome": future_outcome(frame, index, 20),
        "confirmation_outcome": future_outcome(frame, confirmation, 20)
        if confirmation is not None
        else None,
    }


def evaluate_restart_candidate(ticker, features, detected, terminated, mode):
    """Every candidate starts from exactly the same terminated reference cycle."""
    frame = features.frame
    origin = frame.index.get_loc(pd.Timestamp(terminated.terminated_on))
    state = terminated
    params = SwingW150ParametersV2(
        support_cycle=SupportCycleParameters(
            normal_failure_closes=2, support_break_buffer_atr=0, restart_mode=mode
        )
    )
    pivots = defaultdict(list)
    for pivot in confirmed_pivot_events(
        frame["High"].to_numpy(float), frame["Low"].to_numpy(float)
    ):
        pivots[pivot.confirmed_index].append(pivot)
    restart = None
    hh_capture = False
    for current in range(origin + 1, min(origin + 21, len(frame))):
        if frame.index[current].year != frame.index[origin].year:
            break
        day = frame.index[current].date()
        state = advance_up_cycle(
            state,
            frame.iloc[current],
            ticker=ticker,
            day=day,
            finality=BarFinality.FINAL,
            confirmed_pivots=pivots[current],
            independent_entries=[
                signal for signal in detected.signal_history if signal.occurred_on == day
            ],
            sma150_failed=False,
            params=params,
        )
        if state.status == "ACTIVE" and restart is None:
            restart = current
        if restart is not None and any(
            pivot.relation == "HIGHER_HIGH" for pivot in pivots[current]
        ):
            hh_capture = True
    whipsaw = None
    reason = "UNCONFIRMED" if restart is None else future_outcome(frame, restart, 5)["reason"]
    if restart is not None and reason is None:
        below = 0
        whipsaw = False
        for current in range(restart + 1, restart + 6):
            row = frame.iloc[current]
            if number(row, "SMA_150") is None:
                whipsaw, reason = None, "MISSING_ANCHOR"
                break
            below = below + 1 if row["Close"] < row["SMA_150"] else 0
            whipsaw = whipsaw or below >= 2
    mature20 = future_outcome(frame, origin, 20)
    return {
        "confirmation_index": restart,
        "confirmed_on": str(frame.index[restart].date()) if restart is not None else None,
        "delay": restart - origin if restart is not None else None,
        "whipsaw": whipsaw,
        "followup_reason": reason,
        "new_hh_captured": hh_capture if mature20["reason"] is None else None,
        "fixed_origin_outcome": mature20,
        "confirmation_outcome": future_outcome(frame, restart, 20) if restart is not None else None,
    }


def _mean(values):
    valid = [value for value in values if value is not None]
    return float(np.mean(valid)) if valid else None


def _observation_summary(rows, protocol):
    development = set(protocol["periods"]["development_years"])
    validation = set(protocol["periods"]["validation_years"])
    mature = [
        row for row in rows if row["fold"] in validation and row["signed_primary"] is not None
    ]
    folds = {
        year: _mean([row["signed_primary"] for row in mature if row["fold"] == year])
        for year in sorted(validation)
    }
    ci = ticker_bootstrap_ci([(row["ticker"], row["signed_primary"]) for row in mature])
    sufficient = (
        len(mature) >= 50
        and len({row["ticker"] for row in mature}) >= 10
        and sum(value is not None for value in folds.values()) >= 3
    )
    utility = (
        "INSUFFICIENT"
        if not sufficient
        else "SUPPORTED"
        if ci
        and ci[0] > 0
        and sum(value is not None and value > 0 for value in folds.values()) >= 3
        else "UNRESOLVED"
    )
    matched = Counter((row["ticker"], row["comparator"]) for row in rows if row["comparator"])
    overlap = 0
    last = {}
    for row in sorted(rows, key=lambda item: (item["ticker"], item["origin_index"])):
        prior = last.get(row["ticker"])
        overlap += prior is not None and row["origin_index"] - prior <= 20
        last[row["ticker"]] = row["origin_index"]
    return {
        "count": len(rows),
        "development_count": sum(row["fold"] in development for row in rows),
        "validation_mature_paired20": len(mature),
        "validation_tickers": len({row["ticker"] for row in mature}),
        "validation_signed_mean20": _mean([row["signed_primary"] for row in mature]),
        "validation_signed_ci20": ci,
        "validation_fold_signed_mean20": folds,
        "predictive_status": utility,
        "unmatched": sum(row["comparator"] is None for row in rows),
        "comparator_reuse_rows": sum(count - 1 for count in matched.values()),
        "overlap20_rows": int(overlap),
        "horizons": {
            str(horizon): {
                "mature": sum(row["outcome"][str(horizon)]["return"] is not None for row in rows),
                "unmatured": sum(row["outcome"][str(horizon)]["return"] is None for row in rows),
                "mean_return": _mean([row["outcome"][str(horizon)]["return"] for row in rows]),
                "mean_mfe": _mean([row["outcome"][str(horizon)]["mfe"] for row in rows]),
                "mean_mae": _mean([row["outcome"][str(horizon)]["mae"] for row in rows]),
                "mean_future_entry_count": _mean(
                    [row["outcome"][str(horizon)]["future_entry_count"] for row in rows]
                ),
                "mean_paired_return": _mean([row["paired_return"][str(horizon)] for row in rows]),
            }
            for horizon in protocol["outcome"]["horizons"]
        },
    }


def select_detector_default(family, summaries, centers):
    """Development count plateau only; never inspect validation returns here."""
    name = family["id"]
    result = {
        "status": "UNRESOLVED",
        "value": None,
        "predictive_status_affects_selection": False,
        "reason": "NO_DEVELOPMENT_PLATEAU",
        "semantic_review": "REQUIRED_BEFORE_PRODUCT_WIRING",
    }
    if family["selection"] == "fixed_formula_semantics":
        return {
            **result,
            "status": "PROVISIONAL",
            "value": "FIXED",
            "reason": "FIXED_FORMULA_BOUNDARY_PREFIX_SEMANTICS",
        }
    centers_by_family = {
        "UP_VOLUME_EXPANSION": centers.get("up_volume_ratio"),
        "DOWN_VOLUME_EXPANSION": centers.get("down_volume_ratio"),
        "VOLUME_CONTRACTION": centers.get("contraction_ratio"),
        "SUPPORT_BREAK_RECLAIM": [0, 0],
        "MOMENTUM_REACCELERATION": "SMA20_TURN",
    }
    center = centers_by_family[name]
    counts = [summary["development_count"] for summary in summaries]
    values = family["candidate_values"]

    def adjacent(a, b):
        if isinstance(a, list):
            differences = [
                i for i, (left, right) in enumerate(zip(a, b, strict=True)) if left != right
            ]
            if len(differences) != 1:
                return False
            dimension = differences[0]
            ordered = sorted({value[dimension] for value in values})
            return abs(ordered.index(a[dimension]) - ordered.index(b[dimension])) == 1
        return abs(values.index(a) - values.index(b)) == 1

    eligible = [
        i
        for i, count in enumerate(counts)
        if count > 0
        and any(
            i != j
            and adjacent(values[i], values[j])
            and abs(count - counts[j]) / max(count, counts[j]) <= 0.2
            for j in range(len(values))
        )
    ]
    if not eligible:
        return result

    def distance(index):
        value = values[index]
        if isinstance(value, list):
            return (sum(abs(a - b) for a, b in zip(value, center, strict=True)), value)
        if isinstance(value, str):
            return (abs(values.index(value) - values.index(center)), values.index(value))
        return (abs(value - center), value)

    choice = min(eligible, key=distance)
    return {
        **result,
        "status": "PROVISIONAL",
        "value": values[choice],
        "reason": "DEVELOPMENT_FREQUENCY_PLATEAU_NEAREST_CENTER",
    }


def _cohort_summary(rows, protocol):
    by_fold = {}
    for year in protocol["periods"]["development_years"] + protocol["periods"]["validation_years"]:
        subset = [row for row in rows if row["fold"] == year]
        by_fold[str(year)] = {
            "origins": len(subset),
            "confirmed": sum(row["confirmed_on"] is not None for row in subset),
            "mature5": sum(row["whipsaw"] is not None for row in subset),
            "whipsaw_rate": _mean([row["whipsaw"] for row in subset]),
            "mean_delay": _mean([row["delay"] for row in subset]),
        }
    return {
        "count": len(rows),
        "confirmed": sum(row["confirmed_on"] is not None for row in rows),
        "unconfirmed": sum(row["confirmed_on"] is None for row in rows),
        "unmatured5": sum(row["whipsaw"] is None for row in rows),
        "folds": by_fold,
        "whipsaw_rate": _mean([row["whipsaw"] for row in rows]),
        "mean_delay": _mean([row["delay"] for row in rows]),
        "mean_fixed_origin_return20": _mean(
            [row["fixed_origin_outcome"]["return"] for row in rows]
        ),
        "predictive_status": "INSUFFICIENT"
        if len([row for row in rows if row["whipsaw"] is not None]) < 50
        or len({row["ticker"] for row in rows if row["whipsaw"] is not None}) < 10
        or len({row["fold"] for row in rows if row["whipsaw"] is not None}) < 3
        else "UNRESOLVED",
    }


def _cohort_selection(family, all_rows, center_rows, protocol):
    """Same-origin whipsaw and delay Pareto comparison; no forced selection."""
    if family["id"] == "RESTART":
        return {
            "status": "UNRESOLVED",
            "value": None,
            "reason": "STRUCTURAL_MAX20_BELOW_MIN50",
            "predictive_status": "INSUFFICIENT",
        }
    centers = {
        (row["ticker"], row["origin"], row["anchor"]["anchor_id"]): row for row in center_rows
    }
    comparisons = []
    for value, rows in all_rows:
        pairs = []
        for row in rows:
            key = (row["ticker"], row["origin"], row["anchor"]["anchor_id"])
            center = centers.get(key)
            if (
                center
                and row["whipsaw"] is not None
                and center["whipsaw"] is not None
                and row["delay"] is not None
                and center["delay"] is not None
            ):
                pairs.append(
                    {
                        "ticker": row["ticker"],
                        "fold": row["fold"],
                        "whipsaw": int(row["whipsaw"]) - int(center["whipsaw"]),
                        "delay": row["delay"] - center["delay"],
                    }
                )
        development = [
            pair for pair in pairs if pair["fold"] in protocol["periods"]["development_years"]
        ]
        ci = {
            metric: ticker_bootstrap_ci([(pair["ticker"], pair[metric]) for pair in development])
            for metric in ("whipsaw", "delay")
        }
        means = {metric: _mean([pair[metric] for pair in development]) for metric in ci}
        sufficient = (
            len(development) >= 50
            and len({pair["ticker"] for pair in development}) >= 10
            and len({pair["fold"] for pair in development}) >= 3
        )
        pareto = (
            sufficient
            and all(value is not None and value <= 0 for value in means.values())
            and any(interval and interval[1] < 0 for interval in ci.values())
        )
        validation_nonworse = sum(
            all(
                (
                    _mean([pair[metric] for pair in pairs if pair["fold"] == year]) is not None
                    and _mean([pair[metric] for pair in pairs if pair["fold"] == year]) <= 0
                )
                for metric in ci
            )
            for year in protocol["periods"]["validation_years"]
        )
        comparisons.append(
            {
                "value": value,
                "paired_development": len(development),
                "paired_ci": ci,
                "paired_mean": means,
                "development_pareto": pareto,
                "validation_nonworse_folds": validation_nonworse,
                "eligible": pareto and validation_nonworse >= 3,
            }
        )
    eligible = [item for item in comparisons if item["eligible"]]
    return {
        "status": "PROVISIONAL" if len(eligible) == 1 else "UNRESOLVED",
        "value": eligible[0]["value"] if len(eligible) == 1 else None,
        "reason": "SAME_ORIGIN_PARETO_CI_VALIDATION"
        if len(eligible) == 1
        else "INSUFFICIENT_OR_TRADEOFF_OR_CI_OR_VALIDATION",
        "comparisons": comparisons,
    }


def run_calibration(protocol_path: Path, *, output: Path) -> dict:
    """Execute exactly39 prespecified candidates on frozen local CSVs."""
    protocol = json.loads(protocol_path.read_text())
    manifest = verify_frozen_protocol(protocol, output=output)
    if (output / "result-manifest.json").exists():
        raise FileExistsError("results already exist; never overwrite a frozen run")
    candidates = manifest["candidates"]
    families = {family["id"]: family for family in protocol["families"]}
    spy = build_swing_features(
        _read_frame(manifest["inventory"][protocol["market"]]["path"]), SwingW150Parameters()
    ).frame
    regimes = _regimes(spy)
    observation_rows, cohort_rows, zone_rows = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    center_rows = []
    started = time.perf_counter()
    for ticker_index, ticker in enumerate(protocol["universe"], 1):
        ticker_started = time.perf_counter()
        print(
            f"calibrate START {ticker_index}/{len(protocol['universe'])} {ticker} "
            f"elapsed={ticker_started - started:.1f}s",
            file=sys.stderr,
            flush=True,
        )
        raw, features, detected, contexts = _prepare(
            Path(manifest["inventory"][ticker]["path"]), ticker, protocol
        )
        frame = features.frame
        risk = first_cycle_risk_set(ticker, features, detected, contexts)
        for candidate in candidates:
            family, value = candidate["family"], candidate["value"]
            if family in {"NORMAL_FAILURE", "IMMEDIATE_FAILURE"}:
                for origin in risk["origins"]:
                    if not _is_evaluation(origin["origin"], protocol):
                        continue
                    params = SupportCycleParameters(
                        normal_failure_closes=value if family == "NORMAL_FAILURE" else 2,
                        support_break_buffer_atr=0,
                        immediate_failure_volume_ratio=value[0]
                        if family == "IMMEDIATE_FAILURE"
                        else None,
                        immediate_failure_close_location=value[1]
                        if family == "IMMEDIATE_FAILURE"
                        else None,
                    )
                    row = {
                        **candidate,
                        **origin,
                        "fold": pd.Timestamp(origin["origin"]).year,
                        **evaluate_support_candidate(frame, origin, params),
                    }
                    cohort_rows[candidate["candidate_id"]].append(row)
                    if family == "NORMAL_FAILURE" and value == 2:
                        center_rows.append(row)
                continue
            if family == "RESTART":
                cycle = risk["cycle"]
                if cycle.terminated_on is not None and _is_evaluation(
                    cycle.terminated_on, protocol
                ):
                    cohort_rows[candidate["candidate_id"]].append(
                        {
                            **candidate,
                            "ticker": ticker,
                            "origin": str(cycle.terminated_on),
                            "fold": cycle.terminated_on.year,
                            **evaluate_restart_candidate(ticker, features, detected, cycle, value),
                        }
                    )
                continue
            if family == "ZONE":
                previous_pairs = None
                previous_ids = set()
                for index, states in risk["zones"]:
                    if not _is_evaluation(frame.index[index].date(), protocol):
                        continue
                    atr = number(frame.iloc[index], "ATR")
                    if atr is None or atr <= 0:
                        continue
                    clusters = cluster_supports(states, atr=atr, distance_atr=value)
                    ids = {anchor.anchor_id for cluster in clusters for anchor in cluster}
                    merged = {
                        tuple(sorted((a.anchor_id, b.anchor_id)))
                        for cluster in clusters
                        for i, a in enumerate(cluster)
                        for b in cluster[i + 1 :]
                    }
                    common = ids & previous_ids
                    eligible_pairs = {
                        pair for pair in (previous_pairs or set()) if set(pair) <= common
                    }
                    retention = (
                        len(eligible_pairs & merged) / len(eligible_pairs)
                        if eligible_pairs
                        else None
                    )
                    widths = [
                        float(cluster[-1].current_value - cluster[0].current_value) / atr
                        for cluster in clusters
                    ]
                    zone_rows[candidate["candidate_id"]].append(
                        {
                            **candidate,
                            "ticker": ticker,
                            "origin": str(frame.index[index].date()),
                            "fold": frame.index[index].year,
                            "cluster_count": len(clusters),
                            "maximum_width_atr": max(widths, default=0),
                            "merged_pair_retention": retention,
                            "individual_decisions_invariant": True,
                            "anchors": [
                                anchor.model_dump(mode="json")
                                for cluster in clusters
                                for anchor in cluster
                            ],
                        }
                    )
                    previous_pairs, previous_ids = merged, ids
                continue
            params = ObservationParameters(
                up_volume_ratio=1.5,
                down_volume_ratio=1.5,
                contraction_ratio=0.7,
                break_buffer_atr=0,
                reclaim_buffer_atr=0,
                reacceleration_mode="SMA20_TURN",
                zone_distance_atr=0.5,
            )
            if family == "SUPPORT_BREAK_RECLAIM":
                params = replace(params, break_buffer_atr=value[0], reclaim_buffer_atr=value[1])
            elif family != "MOMENTUM_DECELERATION":
                params = replace(params, **{families[family]["parameter"]: value})
            observation_rows[candidate["candidate_id"]].extend(
                _observation_rows(
                    ticker, features, detected, contexts, params, candidate, protocol, regimes
                )
            )
        fixed = {"family": "STRUCTURE", "candidate_id": "STRUCTURE:FIXED", "value": "FIXED"}
        observation_rows[fixed["candidate_id"]].extend(
            _observation_rows(
                ticker,
                features,
                detected,
                contexts,
                ObservationParameters(),
                fixed,
                protocol,
                regimes,
            )
        )
        print(
            f"calibrate DONE {ticker_index}/{len(protocol['universe'])} {ticker} "
            f"ticker_elapsed={time.perf_counter() - ticker_started:.1f}s "
            f"elapsed={time.perf_counter() - started:.1f}s",
            file=sys.stderr,
            flush=True,
        )
    summaries, selections, cases = {}, {}, {}
    for family in protocol["families"]:
        family_candidates = [
            candidate for candidate in candidates if candidate["family"] == family["id"]
        ]
        family_summaries = []
        for candidate in family_candidates:
            identity = candidate["candidate_id"]
            rows = observation_rows[identity] or cohort_rows[identity] or zone_rows[identity]
            if family["id"] == "ZONE":
                development = [
                    row for row in rows if row["fold"] in protocol["periods"]["development_years"]
                ]
                summary = {
                    "count": len(rows),
                    "development_count": len(development),
                    "predictive_status": "NOT_APPLICABLE",
                    "median_cluster_count": float(
                        np.median([row["cluster_count"] for row in development])
                    )
                    if development
                    else None,
                    "maximum_width_atr": max(
                        (row["maximum_width_atr"] for row in rows), default=None
                    ),
                    "mean_merge_retention": _mean([row["merged_pair_retention"] for row in rows]),
                    "individual_decisions_invariant": True,
                }
            elif family["id"] in {"NORMAL_FAILURE", "IMMEDIATE_FAILURE", "RESTART"}:
                summary = _cohort_summary(rows, protocol)
            else:
                summary = _observation_summary(rows, protocol)
                if family["id"] == "SUPPORT_BREAK_RECLAIM":
                    summary["by_code_anchor_class"] = {
                        f"{code}:{kind}": _observation_summary(
                            [
                                row
                                for row in rows
                                if row["code"] == code and row["anchor_class"] == kind
                            ],
                            protocol,
                        )
                        for code, kind in sorted(
                            {(row["code"], row["anchor_class"]) for row in rows}
                        )
                    }
            summary = {**candidate, **summary}
            summaries[identity] = summary
            family_summaries.append(summary)
            indexes = (
                sorted({round((len(rows) - 1) * fraction) for fraction in [0, 0.25, 0.5, 0.75, 1]})
                if rows
                else []
            )
            ordered = sorted(rows, key=lambda row: (row["origin"], row["ticker"]))
            cases[identity] = [ordered[index] for index in indexes]
        if family["id"] in {"NORMAL_FAILURE", "IMMEDIATE_FAILURE", "RESTART"}:
            selections[family["id"]] = _cohort_selection(
                family,
                [
                    (candidate["value"], cohort_rows[candidate["candidate_id"]])
                    for candidate in family_candidates
                ],
                center_rows,
                protocol,
            )
        elif family["id"] == "ZONE":
            eligible = [
                i
                for i, summary in enumerate(family_summaries)
                if summary["median_cluster_count"] is not None
                and all(
                    row["maximum_width_atr"] <= summary["value"] + 1e-12
                    for row in zone_rows[summary["candidate_id"]]
                )
                and any(
                    abs(i - j) == 1
                    and other["median_cluster_count"] is not None
                    and abs(summary["median_cluster_count"] - other["median_cluster_count"])
                    / max(1, summary["median_cluster_count"], other["median_cluster_count"])
                    <= 0.1
                    for j, other in enumerate(family_summaries)
                )
            ]
            choice = (
                min(
                    eligible,
                    key=lambda i: (
                        abs(family_summaries[i]["value"] - 0.5),
                        family_summaries[i]["value"],
                    ),
                )
                if eligible
                else None
            )
            selections[family["id"]] = {
                "status": "PROVISIONAL" if choice is not None else "UNRESOLVED",
                "value": family_summaries[choice]["value"] if choice is not None else None,
                "reason": "DEVELOPMENT_CLUSTER_PLATEAU"
                if choice is not None
                else "NO_DEVELOPMENT_CLUSTER_PLATEAU",
                "predictive_status": "NOT_APPLICABLE",
            }
        else:
            selections[family["id"]] = select_detector_default(
                family, family_summaries, protocol["centers"]
            )
    fixed_rows = observation_rows["STRUCTURE:FIXED"]
    summaries["STRUCTURE:FIXED"] = {
        code: _observation_summary([row for row in fixed_rows if row["code"] == code], protocol)
        for code in ["HIGHER_HIGH", "HIGHER_LOW", "LOWER_HIGH", "LOWER_LOW"]
    }
    for name, mapping in [
        ("observations", observation_rows),
        ("cohorts", cohort_rows),
        ("zones", zone_rows),
    ]:
        with (output / f"{name}.jsonl").open("w") as handle:
            for rows in mapping.values():
                for row in rows:
                    handle.write(
                        json.dumps(row, ensure_ascii=False, allow_nan=False, default=str) + "\n"
                    )
    _write(output / "summaries.json", summaries)
    _write(output / "selection.json", selections)
    _write(output / "semantic-cases.json", cases)
    verify_frozen_protocol(protocol, output=output)
    result = {
        "protocol_sha256": manifest["protocol_sha256"],
        "freeze_manifest_sha256": _hash(output / "freeze-manifest.json"),
        "candidate_count": 39,
        "provider_calls": 0,
        "llm_calls": 0,
        "production_default": "V1",
        "artifacts": {
            path.name: _hash(path)
            for path in sorted(output.iterdir())
            if path.is_file() and path.name != "result-manifest.json"
        },
    }
    _write(output / "result-manifest.json", result)
    return result


def _source_contexts(ticker, raw, features, detected):
    from src.strategies.chart_bundle import chart_series_from_dataframe
    from src.strategies.entry_anchors import build_entry_source_anchors
    from src.strategies.models import ChartBundle, CoverageManifest

    first, last = raw.index[0].date(), raw.index[-1].date()
    coverage = CoverageManifest(
        requested_start=first,
        actual_start=first,
        actual_end=last,
        expected_sessions=tuple(raw.index.date),
        complete=True,
    )
    bundle = ChartBundle(
        profile_version="offline-observation-research-v1",
        ticker=ticker,
        as_of=last,
        instrument=chart_series_from_dataframe(raw, coverage),
        exchange_sessions=tuple(raw.index.date),
    )
    return [
        ObservationSourceContext(
            signal=signal,
            anchors=build_entry_source_anchors(
                signal, bundle, features, detected.observation_history
            ),
        )
        for signal in detected.signal_history
        if signal.code
        in {
            "TREND_BREAKOUT_ENTRY",
            "DEEP_RECOVERY_ENTRY",
            "PULLBACK_REVERSAL_ENTRY",
            "POST_OVERHEAT_RECOVERY_ENTRY",
        }
    ]


def _prepare(path, ticker, protocol):
    raw = _read_frame(path).loc[
        protocol["periods"]["warmup_start"] : protocol["periods"]["evaluation_end"]
    ]
    features = build_swing_features(raw, SwingW150Parameters())
    detected = detect_swing(ticker, features, SwingW150Parameters())
    contexts = _source_contexts(ticker, raw, features, detected)
    return raw, features, detected, contexts


def _anchors(ticker, cycle, day, row, contexts):
    from decimal import Decimal

    anchors = []
    for kind, column in [
        ("SUPERTREND", "SuperTrend_Up"),
        ("SMA50", "SMA_50"),
        ("SMA150", "SMA_150"),
    ]:
        level = number(row, column)
        if level is not None and (kind != "SUPERTREND" or number(row, "SuperTrend_Dir") == 1):
            anchors.append(
                SupportAnchor(
                    anchor_id=f"{ticker}:{cycle.cycle_id}:{kind}",
                    anchor_type=kind,
                    is_dynamic=True,
                    origin_on=day,
                    origin_price=Decimal(str(level)),
                    current_value=Decimal(str(level)),
                    cycle_id=cycle.cycle_id,
                )
            )
    for context in contexts:
        if context.signal.occurred_on <= day and context.anchors.breakout_level is not None:
            anchors.append(
                SupportAnchor(
                    anchor_id=f"{cycle.cycle_id}:{context.signal.signal_id}",
                    anchor_type="PRIOR_BREAKOUT_LEVEL",
                    is_dynamic=False,
                    origin_on=context.signal.occurred_on,
                    origin_price=context.anchors.breakout_level,
                    current_value=context.anchors.breakout_level,
                    source_signal_id=context.signal.signal_id,
                    cycle_id=cycle.cycle_id,
                )
            )
    return anchors


def first_cycle_risk_set(ticker, features, detected, contexts):
    """Build fixed origins with reference normal2, immediate OFF, restart None; no labels."""
    frame = features.frame
    params = SwingW150ParametersV2(
        support_cycle=SupportCycleParameters(normal_failure_closes=2, support_break_buffer_atr=0)
    )
    cycle = UpCycleState(finality=BarFinality.FINAL)
    states, origins, zones = [], [], []
    tests = {}
    waiting_retouch = set()
    pivot_map = defaultdict(list)
    for pivot in confirmed_pivot_events(
        frame["High"].to_numpy(float), frame["Low"].to_numpy(float)
    ):
        pivot_map[pivot.confirmed_index].append(pivot)
    signals = defaultdict(list)
    for signal in detected.signal_history:
        signals[signal.occurred_on].append(signal)
    for index, (stamp, row) in enumerate(frame.iterrows()):
        day = stamp.date()
        if index + 1 < params.minimum_history_bars:
            continue
        cycle = advance_up_cycle(
            cycle,
            row,
            ticker=ticker,
            day=day,
            finality=BarFinality.FINAL,
            confirmed_pivots=pivot_map[index],
            independent_entries=signals[day],
            sma150_failed=False,
            params=params,
        )
        if cycle.status != "ACTIVE":
            continue
        states = advance_support_tests(
            states,
            row,
            new_anchors=_anchors(ticker, cycle, day, row, contexts),
            day=day,
            finality=BarFinality.FINAL,
            params=params.support_cycle,
        )
        # Only the latest nonfailed dynamic episode is eligible, frozen failure never revives.
        latest = {state.anchor.anchor_id: state for state in states}
        for identity, state in latest.items():
            level = state.anchor.current_value
            close, low, atr = (number(row, key) for key in ("Close", "Low", "ATR"))
            if level is None or close is None or low is None or atr is None or atr <= 0:
                continue
            if state.reclaimed_on == day:
                tests.pop(identity, None)
                waiting_retouch.add(identity)
                continue
            frozen_failed = state.failure_latched
            touched = abs(low - float(level)) <= 0.5 * atr
            breach = close < float(level)
            if identity not in tests and not frozen_failed and (touched or breach):
                tests[identity] = index
                waiting_retouch.discard(identity)
                origins.append(
                    {
                        "ticker": ticker,
                        "origin_index": index,
                        "origin": str(day),
                        "anchor": state.anchor.model_dump(mode="json"),
                        "origin_kind": "TOUCH" if touched else "GAP_BREACH",
                    }
                )
            # A first-day failure is still an origin when no earlier touch existed.
            elif identity not in tests and frozen_failed and state.ended_on == day:
                tests[identity] = index
                origins.append(
                    {
                        "ticker": ticker,
                        "origin_index": index,
                        "origin": str(day),
                        "anchor": state.anchor.model_dump(mode="json"),
                        "origin_kind": "GAP_BREACH",
                    }
                )
        zones.append((index, list(latest.values())))
        failed150 = any(
            state.anchor.anchor_type == "SMA150"
            and state.status == "FAILED"
            and state.ended_on == day
            for state in states
        )
        cycle = advance_up_cycle(
            cycle,
            row,
            ticker=ticker,
            day=day,
            finality=BarFinality.FINAL,
            confirmed_pivots=(),
            independent_entries=(),
            sma150_failed=failed150,
            params=params,
        )
        if cycle.status == "TERMINATED":
            break
    return {"origins": origins, "zones": zones, "cycle": cycle}


def risk_set_inventory(protocol: dict, *, cache_dir: Path) -> dict:
    """Feasibility only: no forward prices or outcome function is read."""
    inventory = {}
    started = time.perf_counter()
    for ticker_index, ticker in enumerate(protocol["universe"], 1):
        path = cache_dir / f"{ticker}.csv"
        if not path.is_file():
            inventory[ticker] = {"status": "MISSING"}
            continue
        _, features, detected, contexts = _prepare(path, ticker, protocol)
        risk = first_cycle_risk_set(ticker, features, detected, contexts)
        cycle = risk["cycle"]
        origins = [
            item
            for item in risk["origins"]
            if protocol["periods"]["evaluation_start"]
            <= item["origin"]
            <= protocol["periods"]["evaluation_end"]
        ]
        inventory[ticker] = {
            "status": "PRESENT",
            "cycle_started_on": cycle.started_on,
            "terminated_on": cycle.terminated_on,
            "support_test_origins_in_period": len(origins),
            "terminated_in_period": cycle.terminated_on is not None
            and protocol["periods"]["evaluation_start"]
            <= str(cycle.terminated_on)
            <= protocol["periods"]["evaluation_end"],
        }
        print(
            f"inventory DONE {ticker_index}/{len(protocol['universe'])} {ticker} "
            f"support_origins={len(origins)} elapsed={time.perf_counter() - started:.1f}s",
            file=sys.stderr,
            flush=True,
        )
    return {
        "labels_opened": False,
        "tickers": inventory,
        "restart_origins_in_period": sum(
            item.get("terminated_in_period", False) for item in inventory.values()
        ),
        "structural_maximum": len(protocol["universe"]),
        "minimum_required": 50,
    }

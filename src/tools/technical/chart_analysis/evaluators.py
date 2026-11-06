"""Request-local detector factory over shared strict and compatibility owners."""

from collections.abc import Mapping
from dataclasses import asdict
from importlib.metadata import version

import numpy as np
import pandas as pd

from src.storage.canonical import canonical_hash
from src.tools.technical.chart_analysis import features as feature_api
from src.tools.technical.chart_analysis._legacy_structure import (
    swing_feature_frame,
    swing_numerical_values,
    swing_s01_values,
    swing_signal_values,
)
from src.tools.technical.chart_analysis.detectors import (
    _combined_finality,
    _finality,
    evaluate_anchor,
    evaluate_pivots,
    evaluate_rs,
)
from src.tools.technical.chart_analysis.legacy_facts import (
    FRAME_FAMILIES,
    SUPPLIED_FRAME_FAMILIES,
    close_breakout_values,
    legacy_fact_provider_identity,
    legacy_fact_values_from_frame,
    market_regime_values,
    observation_numerical_values,
    prepare_legacy_frame,
)
from src.tools.technical.chart_analysis.models import ChartItem, FeatureValue, plain
from src.tools.technical.chart_analysis.pattern_parameters import (
    FAMILY_THRESHOLDS,
    validated_thresholds,
)
from src.tools.technical.chart_analysis.pivots import confirmed_pivot_events, confirmed_pivots
from src.tools.technical.chart_analysis.registry import RULE_REGISTRY
from src.tools.technical.chart_analysis.trigger_events import detect_trigger_events


_LEGACY = (feature_api.LEGACY_VERSION, feature_api.SUPPLIED_VERSION)
_STRICT_RULES = {
    "chart.low_break_volume",
    "chart.down_volume_weak_close",
    "chart.extension.sma20",
    "chart.rsi.wilder",
}
_OBSERVATIONS = {"OBSERVATION_V1", "chart.momentum.deceleration", "chart.momentum.reacceleration"}


def snapshot(value):
    """Convert numerical intermediates deliberately before ChartItem.freeze owns them."""
    if isinstance(value, pd.DataFrame):
        return tuple(
            {"on": stamp.date(), "values": snapshot(row.to_dict())}
            for stamp, row in value.iterrows()
        )
    if isinstance(value, (np.ndarray, pd.Series)):
        return tuple(snapshot(x) for x in value)
    if isinstance(value, Mapping):
        return {k: snapshot(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(snapshot(x) for x in value)
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return None if value is pd.NA or value is pd.NaT else value


def provider_identity(scope, request, anchors=()):
    """Only actual numerical dependencies, separate from input provenance."""
    rule = request.rule_id
    packages = {name: version(name) for name in ("pandas", "numpy")}
    if rule == "chart.features.strict":
        fv = scope.primary.manifest.feature_version
        return {"providers": {"instrument": feature_api.feature_provider_identity(fv)}}
    if (
        rule == "chart.close_breakout.strict"
        and request.parameters.get("frame_policy") != "SUPPLIED_AS_IS"
    ):
        identity = {
            "providers": {
                "instrument": {
                    "backend": "raw-ohlcv",
                    "input_feature_version": scope.primary.manifest.feature_version,
                }
            },
            "preparation": None,
            "calculation": {"backend": "pandas/rolling-high", "packages": packages},
        }
        if scope.primary.manifest.feature_version == feature_api.STRICT_VERSION:
            identity["prefix_provider"] = feature_api.feature_provider_identity(
                feature_api.STRICT_VERSION
            )
        return identity
    if rule in ("chart.rs", "chart.market.regime"):
        return {
            "providers": {
                role: {
                    "backend": "pandas/raw-close",
                    "input_feature_version": scope.series_for(role).manifest.feature_version,
                }
                for role in request.input_roles
            },
            "preparation": None,
            "calculation": {"backend": "pandas/raw-close", "packages": packages},
        }
    if rule == "chart.pivot.span3" or (
        rule == "OBSERVATION_V1"
        and request.parameters.get("code")
        in ("HIGHER_LOW", "HIGHER_HIGH", "LOWER_HIGH", "LOWER_LOW")
    ):
        return {"calculation": {"backend": "numpy/span3", "packages": {"numpy": version("numpy")}}}
    if rule == "chart.anchor.break_reclaim":

        def source_provider(series, column):
            fv = series.manifest.feature_version
            if column in ("Open", "High", "Low", "Close", "Volume"):
                return {"backend": "raw-column", "column": column, "input_feature_version": fv}
            if fv in (*_LEGACY, feature_api.STRICT_VERSION):
                return feature_api.feature_provider_identity(fv)
            return {"feature_version": fv, "backend": "supplied-columns"}

        providers = {"instrument:Close": source_provider(scope.primary, "Close")}
        for anchor in anchors:
            if hasattr(anchor, "feature_version"):
                role = anchor.input_role
                series = scope.series_for(role)
                if anchor.feature_version == "SMA_ROLLING_V1":
                    price = {
                        "feature_version": "SMA_ROLLING_V1",
                        "backend": "pandas/rolling",
                        "packages": packages,
                    }
                else:
                    price = source_provider(series, anchor.feature_key)
                providers[f"{role}:price"] = price
                if anchor.active_when == "SUPERTREND_UP":
                    providers[f"{role}:activation"] = source_provider(series, "SuperTrend_Dir")
        if any(request.parameters.get(k) for k in ("break_buffer_atr", "reclaim_buffer_atr")):
            providers["instrument:ATR"] = source_provider(scope.primary, "ATR")
        return {"providers": providers, "calculation": {"backend": "python/anchor-replay"}}
    fv = scope.primary.manifest.feature_version
    if request.parameters.get("frame_policy") in ("SUPPLIED_AS_IS", "SWING_FEATURES"):
        return {
            "providers": {"instrument": feature_api.feature_provider_identity(fv)},
            "preparation": None,
            "calculation": {"backend": "pandas/numpy-common-swing", "packages": packages},
            "parameters": plain(request.parameters),
        }
    if rule.startswith("analysis.") and request.parameters.get("frame_policy") == "SUPPLIED_AS_IS":
        return {
            "providers": {"instrument": feature_api.feature_provider_identity(fv)},
            "preparation": None,
            "calculation": {"backend": "numpy/pandas-common-shadow", "packages": packages},
            "frame_policy": "SUPPLIED_AS_IS",
        }
    if rule in FRAME_FAMILIES and fv in _LEGACY:
        return legacy_fact_provider_identity(scope, family=rule)
    if fv not in (*_LEGACY, feature_api.STRICT_VERSION):
        return {"unavailable": "PROFILE_UNSUPPORTED", "feature_version": fv}
    return {
        "providers": {"instrument": feature_api.feature_provider_identity(fv)},
        "preparation": {"backend": "pandas/rolling-shift", "packages": packages},
        "calculation": {"backend": "numpy/pandas-common-shadow", "packages": packages},
    }


def _validate(request):
    candidates = [r for r in RULE_REGISTRY if r.rule_id == request.rule_id]
    if not candidates:
        raise NotImplementedError(f"No chart evaluator for {request.rule_id}")
    first = candidates[0]
    if (
        request.rule_version != first.rule_version
        or (
            request.input_roles != first.input_roles
            and not (
                request.rule_id == "chart.anchor.break_reclaim"
                and "instrument" in request.input_roles
            )
        )
        or request.alignment_version != first.alignment_version
    ):
        raise ValueError(f"Unsupported {request.rule_id} contract")
    params = dict(request.parameters)
    if (
        request.rule_id == "chart.close_breakout.strict"
        and params.get("frame_policy") == "SUPPLIED_AS_IS"
    ):
        if (
            set(params)
            != {
                "frame_policy",
                "lookback",
                "reference_column",
                "direction_lookback",
                "volume_multiple",
                "comparison_profile",
            }
            or params["comparison_profile"] not in ("V1_REPLAY", "V2_SIGNAL")
            or params["reference_column"] not in ("High_50_Prev", "Trend_Breakout_High_Prev")
        ):
            raise ValueError("Unsupported Swing S01 parameters")
        if (
            any(
                type(params[k]) is not int or params[k] <= 0
                for k in ("lookback", "direction_lookback")
            )
            or not np.isfinite(params["volume_multiple"])
            or params["volume_multiple"] <= 0
        ):
            raise ValueError("Unsupported Swing S01 thresholds")
    elif request.rule_id == "legacy.indicators" and params.get("frame_policy") == "SWING_FEATURES":
        if set(params) != {
            "frame_policy",
            "direction_lookback",
            "trend_breakout_lookback",
            "deep_recovery_lookback",
        } or any(type(v) is not int or v <= 0 for k, v in params.items() if k != "frame_policy"):
            raise ValueError("Unsupported Swing feature parameters")
    elif (
        request.rule_id in ("chart.structure_breakdown.swing", "chart.deep_recovery.swing")
        and params.get("frame_policy") == "SUPPLIED_AS_IS"
    ):
        if set(params) != {
            "frame_policy",
            "volume_multiple",
            "weak_close_location",
            "direction_lookback",
            "trend_volume_multiple",
            "signal_profile",
        } or params["signal_profile"] not in ("V1_REPLAY", "V2_SIGNAL"):
            raise ValueError("Unsupported Swing numerical parameters")
        if (
            any(
                not np.isfinite(params[k]) or params[k] <= 0
                for k in ("volume_multiple", "trend_volume_multiple", "direction_lookback")
            )
            or not 0 <= params["weak_close_location"] <= 1
        ):
            raise ValueError("Unsupported Swing thresholds")
    elif request.rule_id == "OBSERVATION_V1":
        allowed = {"code", "threshold", "frame_policy"}
        if set(params) - allowed or params.get("code") not in {
            r.parameters["code"] for r in candidates
        }:
            raise ValueError("Unsupported observation parameters")
        if params.get("frame_policy") not in (None, "SUPPLIED_AS_IS"):
            raise ValueError("Unsupported observation frame policy")
        threshold = params.get("threshold")
        if threshold is not None and (not np.isfinite(threshold) or threshold <= 0):
            raise ValueError("Observation threshold must be positive or None")
    elif request.rule_id == "chart.anchor.break_reclaim":
        profile = params.get("replay_profile")
        allowed = {"break_buffer_atr", "reclaim_buffer_atr"} | (
            {"replay_profile"} if profile is not None else set()
        )
        if (
            profile not in (None, "LEGACY_OBSERVATION_V1", "ENTRY_SHADOW_V1")
            or set(params) != allowed
            or any(
                params[k] is None or not np.isfinite(params[k]) or params[k] < 0
                for k in ("break_buffer_atr", "reclaim_buffer_atr")
            )
        ):
            raise ValueError("Anchor buffers must be finite and nonnegative")
    elif request.rule_id in _OBSERVATIONS and params.get("frame_policy") == "SUPPLIED_AS_IS":
        base = {k: v for k, v in params.items() if k != "frame_policy"}
        if base not in [dict(r.parameters) for r in candidates]:
            raise ValueError("Unsupported observation parameters")
    elif request.rule_id.startswith("analysis."):
        allowed = {"display_bars", "frame_policy"} | (
            {"pattern_thresholds"} if request.rule_id in FAMILY_THRESHOLDS else set()
        )
        if "pattern_thresholds" in params:
            validated_thresholds(request.rule_id, params["pattern_thresholds"])
        if (
            set(params) - allowed
            or params.get("frame_policy", "PREPARED") not in ("PREPARED", "SUPPLIED_AS_IS")
            or (
                "display_bars" in params
                and (not isinstance(params["display_bars"], int) or params["display_bars"] < 0)
            )
        ):
            raise ValueError("Unsupported trigger parameters")
    elif request.rule_id in FAMILY_THRESHOLDS:
        if set(params) - {"pattern_thresholds"}:
            raise ValueError(f"Unsupported {request.rule_id} parameters")
        validated_thresholds(request.rule_id, params.get("pattern_thresholds"))
    elif params not in [dict(r.parameters) for r in candidates]:
        raise ValueError(f"Unsupported {request.rule_id} parameters")


class DetectorFactory:
    """One owner per AnalysisRequestContext; no global state or frame mutation."""

    def __init__(self):
        self._frames = {}
        self._strict = {}
        self._triggers = {}

    def frame(self, series):
        from src.tools.technical.chart_analysis.models import CalculationScope

        identity = legacy_fact_provider_identity(
            CalculationScope(series, {}), family="feature.window"
        )
        preparation = {
            "providers": {
                "instrument": feature_api.feature_provider_identity(series.manifest.feature_version)
            },
            "preparation": identity["preparation"],
        }
        key = canonical_hash("jarvis:prepared-frame:v1", plain((series.manifest, preparation)))
        if key not in self._frames:
            self._frames[key] = prepare_legacy_frame(series)
        return self._frames[key]

    def strict(self, scope):
        key = canonical_hash(
            "jarvis:strict-features:v1",
            plain(
                (
                    scope.primary.manifest,
                    feature_api.feature_provider_identity(feature_api.STRICT_VERSION),
                )
            ),
        )
        if key not in self._strict:
            self._strict[key] = feature_api.calculate_features(scope)
        return self._strict[key]

    def __call__(self, scope, request, anchors, key):
        _validate(request)
        identity = provider_identity(scope, request, anchors)
        rule = request.rule_id
        primary = scope.primary
        raw = primary.raw
        result_series = scope.series_for("market") if rule == "chart.market.regime" else primary

        def item(
            values,
            *,
            state="OBSERVED",
            kind="STATE",
            occurred=None,
            confirmed=None,
            finality=None,
            anchor_id=None,
            status_on=None,
        ):
            return ChartItem.create(
                manifest=result_series.manifest,
                request=request,
                anchor_id=anchor_id,
                occurred_on=occurred or result_series.manifest.as_of,
                confirmed_on=confirmed or (occurred or result_series.manifest.as_of),
                evaluation_key=key,
                kind=kind,
                status_as_of=status_on or result_series.manifest.as_of,
                state=state,
                finality=finality
                or _combined_finality(*(_finality(primary, d.date()) for d in raw.index)),
                evidence={**snapshot(values), "provider_identity": identity},
            )

        def unavailable(reason, **diagnostics):
            return {}, (
                item(
                    {"reasons": (reason,), **diagnostics}, state="UNAVAILABLE", finality="UNKNOWN"
                ),
            )

        if (
            rule == "chart.anchor.break_reclaim"
            and request.parameters.get("replay_profile") is not None
        ):
            from src.tools.technical.chart_analysis.anchor_profiles import (
                evaluate_compat_anchor,
                evaluate_legacy_anchor_with_preview,
            )

            evaluate = (
                evaluate_legacy_anchor_with_preview
                if request.parameters["replay_profile"] == "LEGACY_OBSERVATION_V1"
                else evaluate_compat_anchor
            )
            return evaluate(scope, request, anchors, key, feature_resolver=self.anchor_feature)
        if rule == "chart.anchor.break_reclaim":
            # The reviewed Task3 replay owns FINAL/preview separation. Providers are
            # injected through an owned feature frame, never by altering manifests.
            return evaluate_anchor(
                scope,
                request,
                anchors,
                key,
                feature_resolver=self.anchor_feature,
                frame_resolver=self.anchor_frame,
            )
        if rule == "chart.rs":
            market_frame = scope.series_for("market").raw
            if "Close" not in raw or "Close" not in market_frame:
                return unavailable("INPUT_MISSING")
            stock = raw["Close"].dropna()
            market = market_frame["Close"].dropna()
            common = stock.index.intersection(market.index)
            valid_common_count = len((stock.loc[common] / market.loc[common]).dropna())
            if valid_common_count < 20:
                return unavailable("HISTORY_SHORT", valid_common_count=valid_common_count)
            return evaluate_rs(scope, request, anchors, key)
        if rule == "chart.pivot.span3":
            if not {"High", "Low"} <= set(raw):
                return unavailable("INPUT_MISSING")
            return evaluate_pivots(scope, request, anchors, key)
        if rule == "chart.market.regime":
            if "Close" not in scope.series_for("market").raw:
                return unavailable("INPUT_MISSING")
            result = market_regime_values(scope.series_for("market").raw)
            if not result["available"]:
                result["reasons"] = ("HISTORY_SHORT",)
            return {}, (
                item(
                    result,
                    state=result["regime"] if result["available"] else "UNAVAILABLE",
                    finality=_combined_finality(
                        *(
                            _finality(scope.series_for("market"), d.date())
                            for d in scope.series_for("market").raw.index
                        )
                    ),
                ),
            )
        if rule == "chart.features.strict":
            if primary.manifest.feature_version != feature_api.STRICT_VERSION:
                return unavailable("PROFILE_UNSUPPORTED")
            return self.strict(scope).get(primary.manifest.as_of, {}), ()
        if raw.empty:
            return unavailable("HISTORY_SHORT")
        if rule in _OBSERVATIONS and (
            primary.manifest.coverage.get("complete") is False
            or primary.manifest.coverage.get("truncation_reason")
        ):
            return unavailable("INCOMPLETE_PREFIX")
        if rule in _STRICT_RULES:
            if primary.manifest.feature_version != feature_api.STRICT_VERSION:
                return unavailable("PROFILE_UNSUPPORTED")
            return self.strict_rule(scope, request, item, unavailable)
        if (
            rule == "chart.close_breakout.strict"
            and request.parameters.get("frame_policy") == "SUPPLIED_AS_IS"
        ):
            if primary.manifest.feature_version != feature_api.SUPPLIED_VERSION:
                raise ValueError("Swing S01 requires supplied feature profile")
            options = {
                k: v for k, v in request.parameters.items() if k not in ("frame_policy", "lookback")
            }
            values = swing_s01_values(raw, **options)
            return {}, (item({**values, "sessions": tuple(raw.index.date)}),)
        if rule == "chart.close_breakout.strict":
            if primary.manifest.feature_version == feature_api.STRICT_VERSION:
                strict_rows = self.strict(scope)
                last_status = strict_rows[max(strict_rows)]["Close"]
                if last_status.status == "UNAVAILABLE":
                    return unavailable("INCOMPLETE_PREFIX")
            if not {"Close", "High"} <= set(raw):
                return unavailable("INPUT_MISSING")
            values = close_breakout_values(raw, lookback=request.parameters["lookback"])
            ready = bool(values["known"][-1])
            if not ready:
                return unavailable(
                    "HISTORY_SHORT"
                    if len(raw) < request.parameters["lookback"] + 2
                    else "INPUT_MISSING"
                )
            if primary.manifest.feature_version == feature_api.STRICT_VERSION:
                if not values["fresh"][-1]:
                    return {}, ()
                return {}, (
                    item(
                        {
                            "close": float(raw["Close"].iloc[-1]),
                            "reference": float(values["reference"][-1]),
                            "fresh": True,
                        },
                        kind="EVENT",
                        state="DETECTED",
                        finality="PROVISIONAL" if last_status.status == "PROVISIONAL" else "FINAL",
                    ),
                )
            return {}, (
                item(
                    {**values, "sessions": tuple(raw.index.date)},
                    state="DETECTED" if values["fresh"][-1] else "CLEAR",
                ),
            )
        if (
            rule in _OBSERVATIONS
            and rule == "OBSERVATION_V1"
            and request.parameters["code"]
            in ("HIGHER_LOW", "HIGHER_HIGH", "LOWER_HIGH", "LOWER_LOW")
        ):
            return {}, self.pivot_observations(scope, request, item)
        if (
            rule == "legacy.indicators"
            and request.parameters.get("frame_policy") == "SWING_FEATURES"
        ):
            if primary.manifest.feature_version != feature_api.LEGACY_VERSION:
                raise ValueError("SWING_FEATURES requires legacy raw provider")
            options = {k: v for k, v in request.parameters.items() if k != "frame_policy"}
            frame = swing_feature_frame(raw, **options)
            return {}, (
                item(
                    {
                        "rows": frame,
                        "dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()},
                    }
                ),
            )
        if (
            rule in ("chart.structure_breakdown.swing", "chart.deep_recovery.swing")
            and request.parameters.get("frame_policy") == "SUPPLIED_AS_IS"
        ):
            if primary.manifest.feature_version != feature_api.SUPPLIED_VERSION:
                raise ValueError("Swing facts require supplied feature profile")
            p = request.parameters
            values = swing_numerical_values(
                raw,
                st=np.nan_to_num(raw["SuperTrend_Dir"].to_numpy(float), nan=1.0),
                higher_low=raw["Higher_Low"].to_numpy(bool),
                lower_low_lower_high=raw["Lower_Low_Lower_High"].to_numpy(bool),
                volume_multiple=p["volume_multiple"],
                weak_close_location=p["weak_close_location"],
                trend_volume_multiple=p["trend_volume_multiple"],
                direction_lookback=p["direction_lookback"],
            )
            if p["signal_profile"] == "V2_SIGNAL":
                values.update(
                    swing_signal_values(
                        raw,
                        direction_lookback=p["direction_lookback"],
                        trend_volume_multiple=p["trend_volume_multiple"],
                    )
                )
            return {}, (item({**values, "sessions": tuple(raw.index.date)}),)
        if primary.manifest.feature_version not in _LEGACY:
            return unavailable("PROFILE_UNSUPPORTED")
        supplied_component = (
            primary.manifest.feature_version == feature_api.SUPPLIED_VERSION
            and rule in SUPPLIED_FRAME_FAMILIES
        )
        if (
            not supplied_component
            and request.parameters.get("frame_policy") != "SUPPLIED_AS_IS"
            and not {"Open", "High", "Low", "Close", "Volume"} <= set(raw)
        ):
            return unavailable("INPUT_MISSING")
        supplied_as_is = request.parameters.get("frame_policy") == "SUPPLIED_AS_IS"
        if supplied_as_is and primary.manifest.feature_version != feature_api.SUPPLIED_VERSION:
            raise ValueError("SUPPLIED_AS_IS requires supplied feature profile")
        frame = (
            raw
            if primary.manifest.feature_version == feature_api.SUPPLIED_VERSION
            and (rule in SUPPLIED_FRAME_FAMILIES or supplied_as_is)
            else self.frame(primary)
        )
        if rule.startswith("analysis."):
            display = request.parameters.get("display_bars", 20)
            cache_key = canonical_hash(
                "jarvis:trigger-batch:v1",
                plain(
                    (
                        primary.manifest,
                        identity,
                        display,
                        request.parameters.get("frame_policy", "PREPARED"),
                        request.parameters.get("pattern_thresholds", {}),
                        rule if request.parameters.get("pattern_thresholds") else None,
                    )
                ),
            )
            if cache_key not in self._triggers:
                self._triggers[cache_key] = detect_trigger_events(
                    frame,
                    display_bars=display,
                    thresholds_by_rule={rule: request.parameters["pattern_thresholds"]}
                    if request.parameters.get("pattern_thresholds")
                    else None,
                )
            return {}, tuple(
                item(asdict(e), state=e.status.upper(), kind="EVENT", occurred=e.occurred_on)
                for e in self._triggers[cache_key]
                if e.code == rule
            )
        if rule in _OBSERVATIONS:
            if not (rule == "OBSERVATION_V1" and request.parameters.get("threshold") is None):
                code = request.parameters.get("code")
                if code in ("UP_VOLUME_EXPANSION", "DOWN_VOLUME_EXPANSION"):
                    required = {"Close", "Previous_Close", "Volume_Ratio_Prev20"}
                elif code == "VOLUME_CONTRACTION":
                    required = {"Contraction_Context", "Volume_Contraction_Ratio"}
                else:
                    required = {
                        "Close",
                        "SMA_20",
                        "SMA_20_Slope_5",
                        "Previous_SMA20_Slope",
                        "Prior_Trend_Context",
                    }
                    if rule == "chart.momentum.reacceleration":
                        required |= {"Prior_Below_SMA20"}
                        if request.parameters["mode"] == "SMA20_TURN_POSITIVE_RETURN":
                            required |= {"Return_5"}
                        elif request.parameters["mode"] == "SMA20_TURN_HIGH_BREAK":
                            required |= {"High_Break_5"}
                if not required <= set(frame):
                    return unavailable("INPUT_MISSING")
            return {}, self.observations(scope, request, frame, item)
        if rule in ("legacy.indicators", "legacy.extrema.order5"):
            columns = list(frame) if rule == "legacy.indicators" else ["Swing_High", "Swing_Low"]
            columns = [c for c in columns if c in frame]
            if not columns:
                return unavailable("INPUT_MISSING")
            selected = frame[columns]
            latest = {
                c: FeatureValue(
                    snapshot(selected[c].iloc[-1]),
                    "READY" if pd.notna(selected[c].iloc[-1]) else "UNAVAILABLE",
                    () if pd.notna(selected[c].iloc[-1]) else ("INPUT_MISSING",),
                )
                for c in columns
            }
            return latest, (item({"rows": selected, "timing": "ASOF_COMPAT"}),)
        if rule == "feature.window":
            column = request.parameters["feature_key"]
            if column not in frame:
                return unavailable("INPUT_MISSING")
            value = snapshot(frame[column].iloc[-1])
            feature = FeatureValue(
                value,
                "READY" if value is not None else "UNAVAILABLE",
                () if value is not None else ("HISTORY_SHORT",),
            )
            return {column: feature}, (
                item(
                    {
                        "feature_key": column,
                        "values": frame[column],
                        "sessions": tuple(frame.index.date),
                    },
                    state=feature.status,
                ),
            )
        if rule in FRAME_FAMILIES:
            prepared = frame
            if rule in ("chart.structure_breakdown.swing", "chart.deep_recovery.swing"):
                prepared = frame.copy(deep=True)
                higher, lower = confirmed_pivots(
                    frame["High"].to_numpy(float), frame["Low"].to_numpy(float)
                )
                if "Higher_Low" not in prepared:
                    prepared["Higher_Low"] = higher
                if "Lower_Low_Lower_High" not in prepared:
                    prepared["Lower_Low_Lower_High"] = lower
            try:
                values = legacy_fact_values_from_frame(
                    prepared, family=rule, parameters=request.parameters
                )
            except KeyError:
                return unavailable("INPUT_MISSING")
            minimum = {
                "chart.vcp.legacy": 20,
                "chart.pocket_pivot.down_candle": 11,
                "chart.power_gap": 2,
                "chart.close_breakout.nanmax": 22,
                "chart.stage2.minervini": 200,
                "chart.velocity.legacy": 15,
                "chart.crsi.legacy": 2,
                "chart.supertrend.legacy": 2,
                "chart.legacy.volume_extra": 2,
                "legacy.confluence": 20,
                "legacy.divergence": 50,
                "chart.vcp.playbook": 20,
            }.get(rule, 1)
            if rule == "chart.pocket_pivot.down_candle":
                minimum = (
                    validated_thresholds(rule, request.parameters.get("pattern_thresholds"))[
                        "PP_LOOKBACK_DAYS"
                    ]
                    + 1
                )
            evidence_key = {
                "chart.vcp.legacy": "atr_contraction_ratio",
                "chart.pocket_pivot.down_candle": "close",
                "chart.power_gap": "gap_size_pct",
                "chart.close_breakout.nanmax": "current_reference",
            }.get(rule)
            available = values.get("available") is not False and (
                evidence_key is None or evidence_key in values
            )
            if rule == "chart.vcp.playbook":
                available = "atr_contraction_ratio" in values["vcp"]
            if not available:
                values["reasons"] = ("HISTORY_SHORT" if len(frame) < minimum else "INPUT_MISSING",)
            state = "OBSERVED" if available else "UNAVAILABLE"
            return {}, (item({**values, "timing": "ASOF_COMPAT"}, state=state),)
        raise NotImplementedError(f"No chart evaluator for {rule}")

    def anchor_frame(self, series):
        fv = series.manifest.feature_version
        if fv == feature_api.LEGACY_VERSION:
            return self.frame(series)
        if fv == feature_api.SUPPLIED_VERSION:
            return series.raw
        if fv == feature_api.STRICT_VERSION:
            from src.tools.technical.chart_analysis.models import CalculationScope

            rows = self.strict(CalculationScope(series, {}))
            return pd.DataFrame(
                {
                    pd.Timestamp(day): {k: v.value for k, v in values.items()}
                    for day, values in rows.items()
                }
            ).T
        return series.raw

    def anchor_feature(self, series, anchor):
        from src.tools.technical.chart_analysis.detectors import resolve_anchor_feature

        if anchor.feature_version == "SMA_ROLLING_V1":
            return resolve_anchor_feature(series, anchor)
        if anchor.feature_version != series.manifest.feature_version:
            raise ValueError("FeatureAnchor feature_version does not match feature provider")
        if anchor.feature_key in ("Open", "High", "Low", "Close", "Volume"):
            frame = series.raw
        else:
            frame = self.anchor_frame(series)
        if anchor.feature_key not in frame:
            raise NotImplementedError(f"No feature provider for {anchor.feature_key}")
        return frame[anchor.feature_key]

    def strict_rule(self, scope, request, item, unavailable):
        rows = self.strict(scope)
        row = rows[max(rows)]
        raw = scope.primary.raw
        last = raw.iloc[-1]
        rule = request.rule_id
        if rule == "chart.extension.sma20":
            values = (row["Close"], row["SMA_20"])
            if any(v.value is None for v in values):
                return unavailable(
                    next((reason for v in values for reason in v.reasons), "INPUT_MISSING")
                )
            observed = values[0].value / values[1].value - 1
            detected = observed >= request.parameters["extension"]
            evidence = {"extension": observed, "sma20": values[1].value, "detected": detected}
        elif rule == "chart.rsi.wilder":
            value = row["RSI"]
            if value.value is None:
                return unavailable(value.reasons[0])
            detected = value.value >= request.parameters["threshold"]
            evidence = {"rsi": value.value, "detected": detected}
        else:
            if len(raw) < 21:
                return unavailable("HISTORY_SHORT")
            prior = raw.iloc[-21:-1]
            required = (
                ["Volume", "Close", "Low"]
                if rule == "chart.low_break_volume"
                else ["Volume", "Close", "Low", "High"]
            )
            if not np.isfinite(raw[required].iloc[-21:].to_numpy(float)).all():
                return unavailable("INPUT_MISSING")
            average = feature_api._mean(prior["Volume"].to_numpy(float))
            if average == 0:
                return unavailable("ZERO_REFERENCE_VOLUME")
            ratio = float(last["Volume"]) / average
            if rule == "chart.low_break_volume":
                reference = float(prior["Low"].min())
                detected = bool(
                    last["Close"] < reference and ratio >= request.parameters["volume_ratio"]
                )
                evidence = {"low_reference": reference, "volume_ratio": ratio, "detected": detected}
            else:
                spread = float(last["High"] - last["Low"])
                if spread == 0:
                    return unavailable("FLAT_RANGE")
                location = float((last["Close"] - last["Low"]) / spread)
                detected = bool(
                    last["Close"] < raw["Close"].iloc[-2]
                    and ratio >= request.parameters["volume_ratio"]
                    and location <= request.parameters["close_location"]
                )
                evidence = {"close_location": location, "volume_ratio": ratio, "detected": detected}
        status = row["Close"].status
        if status == "UNAVAILABLE":
            return unavailable("INCOMPLETE_PREFIX")
        return {}, (
            item(
                evidence,
                state="DETECTED" if detected else "CLEAR",
                kind="RISK",
                finality="PROVISIONAL" if status == "PROVISIONAL" else "FINAL",
            ),
        )

    def pivot_observations(self, scope, request, item):
        frame = scope.primary.raw
        if not {"High", "Low"} <= set(frame):
            return (item({"reasons": ("INPUT_MISSING",)}, state="UNAVAILABLE"),)
        final_mask = [_finality(scope.primary, d.date()) == "FINAL" for d in frame.index]

        def replay(mask, finality):
            events = confirmed_pivot_events(
                frame["High"].to_numpy(float), frame["Low"].to_numpy(float), final_mask=mask
            )
            return tuple(
                item(
                    {**asdict(e), "pivot_on": frame.index[e.pivot_index].date()},
                    kind="EVENT",
                    state="RESOLVED",
                    occurred=frame.index[e.confirmed_index].date(),
                    finality=finality,
                    status_on=frame.index[e.confirmed_index].date(),
                )
                for e in events
                if e.relation == request.parameters["code"]
            )

        final = replay(final_mask, "FINAL")
        if len(frame) and _finality(scope.primary, frame.index[-1].date()) == "PROVISIONAL":
            preview = replay([*final_mask[:-1], True], "PROVISIONAL")
            known = {x.id for x in final}
            final += tuple(
                x for x in preview if x.id not in known and x.occurred_on == frame.index[-1].date()
            )
        return final

    def observations(self, scope, request, frame, item):
        # FINAL history and a trailing preview are replayed independently. A preview
        # may add today's onset; it may never resolve/update a committed episode.
        finalities = [_finality(scope.primary, d.date()) for d in frame.index]
        final_frame = frame.loc[[f == "FINAL" for f in finalities]]
        final = self.observation_replay(request, final_frame, item, "FINAL")
        if finalities and finalities[-1] == "PROVISIONAL":
            preview_frame = frame
            if request.parameters.get("frame_policy") == "SUPPLIED_AS_IS":
                preview_frame = frame.loc[
                    [f == "FINAL" or i == len(frame) - 1 for i, f in enumerate(finalities)]
                ]
            preview = self.observation_replay(request, preview_frame, item, "PROVISIONAL")
            known = {x.id for x in final}
            final += tuple(
                x for x in preview if x.id not in known and x.occurred_on == frame.index[-1].date()
            )
        return final

    def observation_replay(self, request, frame, item, finality):
        rule = request.rule_id
        if frame.empty:
            return ()
        code = request.parameters.get("code")
        threshold = request.parameters.get("threshold")
        if rule == "OBSERVATION_V1" and threshold is None:
            return (
                item(
                    {"code": code, "reasons": ("PARAMETER_NOT_SELECTED",)},
                    state="NOT_SELECTED",
                    finality=finality,
                ),
            )
        kind = (
            "volume"
            if code in ("UP_VOLUME_EXPANSION", "DOWN_VOLUME_EXPANSION")
            else "contraction"
            if code == "VOLUME_CONTRACTION"
            else "deceleration"
            if rule == "chart.momentum.deceleration"
            else "all"
        )
        numerical = observation_numerical_values(
            frame, kind=kind, prepared=request.parameters.get("frame_policy") == "SUPPLIED_AS_IS"
        )
        history = []
        active = None
        for i, (stamp, row) in enumerate(numerical.iterrows()):
            day = stamp.date()
            values = {"code": code or rule, "current": snapshot(row.to_dict())}
            if rule == "OBSERVATION_V1" and code in (
                "UP_VOLUME_EXPANSION",
                "DOWN_VOLUME_EXPANSION",
            ):
                direction = row["Up_Day" if code == "UP_VOLUME_EXPANSION" else "Down_Day"]
                ratio = row["Volume_Ratio_Prev20"]
                if pd.notna(ratio) and direction and ratio >= threshold:
                    history.append(
                        item(
                            values,
                            state="RESOLVED",
                            kind="EVENT",
                            occurred=day,
                            finality=finality,
                            status_on=day,
                        )
                    )
                continue
            if rule == "chart.momentum.reacceleration":
                mode = request.parameters["mode"]
                column = {
                    "SMA20_TURN": "Reacceleration_Turn",
                    "SMA20_TURN_POSITIVE_RETURN": "Reacceleration_Positive_Return",
                    "SMA20_TURN_HIGH_BREAK": "Reacceleration_High_Break",
                }[mode]
                if row[column]:
                    history.append(
                        item(
                            values,
                            state="RESOLVED",
                            kind="EVENT",
                            occurred=day,
                            finality=finality,
                            status_on=day,
                        )
                    )
                continue
            if rule == "OBSERVATION_V1":
                ratio = row["Volume_Contraction_Ratio"]
                context = row.get("Contraction_Context")
                if pd.isna(ratio) or context is None or pd.isna(context):
                    continue
                condition = bool(context and ratio <= threshold)
            else:
                source = frame.iloc[i]
                if any(
                    pd.isna(source.get(k))
                    for k in ("Close", "SMA_20", "SMA_20_Slope_5", "Prior_Trend_Context")
                ):
                    continue
                condition = bool(
                    row["Momentum_Weak"] if active is not None else row["Momentum_Weak_Start"]
                )
            if condition:
                if active is None:
                    active = len(history)
                    history.append(
                        item(
                            {**values, "started_on": day, "origin": values["current"]},
                            state="ACTIVE",
                            kind="EPISODE",
                            occurred=day,
                            finality=finality,
                            status_on=day,
                        )
                    )
                else:
                    old = history[active]
                    history[active] = item(
                        {**values, "started_on": old.occurred_on, "origin": old.evidence["origin"]},
                        state="ACTIVE",
                        kind="EPISODE",
                        occurred=old.occurred_on,
                        finality=finality,
                        status_on=day,
                    )
            elif active is not None:
                old = history[active]
                history[active] = item(
                    {
                        **values,
                        "started_on": old.occurred_on,
                        "ended_on": day,
                        "origin": old.evidence["origin"],
                    },
                    state="RESOLVED",
                    kind="EPISODE",
                    occurred=old.occurred_on,
                    finality=finality,
                    status_on=day,
                )
                active = None
        return tuple(history)


def default_evaluator_factory():
    owner = DetectorFactory()
    return {entry.rule_id: owner for entry in RULE_REGISTRY}

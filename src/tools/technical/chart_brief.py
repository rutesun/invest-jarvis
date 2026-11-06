"""같은 실행의 기술 자료를 차트 브리핑용으로 묶는다. 매매·점수 정책은 바꾸지 않는다."""

from __future__ import annotations

from collections.abc import Mapping
from math import isclose, isfinite

import numpy as np
import pandas as pd

from src.tools.technical.models import TechnicalResult
from src.tools.technical.pivots import confirmed_pivot_events


def _number(value, *, positive=False):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and (not positive or number > 0) else None


def _snapshot_number(snapshot, attr, row, column, *, positive=False):
    value = _number(getattr(snapshot, attr), positive=positive)
    if column in row.index:
        raw = _number(row[column], positive=positive)
        if raw is None or value is None or not isclose(value, raw, rel_tol=1e-8, abs_tol=1e-8):
            return None
    return value


def _direction(value, threshold=0):
    if value is None:
        return "unavailable"
    return "up" if value > threshold else "down" if value < -threshold else "flat"


def _finalities(technical, day, days, common_analyses):
    manifests = [
        analysis.manifest
        for analysis in (*technical.common_analyses, *common_analyses)
        if analysis.manifest.as_of == day and analysis.manifest.ticker == technical.ticker
    ]
    result = {}
    for current in days:
        states = {
            str(manifest.finality.get(current, "UNKNOWN"))
            if isinstance(manifest.finality, Mapping)
            else str(manifest.finality)
            for manifest in manifests
        }
        # 같은 평가일의 알려진 상태만 UNKNOWN을 보강한다. 상충하는 known 값은 확정하지 않는다.
        states &= {"FINAL", "PROVISIONAL"}
        state = next(iter(states)) if len(states) == 1 else "UNKNOWN"
        result[current] = state if state in {"FINAL", "PROVISIONAL"} else "UNKNOWN"
    return result


def _volume(frame):
    result = {"up_pct": None, "down_pct": None, "flat_days": None, "reason": None}
    if len(frame) < 21 or not {"Close", "Volume"}.issubset(frame.columns):
        return result | {"reason": "21개 종가·20개 거래량 필요"}
    closes = pd.to_numeric(frame["Close"].iloc[-21:], errors="coerce").to_numpy(dtype=float)
    volumes = pd.to_numeric(frame["Volume"].iloc[-20:], errors="coerce").to_numpy(dtype=float)
    if not np.all(np.isfinite(closes) & (closes > 0)) or not np.all(
        np.isfinite(volumes) & (volumes >= 0)
    ):
        return result | {"reason": "최근 종가·거래량 결측 또는 잘못된 값"}
    changes = np.diff(closes)
    up, down = float(volumes[changes > 0].sum()), float(volumes[changes < 0].sum())
    if not isfinite(up + down) or up + down == 0:
        return result | {"reason": "상승일·하락일 거래량 합계 0"}
    return result | {
        "up_pct": up / (up + down) * 100,
        "down_pct": down / (up + down) * 100,
        "flat_days": int((changes == 0).sum()),
    }


def _crsi(value, low, high):
    valid = (
        value is not None
        and low is not None
        and high is not None
        and 0 <= low < high <= 100
        and 0 <= value <= 100
    )
    state = (
        "unavailable"
        if not valid
        else "oversold"
        if value < low
        else "overbought"
        if value > high
        else "neutral"
    )
    return {
        "value": value,
        "low": low,
        "high": high,
        "state": state,
        "reason": None if valid else "유효한 cRSI·가변 상하단 밴드 필요",
    }


def _events(frame, finality):
    events = []
    for index in range(max(1, len(frame) - 20), len(frame)):
        previous, current = frame.iloc[index - 1], frame.iloc[index]
        # 종가가 잘못된 봉에서 발생한 지표 사건을 현재로 연결하지 않는다.
        if any(_number(row.get("Close"), positive=True) is None for row in (previous, current)):
            continue
        day = frame.index[index].date()
        found = []
        for fast, slow, prefix in ((20, 50, "short"), (50, 200, "long")):
            values = [
                _number(row.get(f"SMA_{period}"), positive=True)
                for row in (previous, current)
                for period in (fast, slow)
            ]
            if any(value is None for value in values):
                continue
            before, after = values[0] - values[1], values[2] - values[3]
            direction = "up" if before <= 0 < after else "down" if before >= 0 > after else None
            if direction:
                label = (
                    f"{fast}·{slow}일선 단기 {'상향' if direction == 'up' else '하향'} 교차"
                    if prefix == "short"
                    else f"50·200일선 {'골든크로스' if direction == 'up' else '데드크로스'}"
                )
                found.append((f"{prefix}_cross_{direction}", label, direction))
        states = [
            _crsi(
                *[_number(row.get(column)) for column in ("cRSI", "cRSI_LowBand", "cRSI_HighBand")]
            )["state"]
            for row in (previous, current)
        ]
        before, after = states
        if "unavailable" not in states:
            if before == "oversold" and after != "oversold":
                found.append(("crsi_oversold_recovery", "cRSI 하단밴드 회복", "up"))
            if before == "overbought" and after != "overbought":
                found.append(("crsi_overbought_exit", "cRSI 상단밴드 아래 복귀", "down"))
            if after == "oversold" and before != "oversold":
                found.append(("crsi_oversold_entry", "cRSI 과매도권 진입", "down"))
            if after == "overbought" and before != "overbought":
                found.append(("crsi_overbought_entry", "cRSI 과매수권 진입", "up"))
        adjacent_states = {finality[frame.index[index - 1].date()], finality[day]}
        event_finality = (
            "UNKNOWN"
            if "UNKNOWN" in adjacent_states
            else "PROVISIONAL"
            if "PROVISIONAL" in adjacent_states
            else "FINAL"
        )
        events.extend(
            {
                "date": str(day),
                "finality": event_finality,
                "kind": kind,
                "label": label,
                "direction": direction,
            }
            for kind, label, direction in found
        )
    return events[-2:]


def _structure(frame, finality):
    result = {"high": None, "low": None, "reason": "같은 종류의 FINAL pivot 2개 필요"}
    if not {"High", "Low"}.issubset(frame.columns):
        return result
    high = pd.to_numeric(frame["High"], errors="coerce").to_numpy(dtype=float)
    low = pd.to_numeric(frame["Low"], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(high) & np.isfinite(low) & (high >= low) & (low > 0)
    valid &= np.array([finality[day.date()] == "FINAL" for day in frame.index])
    # final_mask는 봉을 압축한다. 미확정·결측 봉을 건너뛰지 않도록 연속 구간마다 owner를 호출한다.
    start = 0
    for end in range(len(frame) + 1):
        if end < len(frame) and valid[end]:
            continue
        for event in confirmed_pivot_events(high[start:end], low[start:end]):
            if event.previous_pivot_price is None:
                continue
            result[event.pivot_type.lower()] = {
                "previous": event.previous_pivot_price,
                "value": event.price,
                "direction": _direction(event.price - event.previous_pivot_price),
                "pivot_on": str(frame.index[start + event.pivot_index].date()),
                "confirmed_on": str(frame.index[start + event.confirmed_index].date()),
                "finality": "FINAL",
            }
        start = end + 1
    if result["high"] is not None and result["low"] is not None:
        result["reason"] = None
    return result


def build_chart_brief(technical: TechnicalResult, *, common_analyses=()) -> dict:
    """요청 단위 표시 재료. 날짜·유효성 불일치는 이전 값을 대신 쓰지 않고 드러낸다."""
    frame = technical.raw_dataframe
    day = technical.scorecard.as_of if technical.scorecard is not None else None
    result = {
        "as_of": str(day) if day else None,
        "finality": "UNKNOWN",
        "reason": None,
        "headline": "차트 브리핑 미산출",
        "moving_averages": [],
        "trends": {},
        "arrays": {},
        "structure": {},
        "crsi": {},
        "volume": {},
        "events": [],
    }
    if frame is None or frame.empty:
        return result | {"reason": "raw 데이터 이용 불가"}
    if (
        not isinstance(frame.index, pd.DatetimeIndex)
        or frame.index.hasnans
        or not frame.index.is_unique
        or not frame.index.is_monotonic_increasing
    ):
        return result | {"reason": "오름차순·중복 없는 날짜 인덱스 필요"}
    if day is None:
        day = frame.index[-1].date()
        result["as_of"] = str(day)
    days = [stamp.date() for stamp in frame.index]
    if len(set(days)) != len(days):
        return result | {"reason": "같은 날짜의 봉 중복"}
    states = _finalities(technical, day, days, common_analyses)
    result["finality"] = states.get(day, "UNKNOWN")
    prefix = frame.loc[[current <= day for current in days]]
    if prefix.empty or prefix.index[-1].date() != day:
        return result | {"reason": "기준일의 raw 봉 부재 · snapshot 재사용 안 함"}
    if len(prefix) != len(frame):
        return result | {"reason": "기준일 이후 raw 봉 제외 · snapshot 기준 불일치"}
    snapshot = technical.snapshot
    close = _number(prefix.iloc[-1].get("Close"), positive=True)
    price = _number(snapshot.price, positive=True)
    if close is None or price is None or not isclose(price, close, rel_tol=1e-8, abs_tol=1e-8):
        return result | {"reason": "기준일 종가와 snapshot 가격 불일치 또는 결측"}
    averages = []
    for period in (20, 50, 150, 200):
        value = _snapshot_number(
            snapshot, f"sma_{period}", prefix.iloc[-1], f"SMA_{period}", positive=True
        )
        slope = _number(getattr(snapshot, f"sma_{period}_slope_pct"))
        averages.append(
            {
                "period": period,
                "value": value,
                "slope_pct": slope,
                "reason": "기준일 MA 값 부재 또는 snapshot 불일치"
                if value is None
                else "21봉 기울기 부족"
                if slope is None
                else None,
                "direction": _direction(slope, 0.5) if value is not None else "unavailable",
                "distance_pct": (price / value - 1) * 100 if value is not None else None,
            }
        )
    trends = {}
    for name, pair in (("short", averages[:2]), ("long", averages[2:])):
        directions = {ma["direction"] for ma in pair}
        trends[name] = (
            "unavailable"
            if "unavailable" in directions
            else next(iter(directions))
            if len(directions) == 1
            else "mixed"
        )
    arrays = {}
    for fast, slow in ((20, 50), (50, 200)):
        a, b = (
            next(ma["value"] for ma in averages if ma["period"] == period)
            for period in (fast, slow)
        )
        arrays[f"{fast}_{slow}"] = (
            "unavailable"
            if a is None or b is None
            else "above"
            if a > b
            else "below"
            if a < b
            else "equal"
        )
    labels = {
        "up": "상승",
        "down": "하락",
        "flat": "보합",
        "mixed": "혼조",
        "unavailable": "미산출",
    }
    distance_150 = next(ma["distance_pct"] for ma in averages if ma["period"] == 150)
    position_150 = (
        "위치 미산출"
        if distance_150 is None
        else "위"
        if distance_150 > 0
        else "아래"
        if distance_150 < 0
        else "일치"
    )
    headline = (
        f"단기선 {labels[trends['short']]} · 장기선 {labels[trends['long']]}"
        f" · 주가 150일선 {position_150}"
    )
    return result | {
        "headline": headline,
        "moving_averages": averages,
        "trends": trends,
        "arrays": arrays,
        "structure": _structure(prefix, states),
        "crsi": _crsi(
            *[
                _snapshot_number(snapshot, attr, prefix.iloc[-1], column)
                for attr, column in (
                    ("crsi", "cRSI"),
                    ("crsi_low_band", "cRSI_LowBand"),
                    ("crsi_high_band", "cRSI_HighBand"),
                )
            ]
        ),
        "volume": _volume(prefix),
        "events": _events(prefix, states),
    }

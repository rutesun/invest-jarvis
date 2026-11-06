import pandas as pd

from src.tools.technical.context import common_evidence, pattern_threshold_snapshot
from src.tools.technical.models import ComponentResult, ComponentSignal


def analyze_volume(df: pd.DataFrame, *, common_analysis=None) -> ComponentResult:
    """Analyze volume patterns (Pocket Pivot, Tennis Ball/Egg, Power Gap Up, Volume Surge)."""
    facts = common_evidence(df, common_analysis, "chart.legacy.volume_extra")
    if "Vol_SMA_20" not in df.columns or len(df) < 2:
        return ComponentResult(
            signals=[],
            evidence=["거래량 데이터 없음"],
            metrics={},
            score=0,
        )

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    volume = latest.get("Volume")
    vol_sma_20 = latest.get("Vol_SMA_20")
    close = latest.get("Close")
    prev_close = prev.get("Close")
    open_price = latest.get("Open")

    if pd.isna(volume) or pd.isna(vol_sma_20) or vol_sma_20 == 0:
        return ComponentResult(
            signals=[],
            evidence=["거래량 SMA 없음"],
            metrics={},
            score=0,
        )

    volume = float(volume)
    vol_sma_20 = float(vol_sma_20)
    vol_ratio = volume / vol_sma_20

    volume, vol_sma_20, vol_ratio = (facts[key] for key in ("volume", "vol_sma_20", "vol_ratio"))

    signals = []
    evidence = []
    score = 0
    metadata = []
    metrics = {"vol_ratio": round(vol_ratio, 2), "volume": volume, "vol_sma_20": vol_sma_20}

    # Price direction
    # price_down: day-over-day comparison (종가 vs 전일 종가)
    price_up = not pd.isna(close) and not pd.isna(prev_close) and float(close) > float(prev_close)
    price_down = not pd.isna(close) and not pd.isna(prev_close) and float(close) < float(prev_close)
    # is_down_day: intraday comparison (종가 vs 시가, 캔들 색상)
    is_down_day = (
        not pd.isna(close) and not pd.isna(open_price) and float(close) < float(open_price)
    )

    price_up, price_down, is_down_day = (
        facts[key] for key in ("price_up", "price_down", "down_candle")
    )

    # Pattern 1: Pocket Pivot (기관 매집 신호)
    pocket_pivot_result = _pocket_from_facts(
        common_evidence(df, common_analysis, "chart.pocket_pivot.down_candle")
    )
    if pocket_pivot_result["detected"]:
        signals.extend(pocket_pivot_result["signals"])
        evidence.extend(pocket_pivot_result["evidence"])
        score += pocket_pivot_result["score"]
        metrics.update(pocket_pivot_result["metrics"])
        metadata.append(
            ComponentSignal(
                signal_type="pullback",
                bias="bullish",
                intent="entry",
                severity="high",
                entry_eligible=True,
                source="volume",
                reason="Pocket Pivot",
            )
        )

    # Pattern 2: Tennis Ball / Egg (평균회귀 신호)
    tennis_egg_result = _tennis_from_facts(facts)
    if tennis_egg_result["detected"]:
        signals.extend(tennis_egg_result["signals"])
        evidence.extend(tennis_egg_result["evidence"])
        score += tennis_egg_result["score"]
        metrics.update(tennis_egg_result["metrics"])
        metadata.append(
            ComponentSignal(
                signal_type="reversal" if tennis_egg_result["score"] > 0 else "breakdown",
                bias="bullish" if tennis_egg_result["score"] > 0 else "bearish",
                intent="watch" if tennis_egg_result["score"] > 0 else "risk",
                severity="medium" if tennis_egg_result["score"] > 0 else "high",
                source="volume",
                reason=tennis_egg_result["signals"][0],
            )
        )

    # Pattern 3: Power Gap Up (갭업 + 거래량 폭발)
    power_gap_result = _gap_from_facts(common_evidence(df, common_analysis, "chart.power_gap"))
    if power_gap_result["detected"]:
        signals.extend(power_gap_result["signals"])
        evidence.extend(power_gap_result["evidence"])
        score += power_gap_result["score"]
        metrics.update(power_gap_result["metrics"])
        metadata.append(
            ComponentSignal(
                signal_type="breakout",
                bias="bullish",
                intent="entry",
                severity="high",
                entry_eligible=True,
                source="volume",
                reason="Power Gap Up",
            )
        )

    # Pattern 4: General Volume Surge (기존 로직 유지)
    if facts["surge"]:
        signals.append("거래량 급증")
        evidence.append(f"거래량 {volume:,.0f} / 20일평균 {vol_sma_20:,.0f} = {vol_ratio:.1f}x")
        if price_up:
            signals.append("가격 상승 + 거래량 급증 (강세 확인)")
            score += 15
            metadata.append(
                ComponentSignal(
                    signal_type="volume_confirmation",
                    bias="bullish",
                    intent="hold",
                    severity="medium",
                    source="volume",
                    reason="가격 상승 + 거래량 급증",
                )
            )
        elif price_down:
            signals.append("가격 하락 + 거래량 급증 (경고)")
            score -= 10
            metadata.append(
                ComponentSignal(
                    signal_type="breakdown",
                    bias="bearish",
                    intent="risk",
                    severity="high",
                    source="volume",
                    reason="가격 하락 + 거래량 급증",
                )
            )
        else:
            score += 5

    elif facts["increase"]:
        evidence.append(f"거래량 증가 ({vol_ratio:.1f}x)")
        if price_up:
            score += 5

    elif facts["moderate"]:
        # 완만한 거래량 증가(1.2x~1.5x) — 급증 임계값엔 못 미치지만 상승 확증으로 소폭 가점.
        # 돌파일 vol_ratio가 1.5x를 살짝 밑돌아 신호가 통째로 사라지던 사각지대 보완.
        if price_up:
            signals.append("거래량 완만 증가 (강세 확인)")
            evidence.append(f"거래량 {volume:,.0f} / 20일평균 {vol_sma_20:,.0f} = {vol_ratio:.1f}x")
            score += 3

    elif vol_ratio < 0.5:
        signals.append("거래량 감소")
        evidence.append(f"거래량 {volume:,.0f} / 20일평균 {vol_sma_20:,.0f} = {vol_ratio:.1f}x")

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
        signal_metadata=metadata,
    )


def _detect_pocket_pivot(df: pd.DataFrame, latest: pd.Series) -> dict:
    """Detect Pocket Pivot (Gil Morales pattern).

    조건:
    1. 최근 다운데이 (close < open)
    2. 해당 다운데이 거래량 > 이전 10일 다운데이 중 최대 거래량
    3. 50일선 ±2% 근처

    Returns 25 points.
    """
    from src.tools.technical.chart_analysis._legacy_components import pocket_pivot_values

    return _pocket_from_facts(
        pocket_pivot_values(
            df,
            latest=latest,
            thresholds=pattern_threshold_snapshot("chart.pocket_pivot.down_candle"),
        )
    )


def _detect_tennis_ball_egg(df: pd.DataFrame, latest: pd.Series, is_down_day: bool) -> dict:
    """Detect Tennis Ball (반등 신호) vs Egg (추가 하락 경고).

    Tennis Ball: 하락 거래량 < 50% 평균 → 반등 가능성 (15 pts)
    Egg: 하락 거래량 > 150% 평균 → 추가 하락 리스크 (-15 pts)

    Args:
        is_down_day: True if close < open (down day)

    Returns negative score for Egg (-15).
    """
    from src.tools.technical.chart_analysis._legacy_components import tennis_ball_values

    return _tennis_from_facts(
        tennis_ball_values(
            df,
            latest=latest,
            is_down_day=is_down_day,
            thresholds=pattern_threshold_snapshot("chart.legacy.volume_extra"),
        )
    )


def _detect_power_gap_up(df: pd.DataFrame) -> dict:
    """Detect Power Gap Up (갭업 + 거래량 폭발).

    조건:
    1. Gap size: open - prev_high ≥ 4%
    2. Volume surge: ≥3x avg

    Returns 20 points.
    """
    from src.tools.technical.chart_analysis._legacy_components import power_gap_values

    return _gap_from_facts(
        power_gap_values(df, thresholds=pattern_threshold_snapshot("chart.power_gap"))
    )


def _empty_pattern():
    return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}


def _pocket_from_facts(values):
    if not values.get("detected"):
        return _empty_pattern()
    volume, maximum, distance = (
        values[key] for key in ("volume", "max_down_volume_10d", "distance_pct")
    )
    return {
        "detected": True,
        "signals": ["Pocket Pivot (기관 매집)"],
        "evidence": [
            f"다운데이 거래량 {volume:,.0f} > 10일 최대 {maximum:,.0f}",
            f"50일선 근처 ({distance * 100:.1f}% 이내)",
        ],
        "metrics": dict(values["metrics"]),
        "score": 25,
    }


def _tennis_from_facts(values):
    if not (values.get("tennis_ball") or values.get("egg")):
        return _empty_pattern()
    tennis = values["tennis_ball"]
    volume, average, ratio = (
        values[key] for key in ("volume", "avg_down_volume_5d", "down_volume_ratio")
    )
    return {
        "detected": True,
        "signals": ["Tennis Ball (반등 신호)" if tennis else "Egg (추가 하락 경고)"],
        "evidence": [
            f"하락 거래량 {volume:,.0f} {'<' if tennis else '>'} 평균 {average:,.0f} ({ratio * 100:.0f}%)"
        ],
        "metrics": {"down_volume_ratio": round(ratio, 2)},
        "score": 15 if tennis else -15,
    }


def _gap_from_facts(values):
    if not values.get("detected"):
        return _empty_pattern()
    gap, volume, ratio = (values[key] for key in ("gap_size_pct", "volume", "gap_vol_ratio"))
    return {
        "detected": True,
        "signals": ["Power Gap Up (강세 갭업)"],
        "evidence": [
            f"갭 크기 {gap * 100:.1f}% (4% 이상)",
            f"거래량 {volume:,.0f} = {ratio:.1f}x (3배 이상)",
        ],
        "metrics": dict(values["metrics"]),
        "score": 20,
    }

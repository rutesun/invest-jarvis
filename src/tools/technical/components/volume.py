import pandas as pd

from src.tools.technical.components.patterns import PatternThresholds
from src.tools.technical.models import ComponentResult


def analyze_volume(df: pd.DataFrame) -> ComponentResult:
    """Analyze volume patterns (Pocket Pivot, Tennis Ball/Egg, Power Gap Up, Volume Surge)."""
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

    signals = []
    evidence = []
    score = 0
    metrics = {"vol_ratio": round(vol_ratio, 2), "volume": volume, "vol_sma_20": vol_sma_20}

    # Price direction
    price_up = not pd.isna(close) and not pd.isna(prev_close) and float(close) > float(prev_close)
    price_down = not pd.isna(close) and not pd.isna(prev_close) and float(close) < float(prev_close)
    is_down_day = (
        not pd.isna(close) and not pd.isna(open_price) and float(close) < float(open_price)
    )

    # Pattern 1: Pocket Pivot (기관 매집 신호)
    pocket_pivot_result = _detect_pocket_pivot(df, latest)
    if pocket_pivot_result["detected"]:
        signals.extend(pocket_pivot_result["signals"])
        evidence.extend(pocket_pivot_result["evidence"])
        score += pocket_pivot_result["score"]
        metrics.update(pocket_pivot_result["metrics"])

    # Pattern 2: Tennis Ball / Egg (평균회귀 신호)
    tennis_egg_result = _detect_tennis_ball_egg(df, latest, is_down_day)
    if tennis_egg_result["detected"]:
        signals.extend(tennis_egg_result["signals"])
        evidence.extend(tennis_egg_result["evidence"])
        score += tennis_egg_result["score"]
        metrics.update(tennis_egg_result["metrics"])

    # Pattern 3: Power Gap Up (갭업 + 거래량 폭발)
    power_gap_result = _detect_power_gap_up(df)
    if power_gap_result["detected"]:
        signals.extend(power_gap_result["signals"])
        evidence.extend(power_gap_result["evidence"])
        score += power_gap_result["score"]
        metrics.update(power_gap_result["metrics"])

    # Pattern 4: General Volume Surge (기존 로직 유지)
    if vol_ratio > PatternThresholds.VOLUME_SURGE_MULTIPLIER:
        signals.append("거래량 급증")
        evidence.append(f"거래량 {volume:,.0f} / 20일평균 {vol_sma_20:,.0f} = {vol_ratio:.1f}x")
        if price_up:
            signals.append("가격 상승 + 거래량 급증 (강세 확인)")
            score += 15
        elif price_down:
            signals.append("가격 하락 + 거래량 급증 (경고)")
            score -= 10
        else:
            score += 5

    elif vol_ratio > 1.5:
        evidence.append(f"거래량 증가 ({vol_ratio:.1f}x)")
        if price_up:
            score += 5

    elif vol_ratio < 0.5:
        signals.append("거래량 감소")
        evidence.append(f"거래량 {volume:,.0f} / 20일평균 {vol_sma_20:,.0f} = {vol_ratio:.1f}x")

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
    )


def _detect_pocket_pivot(df: pd.DataFrame, latest: pd.Series) -> dict:
    """Detect Pocket Pivot (Gil Morales pattern).

    조건:
    1. 최근 다운데이 (close < open)
    2. 해당 다운데이 거래량 > 이전 10일 다운데이 중 최대 거래량
    3. 50일선 ±2% 근처

    Returns 25 points.
    """
    required_cols = ["Open", "Close", "Volume", "SMA_50"]
    if (
        not all(col in df.columns for col in required_cols)
        or len(df) < PatternThresholds.PP_LOOKBACK_DAYS + 1
    ):
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    close = latest.get("Close")
    open_price = latest.get("Open")
    volume = latest.get("Volume")
    sma_50 = latest.get("SMA_50")

    if any(pd.isna(x) for x in [close, open_price, volume, sma_50]) or sma_50 == 0:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    close, open_price, volume, sma_50 = (
        float(close),
        float(open_price),
        float(volume),
        float(sma_50),
    )

    # Condition 1: Down day
    if close >= open_price:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    # Condition 3: Near 50MA (±2%)
    distance_pct = abs(close - sma_50) / sma_50
    if distance_pct > PatternThresholds.PP_SMA_DISTANCE_PCT:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    # Condition 2: Volume exceeds max of last 10 down-days
    lookback = df.iloc[-(PatternThresholds.PP_LOOKBACK_DAYS + 1) : -1].copy()
    down_days = lookback[lookback["Close"] < lookback["Open"]]

    max_down_volume = 0.0 if down_days.empty else float(down_days["Volume"].max())

    if volume <= max_down_volume:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    # Pocket Pivot detected
    return {
        "detected": True,
        "signals": ["Pocket Pivot (기관 매집)"],
        "evidence": [
            f"다운데이 거래량 {volume:,.0f} > 10일 최대 {max_down_volume:,.0f}",
            f"50일선 근처 ({distance_pct * 100:.1f}% 이내)",
        ],
        "metrics": {"pocket_pivot_volume": volume, "max_down_volume_10d": max_down_volume},
        "score": 25,
    }


def _detect_tennis_ball_egg(df: pd.DataFrame, latest: pd.Series, is_down_day: bool) -> dict:
    """Detect Tennis Ball (반등 신호) vs Egg (추가 하락 경고).

    Tennis Ball: 하락 거래량 < 50% 평균 → 반등 가능성 (15 pts)
    Egg: 하락 거래량 > 150% 평균 → 추가 하락 리스크 (-15 pts)

    Args:
        is_down_day: True if close < open (down day)

    Returns negative score for Egg (-15).
    """
    required_cols = ["Close", "Open", "Volume"]
    if (
        not all(col in df.columns for col in required_cols)
        or len(df) < PatternThresholds.MEAN_REVERSION_LOOKBACK + 1
    ):
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    # Only check on down days
    if not is_down_day:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    volume = latest.get("Volume")
    if pd.isna(volume):
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    volume = float(volume)

    # Check last N down-days average volume
    lookback = df.iloc[-(PatternThresholds.MEAN_REVERSION_LOOKBACK + 1) : -1].copy()
    down_days = lookback[lookback["Close"] < lookback["Open"]]

    if len(down_days) < 2:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    avg_down_volume = float(down_days["Volume"].mean())

    if avg_down_volume == 0:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    volume_ratio = volume / avg_down_volume

    # Tennis Ball: volume < 50% avg
    if volume_ratio < PatternThresholds.TENNIS_BALL_THRESHOLD:
        return {
            "detected": True,
            "signals": ["Tennis Ball (반등 신호)"],
            "evidence": [
                f"하락 거래량 {volume:,.0f} < 평균 {avg_down_volume:,.0f} ({volume_ratio * 100:.0f}%)"
            ],
            "metrics": {"down_volume_ratio": round(volume_ratio, 2)},
            "score": 15,
        }

    # Egg: volume > 150% avg
    if volume_ratio > PatternThresholds.EGG_THRESHOLD:
        return {
            "detected": True,
            "signals": ["Egg (추가 하락 경고)"],
            "evidence": [
                f"하락 거래량 {volume:,.0f} > 평균 {avg_down_volume:,.0f} ({volume_ratio * 100:.0f}%)"
            ],
            "metrics": {"down_volume_ratio": round(volume_ratio, 2)},
            "score": -15,  # First negative score!
        }

    return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}


def _detect_power_gap_up(df: pd.DataFrame) -> dict:
    """Detect Power Gap Up (갭업 + 거래량 폭발).

    조건:
    1. Gap size: open - prev_high ≥ 4%
    2. Volume surge: ≥3x avg

    Returns 20 points.
    """
    required_cols = ["Open", "High", "Volume", "Vol_SMA_20"]
    if not all(col in df.columns for col in required_cols) or len(df) < 2:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    open_price = latest.get("Open")
    prev_high = prev.get("High")
    volume = latest.get("Volume")
    vol_sma_20 = latest.get("Vol_SMA_20")

    if (
        any(pd.isna(x) for x in [open_price, prev_high, volume, vol_sma_20])
        or prev_high == 0
        or vol_sma_20 == 0
    ):
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    open_price, prev_high, volume, vol_sma_20 = (
        float(open_price),
        float(prev_high),
        float(volume),
        float(vol_sma_20),
    )

    # Condition 1: Gap size ≥4%
    gap_size_pct = (open_price - prev_high) / prev_high

    if gap_size_pct < PatternThresholds.GAP_SIZE_MIN_PCT:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    # Condition 2: Volume ≥3x avg
    vol_ratio = volume / vol_sma_20

    if vol_ratio < PatternThresholds.GAP_VOLUME_MULTIPLIER:
        return {"detected": False, "signals": [], "evidence": [], "metrics": {}, "score": 0}

    # Power Gap Up detected
    return {
        "detected": True,
        "signals": ["Power Gap Up (강세 갭업)"],
        "evidence": [
            f"갭 크기 {gap_size_pct * 100:.1f}% (4% 이상)",
            f"거래량 {volume:,.0f} = {vol_ratio:.1f}x (3배 이상)",
        ],
        "metrics": {"gap_size_pct": round(gap_size_pct, 3), "gap_vol_ratio": round(vol_ratio, 2)},
        "score": 20,
    }

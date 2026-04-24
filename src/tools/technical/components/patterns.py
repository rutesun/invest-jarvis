import pandas as pd

from src.tools.technical.models import ComponentResult


class PatternThresholds:
    """패턴 감지 임계값 (백테스팅 최적화용)"""

    # VCP Thresholds
    VCP_ATR_CONTRACTION = 0.20  # ATR 수축률 최소 20%
    VCP_TIGHTNESS_MULTIPLIER = 0.5  # Tight day 정의: 일봉 범위 < ATR × 0.5
    VCP_MIN_TIGHT_DAYS = 5  # 20일 중 최소 tight day 개수
    VCP_RECENT_TIGHT_WINDOW = 3  # 최근 N일 연속 tight 체크

    # Pocket Pivot Thresholds
    PP_SMA_DISTANCE_PCT = 0.02  # 50일선 근접 기준 ±2%
    PP_LOOKBACK_DAYS = 10  # 다운데이 검색 기간

    # Tennis Ball / Egg Thresholds
    TENNIS_BALL_THRESHOLD = 0.5  # 하락 거래량 < 50% 평균
    EGG_THRESHOLD = 1.5  # 하락 거래량 > 150% 평균
    MEAN_REVERSION_LOOKBACK = 5  # 평균회귀 신호 검색 기간

    # Power Gap Up Thresholds
    GAP_SIZE_MIN_PCT = 0.04  # 갭업 최소 크기 4%
    GAP_VOLUME_MULTIPLIER = 3.0  # Power Gap Up 거래량 3배
    VOLUME_SURGE_MULTIPLIER = 2.0  # 일반 거래량 급증 2배


def _validate_dataframe(df: pd.DataFrame, min_len: int, required_cols: list[str]) -> bool:
    """DataFrame validation helper.

    Args:
        df: DataFrame to validate
        min_len: Minimum required length
        required_cols: List of required column names

    Returns:
        True if valid, False otherwise
    """
    if len(df) < min_len:
        return False

    return all(col in df.columns for col in required_cols)


def _empty_result() -> dict:
    """일관된 empty result 반환."""
    return {"signals": [], "evidence": [], "metrics": {}, "score": 0}


def analyze_patterns(df: pd.DataFrame) -> ComponentResult:
    """Analyze chart patterns (VCP, Breakout, Candlestick)."""
    if df.empty or len(df) < 3:
        return ComponentResult(
            signals=[],
            evidence=[],
            metrics={},
            score=0,
        )

    signals = []
    evidence = []
    score = 0
    metrics = {}

    # VCP Detection
    vcp_result = _detect_vcp(df)
    signals.extend(vcp_result["signals"])
    evidence.extend(vcp_result["evidence"])
    score += vcp_result["score"]
    metrics.update(vcp_result["metrics"])

    # Breakout Detection
    breakout_result = _detect_breakout(df)
    signals.extend(breakout_result["signals"])
    evidence.extend(breakout_result["evidence"])
    score += breakout_result["score"]
    metrics.update(breakout_result["metrics"])

    # Candlestick Patterns
    candle_result = _detect_candlestick_patterns(df)
    signals.extend(candle_result["signals"])
    evidence.extend(candle_result["evidence"])
    score += candle_result["score"]
    metrics.update(candle_result["metrics"])

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
    )


def _detect_vcp(df: pd.DataFrame) -> dict:
    """Detect Volatility Contraction Pattern (2-Stage Verification).

    Stage 1: ATR contraction (20% 이상)
    Stage 2: Tightness persistence (20일 중 5+ tight days + 최근 3일 연속 tight)

    Returns:
        - VCP Strong (20 pts): Stage 1 + Stage 2 만족
        - VCP General (10 pts): Stage 1만 만족
    """
    required_cols = ["High", "Low", "ATR"]
    if not _validate_dataframe(df, min_len=20, required_cols=required_cols):
        return _empty_result()

    atr_series = df["ATR"].dropna()
    if len(atr_series) < 8:
        return _empty_result()

    # Stage 1: ATR contraction check
    recent_8 = atr_series.iloc[-8:].values
    first_4_avg = recent_8[:4].mean()
    last_4_avg = recent_8[-4:].mean()

    if first_4_avg == 0:
        return _empty_result()

    contraction_ratio = (first_4_avg - last_4_avg) / first_4_avg

    metrics = {
        "atr_contraction_ratio": round(contraction_ratio, 3),
        "atr_current": round(recent_8[-1], 2),
    }

    # Stage 1 failed
    if contraction_ratio <= PatternThresholds.VCP_ATR_CONTRACTION:
        return {"signals": [], "evidence": [], "metrics": metrics, "score": 0}

    # Stage 2: Tightness persistence check
    last_20 = df.iloc[-20:].copy()
    atr_20 = last_20["ATR"]
    high_20 = last_20["High"]
    low_20 = last_20["Low"]

    # Tight day: High-Low < ATR × 0.5
    tight_threshold = atr_20 * PatternThresholds.VCP_TIGHTNESS_MULTIPLIER
    is_tight = (high_20 - low_20) < tight_threshold

    tight_count = is_tight.sum()
    recent_3_tight = is_tight.iloc[-PatternThresholds.VCP_RECENT_TIGHT_WINDOW :].all()

    metrics["tight_days_count"] = int(tight_count)
    metrics["recent_3_tight"] = bool(recent_3_tight)

    # Determine VCP level
    stage_2_passed = tight_count >= PatternThresholds.VCP_MIN_TIGHT_DAYS and recent_3_tight

    if stage_2_passed:
        # VCP Strong
        return {
            "signals": ["VCP Strong (단계 1+2 만족)"],
            "evidence": [
                f"ATR 수축률 {contraction_ratio * 100:.1f}% (20% 이상)",
                f"Tight days {tight_count}/20 (최근 3일 연속 tight)",
            ],
            "metrics": metrics,
            "score": 20,
        }
    else:
        # VCP General
        return {
            "signals": ["VCP (에너지 응축)"],
            "evidence": [f"ATR 수축률 {contraction_ratio * 100:.1f}% (20% 이상)"],
            "metrics": metrics,
            "score": 10,
        }


def _detect_breakout(df: pd.DataFrame) -> dict:
    """Detect breakout patterns."""
    if "Close" not in df.columns or len(df) < 21:
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}

    latest = df.iloc[-1]
    close = latest.get("Close")
    high = latest.get("High")

    if pd.isna(close) or pd.isna(high):
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}

    close = float(close)
    high = float(high)

    signals = []
    evidence = []
    score = 0
    metrics = {}

    # Rolling 20-day high breakout
    high_20 = df["High"].iloc[-21:-1].max()
    if high > high_20:
        signals.append("돌파 (신고가)")
        evidence.append(f"현재 고가 {high:.2f} > 20일 최고가 {high_20:.2f}")
        score += 20
        metrics["high_20"] = round(high_20, 2)

    # Swing high breakout
    if "Swing_High" in df.columns:
        swing_highs = df["Swing_High"].dropna()
        if not swing_highs.empty:
            last_swing_high = swing_highs.iloc[-1]
            if close > last_swing_high:
                signals.append("스윙 고점 돌파")
                evidence.append(f"종가 {close:.2f} > 최근 스윙 고점 {last_swing_high:.2f}")
                score += 10
                metrics["last_swing_high"] = round(last_swing_high, 2)

    return {"signals": signals, "evidence": evidence, "metrics": metrics, "score": score}


def _detect_candlestick_patterns(df: pd.DataFrame) -> dict:
    """Detect basic candlestick patterns."""
    required_cols = ["Open", "High", "Low", "Close"]
    if not all(col in df.columns for col in required_cols) or len(df) < 2:
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    o = latest.get("Open")
    h = latest.get("High")
    low = latest.get("Low")
    c = latest.get("Close")
    prev_o = prev.get("Open")
    prev_c = prev.get("Close")

    if any(pd.isna(x) for x in [o, h, low, c, prev_o, prev_c]):
        return {"signals": [], "evidence": [], "metrics": {}, "score": 0}

    o, h, low, c = float(o), float(h), float(low), float(c)
    prev_o, prev_c = float(prev_o), float(prev_c)

    signals = []
    evidence = []
    score = 0
    metrics = {}

    body = abs(c - o)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - low
    total_range = h - low

    # Hammer detection (can be bullish or bearish)
    if total_range > 0 and body > 0 and lower_shadow > 2 * body and upper_shadow < body * 0.5:
        signals.append("Hammer (망치형)")
        evidence.append(f"아래 꼬리 {lower_shadow:.2f} > 몸통 {body:.2f}의 2배")
        score += 10
        metrics["hammer_ratio"] = round(lower_shadow / body, 2)

    # Bullish Engulfing detection
    prev_body = abs(prev_c - prev_o)
    if (
        prev_c < prev_o and c > o and c > prev_o and o < prev_c and body > prev_body
    ):  # Prev bearish, current bullish engulfs it
        signals.append("Bullish Engulfing (상승장악형)")
        evidence.append(f"현재 양봉이 이전 음봉 완전 포함 (몸통 {body:.2f} > {prev_body:.2f})")
        score += 15
        metrics["engulfing_body"] = round(body, 2)

    return {"signals": signals, "evidence": evidence, "metrics": metrics, "score": score}

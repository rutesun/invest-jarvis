import pandas as pd

from src.tools.technical.context import common_evidence, pattern_threshold_snapshot
from src.tools.technical.models import ComponentResult, ComponentSignal


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
    VOLUME_MODERATE_MULTIPLIER = 1.2  # 완만한 거래량 증가 하한 (1.2x~1.5x 상승 확증)


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


def analyze_patterns(df: pd.DataFrame, *, common_analysis=None) -> ComponentResult:
    """Analyze chart patterns (VCP, Breakout, Candlestick)."""
    facts = common_evidence(df, common_analysis, "chart.vcp.legacy")
    if df.empty or len(df) < 3:
        return ComponentResult(
            signals=[],
            evidence=[],
            metrics={},
            score=0,
        )

    signals = []
    evidence = []
    metadata = []
    score = 0
    metrics = {}

    # VCP Detection
    vcp_result = _vcp_from_facts(facts)
    signals.extend(vcp_result["signals"])
    evidence.extend(vcp_result["evidence"])
    score += vcp_result["score"]
    metrics.update(vcp_result["metrics"])
    metadata.extend(
        ComponentSignal(
            signal_type="support",
            bias="neutral",
            intent="watch",
            severity="medium",
            source="patterns",
            reason=signal,
        )
        for signal in vcp_result["signals"]
    )

    # Breakout Detection
    breakout_result = _breakout_from_facts(
        common_evidence(df, common_analysis, "chart.legacy.patterns_extra")
    )
    signals.extend(breakout_result["signals"])
    evidence.extend(breakout_result["evidence"])
    score += breakout_result["score"]
    metrics.update(breakout_result["metrics"])
    metadata.extend(
        ComponentSignal(
            signal_type="breakout",
            bias="bullish",
            intent="entry",
            severity="high",
            entry_eligible=True,
            source="patterns",
            reason=signal,
        )
        for signal in breakout_result["signals"]
    )

    # Candlestick Patterns
    candle_result = _candles_from_facts(
        common_evidence(df, common_analysis, "chart.legacy.patterns_extra")
    )
    signals.extend(candle_result["signals"])
    evidence.extend(candle_result["evidence"])
    score += candle_result["score"]
    metrics.update(candle_result["metrics"])
    metadata.extend(
        ComponentSignal(
            signal_type="reversal",
            bias="bullish",
            intent="watch",
            severity="medium",
            source="patterns",
            reason=signal,
        )
        for signal in candle_result["signals"]
    )

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
        signal_metadata=metadata,
    )


def _detect_vcp(df: pd.DataFrame) -> dict:
    """Detect Volatility Contraction Pattern (2-Stage Verification).

    Stage 1: ATR contraction (20% 이상)
    Stage 2: Tightness persistence (20일 중 5+ tight days + 최근 3일 연속 tight)

    Returns:
        - VCP Strong (20 pts): Stage 1 + Stage 2 만족
        - VCP General (10 pts): Stage 1만 만족
    """
    from src.tools.technical.chart_analysis._legacy_components import vcp_values

    return _vcp_from_facts(
        vcp_values(df, thresholds=pattern_threshold_snapshot("chart.vcp.legacy"))
    )


def _detect_breakout(df: pd.DataFrame) -> dict:
    """Detect breakout patterns."""
    from src.tools.technical.chart_analysis._legacy_components import breakout_values

    return _breakout_from_facts(breakout_values(df))


def _detect_candlestick_patterns(df: pd.DataFrame) -> dict:
    """Detect basic candlestick patterns."""
    from src.tools.technical.chart_analysis._legacy_components import candlestick_values

    return _candles_from_facts(candlestick_values(df))


def _vcp_from_facts(values):
    metrics = dict(values.get("metrics", {}))
    if not values.get("in_vcp"):
        return {**_empty_result(), "metrics": metrics}
    ratio = values["atr_contraction_ratio"]
    if values["strong"]:
        return {
            "signals": ["VCP Strong (단계 1+2 만족)"],
            "evidence": [
                f"ATR 수축률 {ratio * 100:.1f}% (20% 이상)",
                f"Tight days {values['tight_days_count']}/20 (최근 3일 연속 tight)",
            ],
            "metrics": metrics,
            "score": 20,
        }
    return {
        "signals": ["VCP (에너지 응축)"],
        "evidence": [f"ATR 수축률 {ratio * 100:.1f}% (20% 이상)"],
        "metrics": metrics,
        "score": 10,
    }


def _breakout_from_facts(values):
    result = _empty_result()
    if values.get("high_breakout"):
        result["signals"].append("돌파 (신고가)")
        result["evidence"].append(
            f"현재 고가 {values['high']:.2f} > 20일 최고가 {values['high_20']:.2f}"
        )
        result["score"] += 20
        result["metrics"]["high_20"] = round(values["high_20"], 2)
    if values.get("swing_high_breakout"):
        result["signals"].append("스윙 고점 돌파")
        result["evidence"].append(
            f"종가 {values['close']:.2f} > 최근 스윙 고점 {values['last_swing_high']:.2f}"
        )
        result["score"] += 10
        result["metrics"]["last_swing_high"] = round(values["last_swing_high"], 2)
    return result


def _candles_from_facts(values):
    result = _empty_result()
    if values.get("hammer"):
        result["signals"].append("Hammer (망치형)")
        result["evidence"].append(
            f"아래 꼬리 {values['lower_shadow']:.2f} > 몸통 {values['body']:.2f}의 2배"
        )
        result["score"] += 10
        result["metrics"]["hammer_ratio"] = round(values["lower_shadow"] / values["body"], 2)
    if values.get("bullish_engulfing"):
        result["signals"].append("Bullish Engulfing (상승장악형)")
        result["evidence"].append(
            f"현재 양봉이 이전 음봉 완전 포함 (몸통 {values['body']:.2f} > {values['previous_body']:.2f})"
        )
        result["score"] += 15
        result["metrics"]["engulfing_body"] = round(values["body"], 2)
    return result

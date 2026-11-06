import pandas as pd
from scipy.signal import argrelextrema as argrelextrema

from src.tools.technical.context import common_evidence
from src.tools.technical.models import ComponentResult, ComponentSignal


def analyze_divergence(df: pd.DataFrame, *, common_analysis=None) -> ComponentResult:
    """Analyze price/indicator divergence patterns."""
    facts = common_evidence(df, common_analysis, "legacy.divergence")
    if df.empty or len(df) < 50:
        return ComponentResult(
            signals=[],
            evidence=["데이터 부족 (50일 이상 필요)"],
            metrics={},
            score=0,
        )

    # Check required columns
    if "Close" not in df.columns or "RSI" not in df.columns:
        return ComponentResult(
            signals=[],
            evidence=["필수 지표 없음"],
            metrics={},
            score=0,
        )

    signals = []
    evidence = []
    metadata = []
    metrics = {}
    score = 0

    metrics.update(facts["metrics"])

    # Bearish divergence (가격 고점↑, RSI 고점↓)
    bearish_div = _divergence_from_fact(facts["rsi_bearish"], "rsi")
    if bearish_div:
        signals.append(bearish_div["signal"])
        evidence.append(bearish_div["evidence"])
        score += bearish_div["score"]
        metadata.append(_divergence_metadata("bearish", bearish_div["signal"]))

    # Bullish divergence (가격 저점↓, RSI 저점↑)
    bullish_div = _divergence_from_fact(facts["rsi_bullish"], "rsi")
    if bullish_div:
        signals.append(bullish_div["signal"])
        evidence.append(bullish_div["evidence"])
        score += bullish_div["score"]
        metadata.append(_divergence_metadata("bullish", bullish_div["signal"]))

    # MACD divergence (if available)
    if "MACD" in df.columns:
        macd_div = _divergence_from_fact(facts["macd"], "macd")
        if macd_div:
            signals.append(macd_div["signal"])
            evidence.append(macd_div["evidence"])
            score += macd_div["score"]
            metadata.append(
                _divergence_metadata(
                    "bearish" if macd_div["score"] < 0 else "bullish", macd_div["signal"]
                )
            )

    # cRSI divergence (if available)
    if "cRSI" in df.columns:
        crsi_div = _divergence_from_fact(facts["crsi"], "crsi")
        if crsi_div:
            signals.append(crsi_div["signal"])
            evidence.append(crsi_div["evidence"])
            score += crsi_div["score"]
            metadata.append(
                _divergence_metadata(
                    "bearish" if crsi_div["score"] < 0 else "bullish", crsi_div["signal"]
                )
            )
            # Stronger signal if both RSI and cRSI agree
            if (bearish_div and "bearish" in crsi_div["signal"].lower()) or (
                bullish_div and "bullish" in crsi_div["signal"].lower()
            ):
                signals.append("RSI + cRSI 다이버전스 일치 (강력)")
                score = int(score * 1.5)

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
        signal_metadata=metadata,
    )


def _divergence_metadata(bias: str, reason: str) -> ComponentSignal:
    return ComponentSignal(
        signal_type="reversal",
        bias=bias,
        intent="watch" if bias == "bullish" else "risk",
        severity="medium",
        source="divergence",
        reason=reason,
    )


def _detect_bearish_divergence(df, price_highs_idx, rsi_highs_idx, price_values, rsi_values):
    """Detect bearish divergence: price making higher highs, RSI making lower highs."""
    from src.tools.technical.chart_analysis._legacy_levels import _matching_divergence

    return _divergence_from_fact(
        _matching_divergence(
            price_values, price_highs_idx, rsi_values, rsi_highs_idx, bearish=True
        ),
        "rsi",
    )


def _detect_bullish_divergence(df, price_lows_idx, rsi_lows_idx, price_values, rsi_values):
    """Detect bullish divergence: price making lower lows, RSI making higher lows."""
    from src.tools.technical.chart_analysis._legacy_levels import _matching_divergence

    return _divergence_from_fact(
        _matching_divergence(price_values, price_lows_idx, rsi_values, rsi_lows_idx, bearish=False),
        "rsi",
    )


def _detect_macd_divergence(df, price_highs_idx, price_lows_idx, price_values):
    """Detect MACD divergence."""
    from src.tools.technical.chart_analysis._legacy_levels import indicator_divergences

    matches = indicator_divergences(
        df, price_values, price_highs_idx, price_lows_idx, column="MACD", fallback=0
    )
    return _divergence_from_fact(matches["bearish"] or matches["bullish"], "macd")


def _detect_crsi_divergence(df, price_highs_idx, price_lows_idx, price_values):
    """Detect cRSI divergence."""
    from src.tools.technical.chart_analysis._legacy_levels import indicator_divergences

    matches = indicator_divergences(
        df, price_values, price_highs_idx, price_lows_idx, column="cRSI", fallback=50
    )
    return _divergence_from_fact(matches["bearish"] or matches["bullish"], "crsi")


def _divergence_from_fact(value, indicator):
    """Consumer-owned wording and magnitudes from a raw matched occurrence."""
    if value is None:
        return None
    bearish = value["bias"] == "bearish"
    p1, p2, i1, i2, change, difference = (
        value[key]
        for key in (
            "price1",
            "price2",
            "indicator1",
            "indicator2",
            "price_change_pct",
            "indicator_difference",
        )
    )
    if indicator == "rsi":
        return {
            "signal": "약세 다이버전스 (Bearish Divergence)"
            if bearish
            else "강세 다이버전스 (Bullish Divergence)",
            "evidence": f"가격 고점 상승 ({p1:.2f}→{p2:.2f}, +{change:.1f}%), RSI 고점 하락 ({i1:.1f}→{i2:.1f}, -{difference:.1f})"
            if bearish
            else f"가격 저점 하락 ({p1:.2f}→{p2:.2f}, -{change:.1f}%), RSI 저점 상승 ({i1:.1f}→{i2:.1f}, +{difference:.1f})",
            "score": -15 if bearish else 15,
        }
    label, decimals = ("MACD", 2) if indicator == "macd" else ("cRSI", 1)
    return {
        "signal": f"{label} {'약세' if bearish else '강세'} 다이버전스",
        "evidence": f"가격{'↑' if bearish else '↓'}, {label}{'↓' if bearish else '↑'} ({i1:.{decimals}f}→{i2:.{decimals}f})",
        "score": -10 if bearish else 10,
    }

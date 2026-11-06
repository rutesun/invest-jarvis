import pandas as pd

from src.tools.technical.context import common_evidence
from src.tools.technical.models import ComponentResult, ComponentSignal


def analyze_risk(df: pd.DataFrame, *, common_analysis=None) -> ComponentResult:
    """Analyze risk levels using support/resistance confluence."""
    facts = common_evidence(df, common_analysis, "legacy.confluence")
    if df.empty or len(df) < 20:
        return ComponentResult(
            signals=[],
            evidence=["데이터 부족"],
            metrics={},
            score=0,
        )

    latest = df.iloc[-1]
    close = float(latest.get("Close", 0))

    if close == 0:
        return ComponentResult(
            signals=[],
            evidence=["가격 데이터 없음"],
            metrics={},
            score=0,
        )

    signals = []
    evidence = []
    metrics = {"close": close}
    score = 0
    metadata = []

    support_levels = facts["support_levels"]
    resistance_levels = facts["resistance_levels"]

    metrics["support_levels_count"] = len(support_levels)
    metrics["resistance_levels_count"] = len(resistance_levels)

    # Calculate confluence (levels within 2% of current price)
    support_confluence = facts["support_confluence"]
    resistance_confluence = facts["resistance_confluence"]

    metrics["support_confluence"] = len(support_confluence)
    metrics["resistance_confluence"] = len(resistance_confluence)

    # Strong support confluence = low risk
    if len(support_confluence) >= 3:
        signals.append("강력 지지 (3개 이상 confluence)")
        evidence.append(f"현재가 근처 지지선 {len(support_confluence)}개")
        score += 15
        metadata.append(_support_metadata("강력 지지 (3개 이상 confluence)"))
    elif len(support_confluence) >= 2:
        signals.append("지지 confluence")
        evidence.append(f"지지선 {len(support_confluence)}개")
        score += 10
        metadata.append(_support_metadata("지지 confluence"))

    # Near resistance = higher risk
    if len(resistance_confluence) >= 3:
        signals.append("강력 저항 (3개 이상 confluence)")
        evidence.append(f"현재가 근처 저항선 {len(resistance_confluence)}개")
        score -= 15
        metadata.append(_resistance_metadata("강력 저항 (3개 이상 confluence)"))
    elif len(resistance_confluence) >= 2:
        signals.append("저항 confluence")
        evidence.append(f"저항선 {len(resistance_confluence)}개")
        score -= 10
        metadata.append(_resistance_metadata("저항 confluence"))

    # Nearest support/resistance distance
    if support_levels:
        nearest_support = max(support_levels, key=lambda x: x["level"])
        support_distance = ((close - nearest_support["level"]) / close) * 100
        metrics["nearest_support"] = round(nearest_support["level"], 2)
        metrics["support_distance_pct"] = round(support_distance, 2)
        evidence.append(
            f"최근 지지선: ${nearest_support['level']:.2f} ({nearest_support['type']}) -{support_distance:.1f}%"
        )

    if resistance_levels:
        nearest_resistance = min(resistance_levels, key=lambda x: x["level"])
        resistance_distance = ((nearest_resistance["level"] - close) / close) * 100
        metrics["nearest_resistance"] = round(nearest_resistance["level"], 2)
        metrics["resistance_distance_pct"] = round(resistance_distance, 2)
        evidence.append(
            f"최근 저항선: ${nearest_resistance['level']:.2f} ({nearest_resistance['type']}) +{resistance_distance:.1f}%"
        )

    # Trend context (서사/메타 전용). SMA50 아래·Supertrend 하락은 minervini·supertrend
    # 컴포넌트가 이미 점수화하므로 여기서는 중복 벌점을 더하지 않는다(추세 이중 카운팅 방지).
    if "SMA_50" in df.columns and not pd.isna(latest.get("SMA_50")):
        sma_50 = float(latest["SMA_50"])
        if close < sma_50:
            evidence.append("가격이 SMA 50 아래 (리스크 증가)")
            metadata.append(_breakdown_metadata("가격이 SMA 50 아래"))

    if "SuperTrend_Dir" in df.columns and not pd.isna(latest.get("SuperTrend_Dir")):
        supertrend_dir = int(latest["SuperTrend_Dir"])
        if supertrend_dir == -1:
            evidence.append("Supertrend 하락 (리스크 증가)")
            metadata.append(_breakdown_metadata("Supertrend 하락"))

    # Stop loss calculation (price - 2×ATR)
    if "ATR" in df.columns and not pd.isna(latest.get("ATR")):
        atr = float(latest["ATR"])
        stop_loss = close - (2 * atr)
        metrics["stop_loss"] = round(stop_loss, 2)
        metrics["stop_loss_distance_pct"] = round(((close - stop_loss) / close) * 100, 2)
        evidence.append(
            f"손절가: ${stop_loss:.2f} (2×ATR, -{metrics['stop_loss_distance_pct']:.1f}%)"
        )

    # Overall risk assessment
    if score >= 15:
        signals.insert(0, "저위험")
    elif score >= 5:
        signals.insert(0, "중저위험")
    elif score <= -15:
        signals.insert(0, "고위험")
    elif score <= -5:
        signals.insert(0, "중고위험")
    else:
        signals.insert(0, "중위험")

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
        signal_metadata=metadata,
    )


def _support_metadata(reason: str) -> ComponentSignal:
    return ComponentSignal(
        signal_type="support",
        bias="bullish",
        intent="hold",
        severity="medium",
        source="risk",
        reason=reason,
    )


def _resistance_metadata(reason: str) -> ComponentSignal:
    return ComponentSignal(
        signal_type="resistance",
        bias="bearish",
        intent="risk",
        severity="medium",
        source="risk",
        reason=reason,
    )


def _breakdown_metadata(reason: str) -> ComponentSignal:
    return ComponentSignal(
        signal_type="breakdown",
        bias="bearish",
        intent="risk",
        severity="medium",
        source="risk",
        reason=reason,
    )

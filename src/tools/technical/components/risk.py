import pandas as pd

from src.tools.technical.models import ComponentResult


def analyze_risk(df: pd.DataFrame) -> ComponentResult:
    """Analyze risk levels using support/resistance confluence."""
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

    # Collect support/resistance levels
    support_levels = []
    resistance_levels = []

    # 1. Dynamic MA support/resistance
    for ma_col in ["SMA_20", "SMA_50", "SMA_150", "SMA_200"]:
        if ma_col in df.columns:
            ma_val = latest.get(ma_col)
            if not pd.isna(ma_val):
                ma_val = float(ma_val)
                if ma_val < close:
                    support_levels.append({"level": ma_val, "type": ma_col})
                else:
                    resistance_levels.append({"level": ma_val, "type": ma_col})

    # 2. Swing High/Low (static levels)
    if "Swing_High" in df.columns:
        swing_highs = df["Swing_High"].dropna().tail(5)
        for val in swing_highs:
            val = float(val)
            if val > close:
                resistance_levels.append({"level": val, "type": "Swing High"})

    if "Swing_Low" in df.columns:
        swing_lows = df["Swing_Low"].dropna().tail(5)
        for val in swing_lows:
            val = float(val)
            if val < close:
                support_levels.append({"level": val, "type": "Swing Low"})

    # 3. Pivot points
    if "Pivot" in df.columns and not pd.isna(latest.get("Pivot")):
        pivot = float(latest["Pivot"])
        if pivot < close:
            support_levels.append({"level": pivot, "type": "Pivot"})
        else:
            resistance_levels.append({"level": pivot, "type": "Pivot"})

    if "S1" in df.columns and not pd.isna(latest.get("S1")):
        s1 = float(latest["S1"])
        if s1 < close:
            support_levels.append({"level": s1, "type": "S1"})

    if "R1" in df.columns and not pd.isna(latest.get("R1")):
        r1 = float(latest["R1"])
        if r1 > close:
            resistance_levels.append({"level": r1, "type": "R1"})

    # 4. Gap levels (unfilled gaps)
    if "Is_Gap_Up" in df.columns and "Gap_Up_Lower" in df.columns:
        gap_up_rows = df[df["Is_Gap_Up"]].tail(3)
        for _idx, row in gap_up_rows.iterrows():
            gap_lower = row.get("Gap_Up_Lower")
            if not pd.isna(gap_lower):
                gap_lower = float(gap_lower)
                if gap_lower < close:
                    support_levels.append({"level": gap_lower, "type": "Gap Up (unfilled)"})

    if "Is_Gap_Down" in df.columns and "Gap_Down_Upper" in df.columns:
        gap_down_rows = df[df["Is_Gap_Down"]].tail(3)
        for _idx, row in gap_down_rows.iterrows():
            gap_upper = row.get("Gap_Down_Upper")
            if not pd.isna(gap_upper):
                gap_upper = float(gap_upper)
                if gap_upper > close:
                    resistance_levels.append({"level": gap_upper, "type": "Gap Down (unfilled)"})

    metrics["support_levels_count"] = len(support_levels)
    metrics["resistance_levels_count"] = len(resistance_levels)

    # Calculate confluence (levels within 2% of current price)
    price_range = close * 0.02
    support_confluence = [s for s in support_levels if abs(s["level"] - close) <= price_range]
    resistance_confluence = [r for r in resistance_levels if abs(r["level"] - close) <= price_range]

    metrics["support_confluence"] = len(support_confluence)
    metrics["resistance_confluence"] = len(resistance_confluence)

    # Strong support confluence = low risk
    if len(support_confluence) >= 3:
        signals.append("강력 지지 (3개 이상 confluence)")
        evidence.append(f"현재가 근처 지지선 {len(support_confluence)}개")
        score += 15
    elif len(support_confluence) >= 2:
        signals.append("지지 confluence")
        evidence.append(f"지지선 {len(support_confluence)}개")
        score += 10

    # Near resistance = higher risk
    if len(resistance_confluence) >= 3:
        signals.append("강력 저항 (3개 이상 confluence)")
        evidence.append(f"현재가 근처 저항선 {len(resistance_confluence)}개")
        score -= 15
    elif len(resistance_confluence) >= 2:
        signals.append("저항 confluence")
        evidence.append(f"저항선 {len(resistance_confluence)}개")
        score -= 10

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

    # Risk penalties
    if "SMA_50" in df.columns and not pd.isna(latest.get("SMA_50")):
        sma_50 = float(latest["SMA_50"])
        if close < sma_50:
            evidence.append("가격이 SMA 50 아래 (리스크 증가)")
            score -= 5

    if "SUPERTd_10_3.0" in df.columns and not pd.isna(latest.get("SUPERTd_10_3.0")):
        supertrend_dir = int(latest["SUPERTd_10_3.0"])
        if supertrend_dir == -1:
            evidence.append("Supertrend 하락 (리스크 증가)")
            score -= 5

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
    )

import pandas as pd

from src.tools.technical.models import ComponentResult, ComponentSignal


def analyze_supertrend(df: pd.DataFrame) -> ComponentResult:
    """Analyze Supertrend signals."""
    if df.empty or len(df) < 2:
        return ComponentResult(
            signals=[],
            evidence=[],
            metrics={},
            score=0,
        )

    # Check for Supertrend columns
    if "SuperTrend_Dir" not in df.columns:
        return ComponentResult(
            signals=[],
            evidence=["Supertrend 데이터 없음"],
            metrics={},
            score=0,
        )

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    supertrend_dir = latest.get("SuperTrend_Dir")
    prev_supertrend_dir = prev.get("SuperTrend_Dir")
    # Select the appropriate trend line based on direction
    supertrend_value = (
        latest.get("SuperTrend_Up")
        if not pd.isna(supertrend_dir) and int(supertrend_dir) == 1
        else latest.get("SuperTrend_Dn")
    )
    close = latest.get("Close")

    if pd.isna(supertrend_dir):
        return ComponentResult(
            signals=[],
            evidence=["Supertrend 값 없음"],
            metrics={},
            score=0,
        )

    supertrend_dir = int(supertrend_dir)
    prev_supertrend_dir = (
        int(prev_supertrend_dir) if not pd.isna(prev_supertrend_dir) else supertrend_dir
    )

    signals = []
    evidence = []
    score = 0
    metadata = []
    metrics = {"supertrend_direction": supertrend_dir}

    if not pd.isna(supertrend_value):
        metrics["supertrend_value"] = round(float(supertrend_value), 2)

    if not pd.isna(close):
        metrics["close"] = round(float(close), 2)

    # Current direction
    if supertrend_dir == 1:
        signals.append("Supertrend 상승")
        evidence.append("Supertrend가 매수 신호")
        score += 20
        metadata.append(
            ComponentSignal(
                signal_type="trend",
                bias="bullish",
                intent="hold",
                severity="medium",
                source="supertrend",
                reason="Supertrend 상승",
            )
        )

        if not pd.isna(close) and not pd.isna(supertrend_value):
            distance = ((float(close) - float(supertrend_value)) / float(supertrend_value)) * 100
            if distance > 5:
                evidence.append(f"가격이 Supertrend 라인보다 {distance:.1f}% 위")
                score += 5
            elif distance < 2:
                evidence.append(f"가격이 Supertrend 라인에 근접 ({distance:.1f}%)")

    elif supertrend_dir == -1:
        signals.append("Supertrend 하락")
        evidence.append("Supertrend가 매도 신호")
        score -= 20
        metadata.append(
            ComponentSignal(
                signal_type="trend",
                bias="bearish",
                intent="risk",
                severity="medium",
                source="supertrend",
                reason="Supertrend 하락",
            )
        )

        if not pd.isna(close) and not pd.isna(supertrend_value):
            distance = ((float(supertrend_value) - float(close)) / float(supertrend_value)) * 100
            if distance > 5:
                evidence.append(f"가격이 Supertrend 라인보다 {distance:.1f}% 아래")
                score -= 5
            elif distance < 2:
                evidence.append(f"가격이 Supertrend 라인에 근접 ({distance:.1f}%)")

    # Direction change (signal)
    if prev_supertrend_dir != supertrend_dir:
        if supertrend_dir == 1:
            signals.append("Supertrend 매수 전환")
            evidence.append("Supertrend 방향이 하락에서 상승으로 전환")
            score += 15
            metadata.append(
                ComponentSignal(
                    signal_type="breakout",
                    bias="bullish",
                    intent="entry",
                    severity="high",
                    entry_eligible=True,
                    source="supertrend",
                    reason="Supertrend 매수 전환",
                )
            )
        else:
            signals.append("Supertrend 매도 전환")
            evidence.append("Supertrend 방향이 상승에서 하락으로 전환")
            score -= 15
            metadata.append(
                ComponentSignal(
                    signal_type="breakdown",
                    bias="bearish",
                    intent="risk",
                    severity="high",
                    source="supertrend",
                    reason="Supertrend 매도 전환",
                )
            )

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
        signal_metadata=metadata,
    )

import pandas as pd
from src.tools.technical.models import ComponentResult


def analyze_supertrend(df: pd.DataFrame) -> ComponentResult:
    """Analyze Supertrend signals."""
    if df.empty or len(df) < 2:
        return ComponentResult(
            signals=[], evidence=[], metrics={}, score=0,
        )

    # Check for Supertrend columns
    if "SUPERTd_10_3.0" not in df.columns:
        return ComponentResult(
            signals=[], evidence=["Supertrend 데이터 없음"], metrics={}, score=0,
        )

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    supertrend_dir = latest.get("SUPERTd_10_3.0")
    prev_supertrend_dir = prev.get("SUPERTd_10_3.0")
    supertrend_value = latest.get("SUPERT_10_3.0")
    close = latest.get("Close")

    if pd.isna(supertrend_dir):
        return ComponentResult(
            signals=[], evidence=["Supertrend 값 없음"], metrics={}, score=0,
        )

    supertrend_dir = int(supertrend_dir)
    prev_supertrend_dir = int(prev_supertrend_dir) if not pd.isna(prev_supertrend_dir) else supertrend_dir

    signals = []
    evidence = []
    score = 0
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
        else:
            signals.append("Supertrend 매도 전환")
            evidence.append("Supertrend 방향이 상승에서 하락으로 전환")
            score -= 15

    return ComponentResult(
        signals=signals, evidence=evidence, metrics=metrics, score=score,
    )

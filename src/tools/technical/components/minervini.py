import pandas as pd

from src.tools.technical.models import ComponentResult


def analyze_minervini(df: pd.DataFrame) -> ComponentResult:
    """Analyze Minervini Stage 2 conditions (7 conditions)."""
    if df.empty or len(df) < 200:
        return ComponentResult(
            signals=[],
            evidence=["데이터 부족 (200일 이상 필요)"],
            metrics={},
            score=0,
        )

    latest = df.iloc[-1]

    def safe(col: str) -> float:
        val = latest.get(col)
        if pd.isna(val) or val is None:
            return 0.0
        return float(val)

    close = safe("Close")
    sma_50 = safe("SMA_50")
    sma_150 = safe("SMA_150")
    sma_200 = safe("SMA_200")
    high_52w = safe("High_52w")
    low_52w = safe("Low_52w")

    if not all([close, sma_50, sma_150, sma_200]):
        return ComponentResult(
            signals=[],
            evidence=["이동평균 계산 불가"],
            metrics={},
            score=0,
        )

    # SMA_200 21일 전 (기존)
    sma_200_prev = 0.0
    if len(df) > 21:
        val = df.iloc[-22].get("SMA_200")
        if not pd.isna(val) and val is not None:
            sma_200_prev = float(val)

    # SMA_150 21일 전 [신규: sma_150_rising 판정용]
    sma_150_prev = 0.0
    if len(df) > 21:
        val = df.iloc[-22].get("SMA_150")
        if not pd.isna(val) and val is not None:
            sma_150_prev = float(val)

    conditions = {
        "ma_stack": close > sma_150 > sma_200,  # 1
        "ma_50_stack": sma_50 > sma_150 > sma_200,  # 2 [신규]
        "sma_150_rising": (sma_150 > sma_150_prev) if sma_150_prev else False,  # 3 [신규]
        "sma_200_rising": (sma_200 > sma_200_prev) if sma_200_prev else False,  # 4
        "above_50": close > sma_50,  # 5
        "above_52w_low_30pct": (close >= low_52w * 1.30) if low_52w else False,  # 6
        "within_52w_high_25pct": (close >= high_52w * 0.75) if high_52w else False,  # 7
    }

    met_count = sum(conditions.values())
    is_stage2 = met_count == 7

    metrics = {
        "conditions_met": float(met_count),
        "is_stage2": 1.0 if is_stage2 else 0.0,
        "close": close,
        "sma_50": sma_50,
        "sma_150": sma_150,
        "sma_200": sma_200,
    }

    def _get_failure_reason(name: str) -> str:
        if name == "ma_stack":
            if close <= sma_150:
                return f"{name}: 미충족 (종가 ${close:.2f} ≤ SMA_150 ${sma_150:.2f})"
            elif sma_150 <= sma_200:
                return f"{name}: 미충족 (SMA_150 ${sma_150:.2f} ≤ SMA_200 ${sma_200:.2f})"
            return f"{name}: 미충족"
        elif name == "ma_50_stack":
            if sma_50 <= sma_150:
                return f"{name}: 미충족 (SMA_50 ${sma_50:.2f} ≤ SMA_150 ${sma_150:.2f})"
            elif sma_150 <= sma_200:
                return f"{name}: 미충족 (SMA_150 ${sma_150:.2f} ≤ SMA_200 ${sma_200:.2f})"
            return f"{name}: 미충족"
        elif name == "sma_150_rising":
            if sma_150_prev:
                return f"{name}: 미충족 (SMA_150 ${sma_150:.2f} ≤ 21일 전 ${sma_150_prev:.2f})"
            return f"{name}: 미충족 (21일 전 데이터 없음)"
        elif name == "sma_200_rising":
            if sma_200_prev:
                return f"{name}: 미충족 (SMA_200 ${sma_200:.2f} ≤ 21일 전 ${sma_200_prev:.2f})"
            return f"{name}: 미충족 (21일 전 데이터 없음)"
        elif name == "above_50":
            return f"{name}: 미충족 (종가 ${close:.2f} ≤ SMA_50 ${sma_50:.2f})"
        elif name == "above_52w_low_30pct":
            if low_52w:
                target = low_52w * 1.30
                return f"{name}: 미충족 (종가 ${close:.2f} < 52주 저점 +30% ${target:.2f})"
            return f"{name}: 미충족 (52주 데이터 없음)"
        elif name == "within_52w_high_25pct":
            if high_52w:
                target = high_52w * 0.75
                return f"{name}: 미충족 (종가 ${close:.2f} < 52주 고점 -25% ${target:.2f})"
            return f"{name}: 미충족 (52주 데이터 없음)"
        return f"{name}: 미충족"

    evidence = []
    for name, met in conditions.items():
        evidence.append(f"{name}: 충족" if met else _get_failure_reason(name))

    if is_stage2:
        return ComponentResult(
            signals=["Stage 2 (강력한 상승 국면)"],
            evidence=evidence,
            metrics=metrics,
            score=40,
        )
    elif conditions["above_50"]:
        return ComponentResult(
            signals=["강세 (Stage 2 미충족)"],
            evidence=evidence,
            metrics=metrics,
            score=25,
        )
    else:
        return ComponentResult(
            signals=["약세/보합"],
            evidence=evidence,
            metrics=metrics,
            score=-20,
        )

import pandas as pd

from src.tools.technical.models import ComponentResult


def analyze_minervini(df: pd.DataFrame) -> ComponentResult:
    """Analyze Minervini Stage 2 conditions."""
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

    # Check SMA_200 rising (vs 21 days ago)
    sma_200_prev = 0.0
    if len(df) > 21:
        val = df.iloc[-22].get("SMA_200")
        if not pd.isna(val) and val is not None:
            sma_200_prev = float(val)

    conditions = {
        "ma_stack": close > sma_150 > sma_200,
        "sma_200_rising": sma_200 > sma_200_prev if sma_200_prev else False,
        "above_50": close > sma_50,
        "above_52w_low_30pct": close >= low_52w * 1.30 if low_52w else False,
        "within_52w_high_25pct": close >= high_52w * 0.75 if high_52w else False,
    }

    met_count = sum(conditions.values())
    metrics = {
        "conditions_met": float(met_count),
        "close": close,
        "sma_50": sma_50,
        "sma_150": sma_150,
        "sma_200": sma_200,
    }

    evidence = []
    for name, met in conditions.items():
        status = "충족" if met else "미충족"
        evidence.append(f"{name}: {status}")

    if met_count == 5:
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

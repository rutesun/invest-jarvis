import pandas as pd
from src.tools.technical.models import ComponentResult


def analyze_volume(df: pd.DataFrame) -> ComponentResult:
    """Analyze volume patterns."""
    if "Vol_SMA_20" not in df.columns or len(df) < 2:
        return ComponentResult(
            signals=[], evidence=["거래량 데이터 없음"], metrics={}, score=0,
        )

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    volume = latest.get("Volume")
    vol_sma_20 = latest.get("Vol_SMA_20")
    close = latest.get("Close")
    prev_close = prev.get("Close")

    if pd.isna(volume) or pd.isna(vol_sma_20) or vol_sma_20 == 0:
        return ComponentResult(
            signals=[], evidence=["거래량 SMA 없음"], metrics={}, score=0,
        )

    volume = float(volume)
    vol_sma_20 = float(vol_sma_20)
    vol_ratio = volume / vol_sma_20

    signals = []
    evidence = []
    score = 0
    metrics = {"vol_ratio": round(vol_ratio, 2), "volume": volume, "vol_sma_20": vol_sma_20}

    price_up = not pd.isna(close) and not pd.isna(prev_close) and float(close) > float(prev_close)
    price_down = not pd.isna(close) and not pd.isna(prev_close) and float(close) < float(prev_close)

    # Volume surge
    if vol_ratio > 2.0:
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
        signals=signals, evidence=evidence, metrics=metrics, score=score,
    )

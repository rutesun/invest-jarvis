import pandas as pd

from src.tools.technical.models import ComponentResult, ComponentSignal


def analyze_crsi(df: pd.DataFrame) -> ComponentResult:
    """Analyze Cycle RSI signals."""
    if "cRSI" not in df.columns or len(df) < 2:
        return ComponentResult(
            signals=[],
            evidence=["cRSI 데이터 없음"],
            metrics={},
            score=0,
        )

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    crsi = latest.get("cRSI")
    crsi_high = latest.get("cRSI_HighBand")
    crsi_low = latest.get("cRSI_LowBand")
    prev_crsi = prev.get("cRSI")

    if pd.isna(crsi) or pd.isna(crsi_high) or pd.isna(crsi_low) or pd.isna(prev_crsi):
        return ComponentResult(
            signals=[],
            evidence=["cRSI 값 부족"],
            metrics={},
            score=0,
        )

    crsi = float(crsi)
    crsi_high = float(crsi_high)
    crsi_low = float(crsi_low)
    prev_crsi = float(prev_crsi)

    signals = []
    evidence = []
    metadata = []
    score = 0
    metrics = {
        "crsi": round(crsi, 2),
        "crsi_high_band": round(crsi_high, 2),
        "crsi_low_band": round(crsi_low, 2),
    }

    band_width = crsi_high - crsi_low

    # Hook Down (매도 시그널)
    if prev_crsi > crsi_high and crsi < crsi_high:
        signals.append("cRSI Hook Down (매도 시그널)")
        evidence.append(f"cRSI {prev_crsi:.1f} → {crsi:.1f}, 상단밴드 {crsi_high:.1f} 하향 이탈")
        score -= 20
        metadata.append(
            ComponentSignal(
                signal_type="overextension",
                bias="bearish",
                intent="risk",
                severity="medium",
                source="crsi",
                reason="cRSI Hook Down",
            )
        )

    # Hook Up (매수 시그널)
    elif prev_crsi < crsi_low and crsi > crsi_low:
        signals.append("cRSI Hook Up (매수 시그널)")
        evidence.append(f"cRSI {prev_crsi:.1f} → {crsi:.1f}, 하단밴드 {crsi_low:.1f} 상향 돌파")
        score += 20
        metadata.append(
            ComponentSignal(
                signal_type="pullback",
                bias="bullish",
                intent="entry",
                severity="medium",
                entry_eligible=True,
                source="crsi",
                reason="cRSI Hook Up",
            )
        )

    # Squeeze (에너지 응축)
    if band_width < 10:
        signals.append("cRSI Squeeze (에너지 응축)")
        evidence.append(f"밴드 폭 {band_width:.1f} < 10")
        score += 5

    # Overbought/Oversold
    if crsi > crsi_high:
        evidence.append(f"cRSI {crsi:.1f} > 상단밴드 {crsi_high:.1f} (과매수)")
        score -= 10
    elif crsi < crsi_low:
        evidence.append(f"cRSI {crsi:.1f} < 하단밴드 {crsi_low:.1f} (과매도)")
        score += 10

    return ComponentResult(
        signals=signals,
        evidence=evidence,
        metrics=metrics,
        score=score,
        signal_metadata=metadata,
    )

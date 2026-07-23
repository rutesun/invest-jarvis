LONG_SMA_FLAT_THRESHOLD_PCT = 0.5


def format_long_sma(value: float | None, slope_pct: float | None) -> str:
    if value is None or slope_pct is None:
        return "N/A · — 데이터 부족"
    if slope_pct > LONG_SMA_FLAT_THRESHOLD_PCT:
        icon, label = "↗", "상승"
    elif slope_pct < -LONG_SMA_FLAT_THRESHOLD_PCT:
        icon, label = "↘", "하락"
    else:
        icon, label = "→", "보합"
    return f"${value:.2f} · {icon} {label} ({slope_pct:+.2f}%/21일)"

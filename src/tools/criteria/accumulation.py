import pandas as pd

from src.tools.criteria.models import AccumulationResult


# 오닐 분산일 임계: 전일 대비 종가 하락폭 (>= 0.2%)
_DISTRIBUTION_DROP = 0.002
# 매집일: 종가가 당일 레인지 상단에 마감 (>= 50%)
_TOP_CLOSE_RATIO = 0.5


def analyze_accumulation(df: pd.DataFrame, window: int = 25) -> AccumulationResult:
    """최근 `window` 거래일의 오닐식 매집일/분산일을 센다.

    분산일: 종가 < 전일종가 × (1 - 0.2%)  AND  거래량 > 전일거래량
    매집일: 종가 > 전일종가  AND  거래량 > 전일거래량  AND  (close-low)/(high-low) >= 0.5
    """
    needed = {"Open", "High", "Low", "Close", "Volume"}
    if df is None or df.empty or not needed.issubset(df.columns) or len(df) < 2:
        return AccumulationResult(
            accumulation_days=0, distribution_days=0, accumulation_ratio=0.0, window=window
        )

    recent = df.tail(window + 1).reset_index(drop=True)  # +1: 첫 행의 전일 비교용
    acc = 0
    dist = 0
    for i in range(1, len(recent)):
        prev_close = float(recent.loc[i - 1, "Close"])
        prev_vol = float(recent.loc[i - 1, "Volume"])
        close = float(recent.loc[i, "Close"])
        high = float(recent.loc[i, "High"])
        low = float(recent.loc[i, "Low"])
        vol = float(recent.loc[i, "Volume"])

        vol_up = vol > prev_vol
        if not vol_up:
            continue

        if close < prev_close * (1 - _DISTRIBUTION_DROP):
            dist += 1
        elif close > prev_close:
            rng = high - low
            top_close = (close - low) / rng if rng > 0 else 1.0
            if top_close >= _TOP_CLOSE_RATIO:
                acc += 1

    total = acc + dist
    ratio = acc / total if total > 0 else 0.0
    return AccumulationResult(
        accumulation_days=acc,
        distribution_days=dist,
        accumulation_ratio=round(ratio, 4),
        window=window,
    )

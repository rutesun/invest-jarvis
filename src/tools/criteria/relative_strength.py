import pandas as pd

from src.tools.criteria.models import RelativeStrengthResult


_RP_SMA = 252  # 맨스필드 기준선 (≈1년)
_SLOPE_DAYS = 20  # 4주
_PERF_DAYS = 126  # 6개월
_RS_CROSS_LOOKBACK = 60  # RS 전환 탐색 윈도우


def _detect_rs_cross(mansfield_series: pd.Series, lookback: int = _RS_CROSS_LOOKBACK):
    """최근 lookback 내 mansfield 부호 전환. (type, ISO date, days_ago). 진짜 -1↔+1 만."""
    s = mansfield_series.dropna()
    if len(s) < 2:
        return None, None, None
    recent = s.tail(lookback)
    sign = recent.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    for i in range(len(sign) - 1, 0, -1):
        cur, prev = sign.iloc[i], sign.iloc[i - 1]
        if cur != 0 and prev != 0 and cur != prev:
            cross_date = recent.index[i]
            days_ago = len(s) - 1 - s.index.get_loc(cross_date)
            return (
                "양전환" if cur > 0 else "음전환",
                cross_date.strftime("%Y-%m-%d"),
                int(days_ago),
            )
    return None, None, None


def compute_relative_strength(
    stock_df: pd.DataFrame, index_df: pd.DataFrame, index_symbol: str
) -> RelativeStrengthResult:
    """맨스필드 RS. stock_df/index_df는 'Close' 컬럼 + 날짜 인덱스.

    순수 함수 — 네트워크 호출 없음. RS ≠ RSI.
    """
    s = stock_df["Close"].dropna()
    i = index_df["Close"].dropna()
    common = s.index.intersection(i.index)
    rp = (s.loc[common] / i.loc[common]).dropna()

    if len(rp) < 2:
        return RelativeStrengthResult(
            mansfield_rs=0.0,
            outperform_6m=0.0,
            rp_slope_4w=0.0,
            index_symbol=index_symbol,
        )

    sma_window = min(_RP_SMA, len(rp))
    rp_sma = rp.rolling(window=sma_window, min_periods=max(20, sma_window // 4)).mean()
    last_rp = float(rp.iloc[-1])
    last_sma = float(rp_sma.iloc[-1])
    mansfield = ((last_rp / last_sma) - 1.0) * 100.0 if last_sma else 0.0

    mansfield_series = ((rp / rp_sma) - 1.0) * 100.0
    cross_type, cross_date, cross_days_ago = _detect_rs_cross(mansfield_series)

    slope_n = min(_SLOPE_DAYS, len(rp) - 1)
    rp_slope = float(rp.iloc[-1] - rp.iloc[-1 - slope_n])

    def _perf(series: pd.Series) -> float:
        n = min(_PERF_DAYS, len(series) - 1)
        past = float(series.iloc[-1 - n])
        return ((float(series.iloc[-1]) - past) / past) * 100.0 if past else 0.0

    outperform = _perf(s.loc[common]) - _perf(i.loc[common])

    return RelativeStrengthResult(
        mansfield_rs=round(mansfield, 2),
        outperform_6m=round(outperform, 2),
        rp_slope_4w=round(rp_slope, 6),
        index_symbol=index_symbol,
        rs_cross_type=cross_type,
        rs_cross_date=cross_date,
        rs_cross_days_ago=cross_days_ago,
    )

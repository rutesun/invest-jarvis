import pandas as pd

from src.tools.playbook.models import MarketRegimeResult


def assess_market_regime(index_df: pd.DataFrame, index_symbol: str) -> MarketRegimeResult:
    """지수 종가 데이터로 시장환경(상승/조정/하락)을 판정한다.

    allow_new_buy = True 조건 (모두 충족 필요):
      - 종가 > SMA50
      - 종가 > SMA200
      - SMA200이 21거래일 전보다 상승 중
    """
    close = index_df["Close"].dropna()
    if len(close) < 200:
        return MarketRegimeResult(
            regime="unknown",
            allow_new_buy=False,
            index_symbol=index_symbol,
            detail="데이터 부족(<200)",
        )

    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    last = float(close.iloc[-1])
    s50 = float(sma50.iloc[-1])
    s200 = float(sma200.iloc[-1])

    above = last > s50 and last > s200
    rising = float(sma200.iloc[-1]) > float(sma200.iloc[-21])
    allow = bool(above and rising)

    if allow:
        regime = "상승"
    elif last > s200:
        regime = "조정"
    else:
        regime = "하락"

    ma_desc = "SMA50·200" if above else "below MA"
    sma200_desc = "상승" if rising else "하락"
    return MarketRegimeResult(
        regime=regime,
        allow_new_buy=allow,
        index_symbol=index_symbol,
        detail=f"close>({ma_desc}), SMA200 {sma200_desc}",
    )

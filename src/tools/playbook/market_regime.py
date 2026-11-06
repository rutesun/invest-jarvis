import pandas as pd

from src.tools.playbook.common import playbook_evidence
from src.tools.playbook.models import MarketRegimeResult


def assess_market_regime(
    index_df: pd.DataFrame, index_symbol: str, *, common_analysis=None
) -> MarketRegimeResult:
    """지수 종가 데이터로 시장환경(상승/조정/하락)을 판정한다.

    allow_new_buy = True 조건 (모두 충족 필요):
      - 종가 > SMA50
      - 종가 > SMA200
      - SMA200이 21거래일 전보다 상승 중
    """
    from src.tools.technical.chart_analysis._legacy_playbook import market_regime_values

    values = (
        playbook_evidence(
            index_df,
            common_analysis,
            "chart.market.regime",
            role="market",
            index_symbol=index_symbol,
        )
        if common_analysis is not None
        else market_regime_values(index_df)
    )
    if not values["available"]:
        return MarketRegimeResult(
            regime="unknown",
            allow_new_buy=False,
            index_symbol=index_symbol,
            detail="데이터 부족(<200)",
        )
    ma_desc = "SMA50·200" if values["above"] else "below MA"
    sma200_desc = "상승" if values["rising"] else "하락"
    return MarketRegimeResult(
        regime=values["regime"],
        allow_new_buy=values["above"] and values["rising"],
        index_symbol=index_symbol,
        detail=f"close>({ma_desc}), SMA200 {sma200_desc}",
    )

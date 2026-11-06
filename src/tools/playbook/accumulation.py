import pandas as pd

from src.tools.playbook.common import playbook_evidence
from src.tools.playbook.models import AccumulationResult


# 오닐 분산일 임계: 전일 대비 종가 하락폭 (>= 0.2%)
_DISTRIBUTION_DROP = 0.002
# 매집일: 종가가 당일 레인지 상단에 마감 (>= 50%)
_TOP_CLOSE_RATIO = 0.5


def analyze_accumulation(
    df: pd.DataFrame, window: int = 25, *, common_analysis=None
) -> AccumulationResult:
    """최근 `window` 거래일의 오닐식 매집일/분산일을 센다.

    분산일: 종가 < 전일종가 × (1 - 0.2%)  AND  거래량 > 전일거래량
    매집일: 종가 > 전일종가  AND  거래량 > 전일거래량  AND  (close-low)/(high-low) >= 0.5
    """
    from src.tools.technical.chart_analysis._legacy_playbook import accumulation_values

    values = (
        playbook_evidence(df, common_analysis, "chart.accumulation.days")
        if common_analysis is not None
        else accumulation_values(df, window=window)
    )
    if values["window"] != window:
        raise ValueError("common_analysis accumulation window contract mismatch")
    return AccumulationResult(
        **{
            key: values[key]
            for key in (
                "accumulation_days",
                "distribution_days",
                "accumulation_ratio",
                "window",
            )
        }
    )

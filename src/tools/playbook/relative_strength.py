import pandas as pd

from src.tools.playbook.common import playbook_evidence
from src.tools.playbook.models import RelativeStrengthResult


_RP_SMA = 252  # 맨스필드 기준선 (≈1년)
_SLOPE_DAYS = 20  # 4주
_PERF_DAYS = 126  # 6개월


def compute_relative_strength(
    stock_df: pd.DataFrame, index_df: pd.DataFrame, index_symbol: str, *, common_analysis=None
) -> RelativeStrengthResult:
    """맨스필드 RS. stock_df/index_df는 'Close' 컬럼 + 날짜 인덱스.

    순수 함수 — 네트워크 호출 없음. RS ≠ RSI.
    """
    from src.tools.technical.chart_analysis._legacy_playbook import relative_strength_values

    values = (
        playbook_evidence(
            stock_df, common_analysis, "chart.rs", market=index_df, index_symbol=index_symbol
        )
        if common_analysis is not None
        else relative_strength_values(stock_df, index_df)
    )
    if values.get("reasons") == ("INPUT_MISSING",):
        raise KeyError("Close")
    if "valid_common_count" in values:
        count = values["valid_common_count"]
        if 2 <= count < 20:
            raise ValueError(f"min_periods 20 must be <= window {count}")
        if count < 2:
            return RelativeStrengthResult(
                mansfield_rs=0.0,
                outperform_6m=0.0,
                rp_slope_4w=0.0,
                index_symbol=index_symbol,
            )
    return RelativeStrengthResult(
        index_symbol=index_symbol,
        **{key: values[key] for key in ("mansfield_rs", "outperform_6m", "rp_slope_4w")},
    )

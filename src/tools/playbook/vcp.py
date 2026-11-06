import pandas as pd

from src.tools.playbook.common import playbook_evidence
from src.tools.playbook.models import VcpResult
from src.tools.technical.components.patterns import _detect_vcp as _detect_vcp
from src.tools.technical.context import pattern_threshold_snapshot


_PIVOT_LOOKBACK = 20
_VOL_MULT = 1.5


def detect_vcp_breakout(df: pd.DataFrame, *, common_analysis=None) -> VcpResult:
    """기존 _detect_vcp(수축)에 '마지막 수축 피벗 상향 돌파 + 거래량' 판정을 더한다.

    반환:
      - in_vcp=True, breakout=True: 수축 확인 + 피벗 돌파 + 거래량 급증
      - in_vcp=True, breakout=False: 수축만 확인, 돌파 아직
      - in_vcp=False, breakout=False: 수축 없음
    """
    from src.tools.technical.chart_analysis._legacy_playbook import playbook_vcp_values

    values = (
        playbook_evidence(df, common_analysis, "chart.vcp.playbook")
        if common_analysis is not None
        else playbook_vcp_values(df, thresholds=pattern_threshold_snapshot("chart.vcp.playbook"))
    )
    if not values["in_vcp"] or values["pivot"] is None:
        return VcpResult(
            in_vcp=values["in_vcp"],
            pivot=None,
            breakout=False,
            detail="수축 없음 또는 데이터 부족",
        )
    return VcpResult(
        in_vcp=True,
        pivot=values["pivot"],
        breakout=values["breakout"],
        detail=f"pivot={values['pivot_raw']:.2f}, close={values['close']:.2f}, vol_ok={values['vol_ok']}",
    )

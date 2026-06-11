import pandas as pd

from src.tools.playbook.models import VcpResult
from src.tools.technical.components.patterns import _detect_vcp


_PIVOT_LOOKBACK = 20
_VOL_MULT = 1.5


def detect_vcp_breakout(df: pd.DataFrame) -> VcpResult:
    """기존 _detect_vcp(수축)에 '마지막 수축 피벗 상향 돌파 + 거래량' 판정을 더한다.

    반환:
      - in_vcp=True, breakout=True: 수축 확인 + 피벗 돌파 + 거래량 급증
      - in_vcp=True, breakout=False: 수축만 확인, 돌파 아직
      - in_vcp=False, breakout=False: 수축 없음
    """
    vcp = _detect_vcp(df)
    in_vcp = bool(vcp.get("signals"))

    if not in_vcp or len(df) < _PIVOT_LOOKBACK + 1:
        return VcpResult(
            in_vcp=in_vcp,
            pivot=None,
            breakout=False,
            detail="수축 없음 또는 데이터 부족",
        )

    recent = df.iloc[-(_PIVOT_LOOKBACK + 1) :]
    pivot = float(recent["High"].iloc[:-1].max())

    last = df.iloc[-1]
    last_close = float(last["Close"])

    vol_sma = None
    if "Vol_SMA_50" in df.columns:
        val = last.get("Vol_SMA_50")
        if val is not None and not pd.isna(val):
            vol_sma = float(val)

    vol_ok = vol_sma is not None and float(last["Volume"]) >= vol_sma * _VOL_MULT
    breakout = bool(last_close > pivot and vol_ok)

    return VcpResult(
        in_vcp=True,
        pivot=round(pivot, 2),
        breakout=breakout,
        detail=f"pivot={pivot:.2f}, close={last_close:.2f}, vol_ok={vol_ok}",
    )

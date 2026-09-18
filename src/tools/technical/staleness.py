"""마지막 봉 종가 결측(trailing NaN-Close) 방어.

yfinance는 아직 마감되지 않은 최근 일봉을 Close=NaN으로 반환할 때가 있다. 이 봉을 정제하지
않으면 소비 지점마다 마지막 봉 해석이 갈려(스냅샷은 이전 유효 봉, market context는 close=0.0)
스테일 종가가 조용히 흘러나간다. 여기서 trailing NaN-Close 봉을 한 번에 걷어내고, 몇 개를
걷어냈는지(=가정 위반 여부)를 호출부가 표면화할 수 있게 돌려준다.
"""

from dataclasses import dataclass, field

import pandas as pd


def _fmt(index_value) -> str:
    """DatetimeIndex는 날짜만, 그 외 인덱스는 값 그대로 문자열화."""
    if hasattr(index_value, "date"):
        return str(index_value.date())
    return str(index_value)


@dataclass(frozen=True)
class StaleClose:
    """trailing NaN-Close 정제 결과 요약."""

    dropped_rows: int
    dropped_dates: list[str] = field(default_factory=list)
    last_valid_date: str | None = None

    @property
    def is_stale(self) -> bool:
        return self.dropped_rows > 0


def drop_trailing_nan_close(df: pd.DataFrame) -> tuple[pd.DataFrame, StaleClose]:
    """끝에서부터 연속된 Close=NaN 봉을 걷어낸다.

    중간의 NaN-Close는 건드리지 않는다(트레일링만 대상). 반환한 StaleClose로 몇 개를
    걷어냈는지·마지막 유효 봉 날짜를 알 수 있다.
    """
    # yfinance 단일 티커가 MultiIndex 컬럼을 줄 수 있어 Close 추출 전에 평탄화한다
    # (indicators/from_analysis와 동일한 방어). 평탄화 후 Close는 1-D Series.
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)

    if df.empty or "Close" not in df.columns:
        last_valid = _fmt(df.index[-1]) if not df.empty else None
        return df, StaleClose(dropped_rows=0, dropped_dates=[], last_valid_date=last_valid)

    is_valid = df["Close"].notna().to_numpy()

    # 끝에서부터 유효한 첫 봉을 찾는다.
    keep = len(df)
    while keep > 0 and not is_valid[keep - 1]:
        keep -= 1

    if keep == len(df):
        return df, StaleClose(dropped_rows=0, dropped_dates=[], last_valid_date=_fmt(df.index[-1]))

    dropped_dates = [_fmt(idx) for idx in df.index[keep:]]
    cleaned = df.iloc[:keep]
    last_valid_date = _fmt(cleaned.index[-1]) if not cleaned.empty else None
    return cleaned, StaleClose(
        dropped_rows=len(df) - keep,
        dropped_dates=dropped_dates,
        last_valid_date=last_valid_date,
    )

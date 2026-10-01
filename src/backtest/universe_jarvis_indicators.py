"""확정 시스템 v3를 jarvis 지표(IndicatorCalculator)로 다시 돌려 성과가 유지되는지 본다.

백테스트 자체 지표 중 jarvis와 식이 다른 두 가지만 바꾼다.
- ATR14: 14일 단순평균 → pandas_ta 기본(Wilder)
- 슈퍼트렌드(10,3): 자체 구현 → pandas_ta
SMA·거래량·고가 창은 두 쪽 식이 같아서 그대로 둔다. 규칙·설정·종목·기간은 universe_validate와 같다.
엔진화 전에 재료를 jarvis 한 곳으로 모을 수 있는지 판단하기 위한 비교다. 거래비용 미반영.
"""

from __future__ import annotations

import os
import sys
import warnings

import numpy as np


warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import universe_v04
import universe_validate
from preset_v0 import add_indicators
from universe_extra import EXTRA
from universe_matrix import UNIVERSE
from universe_transition import prepare, simulate
from universe_validate import BASE, CLIMAX, PERIODS, cluster_ci, load_long

from src.tools.technical.indicators import IndicatorCalculator


# 워크트리에는 가격 캐시가 없으므로 환경변수로 기존 캐시 위치를 받는다.
universe_validate.LONG_CACHE = os.environ.get("BT_LONG_CACHE", universe_validate.LONG_CACHE)
_script_supertrend = universe_v04.supertrend_dir


def prepare_jarvis(df, spy_close) -> dict:
    j = IndicatorCalculator().calculate(df.copy())
    d = add_indicators(df, spy_close)
    d["ATR"] = j["ATR"].values
    st = np.nan_to_num(j["SuperTrend_Dir"].values.astype(float), nan=1.0)
    universe_v04.supertrend_dir = lambda h, low, c, period=10, mult=3.0: st
    try:
        return prepare(d)
    finally:
        universe_v04.supertrend_dir = _script_supertrend


def run(prep: dict) -> list[dict]:
    out = []
    for s, f in prep.items():
        for x in simulate(f, **BASE, **CLIMAX):
            x["tk"] = s
            out.append(x)
    return out


def summary(tr: list[dict]) -> str:
    R = np.array([x["R"] for x in tr])
    lo, hi = cluster_ci(tr)
    srt = np.sort(R)[::-1]
    return (
        f"{len(R):>5}{100 * (R > 0).mean():>6.0f}%{R.mean():>7.2f}{np.median(R):>7.2f}"
        f"  [{lo:>5.2f},{hi:>5.2f}]{srt[10:].mean():>9.2f}"
    )


def main() -> None:
    tickers = {**UNIVERSE, **EXTRA}
    data = load_long(list(tickers) + ["SPY"])
    spy = data["SPY"]
    loaded = [s for s in tickers if s in data]
    print(f"종목 {len(loaded)}/{len(tickers)}   설정: v3 (필터 없음, D 경로, 2d1R, 과열 규칙)")

    base = run({s: prepare(add_indicators(data[s], spy["Close"])) for s in loaded})
    jarv = run({s: prepare_jarvis(data[s], spy["Close"]) for s in loaded})

    head = f"  {'':16}{'횟수':>5}{'승률':>7}{'평균R':>7}{'중앙R':>7}  {'95% 구간':>13}{'상위10제외':>9}"
    for pname, (a, b) in PERIODS.items():
        print("\n" + "=" * 80)
        print(f"[{pname}]")
        print(head)
        for name, tr in (("백테스트 지표", base), ("jarvis 지표", jarv)):
            print(f"  {name:16}" + summary([x for x in tr if a <= x["entry_date"] < b]))

    key = lambda x: (x["tk"], x["entry_date"], x["kind"])  # noqa: E731
    bk, jk = {key(x): x for x in base}, {key(x): x for x in jarv}
    same = bk.keys() & jk.keys()
    same_exit = [k for k in same if bk[k]["exit_date"] == jk[k]["exit_date"]]
    print("\n" + "=" * 80)
    print("[매매 일치도 — 전체 기간]")
    print(
        f"  백테스트 {len(bk)}건 / jarvis {len(jk)}건 / 진입 일치 {len(same)}건 / 진입·청산 모두 일치 {len(same_exit)}건"
    )
    for kind in ("S", "D"):
        b_k = [x for x in base if x["kind"] == kind]
        j_k = [x for x in jarv if x["kind"] == kind]
        print(
            f"  {kind}: 백테스트 {len(b_k)}건 {np.mean([x['R'] for x in b_k]):.2f}R"
            f" / jarvis {len(j_k)}건 {np.mean([x['R'] for x in j_k]):.2f}R"
        )


if __name__ == "__main__":
    main()

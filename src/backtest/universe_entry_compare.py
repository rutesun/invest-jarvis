"""진입 타이밍 3종 비교 (청산·손절·과열 규칙은 확정 시스템 v3와 동일, 바닥 경로 D 제외).

E1 150일선 첫 돌파: 전날 종가<=150일선, 오늘 종가>150일선, 거래량 1.4배 (기울기 무관)
E2 30주선 위 20일 신고가: 종가>상승 150일선 + 20일 신고가 첫 돌파 + 거래량 1.4배
E3 30주선 위 50일 신고가: 종가>상승 150일선 + 50일 신고가 첫 돌파 + 거래량 1.4배 (현행 S)
"""

from __future__ import annotations

import warnings

import numpy as np


warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_extra import EXTRA
from universe_matrix import UNIVERSE
from universe_transition import prepare, simulate
from universe_validate import PERIODS, cluster_ci, load_long


EXIT = {
    "T": False,
    "D": False,
    "X": None,
    "exit150": "2d1R",
    "trim": "x",
    "arm_ext": 0.40,
    "trim_st": False,
    "trim_frac": 1.0,
    "trim_ma": "sma20",
}


def entry_arrays(d):
    c = d["Close"].values

    def prev(a):
        return np.r_[np.nan, a[:-1]]

    sma150 = d["SMA150"].values
    rising = d["SMA150_slope"].values > 0
    vol_ok = d["Volume"].values > 1.4 * d["volSMA20"].values
    hi20 = d["High"].rolling(20).max().shift(1).values
    hi50 = d["hi50_prev"].values

    def fresh(hi):
        return (c > hi) & ~(prev(c) > prev(hi))

    cross150 = (prev(c) <= prev(sma150)) & (c > sma150)
    above = (c > sma150) & rising
    return {
        "E1 150일선 첫 돌파": cross150 & vol_ok,
        "E2 30주선 위 20일 신고가": above & fresh(hi20) & vol_ok,
        "E3 30주선 위 50일 신고가": above & fresh(hi50) & vol_ok,
    }


def main():
    tickers = {**UNIVERSE, **EXTRA}
    data = load_long(list(tickers) + ["SPY"])
    spy = data["SPY"]
    loaded = [s for s in tickers if s in data]
    runs = {}
    for s in loaded:
        d = add_indicators(data[s], spy["Close"])
        f = prepare(d)
        for name, arr in entry_arrays(d).items():
            g = dict(f)
            g["swing"] = np.nan_to_num(arr, nan=0).astype(bool)
            for x in simulate(g, **EXIT):
                x["tk"] = s
                runs.setdefault(name, []).append(x)

    head = (
        f"  {'진입':26}{'횟수':>5}{'승률':>7}{'평균R':>7}{'중앙R':>7}  {'95% 구간':>13}"
        f"{'상위10제외':>9}{'보유일':>6}{'비용후R':>8}{'1년당R':>7}"
    )
    for pname, (a, b) in PERIODS.items():
        print("\n" + "=" * 104)
        print(f"[{pname}]  73종목, 청산=v3(30주선 2일/−1R + 과열 규칙)")
        print(head)
        for name, tr in runs.items():
            t = [x for x in tr if a <= x["entry_date"] < b]
            R = np.array([x["R"] for x in t])
            lo, hi = cluster_ci(t)
            srt = np.sort(R)[::-1]
            cost = np.array(
                [0.002 / x["risk_pct"] + x["n_partial"] * 0.001 / x["risk_pct"] for x in t]
            )
            years = 5.0
            print(
                f"  {name:26}{len(R):>5}{100 * (R > 0).mean():>6.0f}%{R.mean():>7.2f}{np.median(R):>7.2f}"
                f"  [{lo:>5.2f},{hi:>5.2f}]{srt[10:].mean():>9.2f}"
                f"{int(np.median([x['days'] for x in t])):>6}{(R - cost).mean():>8.2f}{R.sum() / years / 73:>7.2f}"
            )
    print("\n  1년당R = 종목 하나에서 1년에 버는 R 합계(매매 빈도 반영). 종목당 동시 보유는 1건.")


if __name__ == "__main__":
    main()

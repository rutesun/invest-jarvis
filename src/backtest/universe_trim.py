"""50일선 이탈·슈퍼트렌드 하락 전환 시 25% 매도 → 눌림목 반등에 재매수.

기준: S+D(바닥 경로) + 새 청산(150일선 2일 연속 또는 150일선-1R 아래).
TR0 매도만, TR1 재매수=50일선 위+슈퍼트렌드 상승, TR2 재매수=50일선 위+전날 고가 돌파.
비용후R은 전량 매매 왕복 + 부분 매매(25%) 각 한쪽 0.1% 반영.
"""

from __future__ import annotations

import warnings

import numpy as np

warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_extra import EXTRA
from universe_matrix import UNIVERSE, load_universe
from universe_trailing_beta import trailing_beta
from universe_transition import AVOID, CUTOFF, prepare, simulate

VARIANTS = {
    "기준 (부분매매 없음)": dict(),
    "이격25%→50일선 25%매도→회복재매수": dict(trim="x", arm_ext=0.25, trim_st=False, trim_frac=0.25),
    "이격25%→50일선 50%매도→회복재매수": dict(trim="x", arm_ext=0.25, trim_st=False, trim_frac=0.5),
    "이격25%→50일선 전량→회복재매수": dict(trim="x", arm_ext=0.25, trim_st=False, trim_frac=1.0),
    "이격40%→50일선 전량→회복재매수": dict(trim="x", arm_ext=0.40, trim_st=False, trim_frac=1.0),
    "이격40%→50일선 전량→100일선눌림": dict(trim="x", arm_ext=0.40, trim_st=False, trim_frac=1.0, rebuy="pullback100"),
    "이격40%→50일선 전량 매도만": dict(trim="sell_only", arm_ext=0.40, trim_st=False, trim_frac=1.0),
    "이격40%→20일선 전량→회복재매수": dict(trim="x", arm_ext=0.40, trim_st=False, trim_frac=1.0, trim_ma="sma20"),
}


def row(name, tr):
    R = np.array([x["R"] for x in tr])
    cost = np.array([0.002 / x["risk_pct"] + x["n_partial"] * 0.25 * 0.001 / x["risk_pct"] for x in tr])
    is_r = [x["R"] for x in tr if x["entry_date"] < CUTOFF]
    oos_r = [x["R"] for x in tr if x["entry_date"] >= CUTOFF]
    big = np.sort(R)[::-1]
    days = int(np.median([x["days"] for x in tr]))
    return (f"  {name:31}{len(R):>5}{100*(R>0).mean():>6.0f}%{R.mean():>7.2f}{np.mean(is_r):>7.2f}"
            f"{np.mean(oos_r):>7.2f}{(R-cost).mean():>8.2f}{np.mean(big[5:]):>9.2f}{R.min():>7.2f}"
            f"{np.mean([x['n_partial'] for x in tr]):>7.1f}{days:>6}")


def main():
    data = load_universe(list(UNIVERSE) + list(EXTRA) + ["SPY"])
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]
    prep = {s: prepare(add_indicators(data[s], spy["Close"])) for s in loaded}
    elig = {s: np.nan_to_num(trailing_beta(data[s]["Close"], spy["Close"]), nan=0) >= 1.3 for s in loaded}
    head = (f"  {'변형':31}{'횟수':>5}{'승률':>7}{'평균R':>7}{'IS R':>7}{'OOS R':>7}{'비용후R':>8}"
            f"{'상위5제외':>9}{'최악R':>7}{'부분매매':>7}{'보유일':>6}")
    groups = {
        "73종목 전체 (필터 없음)": (loaded, False),
        "고베타 관문 (과거1년 β≥1.3, 손실섹터 제외)": ([s for s in loaded if tickers[s] not in AVOID], True),
    }
    for g, (keys, gate) in groups.items():
        print("\n" + "=" * 100)
        print(f"[{g}]  진입 S+D, 청산 150일선 2일/−1R")
        print(head)
        for name, cfg in VARIANTS.items():
            tr = []
            for s in keys:
                tr += simulate(prep[s], T=False, D=True, X=None, exit150="2d1R",
                               eligible=elig[s] if gate else None, **cfg)
            print(row(name, tr))


if __name__ == "__main__":
    main()

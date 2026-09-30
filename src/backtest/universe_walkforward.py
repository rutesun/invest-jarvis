"""Walk-forward: 엣지가 '한 국면 운'인지, 여러 기간에 걸쳐 꾸준한지 본다.

preset은 고정 규칙이라 튜닝은 없다. 대신 6개월 단위로 진입일을 쪼개
기간별 preset·베타 엣지를 나열하고, '몇 개 기간에서 플러스였나'로 견고함을 잰다.
효율을 위해 각 종목·preset은 전 구간 1회 시뮬 후 진입일로 버킷팅한다.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


warnings.filterwarnings("ignore")

from preset_v0 import add_indicators, simulate
from universe_extra import EXTRA
from universe_matrix import PRESETS, UNIVERSE, agg, beta_bucket, beta_vs_spy, load_universe


EDGES = list(pd.date_range("2021-10-01", "2026-10-01", freq="6MS"))
LABELS = [
    f"{EDGES[i].strftime('%y/%m')}~{EDGES[i + 1].strftime('%y/%m')}" for i in range(len(EDGES) - 1)
]


def bucket_of(dt) -> int | None:
    ts = pd.Timestamp(dt)
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= ts < EDGES[i + 1]:
            return i
    return None


def main() -> None:
    syms = list(UNIVERSE) + list(EXTRA) + ["SPY"]
    data = load_universe(syms)
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]

    # 전 구간 1회 시뮬 후 버킷팅
    trades_by: dict = {}
    betas: dict = {}
    for s in loaded:
        d = add_indicators(data[s], spy["Close"])
        betas[s] = beta_vs_spy(data[s], spy)
        trades_by[s] = {p: simulate(d, p) for p in PRESETS}

    P = len(LABELS)
    # 기간 × preset
    per: dict = {i: {p: [] for p in PRESETS} for i in range(P)}
    # 기간 × 베타버킷 (와인스타인 기준)
    per_beta: dict = {i: {"고": [], "저": []} for i in range(P)}

    for s in loaded:
        bb = beta_bucket(betas[s])
        for p in PRESETS:
            for t in trades_by[s][p]:
                bi = bucket_of(t["entry_date"])
                if bi is None:
                    continue
                per[bi][p].append(t)
                if p == "WEINSTEIN":
                    if bb == "고베타(≥1.3)":
                        per_beta[bi]["고"].append(t)
                    elif bb == "저베타(<0.8)":
                        per_beta[bi]["저"].append(t)

    print(f"Walk-forward: 6개월 × {P}구간   종목 {len(loaded)}")
    print("\n" + "=" * 92)
    print("① 기간별 preset 기댓값R  (괄호=매매수)")
    print(f"  {'기간':16}" + "".join(f"{p:>18}" for p in PRESETS))
    for i in range(P):
        cells = []
        for p in PRESETS:
            a = agg(per[i][p])
            cells.append(f"{a['expR']:>6} ({a['n']:>3})" if a["n"] else f"{'-':>12}")
        print(f"  {LABELS[i]:16}" + "".join(f"{c:>18}" for c in cells))

    # 견고함: 몇 개 기간에서 플러스였나 (매매 있는 기간만)
    print("\n" + "=" * 92)
    print("② 견고함 — 매매가 있던 기간 중 '플러스'였던 비율")
    for p in PRESETS:
        active = [i for i in range(P) if agg(per[i][p])["n"] >= 5]
        pos = [i for i in active if agg(per[i][p])["expR"] > 0]
        avg = np.mean([agg(per[i][p])["expR"] for i in active]) if active else 0
        print(f"  {p:10}  플러스 {len(pos)}/{len(active)} 기간   기간평균 expR {avg:>5.2f}")
    # 와인스타인이 세 preset 중 1등이던 기간 수
    wins = 0
    active_all = 0
    for i in range(P):
        vals = {p: agg(per[i][p]) for p in PRESETS}
        if all(vals[p]["n"] >= 5 for p in PRESETS):
            active_all += 1
            if vals["WEINSTEIN"]["expR"] == max(v["expR"] for v in vals.values()):
                wins += 1
    print(f"  WEINSTEIN 1위:  {wins}/{active_all} 기간 (셋 다 매매≥5인 기간 기준)")

    print("\n" + "=" * 92)
    print("③ 고베타 vs 저베타 (WEINSTEIN 기댓값R, 괄호=매매수)")
    print(f"  {'기간':16}{'고베타':>16}{'저베타':>16}")
    hi_wins = 0
    hi_active = 0
    for i in range(P):
        a = agg(per_beta[i]["고"])
        b = agg(per_beta[i]["저"])
        ac = f"{a['expR']:>6} ({a['n']:>2})" if a["n"] else f"{'-':>10}"
        bc = f"{b['expR']:>6} ({b['n']:>2})" if b["n"] else f"{'-':>10}"
        print(f"  {LABELS[i]:16}{ac:>16}{bc:>16}")
        if a["n"] >= 5 and b["n"] >= 5:
            hi_active += 1
            if a["expR"] > b["expR"]:
                hi_wins += 1
    print(f"\n  고베타 > 저베타:  {hi_wins}/{hi_active} 기간 (양쪽 매매≥5인 기간 기준)")
    print("\n  주: 워밍업(SMA200)으로 초기 구간은 매매가 적다. 매매수 적은 셀은 노이즈.")


if __name__ == "__main__":
    main()

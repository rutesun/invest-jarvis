"""시장 국면 필터 실험: 'SPY > SMA200일 때만 진입'이 조정기 붕괴를 막나.

walk-forward에서 드러난 약점(2024중반~2025초 momentum 붕괴)이
시장 필터로 제거되는지, 기간별로 필터 없음 vs 있음을 비교한다. (거래비용 미반영)
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


warnings.filterwarnings("ignore")

from preset_v0 import add_indicators, simulate
from universe_extra import EXTRA
from universe_matrix import PRESETS, UNIVERSE, agg, load_universe


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


def by_period(trades_by: dict, preset: str) -> dict:
    per: dict = {i: [] for i in range(len(LABELS))}
    for s in trades_by:
        for t in trades_by[s][preset]:
            bi = bucket_of(t["entry_date"])
            if bi is not None:
                per[bi].append(t)
    return per


def main() -> None:
    syms = list(UNIVERSE) + list(EXTRA) + ["SPY"]
    data = load_universe(syms)
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]

    spy_close = data["SPY"]["Close"]  # 지수 > 월간 10-EMA (미네르비니 원문)
    ema10_m = spy_close.resample("ME").last().ewm(span=10, adjust=False).mean()
    ema10_daily = ema10_m.reindex(spy_close.index, method="ffill")  # 직전 완료월 기준(ffill)
    market_up = spy_close > ema10_daily
    up_ratio = market_up.mean()
    print(
        f"시장 필터: SPY > 월간 10-EMA일 때만 진입 (미네르비니 원문).  상승국면 비율 {up_ratio:.0%}   종목 {len(loaded)}"
    )

    base: dict = {}
    filt: dict = {}
    for s in loaded:
        d = add_indicators(data[s], data["SPY"]["Close"])
        mo = market_up.reindex(d.index).ffill().fillna(False)
        base[s] = {p: simulate(d, p) for p in PRESETS}
        filt[s] = {p: simulate(d, p, market_ok=mo) for p in PRESETS}

    # ① 전체 종합: 필터 없음 vs 있음
    print("\n" + "=" * 88)
    print("① 전체 종합  (필터 없음 → 있음)")
    print(
        f"  {'preset':10}{'base expR':>11}{'base n':>8}   {'filt expR':>11}{'filt n':>8}{'매매감소':>9}"
    )
    for p in PRESETS:
        a = agg([t for s in loaded for t in base[s][p]])
        b = agg([t for s in loaded for t in filt[s][p]])
        cut = f"-{100 * (1 - b['n'] / a['n']):.0f}%" if a["n"] else "-"
        print(f"  {p:10}{a['expR']:>11}{a['n']:>8}   {b['expR']:>11}{b['n']:>8}{cut:>9}")

    # ② 기간별 (붕괴 구간 복구 확인)
    for p in PRESETS:
        pb, pf = by_period(base, p), by_period(filt, p)
        print("\n" + "=" * 88)
        print(f"② {p}  기간별 기댓값R  (base → filt, 괄호=매매수)")
        for i in range(len(LABELS)):
            a, b = agg(pb[i]), agg(pf[i])
            ac = f"{a['expR']:>6}({a['n']:>3})" if a["n"] else f"{'-':>10}"
            bc = f"{b['expR']:>6}({b['n']:>3})" if b["n"] else f"{'-':>10}"
            mark = ""
            if a["n"] >= 5 and a["expR"] < 0 and b["n"] >= 3 and b["expR"] > a["expR"]:
                mark = "  ↑복구"
            print(f"  {LABELS[i]:16}{ac:>12}  →{bc:>12}{mark}")

    # ③ 견고함 요약
    print("\n" + "=" * 88)
    print("③ 견고함: 매매≥5 기간 중 플러스 비율  (base → filt)")
    for p in PRESETS:
        pb, pf = by_period(base, p), by_period(filt, p)
        ab = [i for i in pb if agg(pb[i])["n"] >= 5]
        posb = [i for i in ab if agg(pb[i])["expR"] > 0]
        af = [i for i in pf if agg(pf[i])["n"] >= 5]
        posf = [i for i in af if agg(pf[i])["expR"] > 0]
        avgb = np.mean([agg(pb[i])["expR"] for i in ab]) if ab else 0
        avgf = np.mean([agg(pf[i])["expR"] for i in af]) if af else 0
        print(
            f"  {p:10}  base {len(posb)}/{len(ab)} (평균 {avgb:>5.2f})"
            f"   →  filt {len(posf)}/{len(af)} (평균 {avgf:>5.2f})"
        )


if __name__ == "__main__":
    main()

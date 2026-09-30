"""진입 품질 비교: 청산을 넓은 추적(SMA150)으로 고정하고 진입만 바꿔 A/B 비교.

질문: "미네르비니 진입 품질(Trend Template+RS+52주고)"을 넣으면 그냥 돌파보다 나은가?
- 청산 고정 = 넓은 추적(종가<SMA150), 초기 손절 = min(SMA150, 진입-3ATR)  → 스윙/포지션
- 진입 A(plain): 상승(>SMA150, 상승) + 50일 신고가 돌파 + 거래량 1.4x
- 진입 B(quality): A + Trend Template(>50>150>200, 200상승, 52주고 75%↑, RS>0, 과열 아님)
per-trade R 기준(≥2주 보유자에게 맞는 지표). 거래비용 미반영.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_extra import EXTRA
from universe_matrix import UNIVERSE, agg, beta_bucket, beta_vs_spy, load_universe


def entry_plain(d: pd.DataFrame, i: int) -> bool:
    r, pr = d.iloc[i], d.iloc[i - 1]
    if any(pd.isna(r[k]) for k in ("SMA150", "SMA150_slope", "volSMA20", "hi50_prev")):
        return False
    if pd.isna(pr["hi50_prev"]):
        return False
    breakout = r["Close"] > r["hi50_prev"] and not (pr["Close"] > pr["hi50_prev"])
    return bool(
        r["Close"] > r["SMA150"]
        and r["SMA150_slope"] > 0
        and breakout
        and r["Volume"] > 1.4 * r["volSMA20"]
    )


def entry_quality(d: pd.DataFrame, i: int) -> bool:
    if not entry_plain(d, i):
        return False
    r = d.iloc[i]
    if any(pd.isna(r[k]) for k in ("SMA50", "SMA200", "SMA200_slope", "hi252")):
        return False
    tt = r["Close"] > r["SMA50"] > r["SMA150"] > r["SMA200"] and r["SMA200_slope"] > 0
    rs_ok = True
    if "rs6" in d.columns:
        if pd.isna(r["rs6"]):
            return False
        rs_ok = r["rs6"] > 0
    return bool(tt and r["Close"] >= 0.75 * r["hi252"] and r["Close"] < r["SMA50"] * 1.30 and rs_ok)


def simulate_widetrail(d: pd.DataFrame, entry_fn) -> list[dict]:
    """공통 청산: 종가<SMA150 넓은 추적, 초기 손절 min(SMA150, 진입-3ATR)."""
    trades: list[dict] = []
    n = len(d)
    i = 60
    while i < n - 1:
        if not entry_fn(d, i):
            i += 1
            continue
        entry = d.iloc[i + 1]["Open"]
        r = d.iloc[i]
        if pd.isna(entry) or entry <= 0 or pd.isna(r["SMA150"]) or pd.isna(r["ATR"]):
            i += 1
            continue
        stop = min(r["SMA150"], entry - 3 * r["ATR"])
        if stop >= entry:
            i += 1
            continue
        risk = entry - stop
        entry_idx = i + 1
        exit_price = exit_idx = None
        j = entry_idx
        while j < n:
            rj = d.iloc[j]
            if rj["Low"] <= stop:
                exit_price, exit_idx = stop, j
                break
            if not pd.isna(rj["SMA150"]) and rj["Close"] < rj["SMA150"]:
                exit_price, exit_idx = rj["Close"], j
                break
            j += 1
        if exit_price is None:
            exit_price, exit_idx = d.iloc[n - 1]["Close"], n - 1
        trades.append(
            {
                "R": (exit_price - entry) / risk,
                "ret": (exit_price / entry - 1) * 100,
                "days": exit_idx - entry_idx,
                "entry_date": d.index[entry_idx].date(),
                "risk_pct": risk / entry,
            }
        )
        i = exit_idx + 1
    return trades


def med_days(trades: list[dict]) -> int:
    return int(np.median([t["days"] for t in trades])) if trades else 0


def main() -> None:
    syms = list(UNIVERSE) + list(EXTRA) + ["SPY"]
    data = load_universe(syms)
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]

    A: dict[str, list[dict]] = {}
    B: dict[str, list[dict]] = {}
    betas: dict[str, float] = {}
    for s in loaded:
        d = add_indicators(data[s], spy["Close"])
        betas[s] = beta_vs_spy(data[s], spy)
        A[s] = simulate_widetrail(d, entry_plain)
        B[s] = simulate_widetrail(d, entry_quality)

    print(f"진입 품질 비교 (청산=넓은 추적 SMA150 고정)   종목 {len(loaded)}   거래비용 미반영")

    ta = [t for s in loaded for t in A[s]]
    tb = [t for s in loaded for t in B[s]]
    sa, sb = agg(ta), agg(tb)
    print("\n" + "=" * 78)
    print("① 전체 (per-trade R)")
    print(f"  {'진입':22}{'expR':>7}{'승률':>6}{'payoff':>8}{'매매수':>7}{'중앙보유일':>9}")
    print(
        f"  {'A: 그냥 돌파':22}{sa['expR']:>7}{int(sa['win']):>5}%{sa['payoff']:>8}{sa['n']:>7}{med_days(ta):>9}"
    )
    print(
        f"  {'B: 미네르비니 품질':20}{sb['expR']:>7}{int(sb['win']):>5}%{sb['payoff']:>8}{sb['n']:>7}{med_days(tb):>9}"
    )

    def matrix(title: str, groups: list[str], keyfn) -> None:
        print("\n" + "=" * 78)
        print(title + "   (expR / 승률% / 매매수)")
        print(f"  {'그룹':16}{'A: 그냥 돌파':>22}{'B: 미네르비니 품질':>24}")
        for g in groups:
            keys = [s for s in loaded if keyfn(s) == g]
            a = agg([t for s in keys for t in A[s]])
            b = agg([t for s in keys for t in B[s]])
            ac = f"{a['expR']:>6} / {int(a['win']):>3}% / {a['n']:>3}" if a["n"] else f"{'-':>16}"
            bc = f"{b['expR']:>6} / {int(b['win']):>3}% / {b['n']:>3}" if b["n"] else f"{'-':>16}"
            print(f"  {g:16}{ac:>22}{bc:>24}")

    matrix(
        "② 베타 버킷별",
        ["고베타(≥1.3)", "중베타(0.8~1.3)", "저베타(<0.8)"],
        lambda s: beta_bucket(betas[s]),
    )
    matrix("③ 섹터별", sorted(set(tickers.values())), lambda s: tickers[s])


if __name__ == "__main__":
    main()

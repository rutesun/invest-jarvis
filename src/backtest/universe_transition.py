"""SWING_W150에 v0.4 조각을 하나씩 붙여 baseline을 이기는지 본다.

조각 1(T): 추세 전환(TRANSITION) + 초기 신호로 추가 진입. 손절은 최근 20일 저점-0.5ATR(최대 -15%).
          상승 30주선 위로 올라서기 전에는 손절만, 올라선 뒤에는 30주선 이탈 청산.
조각 1'(D): 200일선 아래 바닥(DEEP_RECOVERY) 경로를 같은 방식으로 추가.
조각 2(X): 진입 후 +30% 이상이면 청산을 촘촘하게(X1 최고종가-10%, X2 종가<20일선).
트레이드당 1R. 청산·손절 체결은 baseline(simulate_widetrail)과 같은 방식. 거래비용 미반영.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_entry_quality import entry_plain
from universe_extra import EXTRA
from universe_matrix import UNIVERSE, beta_vs_spy, load_universe
from universe_v04 import features

CUTOFF = pd.Timestamp("2024-09-29").date()
AVOID = {"ConsDisc", "Energy"}
TIGHTEN_AT = 0.30

VARIANTS = {
    "A  baseline (SWING_W150)": dict(T=False, D=False, X=None),
    "B  + 촘촘 청산 X1(고점-10%)": dict(T=False, D=False, X="pct10"),
    "C  + 촘촘 청산 X2(20일선)": dict(T=False, D=False, X="sma20"),
    "D  + 전환 진입 T": dict(T=True, D=False, X=None),
    "E  + 전환 T + 바닥 D": dict(T=True, D=True, X=None),
    "H  + 바닥 D만": dict(T=False, D=True, X=None),
    "A2 baseline + 새 청산": dict(T=False, D=False, X=None, exit150="2d1R"),
    "D2 + 전환 T + 새 청산": dict(T=True, D=False, X=None, exit150="2d1R"),
    "H2 + 바닥 D + 새 청산": dict(T=False, D=True, X=None, exit150="2d1R"),
    "E2 + T + D + 새 청산": dict(T=True, D=True, X=None, exit150="2d1R"),
    "F  + 전환 T + X1": dict(T=True, D=False, X="pct10"),
    "G  + 전환 T + X2": dict(T=True, D=False, X="sma20"),
}


def prepare(d: pd.DataFrame) -> dict:
    f = features(d)
    f["swing"] = np.array([entry_plain(d, i) if i >= 60 else False for i in range(len(d))])
    f["sma150"] = d["SMA150"].values
    f["slope150"] = d["SMA150_slope"].values
    f["low20"] = d["Low"].rolling(20).min().values
    f["sma100"] = d["Close"].rolling(100).mean().values
    return f


def simulate(f: dict, T: bool, D: bool, X: str | None, exit150: str = "1d",
             eligible: np.ndarray | None = None, trim: str | None = None,
             trim_ma: str = "sma50", trim_st: bool = True, exit_ma: str = "sma150",
             trim_frac: float = 0.25, arm_ext: float | None = None, rebuy: str = "reclaim") -> list[dict]:
    """exit150: '1d' 종가가 150일선 아래면 매도 / '2d1R' 2일 연속 아래 또는 150일선-1R 아래면 매도."""
    c, o, h, l = f["c"], f["o"], f["h"], f["l"]
    n = len(c)
    trades: list[dict] = []
    t = 250
    while t < n - 1:
        if eligible is not None and not eligible[t]:
            t += 1
            continue
        kind = None
        if f["swing"][t]:
            kind = "S"
        elif T and f["transition"][t] and (f["fresh20"][t] or f["reclaim50"][t]) and not f["overext"][t]:
            kind = "T"
        elif D and f["deep"][t] and (f["fresh20"][t] or f["reclaim50"][t]):
            kind = "D"
        if kind is None:
            t += 1
            continue
        entry = o[t + 1]
        atr = f["atr"][t]
        if np.isnan(entry) or np.isnan(atr):
            t += 1
            continue
        if kind == "S":
            stop = min(f["sma150"][t], entry - 3 * atr)
        else:
            stop = max(f["low20"][t] - 0.5 * atr, entry * 0.85)
        if not stop < entry:
            t += 1
            continue
        risk = entry - stop
        ei = t + 1
        graduated = kind == "S"
        maxc = entry
        prev_below = False
        units = 1.0
        armed = False
        realized = 0.0  # 부분 매매로 확정된 손익 (가격 단위 × 비중)
        lots = [(1.0, entry)]
        n_partial = 0
        xp = xi = None
        why = "end"
        for k in range(ei, n):
            if l[k] <= stop:
                xp, xi, why = stop, k, "stop"
                break
            maxc = max(maxc, c[k])
            if trim:
                tm = f[trim_ma]
                if arm_ext is not None and c[k] / f["sma50"][k] - 1 >= arm_ext:
                    armed = True
                can_sell = armed if arm_ext is not None else True
                broke = c[k] < tm[k] and c[k - 1] >= tm[k - 1]
                st_flip = trim_st and f["st"][k] == -1 and f["st"][k - 1] == 1
                if units == 1.0 and can_sell and (broke or st_flip):
                    avg = np.average([p for _, p in lots], weights=[u for u, _ in lots])
                    realized += trim_frac * (c[k] - avg)
                    units = 1.0 - trim_frac
                    lots = [(units, avg)] if units > 0 else []
                    armed = False
                    n_partial += 1
                elif units < 1.0 and trim != "sell_only":
                    if rebuy == "pullback100":
                        near = l[max(ei, k - 4):k + 1].min() <= f["sma100"][k] * 1.03
                        ok = near and c[k] > f["sma100"][k] and c[k] > h[k - 1]
                    elif trim == "rebuy_st" and arm_ext is None:
                        ok = c[k] > tm[k] and (f["st"][k] == 1 or not trim_st)
                    else:
                        ok = c[k] > tm[k] and c[k] > h[k - 1]
                    if ok:
                        lots.append((1.0 - units, c[k]))
                        units = 1.0
                        n_partial += 1
            if not graduated and c[k] > f["sma150"][k] and f["slope150"][k] > 0:
                graduated = True
            if X and maxc / entry - 1 >= TIGHTEN_AT:
                if (X == "pct10" and c[k] < maxc * 0.90) or (X == "sma20" and c[k] < f["sma20"][k]):
                    xp, xi, why = c[k], k, "tighten"
                    break
            if graduated:
                em = f[exit_ma]
                below = c[k] < em[k]
                if exit150 == "1d":
                    hit = below
                else:
                    hit = (below and prev_below) or c[k] < em[k] - risk
                prev_below = below
                if hit:
                    xp, xi, why = c[k], k, "sma150"
                    break
        if xp is None:
            xp, xi = c[-1], n - 1
        pnl = realized + sum(u * (xp - p) for u, p in lots)
        trades.append(dict(kind=kind, entry_date=f["dates"][ei], exit_date=f["dates"][xi], entry=entry,
                           exit=xp, R=pnl / risk, ret=pnl / entry * 100, days=xi - ei,
                           why=why, risk_pct=risk / entry, n_partial=n_partial))
        t = xi + 1
    return trades


def row(name: str, tr: list[dict]) -> str:
    if not tr:
        return f"  {name:30} 없음"
    R = np.array([x["R"] for x in tr])
    cost = np.array([0.002 / x["risk_pct"] for x in tr])  # 매수·매도 각 0.1%, 1R=명목×risk_pct
    is_r = [x["R"] for x in tr if x["entry_date"] < CUTOFF]
    oos_r = [x["R"] for x in tr if x["entry_date"] >= CUTOFF]
    return (f"  {name:30}{len(R):>5}{100*(R>0).mean():>6.0f}%{R.mean():>7.2f}{R.sum():>8.1f}"
            f"{int(np.median([x['days'] for x in tr])):>6}{np.mean(is_r):>7.2f}{np.mean(oos_r):>7.2f}"
            f"{(R-cost).mean():>8.2f}")


def main() -> None:
    data = load_universe(list(UNIVERSE) + list(EXTRA) + ["SPY"])
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]
    betas = {s: beta_vs_spy(data[s], spy) for s in loaded}
    prepared = {s: prepare(add_indicators(data[s], spy["Close"])) for s in loaded}
    results = {name: {s: simulate(prepared[s], **cfg) for s in loaded} for name, cfg in VARIANTS.items()}

    groups = {
        "전체 73종목": loaded,
        "고베타 대상(β≥1.3, 손실섹터 제외)": [s for s in loaded if betas[s] >= 1.3 and tickers[s] not in AVOID],
        "그 외 종목": [s for s in loaded if not (betas[s] >= 1.3 and tickers[s] not in AVOID)],
    }
    head = f"  {'변형':30}{'횟수':>5}{'승률':>7}{'평균R':>7}{'합계R':>8}{'보유일':>6}{'IS R':>7}{'OOS R':>7}{'비용후R':>8}"
    print("SWING_W150 + v0.4 조각   (트레이드당 1R, 거래비용은 비용후R만 반영)")
    for g, keys in groups.items():
        print("\n" + "=" * 96)
        print(f"[{g}] {len(keys)}종목")
        print(head)
        for name in VARIANTS:
            print(row(name, [x for s in keys for x in results[name][s]]))

    print("\n" + "=" * 96)
    print("[진입 종류별]  전체 73종목")
    print(head)
    for name in ("D  + 전환 진입 T", "D2 + 전환 T + 새 청산", "H  + 바닥 D만", "H2 + 바닥 D + 새 청산"):
        allt = [x for s in loaded for x in results[name][s]]
        for kind, label in (("S", "기존 돌파 S"), ("T", "전환 T"), ("D", "바닥 D")):
            sub = [x for x in allt if x["kind"] == kind]
            if sub:
                print(row(f"{name[:2]} {label}", sub))


if __name__ == "__main__":
    main()

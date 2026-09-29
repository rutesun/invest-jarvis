"""v0.4 단계형 레시피(STAGED_V04) vs 확정 시스템(SWING_W150) 비교.

단위는 계좌 R(1R = 계좌의 0.5% 손실). v0.4는 진입 경로마다 위험 예산이 달라서
(탐색 0.25~0.5R, 본 매수 1R, 추가 0.5R) 트레이드당 R 대신 에피소드당 계좌 R로 비교한다.
v0.5에서 제외된 POWER_GAP/POCKET_PIVOT은 넣지 않는다. 거래비용 미반영.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_entry_quality import entry_plain, simulate_widetrail
from universe_extra import EXTRA
from universe_matrix import UNIVERSE, beta_vs_spy, load_universe

UNIT = 0.005
COST_PER_SIDE = 0.001  # 수수료+슬리피지, 매수·매도 각각 명목금액의 0.1%
CUTOFF = pd.Timestamp("2024-09-29").date()
AVOID = {"ConsDisc", "Energy"}
LEVEL_EXPOSURE = [1.0, 0.85, 0.65, 0.35]


def supertrend_dir(h, l, c, period=10, mult=3.0):
    n = len(c)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    atr = pd.Series(tr).rolling(period).mean().values
    hl2 = (h + l) / 2
    ub, lb = hl2 + mult * atr, hl2 - mult * atr
    fub, flb = ub.copy(), lb.copy()
    d = np.ones(n)
    for i in range(1, n):
        if np.isnan(atr[i]) or np.isnan(fub[i - 1]):
            continue
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
        if d[i - 1] == 1:
            d[i] = -1 if c[i] < flb[i] else 1
        else:
            d[i] = 1 if c[i] > fub[i] else -1
    return d


def confirmed_pivots(h, l):
    """pivot은 i+3 거래일 종가 이후에만 알려진 것으로 처리 (미래정보 차단)."""
    n = len(l)
    pl, ph = [], []
    for i in range(3, n - 3):
        if l[i] < l[i - 3:i].min() and l[i] <= l[i + 1:i + 4].min():
            pl.append((i + 3, l[i]))
        if h[i] > h[i - 3:i].max() and h[i] >= h[i + 1:i + 4].max():
            ph.append((i + 3, h[i]))
    higher_low = np.zeros(n, bool)
    lhll = np.zeros(n, bool)
    lows, highs, j, k = [], [], 0, 0
    for t in range(n):
        while j < len(pl) and pl[j][0] <= t:
            lows.append(pl[j][1]); j += 1
        while k < len(ph) and ph[k][0] <= t:
            highs.append(ph[k][1]); k += 1
        if len(lows) >= 2:
            higher_low[t] = lows[-1] > lows[-2]
            if len(highs) >= 2:
                lhll[t] = lows[-1] < lows[-2] and highs[-1] < highs[-2]
    return higher_low, lhll


def features(d: pd.DataFrame) -> dict:
    c, o, h, l, v = (d[k].values.astype(float) for k in ("Close", "Open", "High", "Low", "Volume"))
    s = lambda a: pd.Series(a, index=d.index)
    sma20, sma50, sma150, sma200 = (d[f"SMA{w}"].values for w in (20, 50, 150, 200))
    atr = d["ATR"].values
    prev = lambda a: np.r_[np.nan, a[:-1]]
    vr20 = v / s(v).rolling(20).mean().shift(1).values
    rng = h - l
    cl = np.where(rng > 0, (c - l) / np.where(rng > 0, rng, 1), 0.5)
    hi20p = s(h).rolling(20).max().shift(1).values
    lo20p = s(l).rolling(20).min().shift(1).values
    hi5p = s(h).rolling(5).max().shift(1).values
    lo5p = s(l).rolling(5).min().shift(1).values
    st = supertrend_dir(h, l, c)
    higher_low, lhll = confirmed_pivots(h, l)
    sma20_slope = sma20 - prev(prev(prev(prev(prev(sma20)))))
    ret5 = c / np.r_[[np.nan] * 5, c[:-5]] - 1
    dist20_atr = (c - sma20) / atr
    overext = (dist20_atr >= 2.5) | (c / sma20 - 1 >= 0.15)
    fresh20 = (c > hi20p) & ~(prev(c) > prev(hi20p))
    reclaim50 = (prev(c) <= prev(sma50)) & (c > sma50)
    valid50 = s(reclaim50.astype(float)).rolling(5).max().values.astype(bool) & (c >= sma50)
    cross20 = (prev(c) <= prev(sma20)) & (c > sma20)
    strong_reclaim = (cross20 | reclaim50) & (cl >= 0.7)
    tight_pb = ((hi5p - lo5p) <= 1.5 * atr) & (c > hi5p)
    hb = ((c < lo20p) & (vr20 >= 1.5)) | ((c < sma50) & (cl <= 0.25) & (vr20 >= 1.5) & (st == -1)) \
        | ((c < sma200) & (c < sma50) & (st == -1) & lhll)
    stage2 = (c > sma50) & (sma50 > sma150) & (sma150 > sma200) & (d["SMA200_slope"].values > 0)
    trend = ~hb & (stage2 | ((c > sma200) & (c > sma50) & (sma20 > sma50) & (st == 1)))
    groups = (((c > sma20) | valid50).astype(int) + ((sma20_slope > 0) | higher_low).astype(int)
              + (st == 1).astype(int))
    transition = ~hb & ~trend & (c > sma200) & (groups >= 2)
    deep = ~hb & (c < sma200) & (c > sma20) & (c > sma50) & (sma20_slope > 0) & higher_low & (st == 1)
    below20, below50 = c < sma20, c < sma50
    lv1 = (ret5 >= 0.20) & (dist20_atr >= 2.5)
    lv2 = below20 & prev(below20).astype(bool)
    below50_3 = below50 & prev(below50).astype(bool) & prev(prev(below50)).astype(bool)
    lv3 = below50 & prev(below50).astype(bool) & ((sma20 <= sma50) | below50_3)
    return dict(st=st, c=c, o=o, h=h, l=l, sma20=sma20, sma50=sma50, atr=atr, cl=cl, hi20p=hi20p, lo5p=lo5p,
                overext=overext, fresh20=fresh20, reclaim50=reclaim50, cross20=cross20,
                strong_reclaim=strong_reclaim, tight_pb=tight_pb, hb=hb, trend=trend,
                transition=transition, deep=deep, lv1=lv1, lv2=lv2, lv3=lv3,
                dates=[x.date() for x in d.index])


def confirm_stop(f, t):
    """본 매수 확인 신호별 구조 손절."""
    if f["fresh20"][t]:
        return f["hi20p"][t] - 0.5 * f["atr"][t]
    if f["tight_pb"][t]:
        return f["lo5p"][t] - 0.5 * f["atr"][t]
    level = f["sma20"][t] if f["cross20"][t] else f["sma50"][t]
    return level - 0.5 * f["atr"][t]


def early_stop(f, t):
    if f["fresh20"][t]:
        return f["hi20p"][t] - 0.5 * f["atr"][t]
    return f["sma50"][t] - 0.5 * f["atr"][t]


def simulate_v04(d: pd.DataFrame) -> list[dict]:
    f = features(d)
    c, o, lo = f["c"], f["o"], f["l"]
    n = len(c)
    episodes: list[dict] = []
    pos = None
    pending = None

    def confirm_any(t):
        return bool(f["fresh20"][t] or f["strong_reclaim"][t] or f["tight_pb"][t])

    def buy(price, budget, cap, stop):
        rps = price - stop
        cur = pos["shares"] * price if pos else 0.0
        notional = min(budget * UNIT * price / rps, cap, 1.0 - cur)
        return max(notional, 0.0) / price

    def close_episode(t, price, reason):
        nonlocal pos
        pos["pnl"] += pos["shares"] * (price - pos["avg"])
        pos["traded"] += pos["shares"] * price
        episodes.append(dict(traded=pos["traded"], entry_date=f["dates"][pos["start"]], exit_date=f["dates"][t], path=pos["path"],
                             promoted=pos["promoted"], winner=pos["winner_seen"], max_level=pos["max_level"],
                             R=pos["pnl"] / UNIT, days=t - pos["start"], reason=reason))
        pos = None

    for t in range(250, n):
        # 1) t 시가에 전날 결정 집행
        if pending:
            kind = pending[0]
            if kind == "entry" and pos is None:
                _, path, budget, cap, hard, struct, trig = pending
                price = o[t]
                if price <= trig * 1.05:
                    stop = max(struct, price * (1 - hard))
                    if stop < price:
                        sh = buy(price, budget, cap, stop)
                        if sh > 0:
                            pos = dict(traded=sh * price, shares=sh, avg=price, stop=stop, rps0=price - stop, start=t,
                                       path=path, pstate="PROBE" if path != "DIRECT" else "CORE",
                                       mode="NORMAL", age=0, adds=0, maxc=price, pnl=0.0,
                                       promoted=False, winner_seen=False, max_level=0, level=0,
                                       peak=0.0, rec=0, early_close=trig, early_t=t - 1)
            elif kind in ("promote", "add") and pos is not None:
                _, struct, trig, budget = pending
                price = o[t]
                if price <= trig * 1.05:
                    hard = 0.07 if kind == "promote" else 0.05
                    stop = max(struct, price * (1 - hard))
                    if stop < price:
                        sh = buy(price, budget, 0.60 if kind == "promote" else 1.0, stop)
                        if sh > 0:
                            pos["traded"] += sh * price
                            pos["avg"] = (pos["avg"] * pos["shares"] + price * sh) / (pos["shares"] + sh)
                            pos["shares"] += sh
                            pos["stop"] = max(pos["stop"], stop)
                        if kind == "promote":
                            pos["pstate"], pos["promoted"] = "CORE", True
                        else:
                            pos["adds"] += 1
            elif kind == "exit" and pos is not None:
                close_episode(t, o[t], pending[1])
            elif kind == "target" and pos is not None:
                target = pending[1] * pos["peak"]
                diff = target - pos["shares"]
                pos["traded"] += abs(diff) * o[t]
                if diff < 0:
                    pos["pnl"] += -diff * (o[t] - pos["avg"])
                    pos["shares"] = target
                elif diff > 0:
                    room = max(1.0 - pos["shares"] * o[t], 0.0) / o[t]
                    add = min(diff, room)
                    pos["avg"] = (pos["avg"] * pos["shares"] + o[t] * add) / (pos["shares"] + add)
                    pos["shares"] += add
            pending = None

        # 2) 장중 손절 (갭 하락이면 시가 체결)
        if pos is not None:
            if o[t] <= pos["stop"]:
                close_episode(t, o[t], "stop"); continue
            if lo[t] <= pos["stop"]:
                close_episode(t, pos["stop"], "stop"); continue

        # 3) t 종가 판정 → t+1 집행 예약
        if t == n - 1:
            break
        if pos is None:
            if f["hb"][t]:
                continue
            if f["trend"][t] and confirm_any(t) and not f["overext"][t]:
                pending = ("entry", "DIRECT", 1.0, 0.60, 0.07, confirm_stop(f, t), c[t])
            elif f["transition"][t] and (f["fresh20"][t] or f["reclaim50"][t]) and not f["overext"][t]:
                pending = ("entry", "PROBE", 0.5, 0.25, 0.05, early_stop(f, t), c[t])
            elif f["deep"][t] and (f["fresh20"][t] or f["reclaim50"][t]):
                pending = ("entry", "RECOVERY", 0.25, 0.15, 0.04, early_stop(f, t), c[t])
            continue

        if f["hb"][t]:
            pending = ("exit", "breakdown"); continue
        pos["maxc"] = max(pos["maxc"], c[t])
        pos_ret = c[t] / pos["avg"] - 1
        if f["fresh20"][t] or f["reclaim50"][t]:
            pos["early_close"], pos["early_t"] = c[t], t

        if pos["mode"] == "NORMAL":
            winner = ((pos_ret >= 0.20 or (pos["maxc"] - pos["avg"]) / pos["rps0"] >= 2.0)
                      and f["trend"][t])
            if winner:
                pos["mode"], pos["winner_seen"], pos["peak"], pos["level"] = "WINNER", True, pos["shares"], 0
            elif pos["pstate"] == "PROBE":
                pos["age"] += 1
                follow = (t - pos["early_t"] <= 10 and c[t] > pos["early_close"] and f["cl"][t] >= 0.6
                          and c[t] > c[t - 1])
                if f["trend"][t] and (confirm_any(t) or follow) and not f["overext"][t]:
                    struct = confirm_stop(f, t) if confirm_any(t) else lo[t] - 0.5 * f["atr"][t]
                    pending = ("promote", struct, c[t], 1.0)
                elif pos["age"] >= 10:
                    pending = ("exit", "probe_expired")
            else:
                add_trig = f["fresh20"][t] or f["tight_pb"][t] or (f["cross20"][t] and f["cl"][t] >= 0.7)
                if (f["trend"][t] and pos_ret > 0 and add_trig and not f["overext"][t]
                        and pos["adds"] < 2 and pos["shares"] * c[t] < 1.0):
                    pending = ("add", confirm_stop(f, t), c[t], 0.5)

        if pos["mode"] == "WINNER" and pending is None:
            active = 3 if f["lv3"][t] else 2 if f["lv2"][t] else 1 if f["lv1"][t] else 0
            if active > pos["level"]:
                pos["level"], pos["rec"] = active, 0
                pos["max_level"] = max(pos["max_level"], active)
                pending = ("target", LEVEL_EXPOSURE[active])
            elif active < pos["level"]:
                pos["rec"] += 1
                if pos["rec"] >= 3:
                    new = pos["level"] - 1
                    if new >= 2 or confirm_any(t) or f["reclaim50"][t]:
                        pos["level"], pos["rec"] = new, 0
                        pending = ("target", LEVEL_EXPOSURE[new])
            else:
                pos["rec"] = 0

    if pos is not None:
        close_episode(n - 1, c[-1], "end")
    return episodes


def summarize(name: str, eps: list[dict]) -> None:
    if not eps:
        print(f"  {name:28} 없음"); return
    R = np.array([e["R"] for e in eps])
    net = R - np.array([COST_PER_SIDE * e["traded"] / UNIT for e in eps])
    is_r = [e["R"] for e in eps if e["entry_date"] < CUTOFF]
    oos_r = [e["R"] for e in eps if e["entry_date"] >= CUTOFF]
    print(f"  {name:28}{len(R):>6}{100*(R>0).mean():>6.0f}%{R.mean():>8.2f}{R.sum():>9.1f}"
          f"{int(np.median([e['days'] for e in eps])):>7}{np.mean(is_r) if is_r else 0:>8.2f}"
          f"{np.mean(oos_r) if oos_r else 0:>8.2f}{R.min():>8.2f}{net.mean():>9.2f}")


def main() -> None:
    data = load_universe(list(UNIVERSE) + list(EXTRA) + ["SPY"])
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]
    betas = {s: beta_vs_spy(data[s], spy) for s in loaded}

    v04, swing = {}, {}
    for s in loaded:
        d = add_indicators(data[s], spy["Close"])
        v04[s] = simulate_v04(d)
        swing[s] = [dict(entry_date=t["entry_date"], R=t["R"], days=t["days"],
                         traded=2 * UNIT / t["risk_pct"])
                    for t in simulate_widetrail(d, entry_plain)]

    groups = {
        "전체 73종목": loaded,
        "SWING 필터 대상(β≥1.3, 손실섹터 제외)": [s for s in loaded if betas[s] >= 1.3 and tickers[s] not in AVOID],
        "필터 밖 종목": [s for s in loaded if not (betas[s] >= 1.3 and tickers[s] not in AVOID)],
    }
    print("STAGED_V04 vs SWING_W150  (단위: 계좌 R, 1R=계좌 0.5% 손실)  거래비용 미반영")
    for g, keys in groups.items():
        print("\n" + "=" * 100)
        print(f"[{g}] {len(keys)}종목")
        print(f"  {'레시피':28}{'횟수':>6}{'승률':>7}{'평균R':>8}{'합계R':>9}{'보유일':>7}{'IS R':>8}{'OOS R':>8}{'최악R':>8}{'비용후R':>9}")
        summarize("SWING_W150", [e for s in keys for e in swing[s]])
        summarize("STAGED_V04", [e for s in keys for e in v04[s]])

    eps = [e for s in loaded for e in v04[s]]
    print("\n" + "=" * 100)
    print("[STAGED_V04 진입 경로별]  전체 73종목")
    print(f"  {'경로':28}{'횟수':>6}{'승률':>7}{'평균R':>8}{'합계R':>9}{'보유일':>7}{'IS R':>8}{'OOS R':>8}{'최악R':>8}{'비용후R':>9}")
    for p in ("PROBE", "RECOVERY", "DIRECT"):
        summarize(p, [e for e in eps if e["path"] == p])
    probes = [e for e in eps if e["path"] in ("PROBE", "RECOVERY")]
    if probes:
        promoted = [e for e in probes if e["promoted"]]
        print(f"\n  탐색 매수 {len(probes)}회 중 본 매수 승격 {len(promoted)}회 ({100*len(promoted)/len(probes):.0f}%)")
        for label, sub in (("승격됨", promoted), ("승격 안 됨", [e for e in probes if not e["promoted"]])):
            if sub:
                r = np.array([e["R"] for e in sub])
                print(f"    {label:8} 평균 {r.mean():.2f}R  합계 {r.sum():.1f}R")
    w = [e for e in eps if e["winner"]]
    print(f"  WINNER 진입 {len(w)}회, 평균 {np.mean([e['R'] for e in w]):.2f}R, "
          f"최대 Level 분포 " + str({k: sum(1 for e in w if e['max_level'] == k) for k in range(4)}))
    reasons = pd.Series([e["reason"] for e in eps]).value_counts().to_dict()
    print(f"  종료 사유: {reasons}")


if __name__ == "__main__":
    main()

"""확정 시스템 v2와 과열 규칙의 신뢰도 검증.

1) 이익 쏠림: 상위 N건 제외 평균, 종목 쏠림, 종목 단위 부트스트랩 신뢰구간
2) 새 기간: 규칙을 고른 2021-09~2026-09가 아닌 2016-09~2021-09에 그대로 적용
3) 연도별 평균
4) 과열 규칙: 같은 진입(종목·진입일)끼리 기준 vs 과열 규칙 짝 비교, 이웃 설정 민감도
현재 상장 종목만이라 생존편향은 남는다. 거래비용 미반영.
"""

from __future__ import annotations

import os
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_extra import EXTRA
from universe_matrix import UNIVERSE
from universe_trailing_beta import trailing_beta
from universe_transition import AVOID, prepare, simulate

LONG_CACHE = "tmp/bt_cache_long"
PERIODS = {
    "새 기간 2016-09~2021-09": (pd.Timestamp("2016-09-29").date(), pd.Timestamp("2021-09-29").date()),
    "기존 기간 2021-09~2026-09": (pd.Timestamp("2021-09-29").date(), pd.Timestamp("2026-12-31").date()),
}
BASE = dict(T=False, D=True, X=None, exit150="2d1R")
CLIMAX = dict(trim="x", arm_ext=0.40, trim_st=False, trim_frac=1.0, trim_ma="sma20")
rng = np.random.default_rng(0)


def load_long(symbols):
    os.makedirs(LONG_CACHE, exist_ok=True)
    missing = [s for s in symbols if not os.path.exists(f"{LONG_CACHE}/{s}.csv")]
    if missing:
        raw = yf.download(missing, start="2014-01-01", auto_adjust=True, group_by="ticker",
                          threads=True, progress=False)
        for s in missing:
            try:
                d = raw[s][["Open", "High", "Low", "Close", "Volume"]].dropna(how="all")
                d.index = d.index.tz_localize(None)
                d.index.name = "Date"
                if len(d) > 300:
                    d.to_csv(f"{LONG_CACHE}/{s}.csv")
            except Exception:
                pass
    return {s: pd.read_csv(f"{LONG_CACHE}/{s}.csv", parse_dates=["Date"]).set_index("Date")
            for s in symbols if os.path.exists(f"{LONG_CACHE}/{s}.csv")}


def cluster_ci(trades, n_boot=2000):
    """종목 단위로 다시 뽑는 부트스트랩: 같은 종목 매매끼리의 연관을 반영한다."""
    by = {}
    for x in trades:
        by.setdefault(x["tk"], []).append(x["R"])
    keys = list(by)
    means = []
    for _ in range(n_boot):
        pick = rng.choice(len(keys), len(keys), replace=True)
        rs = [r for i in pick for r in by[keys[i]]]
        means.append(np.mean(rs))
    return np.percentile(means, [2.5, 97.5])


def describe(name, tr):
    R = np.array([x["R"] for x in tr])
    if len(R) == 0:
        print(f"  {name}: 매매 없음"); return
    srt = np.sort(R)[::-1]
    by_tk = pd.Series({x["tk"]: 0.0 for x in tr})
    for x in tr:
        by_tk[x["tk"]] += x["R"]
    top_tk = by_tk.sort_values(ascending=False)
    lo, hi = cluster_ci(tr)
    print(f"  {name:22}{len(R):>5}{100*(R>0).mean():>6.0f}%{R.mean():>7.2f}{np.median(R):>7.2f}"
          f"  [{lo:>5.2f},{hi:>5.2f}]{srt[5:].mean():>8.2f}{srt[10:].mean():>8.2f}"
          f"{100*srt[:5].sum()/R.sum():>7.0f}%  {top_tk.index[0]}({100*top_tk.iloc[0]/R.sum():.0f}%)")


def main():
    tickers = {**UNIVERSE, **EXTRA}
    data = load_long(list(tickers) + ["SPY"])
    spy = data["SPY"]
    loaded = [s for s in tickers if s in data]
    print(f"장기 데이터 로드 {len(loaded)}/{len(tickers)}종목, SPY {spy.index[0].date()}~{spy.index[-1].date()}")
    first = {s: data[s].index[0].date() for s in loaded}
    late = [s for s in loaded if first[s] > pd.Timestamp("2016-06-01").date()]
    print(f"2016-06 이후 상장(새 기간 일부만 참여): {', '.join(late)}")

    prep, elig = {}, {}
    for s in loaded:
        prep[s] = prepare(add_indicators(data[s], spy["Close"]))
        elig[s] = np.nan_to_num(trailing_beta(data[s]["Close"], spy["Close"]), nan=0) >= 1.3

    def run(keys, gate, **extra):
        out = []
        for s in keys:
            for x in simulate(prep[s], eligible=elig[s] if gate else None, **BASE, **extra):
                x["tk"] = s
                out.append(x)
        return out

    universes = {
        "고베타 관문": ([s for s in loaded if tickers[s] not in AVOID], True),
        "73종목 필터 없음": (loaded, False),
    }
    all_runs = {}
    for u, (keys, gate) in universes.items():
        all_runs[(u, "기준")] = run(keys, gate)
        all_runs[(u, "과열 규칙")] = run(keys, gate, **CLIMAX)

    head = (f"  {'':22}{'횟수':>5}{'승률':>7}{'평균R':>7}{'중앙R':>7}  {'95% 구간':>13}"
            f"{'상위5제외':>8}{'상위10제외':>8}{'상위5비중':>7}  최대 종목(비중)")
    for pname, (a, b) in PERIODS.items():
        print("\n" + "=" * 110)
        print(f"[{pname}]")
        for u in universes:
            print(f" ◆ {u}")
            print(head)
            for v in ("기준", "과열 규칙"):
                tr = [x for x in all_runs[(u, v)] if a <= x["entry_date"] < b]
                describe(v, tr)

    print("\n" + "=" * 110)
    print("[연도별 평균 R — 고베타 관문, 진입 연도 기준]")
    yrs = sorted({x["entry_date"].year for x in all_runs[("고베타 관문", "기준")]})
    print("  연도   " + "".join(f"{y:>8}" for y in yrs))
    for v in ("기준", "과열 규칙"):
        tr = all_runs[("고베타 관문", v)]
        cells = []
        for y in yrs:
            r = [x["R"] for x in tr if x["entry_date"].year == y]
            cells.append(f"{np.mean(r):>6.2f}({len(r):>2})" if r else f"{'-':>8}")
        print(f"  {v:6} " + "".join(f"{c:>8}" for c in cells))

    print("\n" + "=" * 110)
    print("[과열 규칙 짝 비교 — 같은 종목·같은 진입일 매매]")
    for u in universes:
        base = {(x["tk"], x["entry_date"]): x for x in all_runs[(u, "기준")]}
        for pname, (a, b) in PERIODS.items():
            pairs = [(base[(x["tk"], x["entry_date"])], x) for x in all_runs[(u, "과열 규칙")]
                     if (x["tk"], x["entry_date"]) in base and x["n_partial"] > 0 and a <= x["entry_date"] < b]
            if not pairs:
                print(f"  {u} / {pname}: 작동 없음"); continue
            d = np.array([c["R"] - bse["R"] for bse, c in pairs])
            print(f"  {u} / {pname}: 작동 {len(d)}회, 과열 규칙이 나은 비율 {100*(d>0).mean():.0f}%, "
                  f"평균 차이 {d.mean():+.2f}R, 합계 차이 {d.sum():+.1f}R, 최대 이득 {d.max():+.1f}R, 최대 손해 {d.min():+.1f}R")

    print("\n" + "=" * 110)
    print("[과열 규칙 설정 민감도 — 고베타 관문, 평균 R (새 기간 / 기존 기간)]")
    keys, gate = universes["고베타 관문"]
    base_tr = all_runs[("고베타 관문", "기준")]
    def pm(tr, p):
        a, b = PERIODS[p]
        return np.mean([x["R"] for x in tr if a <= x["entry_date"] < b])
    pn = list(PERIODS)
    print(f"  {'기준':20}{pm(base_tr, pn[0]):>8.2f}{pm(base_tr, pn[1]):>8.2f}")
    for ext in (0.30, 0.35, 0.40, 0.45, 0.50):
        for ma in ("sma20", "sma50"):
            tr = run(keys, gate, **{**CLIMAX, "arm_ext": ext, "trim_ma": ma})
            print(f"  {f'이격 {int(ext*100)}% / {ma[3:]}일선':20}{pm(tr, pn[0]):>8.2f}{pm(tr, pn[1]):>8.2f}")


if __name__ == "__main__":
    main()

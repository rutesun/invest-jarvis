"""홀드아웃 검증: 지도가 '숨긴 기간(OOS)'에도 살아남나.

데이터를 학습(IS)/홀드아웃(OOS) 두 기간으로 나눠 진입 시점 기준으로 매매를 분리,
preset 순위·베타·섹터 패턴이 OOS에서도 재현되는지 비교한다. (거래비용은 미반영)
"""

from __future__ import annotations

import warnings

import pandas as pd

warnings.filterwarnings("ignore")

from preset_v0 import add_indicators, simulate
from universe_extra import EXTRA
from universe_matrix import PRESETS, UNIVERSE, agg, beta_bucket, beta_vs_spy, load_universe

CUTOFF = pd.Timestamp("2024-09-29")  # 이전 = IS(학습), 이후 = OOS(숨김)


def pooled(trades_by: dict, keys: list[str], preset: str) -> list[dict]:
    return [t for s in keys for t in trades_by[s][preset]]


def main() -> None:
    syms = list(UNIVERSE) + list(EXTRA) + ["SPY"]
    data = load_universe(syms)
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]

    is_tb: dict = {}
    oos_tb: dict = {}
    betas: dict = {}
    for s in loaded:
        d = add_indicators(data[s], spy["Close"])
        betas[s] = beta_vs_spy(data[s], spy)
        is_tb[s] = {p: simulate(d, p, entry_to=CUTOFF) for p in PRESETS}
        oos_tb[s] = {p: simulate(d, p, entry_from=CUTOFF) for p in PRESETS}

    print(f"홀드아웃 분할: IS = ~{CUTOFF.date()} 이전(학습),  OOS = 이후(숨김)   종목 {len(loaded)}")

    # ① 전체 preset: IS vs OOS
    print("\n" + "=" * 84)
    print("① 전체 preset 기댓값R  (IS = 학습 / OOS = 숨김)")
    print(f"  {'preset':10}{'IS expR':>10}{'IS win%':>9}{'IS n':>6}   {'OOS expR':>10}{'OOS win%':>10}{'OOS n':>7}")
    for p in PRESETS:
        a = agg(pooled(is_tb, loaded, p))
        b = agg(pooled(oos_tb, loaded, p))
        print(
            f"  {p:10}{a['expR']:>10}{int(a['win']):>8}%{a['n']:>6}   "
            f"{b['expR']:>10}{int(b['win']):>9}%{b['n']:>7}"
        )

    # ② 베타 버킷: IS vs OOS
    print("\n" + "=" * 84)
    print("② 베타 버킷 기댓값R  (IS → OOS)")
    print(f"  {'버킷':16}" + "".join(f"{p:>20}" for p in PRESETS))
    order = ["고베타(≥1.3)", "중베타(0.8~1.3)", "저베타(<0.8)"]
    for bk in order:
        keys = [s for s in loaded if beta_bucket(betas[s]) == bk]
        cells = []
        for p in PRESETS:
            a = agg(pooled(is_tb, keys, p))
            b = agg(pooled(oos_tb, keys, p))
            cells.append(f"{a['expR']:>6} → {b['expR']:>6}")
        print(f"  {bk:16}" + "".join(f"{c:>20}" for c in cells))

    # ③ 섹터: IS vs OOS (재현 여부)
    print("\n" + "=" * 84)
    print("③ 섹터 기댓값R  (IS → OOS, OOS 매매수)   ✅=부호 유지 & OOS n≥5")
    sectors = sorted(set(tickers.values()))
    print(f"  {'섹터':14}" + "".join(f"{p:>22}" for p in PRESETS))
    for sec in sectors:
        keys = [s for s in loaded if tickers[s] == sec]
        cells = []
        for p in PRESETS:
            a = agg(pooled(is_tb, keys, p))
            b = agg(pooled(oos_tb, keys, p))
            hold = "✅" if (a["expR"] > 0) == (b["expR"] > 0) and b["n"] >= 5 else "·"
            cells.append(f"{a['expR']:>5}→{b['expR']:>5}({b['n']:>2}){hold}")
        print(f"  {sec:14}" + "".join(f"{c:>22}" for c in cells))

    print("\n  주: OOS 매매수가 적은 셀은 노이즈. ✅는 IS 방향이 OOS에서도 부호 유지된 셀.")


if __name__ == "__main__":
    main()

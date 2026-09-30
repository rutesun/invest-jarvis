"""추격 × 시장 국면: 강세/횡보/하락장에서 추격 페널티가 달라지나.

돌파 시점의 SPY 국면으로 신호를 분류하고, 국면별로 추격 거리별 per-signal 성과를 본다.
per-signal = 전체 돌파 대비(놓친 것=0, 정직). 거래비용 미반영.
국면: 강세 SPY>SMA50>SMA200 / 하락 SPY<SMA50<SMA200 / 횡보 그 외.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


warnings.filterwarnings("ignore")

from preset_v0 import add_indicators
from universe_chase import AVOID, CHASE, breakout_signals, chase_outcome
from universe_extra import EXTRA
from universe_matrix import UNIVERSE, load_universe


REGIMES = ["강세", "횡보", "하락"]


def spy_regime(spy_ind: pd.DataFrame) -> pd.Series:
    c, s50, s200 = spy_ind["Close"], spy_ind["SMA50"], spy_ind["SMA200"]
    reg = pd.Series("횡보", index=c.index, dtype=object)
    reg[(c > s50) & (s50 > s200)] = "강세"
    reg[(c < s50) & (s50 < s200)] = "하락"
    reg[s200.isna()] = "?"
    return reg


def main() -> None:
    syms = list(UNIVERSE) + list(EXTRA) + ["SPY"]
    data = load_universe(syms)
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    keys = [s for s in tickers if s in data and tickers[s] not in AVOID]

    reg_series = spy_regime(add_indicators(spy))
    prepared = {s: add_indicators(data[s], spy["Close"]) for s in keys}
    signals = {s: breakout_signals(prepared[s]) for s in keys}

    # 국면별 × 추격별 결과 수집
    res: dict = {r: {x: [] for x in CHASE} for r in REGIMES}
    sig_count = dict.fromkeys(REGIMES, 0)
    for s in keys:
        d = prepared[s]
        rt = reg_series.reindex(d.index, method="ffill")
        for i in signals[s]:
            reg = rt.iloc[i]
            if reg not in REGIMES:
                continue
            sig_count[reg] += 1
            for x in CHASE:
                o = chase_outcome(d, i, x)
                if o:
                    res[reg][x].append(o)

    tot = sum(sig_count.values())
    print(
        f"추격 × 시장 국면   유니버스=손실섹터제외 {len(keys)}종목   전체 돌파 {tot}개   거래비용 미반영"
    )
    print(
        "국면별 돌파 신호 수: "
        + "  ".join(f"{r} {sig_count[r]}({100 * sig_count[r] / tot:.0f}%)" for r in REGIMES)
    )

    for reg in REGIMES:
        print("\n" + "=" * 88)
        print(f"[{reg}장]  돌파 신호 {sig_count[reg]}개")
        print(
            f"  {'추격':>6}{'체결%':>7}{'체결분평균%':>12}{'체결분승률':>10}{'신호당평균%':>13}{'신호당expR':>11}"
        )
        for x in CHASE:
            outs = res[reg][x]
            if not outs:
                continue
            filled = [o for o in outs if o["filled"]]
            fill = 100 * len(filled) / len(outs)
            fret = np.mean([o["ret"] for o in filled]) if filled else 0
            fwin = 100 * np.mean([o["R"] > 0 for o in filled]) if filled else 0
            ps_ret = sum(o["ret"] for o in filled) / len(outs)
            ps_R = sum(o["R"] for o in filled) / len(outs)
            print(
                f"  {int(x * 100):>5}%{fill:>6.0f}%{fret:>12.1f}{fwin:>9.0f}%{ps_ret:>13.1f}{ps_R:>11.2f}"
            )

    print("\n  비교 포인트: 강세장은 체결%·신호당이 높고 추격 페널티가 완만할 것,")
    print(
        "  하락/횡보는 돌파 실패↑로 신호당이 낮고 추격이 더 크게 손해일 것. (하락장 표본 적으면 노이즈)"
    )


if __name__ == "__main__":
    main()

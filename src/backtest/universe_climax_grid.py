"""과열(50일선 이격) 이후 20/50일선 이탈 시 일부·전량 매도 → 회복 시 재매수, 격자 탐색.

기준: 진입 S+D, 청산 150일선 2일 연속 또는 150일선-1R 아래.
이격 20~60%(10%p 단위) × 기준선 20/50일선 × 매도 비중 25/50/100% = 30조합.
조합이 많아 우연히 좋은 칸이 나올 수 있으므로 숨긴 기간(OOS)과 이웃 칸의 일관성도 함께 본다.
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


EXTS = [0.20, 0.30, 0.40, 0.50, 0.60]
MAS = ["sma20", "sma50"]
FRACS = [0.25, 0.5, 1.0]


def stats(tr):
    R = np.array([x["R"] for x in tr])
    oos = [x["R"] for x in tr if x["entry_date"] >= CUTOFF]
    return R.mean(), np.mean(oos), R.min()


def main():
    data = load_universe(list(UNIVERSE) + list(EXTRA) + ["SPY"])
    spy = data["SPY"]
    tickers = {**UNIVERSE, **EXTRA}
    loaded = [s for s in tickers if s in data]
    prep = {s: prepare(add_indicators(data[s], spy["Close"])) for s in loaded}
    elig = {
        s: np.nan_to_num(trailing_beta(data[s]["Close"], spy["Close"]), nan=0) >= 1.3
        for s in loaded
    }
    groups = {
        "73종목 전체": (list(loaded), False),
        "고베타 관문(과거1년 β≥1.3, 손실섹터 제외)": (
            [s for s in loaded if tickers[s] not in AVOID],
            True,
        ),
    }

    def run(keys, gate, **cfg):
        tr = []
        for s in keys:
            tr += simulate(
                prep[s],
                T=False,
                D=True,
                X=None,
                exit150="2d1R",
                eligible=elig[s] if gate else None,
                **cfg,
            )
        return tr

    for g, (keys, gate) in groups.items():
        base = stats(run(keys, gate))
        res = {}
        for e in EXTS:
            for ma in MAS:
                for fr in FRACS:
                    res[(e, ma, fr)] = stats(
                        run(
                            keys, gate, trim="x", arm_ext=e, trim_st=False, trim_frac=fr, trim_ma=ma
                        )
                    )
        print("\n" + "=" * 100)
        print(
            f"[{g}]  기준(과열 규칙 없음): 평균 {base[0]:.2f}R / 숨긴기간 {base[1]:.2f}R / 최악 {base[2]:.2f}R"
        )
        for label, idx in (("평균 R", 0), ("숨긴 기간(OOS) R", 1), ("최악 R", 2)):
            print(f"\n  {label}  (기준 대비 나으면 *)")
            print(
                "  이격   "
                + "".join(
                    f"{ma[3:]}일선 {int(fr * 100):>3}%".rjust(13) for ma in MAS for fr in FRACS
                )
            )
            for e in EXTS:
                cells = []
                for ma in MAS:
                    for fr in FRACS:
                        v = res[(e, ma, fr)][idx]
                        better = v > base[idx] + 1e-9
                        cells.append(f"{v:>7.2f}{'*' if better else ' '}".rjust(13))
                print(f"  {int(e * 100):>3}%  " + "".join(cells))


if __name__ == "__main__":
    main()
